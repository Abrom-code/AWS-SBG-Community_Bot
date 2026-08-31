import html
import logging
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.challenge.service import (
    get_active_challenge,
    get_challenge,
    register_or_get_participant,
    start_participant_quiz,
    get_next_question_for_participant,
    record_answer_and_advance,
    get_weekly_leaderboard,
    get_monthly_leaderboard,
    get_challenge_questions,
)
from app.challenge.keyboards import (
    get_challenge_start_keyboard,
    get_question_options_keyboard,
    get_leaderboard_keyboard,
    get_scoring_rules_keyboard,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper Formatters
# ---------------------------------------------------------------------------
def _format_question_card(q_data: dict) -> str:
    """Renders a formatted question card with randomized options."""
    q_num = q_data["question_number"]
    total = q_data["total_questions"]
    q_text = html.escape(q_data["question_text"])
    cat = html.escape(q_data["category"])
    diff = html.escape(q_data["difficulty"])
    opts = q_data["options"]

    opt_a = html.escape(opts["A"])
    opt_b = html.escape(opts["B"])
    opt_c = html.escape(opts["C"])
    opt_d = html.escape(opts["D"])

    return (
        f"🧩 <b>Question {q_num} of {total}</b> <i>[{cat} • {diff}]</i>\n\n"
        f"<b>{q_text}</b>\n\n"
        f"<b>A.</b> {opt_a}\n"
        f"<b>B.</b> {opt_b}\n"
        f"<b>C.</b> {opt_c}\n"
        f"<b>D.</b> {opt_d}\n\n"
        f"⏱️ <i>Select your answer below as quickly as possible:</i>"
    )


# ---------------------------------------------------------------------------
# Student Challenge Commands & Callbacks
# ---------------------------------------------------------------------------
async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates or displays active community challenges."""
    user = update.effective_user
    user_id = user.id
    user_name = f"{user.first_name} {user.last_name or ''}".strip()

    challenge = await get_active_challenge()
    if not challenge:
        await update.message.reply_text(
            "⚡ <b>AWS Builder Challenges</b>\n\n"
            "There is no live challenge at the moment.\n"
            "Weekly challenges are scheduled by the core team. Check back soon or stay tuned to @AWSAASTU!",
            parse_mode=ParseMode.HTML,
        )
        return

    ch_id = challenge["id"]
    title = html.escape(challenge["title"])
    desc = html.escape(challenge["description"] or "Test your AWS cloud skills!")
    category = html.escape(challenge["category"])
    time_limit = challenge["question_time_limit_seconds"]
    status = challenge["status"]

    questions = await get_challenge_questions(ch_id)
    total_q = len(questions)

    # Check participant state
    part = await register_or_get_participant(ch_id, user_id, user_name)

    if part["status"] == "COMPLETED":
        score = part["score"]
        correct = part["correct_count"]
        answered = part["answered_count"]
        await update.message.reply_text(
            f"🏁 <b>You already completed this challenge!</b>\n\n"
            f"⚡ <b>{title}</b>\n"
            f"🏆 <b>Your Score:</b> <code>{score} pts</code>\n"
            f"✅ <b>Accuracy:</b> {correct} / {answered} correct\n\n"
            f"Check the leaderboard to see where you rank!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_leaderboard_keyboard(ch_id),
        )
        return

    if status == "SCHEDULED":
        starts_at = challenge.get("starts_at", "Soon")
        await update.message.reply_text(
            f"📅 <b>Upcoming AWS Builder Challenge</b>\n\n"
            f"⚡ <b>{title}</b>\n"
            f"🏗️ <b>Category:</b> {category}\n"
            f"🕒 <b>Scheduled for:</b> {starts_at}\n\n"
            f"<i>Registration is open! The challenge will go live at the scheduled time.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Challenge is LIVE and participant can take it
    await update.message.reply_text(
        f"⚡ <b>{title}</b>\n\n"
        f"<blockquote>{desc}</blockquote>\n\n"
        f"📊 <b>Questions:</b> {total_q} questions\n"
        f"⏱️ <b>Time Limit:</b> {time_limit} seconds per question\n"
        f"🎯 <b>Rules:</b> 1 attempt only • Instant scoring based on accuracy & speed\n\n"
        f"Ready to prove your cloud architecture knowledge?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_challenge_start_keyboard(ch_id),
    )


async def handle_challenge_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the timed quiz session and delivers Question 1."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(":")
    ch_id = int(data[1])
    user = query.from_user
    user_id = user.id
    user_name = f"{user.first_name} {user.last_name or ''}".strip()

    part = await register_or_get_participant(ch_id, user_id, user_name)
    if part["status"] == "COMPLETED":
        await query.edit_message_text(
            f"🏁 You have already completed this challenge! Check the leaderboard for standings.",
            reply_markup=get_leaderboard_keyboard(ch_id),
        )
        return

    await start_participant_quiz(ch_id, user_id)
    q_data = await get_next_question_for_participant(ch_id, user_id)

    if not q_data:
        await query.edit_message_text("⚠️ No questions configured for this challenge yet.")
        return

    text = _format_question_card(q_data)
    kb = get_question_options_keyboard(ch_id, q_data["question_number"] - 1, q_data["display_keys"])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def handle_challenge_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validates and scores an answer, advancing to the next question or finishing."""
    query = update.callback_query

    parts = query.data.split(":")
    if len(parts) < 4:
        await query.answer()
        return

    ch_id = int(parts[1])
    q_index = int(parts[2])
    selected_key = parts[3]
    user_id = query.from_user.id

    result = await record_answer_and_advance(ch_id, user_id, selected_key, q_index)

    if "error" in result:
        await query.answer(result["error"], show_alert=False)
        return

    await query.answer(f"Answer {selected_key} recorded!", show_alert=False)

    if result.get("is_completed"):
        # Challenge completed!
        score = result["current_score"]
        correct = result["correct_count"]
        total = result["total_questions"]

        completion_text = (
            f"🏁 <b>CHALLENGE COMPLETE!</b>\n\n"
            f"🎉 <b>Outstanding effort, Builder!</b>\n\n"
            f"📊 <b>Total Questions:</b> {total}\n"
            f"✅ <b>Correct Answers:</b> {correct} / {total}\n"
            f"🏆 <b>Final Score:</b> <code>{score} pts</code>\n\n"
            f"<i>Your score has been submitted to the leaderboard.</i>"
        )
        await query.edit_message_text(
            completion_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_leaderboard_keyboard(ch_id),
        )
        return

    # Fetch and render next question
    next_q = await get_next_question_for_participant(ch_id, user_id)
    if not next_q:
        await query.edit_message_text(
            "🏁 You have completed all questions!",
            reply_markup=get_leaderboard_keyboard(ch_id),
        )
        return

    text = _format_question_card(next_q)
    kb = get_question_options_keyboard(ch_id, next_q["question_number"] - 1, next_q["display_keys"])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the community challenge leaderboard."""
    challenge = await get_active_challenge()
    ch_id = challenge["id"] if challenge else 0
    await send_leaderboard_view(update.message.reply_text, ch_id, mode="weekly", page=1)


async def handle_leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switches leaderboard views and handles next/prev pagination."""
    query = update.callback_query
    await query.answer()

    if query.data == "noop":
        return

    data = query.data.split(":")
    mode_prefix = data[0]

    if mode_prefix == "lb_weekly":
        ch_id = int(data[1]) if len(data) > 1 and data[1].isdigit() else 0
        page = int(data[2]) if len(data) > 2 and data[2].isdigit() else 1
        if ch_id == 0:
            active = await get_active_challenge()
            ch_id = active["id"] if active else 0
        await send_leaderboard_view(query.edit_message_text, ch_id, mode="weekly", page=page)
    elif mode_prefix == "lb_monthly":
        page = int(data[2]) if len(data) > 2 and data[2].isdigit() else (int(data[1]) if len(data) > 1 and data[1].isdigit() else 1)
        await send_leaderboard_view(query.edit_message_text, 0, mode="monthly", page=page)


def _get_rank_badge(rank: int) -> str:
    if rank == 1:
        return "🥇"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    elif rank <= 10:
        return f"<b>{rank}.</b>"
    return f"#{rank}"


async def send_leaderboard_view(sender_func, challenge_id: int, mode: str = "weekly", page: int = 1):
    """Renders formatted leaderboard text with ranks, medals, and clickable Telegram profile links."""
    if mode == "weekly" and challenge_id > 0:
        ch = await get_challenge(challenge_id)
        title = html.escape(ch["title"]) if ch else "Challenge"
        lb_data = await get_weekly_leaderboard(challenge_id, limit=10, page=page)
        entries = lb_data["entries"]
        total_pages = lb_data["total_pages"]
        total_count = lb_data["total_count"]

        if not entries:
            text = (
                f"🏆 <b>Weekly Leaderboard: {title}</b>\n\n"
                f"<i>No completed submissions yet. Be the first to top the board!</i>"
            )
        else:
            page_info = f" <i>(Page {page} of {total_pages})</i>" if total_pages > 1 else ""
            lines = [f"🏆 <b>Weekly Leaderboard: {title}</b>{page_info}\n"]
            for row in entries:
                rank_icon = _get_rank_badge(row["rank"])
                escaped_name = html.escape(row["user_name"])
                username = row.get("username", "")

                if username:
                    user_link = f'<a href="https://t.me/{html.escape(username)}">{escaped_name}</a>'
                    handle_tag = f" (@{html.escape(username)})"
                else:
                    user_link = f'<a href="tg://user?id={row["telegram_user_id"]}">{escaped_name}</a>'
                    handle_tag = ""

                score = row["score"]
                correct = row["correct_count"]
                total = row["answered_count"]
                lines.append(f"{rank_icon} {user_link}{handle_tag} — <code>{score} pts</code> ({correct}/{total} ✅)")
            text = "\n".join(lines)
    else:
        lb_data = await get_monthly_leaderboard(limit=10, page=page)
        entries = lb_data["entries"]
        total_pages = lb_data["total_pages"]
        total_count = lb_data["total_count"]

        if not entries:
            text = (
                f"📅 <b>Monthly Cumulative Leaderboard</b>\n\n"
                f"<i>No completed challenge data for this season yet.</i>"
            )
        else:
            page_info = f" <i>(Page {page} of {total_pages})</i>" if total_pages > 1 else ""
            lines = [f"📅 <b>Monthly Cumulative Champions</b>{page_info}\n"]
            for row in entries:
                rank_icon = _get_rank_badge(row["rank"])
                escaped_name = html.escape(row["user_name"])
                username = row.get("username", "")

                if username:
                    user_link = f'<a href="https://t.me/{html.escape(username)}">{escaped_name}</a>'
                    handle_tag = f" (@{html.escape(username)})"
                else:
                    user_link = f'<a href="tg://user?id={row["telegram_user_id"]}">{escaped_name}</a>'
                    handle_tag = ""

                total_pts = row["total_score"]
                completed = row["challenges_completed"]
                lines.append(f"{rank_icon} {user_link}{handle_tag} — <code>{total_pts} pts</code> ({completed} challenges)")
            text = "\n".join(lines)

    await sender_func(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_leaderboard_keyboard(challenge_id, mode=mode, page=page, total_pages=total_pages),
    )


# ---------------------------------------------------------------------------
# Scoring & Informative Rules
# ---------------------------------------------------------------------------
def get_scoring_rules_text() -> str:
    """Returns formatted explanation of server-side timing and continuous decay scoring."""
    return (
        "📖 <b>AWS Builder Challenge: Rules & Scoring Guide</b>\n\n"
        "🎯 <b>1. Continuous Decay Scoring Formula</b>\n"
        "Your points on every question combine <b>Accuracy (70%)</b> and <b>Speed (30%)</b>:\n\n"
        "<blockquote><b>Score = Base Points × (0.70 + 0.30 × (1 - t / T))</b></blockquote>\n\n"
        "• <b>Base Points:</b> Usually 10 points per question\n"
        "• <b>t:</b> Your exact server-measured response time (seconds)\n"
        "• <b>T:</b> Question time limit (e.g. 60 seconds)\n\n"
        "📊 <b>Score Breakdown Example (10-Point Question, 60s limit):</b>\n"
        "  ⚡ <b>0s (Instant):</b> <code>10.00 pts</code> (100% max)\n"
        "  ⚡ <b>10s:</b> <code>9.50 pts</code> (95%)\n"
        "  ⚡ <b>20s:</b> <code>9.00 pts</code> (90%)\n"
        "  ⚡ <b>30s:</b> <code>8.50 pts</code> (85%)\n"
        "  ⚡ <b>45s:</b> <code>7.75 pts</code> (77.5%)\n"
        "  ⚡ <b>60s:</b> <code>7.00 pts</code> (70% base accuracy)\n"
        "  ❌ <b>Wrong Answer / >60s (Overtime):</b> <code>0.00 pts</code>\n\n"
        "⏱️ <b>2. Server-Side Timing</b>\n"
        "The clock starts the exact millisecond the question is delivered and stops when your tap reaches the server. Client time cannot be spoofed.\n\n"
        "🔀 <b>3. Anti-Cheat Randomization</b>\n"
        "Every student receives a unique randomized question order and randomized answer option buttons (A, B, C, D).\n\n"
        "🏆 <b>4. Championship Leaderboards</b>\n"
        "• <b>Weekly Leaderboard:</b> Instant rankings for the active quiz.\n"
        "• <b>Monthly Cumulative Championship:</b> Sum of all weekly challenge scores for the month.\n\n"
        "<i>Compete weekly, build your streak, and become an AWS Student Builder Champion!</i>"
    )


async def scoring_rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the scoring rules to the user."""
    challenge = await get_active_challenge()
    ch_id = challenge["id"] if challenge else 0
    await update.message.reply_text(
        get_scoring_rules_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_scoring_rules_keyboard(ch_id),
    )


async def handle_challenge_rules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline callback handler to view scoring rules."""
    query = update.callback_query
    await query.answer()
    challenge = await get_active_challenge()
    ch_id = challenge["id"] if challenge else 0
    await query.edit_message_text(
        get_scoring_rules_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_scoring_rules_keyboard(ch_id),
    )

