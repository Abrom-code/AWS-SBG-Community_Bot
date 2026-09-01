import html
import logging
import math
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
    list_past_challenges,
    calculate_remaining_exam_seconds,
)
from app.challenge.keyboards import (
    get_challenge_start_keyboard,
    get_question_options_keyboard,
    get_leaderboard_keyboard,
    get_scoring_rules_keyboard,
    get_past_challenges_keyboard,
    get_past_challenge_detail_keyboard,
    get_challenge_hub_inline_keyboard,
    get_guidelines_keyboard,
)
from app.db import register_or_update_bot_user

logger = logging.getLogger(__name__)


from datetime import datetime, timezone


def _format_time_until(starts_at_str: Optional[str]) -> str:
    """Returns a concise relative time string (e.g., 'in 2h 15m' or 'in 45m')."""
    if not starts_at_str:
        return "soon"
    try:
        dt = datetime.fromisoformat(str(starts_at_str).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (dt - now).total_seconds()
        if diff <= 0:
            return "momentarily"
        hours = int(diff // 3600)
        minutes = int((diff % 3600) // 60)
        if hours >= 24:
            days = hours // 24
            return f"in {days}d {hours % 24}h"
        elif hours > 0:
            return f"in {hours}h {minutes}m"
        elif minutes > 0:
            return f"in {minutes}m"
        else:
            return "in less than 1m"
    except Exception:
        return f"at {starts_at_str}"


# ---------------------------------------------------------------------------
# Helper Formatters
# ---------------------------------------------------------------------------
def _format_question_card(q_data: dict) -> str:
    """Renders a formatted question card with randomized options and live exam countdown."""
    q_num = q_data["question_number"]
    total = q_data["total_questions"]
    q_text = html.escape(q_data["question_text"])
    cat = html.escape(q_data["category"])
    diff = html.escape(q_data["difficulty"])
    opts = q_data["options"]
    timer_str = q_data.get("time_remaining_str", "")
    is_capped = q_data.get("is_deadline_capped", False)

    opt_a = html.escape(opts["A"])
    opt_b = html.escape(opts["B"])
    opt_c = html.escape(opts["C"])
    opt_d = html.escape(opts["D"])

    if timer_str:
        if is_capped:
            timer_line = f"⏱️ <b>Exam Time Left:</b> <code>{timer_str}</code> ⚠️ <i>(Capped by Challenge Deadline)</i>\n\n"
        else:
            timer_line = f"⏱️ <b>Exam Time Left:</b> <code>{timer_str}</code>\n\n"
    else:
        timer_line = ""

    return (
        f"🧩 <b>Question {q_num} of {total}</b> <i>[{cat} • {diff}]</i>\n"
        f"{timer_line}"
        f"<b>{q_text}</b>\n\n"
        f"<b>A.</b> {opt_a}\n"
        f"<b>B.</b> {opt_b}\n"
        f"<b>C.</b> {opt_c}\n"
        f"<b>D.</b> {opt_d}\n\n"
        f"👉 <i>Select your answer below:</i>"
    )


# ---------------------------------------------------------------------------
# Student Challenge Commands & Callbacks
# ---------------------------------------------------------------------------
async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates or displays active community challenges."""
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    user_name = f"{user.first_name} {user.last_name or ''}".strip()
    username = user.username or ""
    await register_or_update_bot_user(user_id, user_name, username)

    cb_query = getattr(update, "callback_query", None)
    if cb_query:
        await cb_query.answer()
        sender_func = cb_query.edit_message_text
    elif update.message:
        sender_func = lambda text, **kwargs: update.message.reply_text(text, protect_content=True, **kwargs)
    else:
        return

    challenge = await get_active_challenge()
    if not challenge:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        no_ch_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📚 Past Challenges", callback_data="ch_past_list"),
                InlineKeyboardButton("🏆 Monthly Leaderboard", callback_data="lb_monthly:0:1"),
            ],
            [InlineKeyboardButton("📖 Scoring & Rules", callback_data="ch_rules")],
        ])
        await sender_func(
            "⚡ <b>AWS Builder Challenges</b>\n\n"
            "There is no live challenge at the moment.\n"
            "Weekly challenges are scheduled by the core team. Check back soon or stay tuned to @AWSAASTU!\n\n"
            "<i>Browse past challenges or check the leaderboard below:</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=no_ch_kb,
        )
        return

    ch_id = challenge["id"]
    title = html.escape(challenge["title"])
    desc = html.escape(challenge["description"] or "Test your AWS cloud skills!")
    category = html.escape(challenge["category"])
    dur_secs = challenge.get("duration_seconds") or 600
    exam_mins = int(dur_secs // 60) if dur_secs <= 7200 else 10
    duration_str = f"{exam_mins} minutes total"
    status = challenge["status"]

    questions = await get_challenge_questions(ch_id)
    total_q = len(questions)

    # Check participant state
    part = await register_or_get_participant(ch_id, user_id, user_name, username)

    if part["status"] == "COMPLETED":
        score = part["score"]
        correct = part["correct_count"]
        answered = part["answered_count"]
        await sender_func(
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
        time_until = _format_time_until(challenge.get("starts_at"))
        starts_at = challenge.get("starts_at", "Soon")
        await sender_func(
            f"\n"
            f"📅 <b>Upcoming AWS Builder Challenge</b>\n\n"
            f"<blockquote>⚡ <b>{title}</b>\n"
            f"{desc}</blockquote>\n\n"
            f"🏗️ <b>Category:</b>  {category}\n"
            f"⏳ <b>Starts:</b>  {time_until} <i>({starts_at})</i>\n"
            f"📊 <b>Questions:</b>  {total_q} questions\n"
            f"⏱️ <b>Exam Time:</b>  {duration_str}\n"
            f"🎯 <b>Scoring:</b>  70% Accuracy + 30% Speed Bonus\n\n"
            f"<i>The challenge will automatically unlock at the scheduled start time.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_start_keyboard(ch_id),
        )
        return

    # Check if closing deadline is near or passed
    remaining_sec, is_capped, ends_at_str = calculate_remaining_exam_seconds(challenge, None)
    if ends_at_str and remaining_sec <= 0:
        await sender_func(
            f"🏁 <b>This challenge has concluded!</b>\n\n"
            f"⚡ <b>{title}</b>\n"
            f"The challenge closing deadline was reached.\n"
            f"Check the leaderboard or stay tuned for our next weekly competition!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_leaderboard_keyboard(ch_id),
        )
        return

    capped_notice = ""
    if is_capped and remaining_sec > 0:
        capped_mins = max(1, int(math.ceil(remaining_sec / 60)))
        duration_str = f"<b>{capped_mins} minutes</b> ⚠️ <i>(Capped by Deadline)</i>"
        capped_notice = (
            f"\n\n<blockquote>⚠️ <b>Deadline Notice:</b>\n"
            f"Standard exam is {exam_mins} min, but this challenge closes in "
            f"<b>{capped_mins} min</b>. Your timer is capped.</blockquote>"
        )

    # Challenge is LIVE and participant can take it
    await sender_func(
        f"\n"
        f"⚡ <b>{title}</b>\n\n"
        f"<blockquote>{desc}</blockquote>\n\n"
        f"📊 <b>Questions:</b>  {total_q} questions\n"
        f"⏱️ <b>Exam Duration:</b>  {duration_str}\n"
        f"🎯 <b>Scoring:</b>  70% Accuracy + 30% Speed Bonus\n"
        f"🏗️ <b>Category:</b>  {category}"
        f"{capped_notice}\n\n"
        f"<i>Tap</i> <b>Start Challenge</b> <i>when you're ready — the timer begins immediately.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_challenge_start_keyboard(ch_id),
    )


async def handle_challenge_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the timed quiz session and delivers Question 1 with modal popup validation."""
    query = update.callback_query

    data = query.data.split(":")
    ch_id = int(data[1])
    user = query.from_user
    user_id = user.id
    user_name = f"{user.first_name} {user.last_name or ''}".strip()
    username = user.username or ""
    await register_or_update_bot_user(user_id, user_name, username)

    challenge = await get_challenge(ch_id)
    if not challenge or challenge.get("status") == "CANCELLED":
        await query.answer("❌ This challenge has been cancelled.", show_alert=True)
        return

    ch_status = challenge.get("status", "DRAFT")
    if ch_status == "SCHEDULED":
        time_until = _format_time_until(challenge.get("starts_at"))
        await query.answer(f"⏳ Not yet! Challenge starts {time_until}.", show_alert=True)
        return
    elif ch_status == "DRAFT":
        await query.answer("🛠️ This challenge is in draft mode and not yet published.", show_alert=True)
        return

    # Check if challenge deadline has passed
    remaining_sec, is_capped, ends_at_str = calculate_remaining_exam_seconds(challenge, None)
    if ends_at_str and remaining_sec <= 0:
        await query.answer("❌ This challenge window has officially closed. The deadline has passed.", show_alert=True)
        return

    part = await register_or_get_participant(ch_id, user_id, user_name, username)
    if part["status"] == "COMPLETED":
        await query.answer(f"🏁 You already completed this challenge! (Score: {part['score']} pts)", show_alert=True)
        return

    await query.answer()
    await start_participant_quiz(ch_id, user_id)
    q_data = await get_next_question_for_participant(ch_id, user_id)

    if not q_data:
        await query.answer("⚠️ No questions configured for this challenge yet.", show_alert=True)
        return

    text = _format_question_card(q_data)
    kb = get_question_options_keyboard(ch_id, q_data["question_number"] - 1, q_data["display_keys"])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ---------------------------------------------------------------------------
# Past Challenges & Archive
# ---------------------------------------------------------------------------
async def past_challenges_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays previous challenges for leaderboard inspection and question practice."""
    challenges = await list_past_challenges(limit=15)
    if not challenges:
        await update.message.reply_text(
            "📚 <b>Past Challenges Archive</b>\n\n"
            "No archived challenges available yet. Check back once weekly competitions conclude!",
            parse_mode=ParseMode.HTML,
        )
        return

    text = (
        "📚 <b>AWS Builder Challenge Archive</b>\n\n"
        "Browse previous competitions to inspect final leaderboards or practice quiz questions:\n\n"
        "<i>Select a challenge below:</i>"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_past_challenges_keyboard(challenges),
    )


async def handle_past_challenges_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles interaction with past challenges archive."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "ch_past_list":
        challenges = await list_past_challenges(limit=15)
        if not challenges:
            await query.edit_message_text(
                "📚 <b>Past Challenges Archive</b>\n\nNo archived challenges found.",
                parse_mode=ParseMode.HTML,
            )
            return

        text = (
            "📚 <b>AWS Builder Challenge Archive</b>\n\n"
            "Browse previous competitions to inspect final leaderboards or practice quiz questions:\n\n"
            "<i>Select a challenge below:</i>"
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_past_challenges_keyboard(challenges),
        )

    elif data.startswith("ch_past:"):
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        if not ch:
            await query.answer("⚠️ Challenge not found.", show_alert=True)
            return

        title = html.escape(ch["title"])
        category = html.escape(ch["category"])
        status = ch["status"]
        desc = html.escape(ch.get("description") or "Test your AWS cloud skills!")
        questions = await get_challenge_questions(ch_id)
        total_q = len(questions)
        dur_secs = ch.get("duration_seconds") or 600
        exam_mins = int(dur_secs // 60) if dur_secs <= 7200 else 10

        status_icons = {"ENDED": "🏁 Ended", "LIVE": "🟢 Live", "CANCELLED": "❌ Cancelled"}
        status_tag = status_icons.get(status, status)

        card = (
            f"⚡ <b>{title}</b> <i>[{status_tag}]</i>\n\n"
            f"<blockquote>{desc}</blockquote>\n\n"
            f"🏗️ <b>Category:</b> {category}\n"
            f"📊 <b>Total Questions:</b> {total_q} questions\n"
            f"⏱️ <b>Exam Time:</b> {exam_mins} minutes\n\n"
            f"<i>You can inspect the final leaderboard or practice all questions below:</i>"
        )
        await query.edit_message_text(
            card,
            parse_mode=ParseMode.HTML,
            reply_markup=get_past_challenge_detail_keyboard(ch_id),
        )


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
        await query.answer(result["error"], show_alert=True)
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
    user = update.effective_user
    chat = update.effective_chat
    from app.challenge.admin import is_admin_user
    is_admin = await is_admin_user(user.id if user else 0, chat.id if chat else None, context.bot)
    await send_leaderboard_view(update.message.reply_text, ch_id, mode="weekly", page=1, is_admin=is_admin)


async def handle_leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switches leaderboard views and handles next/prev pagination."""
    query = update.callback_query
    await query.answer()

    if query.data == "noop":
        return

    data = query.data.split(":")
    mode_prefix = data[0]
    user = query.from_user
    chat = query.message.chat if query.message else None
    from app.challenge.admin import is_admin_user
    is_admin = await is_admin_user(user.id if user else 0, chat.id if chat else None, context.bot)

    if mode_prefix == "lb_weekly":
        ch_id = int(data[1]) if len(data) > 1 and data[1].isdigit() else 0
        page = int(data[2]) if len(data) > 2 and data[2].isdigit() else 1
        if ch_id == 0:
            active = await get_active_challenge()
            ch_id = active["id"] if active else 0
        await send_leaderboard_view(query.edit_message_text, ch_id, mode="weekly", page=page, is_admin=is_admin)
    elif mode_prefix == "lb_monthly":
        page = int(data[2]) if len(data) > 2 and data[2].isdigit() else (int(data[1]) if len(data) > 1 and data[1].isdigit() else 1)
        await send_leaderboard_view(query.edit_message_text, 0, mode="monthly", page=page, is_admin=is_admin)


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


async def send_leaderboard_view(sender_func, challenge_id: int, mode: str = "weekly", page: int = 1, is_admin: bool = False):
    """Renders formatted leaderboard text. For non-admins shows real names only. For admins shows username."""
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

                if is_admin and username:
                    name_display = f"<b>{escaped_name}</b> (@{html.escape(username)})"
                else:
                    name_display = f"<b>{escaped_name}</b>"

                score = row["score"]
                correct = row["correct_count"]
                total = row["answered_count"]
                lines.append(f"{rank_icon} {name_display} — <code>{score} pts</code> ({correct}/{total} ✅)")
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

                if is_admin and username:
                    name_display = f"<b>{escaped_name}</b> (@{html.escape(username)})"
                else:
                    name_display = f"<b>{escaped_name}</b>"

                total_pts = row["total_score"]
                completed = row["challenges_completed"]
                lines.append(f"{rank_icon} {name_display} — <code>{total_pts} pts</code> ({completed} challenges)")
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
    """Returns formatted explanation of overall exam timing and two-factor scoring."""
    return (
        "📖 <b>How Scoring Works</b>\n\n"
        "<blockquote>⏱️ <b>Overall Exam Timer & Self-Pacing</b>\n\n"
        "Each challenge has a unified <b>Overall Test Time Limit</b> "
        "(e.g. 10 minutes total for all questions).\n"
        "• You control your own pacing across the entire exam\n"
        "• Spend more time on harder questions, answer simpler ones quickly\n"
        "• The countdown clock is displayed live at the top of each question</blockquote>\n\n"
        "<blockquote>🎯 <b>Two-Factor Scoring Formula</b>\n\n"
        "Your final score combines <b>Accuracy (70%)</b> and <b>Speed Bonus (30%)</b>:\n\n"
        "<b>Score = Raw Points × (0.70 + 0.30 × (1 - Time Used / Allotted Time))</b></blockquote>\n\n"
        "📊 <b>Efficiency Multiplier Examples (10-min exam):</b>\n"
        "  ⚡ <b>2 mins →</b> <code>~94%</code> of max points\n"
        "  ⚡ <b>5 mins →</b> <code>85%</code> of max points\n"
        "  ⚡ <b>8 mins →</b> <code>76%</code> of max points\n"
        "  ⚡ <b>10 mins →</b> <code>70%</code> (Full accuracy baseline)\n"
        "  ❌ <b>Overtime →</b> Auto-submits answered questions\n\n"
        "<blockquote>🏆 <b>Leaderboards & Tie-Breakers</b>\n\n"
        "• <b>Weekly Leaderboard:</b> Instant rankings for each quiz\n"
        "• <b>Monthly Championship:</b> Cumulative score across all weeks\n"
        "• <b>Tie-Breaker:</b> Fastest completion time wins</blockquote>\n\n"
        "<i>Compete weekly, master AWS cloud, and climb the leaderboard!</i>"
    )


def get_guidelines_text() -> str:
    """Returns the community guidelines and code of conduct text."""
    return (
        "🛡️ <b>Community Guidelines & Code of Conduct</b>\n\n"
        "These rules apply to <b>all</b> AWS Builder Challenges. "
        "Please read and follow them carefully.\n\n"
        "<blockquote>🚫 <b>Strictly One Account</b>\n\n"
        "Participating using multiple or secondary Telegram accounts is strictly forbidden. "
        "Builders caught using duplicate accounts will have all entries disqualified from "
        "weekly and monthly championship boards.</blockquote>\n\n"
        "<blockquote>🤖 <b>No AI or Automation Assistance</b>\n\n"
        "The goal is to build genuine cloud engineering competence. "
        "Using automated bots, OCR scrapers, or pasting questions into "
        "AI tools during timed quizzes is prohibited.</blockquote>\n\n"
        "<blockquote>⏱️ <b>Single Continuous Attempt</b>\n\n"
        "Once you tap <b>Start Challenge</b>, your exam clock runs continuously. "
        "Leaving Telegram does not pause the timer. "
        "You get only <b>one attempt</b> per challenge.</blockquote>\n\n"
        "<blockquote>🔒 <b>Academic Integrity & No Leaks</b>\n\n"
        "Do not share question screenshots, answer keys, or question dumps "
        "with others before the weekly challenge concludes.</blockquote>\n\n"
        "<blockquote>📸 <b>Screenshots Disabled</b>\n\n"
        "Questions are sent with content protection enabled. "
        "Forwarding and screenshots of quiz questions are restricted.</blockquote>\n\n"
        "<blockquote>📚 <b>Post-Exam Review</b>\n\n"
        "Full explanations and correct answers are revealed right after you submit. "
        "Past challenges remain in /archive for open practice!</blockquote>\n\n"
        "<i>Fair play ensures a level playing field for all builders. Good luck! 🍀</i>"
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


async def guidelines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the community guidelines to the user."""
    challenge = await get_active_challenge()
    ch_id = challenge["id"] if challenge else 0
    await update.message.reply_text(
        get_guidelines_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_guidelines_keyboard(ch_id),
    )


async def handle_guidelines_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline callback handler to view community guidelines."""
    challenge = await get_active_challenge()
    ch_id = challenge["id"] if challenge else 0
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            get_guidelines_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=get_guidelines_keyboard(ch_id),
        )
    elif update.message:
        await update.message.reply_text(
            get_guidelines_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=get_guidelines_keyboard(ch_id),
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

