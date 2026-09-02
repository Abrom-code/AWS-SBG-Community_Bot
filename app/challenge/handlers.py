import html
import logging
import math
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.challenge.service import (
    get_active_challenge,
    get_active_challenges,
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
    get_challenge_review_data,
    to_utc_datetime,
    update_challenge_status,
    LOCAL_TZ,
    BOT_TIMEZONE_NAME,
)
from app.challenge.keyboards import (
    get_challenge_start_keyboard,
    get_active_challenges_keyboard,
    get_active_challenges_nav_keyboard,
    get_question_options_keyboard,
    get_leaderboard_keyboard,
    get_scoring_rules_keyboard,
    get_past_challenges_keyboard,
    get_past_challenge_detail_keyboard,
    get_challenge_hub_inline_keyboard,
    get_guidelines_keyboard,
    get_review_navigation_keyboard,
    get_challenge_completion_keyboard,
)
from app.db import register_or_update_bot_user

logger = logging.getLogger(__name__)


from datetime import datetime, timezone


def _format_scheduled_datetime(starts_at_str: Optional[str]) -> str:
    """Formats an ISO timestamp into a clear human-readable date and time in East Africa Time (EAT)."""
    if not starts_at_str:
        return "To be announced"
    dt = to_utc_datetime(starts_at_str)
    if not dt:
        return str(starts_at_str)
    local_dt = dt.astimezone(LOCAL_TZ)
    day = local_dt.day
    hour_12 = local_dt.strftime("%I").lstrip("0") or "12"
    minute = local_dt.strftime("%M")
    ampm = local_dt.strftime("%p")
    month_name = local_dt.strftime("%b")
    weekday = local_dt.strftime("%A")
    year = local_dt.year
    return f"{weekday}, {month_name} {day}, {year} · {hour_12}:{minute} {ampm} {BOT_TIMEZONE_NAME}"


def _format_time_until(starts_at_str: Optional[str]) -> str:
    """Returns a clear relative countdown string (e.g., 'in 2 days, 4 hrs' or 'in 45 mins')."""
    if not starts_at_str:
        return "soon"
    try:
        dt = to_utc_datetime(starts_at_str)
        if not dt:
            return "soon"
        now = datetime.now(timezone.utc)
        diff = (dt - now).total_seconds()
        if diff <= 0:
            return "opening momentarily"
        hours = int(diff // 3600)
        minutes = int((diff % 3600) // 60)
        days = hours // 24
        rem_hours = hours % 24
        if days >= 1:
            day_str = f"{days} day" if days == 1 else f"{days} days"
            if rem_hours > 0:
                hr_str = f"{rem_hours} hr" if rem_hours == 1 else f"{rem_hours} hrs"
                return f"in {day_str}, {hr_str}"
            return f"in {day_str}"
        elif hours >= 1:
            hr_str = f"{hours} hr" if hours == 1 else f"{hours} hrs"
            if minutes > 0:
                min_str = f"{minutes} min" if minutes == 1 else f"{minutes} mins"
                return f"in {hr_str}, {min_str}"
            return f"in {hr_str}"
        elif minutes >= 1:
            return f"in {minutes} min" if minutes == 1 else f"in {minutes} mins"
        else:
            return "in less than a minute"
    except Exception:
        return "soon"


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

    idx = q_data.get("question_index", q_num - 1)
    is_answered = idx in q_data.get("answered_indices", [])
    status_tag = " • ✓ <i>Answered</i>" if is_answered else ""
    prompt_line = "✓ <i>Answer submitted for this question.</i>" if is_answered else "➤ <i>Select your answer below:</i>"

    if timer_str:
        if is_capped:
            timer_line = f"⏱️ <code>{timer_str}</code> left ⚠️ <i>(Capped by Deadline • 30% Speed Weight)</i>\n\n"
        else:
            timer_line = f"⏱️ <code>{timer_str}</code> left <i>(Speed bonus applies to remaining time)</i>\n\n"
    else:
        timer_line = ""

    return (
        f"✦ <b>Question {q_num} of {total}</b> <i>[{cat} • {diff}]</i>{status_tag}\n"
        f"{timer_line}"
        f"<b>{q_text}</b>\n\n"
        f"<b>A.</b> {opt_a}\n"
        f"<b>B.</b> {opt_b}\n"
        f"<b>C.</b> {opt_c}\n"
        f"<b>D.</b> {opt_d}\n\n"
        f"{prompt_line}"
    )


def _format_review_card(q_data: dict) -> str:
    """Formats a question review card with correct answers, user selection, and explanation."""
    q_num = q_data["question_number"]
    total = q_data["total_questions"]
    q_text = html.escape(q_data.get("question_text", ""))
    cat = html.escape(q_data.get("category", "General"))
    diff = html.escape(q_data.get("difficulty", "MEDIUM"))
    correct_opt = (q_data.get("correct_option") or "A").upper()
    user_opt = (q_data.get("user_selected_option") or "").upper()
    is_correct = q_data.get("is_correct")
    explanation = html.escape(q_data.get("explanation") or "AWS Cloud architecture and service best practice.")

    options = {
        "A": q_data.get("option_a", ""),
        "B": q_data.get("option_b", ""),
        "C": q_data.get("option_c", ""),
        "D": q_data.get("option_d", ""),
    }

    opt_lines = []
    for key in ["A", "B", "C", "D"]:
        opt_text = html.escape(options.get(key, ""))
        if key == correct_opt:
            prefix = "✓ <b>Option " + key + ":</b> "
        elif user_opt and key == user_opt and not is_correct:
            prefix = "▪️ <b>Option " + key + ":</b> "
        else:
            prefix = "▫️ <b>Option " + key + ":</b> "
        opt_lines.append(f"{prefix}{opt_text}")

    if user_opt:
        if is_correct:
            result_badge = f"✓ <b>Your Answer:</b> Option {user_opt} (Correct)"
        else:
            result_badge = f"▪️ <b>Your Answer:</b> Option {user_opt} (Incorrect › Correct: Option {correct_opt})"
    else:
        result_badge = f"✓ <b>Correct Answer:</b> Option {correct_opt}"

    card = (
        f"✦ <b>Question Review ({q_num} of {total})</b> <i>[{cat} • {diff}]</i>\n\n"
        f"<b>{q_text}</b>\n\n"
        + "\n".join(opt_lines) + f"\n\n"
        f"{result_badge}\n\n"
        f"<blockquote><b>Explanation:</b>\n{explanation}</blockquote>"
    )
    return card


async def handle_challenge_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays question explanations and answer reviews for completed or ended challenges."""
    query = update.callback_query
    if not query:
        return

    data = query.data.split(":")
    ch_id = int(data[1])
    q_index = int(data[2]) if len(data) > 2 and data[2].isdigit() else 0
    user_id = query.from_user.id

    review_data = await get_challenge_review_data(ch_id, user_id, question_index=q_index)
    if "error" in review_data:
        if review_data.get("error") == "locked":
            msg = review_data.get("message", "🔒 Complete the challenge first to review questions & answers!")
        else:
            msg = review_data.get("error", "⚠️ Could not load review.")
        try:
            await query.answer(msg, show_alert=True)
        except Exception:
            pass
        return

    try:
        await query.answer()
    except Exception:
        pass

    text = _format_review_card(review_data)
    kb = get_review_navigation_keyboard(
        ch_id,
        review_data["question_index"],
        review_data["total_questions"],
        review_data.get("answered_status"),
    )
    await _safe_edit_or_reply(query, text, reply_markup=kb)


async def _safe_edit_or_reply(query, text: str, reply_markup=None):
    """Safely edits text or caption depending on whether the original message was a photo, with fallback to reply."""
    is_photo = bool(query.message and getattr(query.message, "photo", None))
    if is_photo:
        try:
            await query.edit_message_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            return
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
            logger.debug("edit_message_caption BadRequest: %s", e)
        except Exception as e:
            logger.debug("edit_message_caption failed: %s", e)

    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return
        logger.debug("edit_message_text BadRequest: %s", e)
    except Exception as exc:
        logger.debug("edit_message_text exception: %s", exc)

    # Fallback to sending a new message in chat if in-place edit was rejected
    try:
        if query.message:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except Exception as e:
        logger.error("Fallback reply_text failed: %s", e)


# ---------------------------------------------------------------------------
# Student Challenge Commands & Callbacks
# ---------------------------------------------------------------------------
async def _render_active_challenge_card(
    sender_func,
    active_challenges: list,
    current_index: int,
    user_id: int,
    user_name: str,
    username: str,
):
    """Renders an active challenge in questions format with a smart navigation bar."""
    total = len(active_challenges)
    if current_index < 0 or current_index >= total:
        current_index = 0

    challenge = active_challenges[current_index]
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
    is_completed = (part.get("status") == "COMPLETED")
    is_scheduled = (status == "SCHEDULED")

    # Collect status indicator for each challenge in the navigation bar
    challenge_statuses = []
    for ch in active_challenges:
        p = await register_or_get_participant(ch["id"], user_id, user_name, username)
        if p.get("status") == "COMPLETED":
            challenge_statuses.append("✔️")
        elif ch.get("status") == "SCHEDULED":
            challenge_statuses.append("🕒")
        else:
            challenge_statuses.append("🟢")

    acc_w = float(challenge.get("accuracy_weight") or 0.70)
    spd_w = float(challenge.get("speed_weight") or 0.30)
    acc_pct = int(round(acc_w * 100))
    spd_pct = int(round(spd_w * 100))

    header_prefix = f"✦ <b>Active Challenge ({current_index + 1} of {total})</b>" if total > 1 else f"✦ <b>Active Challenge: {title}</b>"

    if is_completed:
        score = part["score"]
        correct = part["correct_count"]
        answered = part["answered_count"]
        text = (
            f"{header_prefix}\n\n"
            f"✔️ <b>Status: Completed</b>\n\n"
            f"<blockquote><b>{title}</b>\n{desc}</blockquote>\n\n"
            f"▫️ <b>Category:</b> {category}\n"
            f"▫️ <b>Your Score:</b> <code>{score} pts</code>\n"
            f"▫️ <b>Accuracy:</b> {correct} / {answered} correct\n\n"
            f"➤ <i>You have already submitted this challenge. View standings below!</i>"
        )
    elif is_scheduled:
        countdown = _format_time_until(challenge.get("starts_at"))
        opening_time = _format_scheduled_datetime(challenge.get("starts_at"))
        text = (
            f"{header_prefix}\n\n"
            f"🕒 <b>Status: Upcoming Challenge</b>\n\n"
            f"<blockquote><b>{title}</b>\n{desc}</blockquote>\n\n"
            f"▫️ <b>Category:</b> {category}\n"
            f"▫️ <b>Scheduled Opening:</b> {opening_time}\n"
            f"▫️ <b>Countdown:</b> Opens {countdown}\n"
            f"▫️ <b>Questions:</b> {total_q}\n"
            f"▫️ <b>Exam Time Limit:</b> {duration_str}\n"
            f"▫️ <b>Scoring Breakdown:</b> {acc_pct}% Accuracy + {spd_pct}% Speed Bonus\n\n"
            f"➤ <i>This challenge will automatically unlock when the opening time is reached.</i>"
        )
    else:
        # Check deadline
        remaining_sec, is_capped, ends_at_str = calculate_remaining_exam_seconds(challenge, None)
        capped_notice = ""
        if is_capped and remaining_sec > 0:
            capped_mins = max(1, int(math.ceil(remaining_sec / 60)))
            duration_str = f"<b>{capped_mins} minutes</b> ⚠️ <i>(Capped by Deadline)</i>"
            capped_notice = (
                f"\n\n<blockquote>⚠️ <b>Deadline Notice:</b>\n"
                f"Standard exam is {exam_mins} min, but this challenge closes in "
                f"<b>{capped_mins} min</b>. Your timer is capped.</blockquote>"
            )

        text = (
            f"{header_prefix}\n\n"
            f"🟢 <b>Status: Live Now</b>\n\n"
            f"<blockquote><b>{title}</b>\n{desc}</blockquote>\n\n"
            f"▫️ <b>Category:</b> {category}\n"
            f"▫️ <b>Questions:</b> {total_q}\n"
            f"▫️ <b>Exam Time Limit:</b> {duration_str}\n"
            f"▫️ <b>Scoring Breakdown:</b> {acc_pct}% Accuracy + {spd_pct}% Speed Bonus"
            f"{capped_notice}\n\n"
            f"➤ <i>Tap <b>Start Challenge</b> below when ready. The timer begins immediately!</i>"
        )

    sched_countdown = _format_time_until(challenge.get("starts_at")) if is_scheduled else None
    kb = get_active_challenges_nav_keyboard(
        challenge_id=ch_id,
        current_index=current_index,
        total_challenges=total,
        is_completed=is_completed,
        is_scheduled=is_scheduled,
        challenge_statuses=challenge_statuses,
        scheduled_countdown=sched_countdown,
    )
    await sender_func(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates or displays active community challenges in questions format with smart navigation."""
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    user_name = f"{user.first_name} {user.last_name or ''}".strip()
    username = user.username or ""
    await register_or_update_bot_user(user_id, user_name, username)

    cb_query = getattr(update, "callback_query", None)
    if cb_query:
        try:
            await cb_query.answer("⏳ Loading challenges...", show_alert=False)
        except Exception:
            pass
        sender_func = cb_query.edit_message_text
    elif update.message:
        if context.bot and update.effective_chat:
            try:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            except Exception:
                pass
        sender_func = lambda text, **kwargs: update.message.reply_text(text, protect_content=True, **kwargs)
    else:
        return

    active_challenges = await get_active_challenges()
    if not active_challenges:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        no_ch_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Past Challenges", callback_data="ch_past_list")],
            [InlineKeyboardButton("🏆 Monthly Leaderboard", callback_data="lb_monthly:0:1")],
            [InlineKeyboardButton("📖 Scoring & Rules", callback_data="ch_rules")],
        ])
        await sender_func(
            "✦ <b>AWS Builder Challenges</b>\n\n"
            "No live challenge is active at the moment.\n"
            "Weekly challenges are scheduled by the core team. Check back soon or stay tuned to @AWSAASTU!\n\n"
            "➤ <i>Browse past challenges or check the leaderboard below:</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=no_ch_kb,
        )
        return

    await _render_active_challenge_card(
        sender_func,
        active_challenges,
        current_index=0,
        user_id=user_id,
        user_name=user_name,
        username=username,
    )


async def handle_challenge_nav_active_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles navigating between active challenges via the smart navigation bar."""
    query = update.callback_query
    data = query.data
    user = query.from_user
    user_id = user.id
    user_name = f"{user.first_name} {user.last_name or ''}".strip()
    username = user.username or ""

    try:
        target_idx = int(data.split(":")[1])
    except (IndexError, ValueError):
        return

    try:
        await query.answer()
    except Exception:
        pass

    active_challenges = await get_active_challenges()
    if not active_challenges:
        return

    await _render_active_challenge_card(
        query.edit_message_text,
        active_challenges,
        current_index=target_idx,
        user_id=user_id,
        user_name=user_name,
        username=username,
    )


async def handle_challenge_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles jumping directly to an active challenge by challenge ID."""
    query = update.callback_query
    data = query.data
    user = query.from_user
    user_id = user.id
    user_name = f"{user.first_name} {user.last_name or ''}".strip()
    username = user.username or ""

    try:
        await query.answer("✦ Loading challenge...", show_alert=False)
    except Exception:
        pass

    try:
        ch_id = int(data.split(":")[1])
    except (IndexError, ValueError):
        return

    active_challenges = await get_active_challenges()
    target_idx = 0
    for idx, ch in enumerate(active_challenges):
        if ch["id"] == ch_id:
            target_idx = idx
            break

    if active_challenges:
        await _render_active_challenge_card(
            query.edit_message_text,
            active_challenges,
            current_index=target_idx,
            user_id=user_id,
            user_name=user_name,
            username=username,
        )


async def handle_scheduled_challenge_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides an informative popup indicating the exact opening time and countdown."""
    query = update.callback_query
    data = query.data
    try:
        ch_id = int(data.split(":")[1])
    except (IndexError, ValueError):
        await query.answer("🕒 This challenge has not opened yet.", show_alert=True)
        return

    challenge = await get_challenge(ch_id)
    if not challenge:
        await query.answer("▪️ Challenge not found.", show_alert=True)
        return

    countdown = _format_time_until(challenge.get("starts_at"))
    opening_time = _format_scheduled_datetime(challenge.get("starts_at"))
    await query.answer(
        f"Scheduled Challenge\n\n"
        f"Opening: {opening_time}\n"
        f"Countdown: Opens {countdown}",
        show_alert=True,
    )


async def handle_challenge_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refreshes the challenge status and re-renders the challenge card in real time without emojis."""
    query = update.callback_query
    if not query:
        return
    data = query.data.split(":")
    ch_id = int(data[1]) if len(data) > 1 and data[1].isdigit() else 0
    curr_idx = int(data[2]) if len(data) > 2 and data[2].isdigit() else 0

    user = query.from_user
    user_id = user.id if user else 0
    user_name = f"{user.first_name} {user.last_name or ''}".strip() if user else ""
    username = user.username or "" if user else ""

    # Clear cache and evaluate real-time status transitions
    await get_challenge(ch_id, force_refresh=True)
    active_challenges = await get_active_challenges()

    if not active_challenges:
        try:
            await query.answer("No active challenges found.", show_alert=True)
        except Exception:
            pass
        return

    # Match target index
    target_idx = curr_idx
    for idx, ch in enumerate(active_challenges):
        if ch["id"] == ch_id:
            target_idx = idx
            break
    if target_idx >= len(active_challenges):
        target_idx = 0

    cur_ch = active_challenges[target_idx]
    if cur_ch.get("status") == "LIVE":
        try:
            await query.answer("Challenge is LIVE. Ready to start.", show_alert=False)
        except Exception:
            pass
    elif cur_ch.get("status") == "SCHEDULED":
        countdown = _format_time_until(cur_ch.get("starts_at"))
        try:
            await query.answer(f"Status refreshed. Opens {countdown}.", show_alert=False)
        except Exception:
            pass
    else:
        try:
            await query.answer("Status refreshed.", show_alert=False)
        except Exception:
            pass

    try:
        await _render_active_challenge_card(
            query.edit_message_text,
            active_challenges,
            current_index=target_idx,
            user_id=user_id,
            user_name=user_name,
            username=username,
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            raise


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
        s_dt = to_utc_datetime(challenge.get("starts_at"))
        now_dt = datetime.now(timezone.utc)
        if s_dt and now_dt >= s_dt:
            await update_challenge_status(ch_id, "LIVE")
            challenge["status"] = "LIVE"
            ch_status = "LIVE"
        else:
            time_until = _format_time_until(challenge.get("starts_at"))
            await query.answer(f"⏳ Not yet! Challenge starts {time_until}.", show_alert=True)
            return
    elif ch_status == "DRAFT":
        await query.answer("🛠️ This challenge is in draft mode and not yet published.", show_alert=True)
        return

    # Check if challenge deadline has passed
    remaining_sec, is_capped, ends_at_str = calculate_remaining_exam_seconds(challenge, None)
    if ends_at_str and remaining_sec <= 0:
        review_data = await get_challenge_review_data(ch_id, user_id, question_index=0)
        if "error" not in review_data:
            text = _format_review_card(review_data)
            kb = get_review_navigation_keyboard(
                ch_id,
                0,
                review_data["total_questions"],
                review_data.get("answered_status"),
            )
            await _safe_edit_or_reply(query, text, reply_markup=kb)
            return
        await query.answer("❌ This challenge window has officially closed.", show_alert=True)
        return

    part = await register_or_get_participant(ch_id, user_id, user_name, username)
    if part["status"] == "COMPLETED":
        review_data = await get_challenge_review_data(ch_id, user_id, question_index=0)
        if "error" not in review_data:
            text = _format_review_card(review_data)
            kb = get_review_navigation_keyboard(
                ch_id,
                0,
                review_data["total_questions"],
                review_data.get("answered_status"),
            )
            await _safe_edit_or_reply(query, text, reply_markup=kb)
            return
        await query.answer(f"🏁 You already completed this challenge! (Score: {part['score']} pts)", show_alert=True)
        return

    try:
        await query.answer("🚀 Initializing quiz session...", show_alert=False)
    except Exception:
        pass

    try:
        await start_participant_quiz(ch_id, user_id)
        q_data = await get_next_question_for_participant(ch_id, user_id)
    except Exception as exc:
        logger.exception("Error starting participant quiz: %s", exc)
        try:
            await query.answer("⚠️ Could not start quiz. Please try again.", show_alert=True)
        except Exception:
            pass
        return

    if not q_data:
        try:
            await query.answer("⚠️ No questions configured for this challenge yet.", show_alert=True)
        except Exception:
            pass
        return

    text = _format_question_card(q_data)
    kb = get_question_options_keyboard(
        ch_id,
        q_data["question_number"] - 1,
        q_data["display_keys"],
        q_data["total_questions"],
        q_data.get("answered_indices"),
    )
    if query.message and getattr(query.message, "photo", None):
        try:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception:
            pass
    await _safe_edit_or_reply(query, text, reply_markup=kb)


# ---------------------------------------------------------------------------
# Past Challenges & Archive
# ---------------------------------------------------------------------------
async def past_challenges_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays previous challenges for leaderboard inspection and question practice."""
    if context.bot and update.effective_chat:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        except Exception:
            pass
    challenges = await list_past_challenges(limit=15)
    challenges = [c for c in challenges if c.get("status") not in ("DRAFT", "SCHEDULED")]
    if not challenges:
        await update.message.reply_text(
            "✦ <b>Past Challenges Archive</b>\n\n"
            "No archived challenges available yet. Check back once weekly competitions conclude!",
            parse_mode=ParseMode.HTML,
        )
        return

    text = (
        "✦ <b>AWS Builder Challenge Archive</b>\n\n"
        "Browse previous competitions to inspect final standings or practice questions:\n\n"
        "➤ <i>Select a challenge below:</i>"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_past_challenges_keyboard(challenges),
    )


async def handle_past_challenges_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles interaction with past challenges archive."""
    query = update.callback_query
    data = query.data

    if data == "ch_past_list":
        try:
            await query.answer("✦ Loading archive...", show_alert=False)
        except Exception:
            pass
        challenges = await list_past_challenges(limit=15)
        challenges = [c for c in challenges if c.get("status") not in ("DRAFT", "SCHEDULED")]
        if not challenges:
            await query.edit_message_text(
                "✦ <b>Past Challenges Archive</b>\n\nNo archived challenges found.",
                parse_mode=ParseMode.HTML,
            )
            return

        text = (
            "✦ <b>AWS Builder Challenge Archive</b>\n\n"
            "Browse previous competitions to inspect final standings or practice questions:\n\n"
            "➤ <i>Select a challenge below:</i>"
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_past_challenges_keyboard(challenges),
        )

    elif data.startswith("ch_past:"):
        try:
            await query.answer("✦ Loading challenge details...", show_alert=False)
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        if not ch:
            await query.answer("▪️ Challenge not found.", show_alert=True)
            return

        from app.challenge.admin import is_admin_user
        user = query.from_user
        chat = getattr(query.message, "chat", None)
        chat_id = chat.id if chat else getattr(query.message, "chat_id", None)
        is_admin = await is_admin_user(user.id if user else 0, chat_id, context.bot)

        if ch.get("status") == "DRAFT" and not is_admin:
            await query.answer("🛠️ This challenge is in draft mode and not yet published.", show_alert=True)
            return

        title = html.escape(ch["title"])
        category = html.escape(ch["category"])
        status = ch["status"]
        desc = html.escape(ch.get("description") or "Test your AWS cloud skills!")
        questions = await get_challenge_questions(ch_id)
        total_q = len(questions)
        dur_secs = ch.get("duration_seconds") or 600
        exam_mins = int(dur_secs // 60) if dur_secs <= 7200 else 10

        status_icons = {"ENDED": "✔️ Ended", "LIVE": "🟢 Live", "CANCELLED": "❌ Cancelled", "SCHEDULED": "🕒 Scheduled"}
        status_tag = status_icons.get(status, status)

        card = (
            f"✦ <b>{title}</b> <i>[{status_tag}]</i>\n\n"
            f"<blockquote>{desc}</blockquote>\n\n"
            f"▫️ <b>Category:</b> {category}\n"
            f"▫️ <b>Total Questions:</b> {total_q}\n"
            f"▫️ <b>Exam Time:</b> {exam_mins} minutes\n\n"
            f"➤ <i>Inspect final rankings or practice questions below:</i>"
        )
        await query.edit_message_text(
            card,
            parse_mode=ParseMode.HTML,
            reply_markup=get_past_challenge_detail_keyboard(ch_id),
        )


def _format_completion_card(
    total: int,
    correct: int,
    score: float,
    time_taken_seconds: Optional[float] = None,
    time_limit_seconds: Optional[float] = None,
    accuracy_weight: float = 0.70,
    speed_weight: float = 0.30,
) -> str:
    acc_pct = int(round((correct / total) * 100)) if total > 0 else 0
    acc_weight_pct = int(round(accuracy_weight * 100))
    speed_weight_pct = int(round(speed_weight * 100))

    quote_lines = [
        "<blockquote>💡 <b>Score Calculation:</b>",
        f"• <b>Base Accuracy:</b> {correct}/{total} correct ({acc_pct}%) · {acc_weight_pct}% weight",
    ]

    if time_taken_seconds is not None and time_taken_seconds > 0:
        mins_taken = int(time_taken_seconds // 60)
        secs_taken = int(time_taken_seconds % 60)
        time_str = f"{mins_taken}m {secs_taken:02d}s" if mins_taken > 0 else f"{secs_taken}s"

        if time_limit_seconds and time_limit_seconds > 0:
            limit_mins = int(time_limit_seconds // 60)
            quote_lines.append(f"• <b>Time Taken:</b> {time_str} of {limit_mins}m limit · {speed_weight_pct}% speed bonus")
        else:
            quote_lines.append(f"• <b>Time Taken:</b> {time_str}")

    quote_lines.append(f"• <b>Final Points:</b> <code>{score} pts</code></blockquote>")
    quote_text = "\n".join(quote_lines)

    return (
        f"✓ <b>Challenge Completed!</b>\n\n"
        f"✦ <b>Results</b>\n"
        f"▫️ <b>Total Questions:</b> {total}\n"
        f"▫️ <b>Correct Answers:</b> {correct} / {total} ({acc_pct}%)\n"
        f"▫️ <b>Final Score:</b> <code>{score} pts</code>\n\n"
        f"{quote_text}\n\n"
        f"➤ <i>Your score has been submitted to the leaderboard. Select a view below:</i>"
    )


async def handle_challenge_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validates and scores an answer, advancing immediately to the next question screen or finishing."""
    query = update.callback_query

    parts = query.data.split(":")
    if len(parts) < 4:
        try:
            await query.answer()
        except Exception:
            pass
        return

    ch_id = int(parts[1])
    q_index = int(parts[2])
    selected_key = parts[3]
    user_id = query.from_user.id

    # Stop Telegram button loading spinner immediately with zero toast delay
    try:
        await query.answer()
    except Exception:
        pass

    try:
        result = await record_answer_and_advance(ch_id, user_id, selected_key, q_index)
    except Exception as exc:
        logger.exception("record_answer_and_advance crashed: %s", exc)
        try:
            await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)
        except Exception:
            pass
        return

    if "error" in result:
        # Check if participant is already completed
        part = await register_or_get_participant(ch_id, user_id)
        if part.get("status") == "COMPLETED":
            challenge = await get_challenge(ch_id)
            score = part["score"]
            correct = part["correct_count"]
            total = len(part["question_order"])
            s_dt = to_utc_datetime(part.get("started_at"))
            c_dt = to_utc_datetime(part.get("completed_at"))
            time_taken = max(0.0, (c_dt - s_dt).total_seconds()) if (s_dt and c_dt) else None
            time_limit = float(challenge.get("duration_seconds") or 600) if challenge else 600
            acc_w = float(challenge.get("accuracy_weight", 0.70)) if challenge else 0.70
            spd_w = float(challenge.get("speed_weight", 0.30)) if challenge else 0.30

            completion_text = _format_completion_card(
                total=total,
                correct=correct,
                score=score,
                time_taken_seconds=time_taken,
                time_limit_seconds=time_limit,
                accuracy_weight=acc_w,
                speed_weight=spd_w,
            )
            await _safe_edit_or_reply(query, completion_text, reply_markup=get_challenge_completion_keyboard(ch_id))
            return
        else:
            try:
                await query.answer(result["error"], show_alert=True)
            except Exception:
                pass
            return

    if result.get("is_completed"):
        # Challenge completed!
        score = result["current_score"]
        correct = result["correct_count"]
        total = result["total_questions"]
        time_taken = result.get("time_taken_seconds")
        time_limit = result.get("time_limit_seconds")
        acc_w = result.get("accuracy_weight", 0.70)
        spd_w = result.get("speed_weight", 0.30)

        completion_text = _format_completion_card(
            total=total,
            correct=correct,
            score=score,
            time_taken_seconds=time_taken,
            time_limit_seconds=time_limit,
            accuracy_weight=acc_w,
            speed_weight=spd_w,
        )
        await _safe_edit_or_reply(query, completion_text, reply_markup=get_challenge_completion_keyboard(ch_id))
        return

    # Fetch and render next question immediately using prefetched state
    next_target_idx = result.get("next_question_index")
    next_q = await get_next_question_for_participant(
        ch_id,
        user_id,
        question_index=next_target_idx,
        prefetched_part=result.get("_participant"),
        prefetched_challenge=result.get("_challenge"),
        prefetched_answered_indices=result.get("_answered_indices"),
    )
    if not next_q:
        part = await register_or_get_participant(ch_id, user_id)
        challenge = await get_challenge(ch_id)
        score = part["score"]
        correct = part["correct_count"]
        total = len(part["question_order"])
        s_dt = to_utc_datetime(part.get("started_at"))
        c_dt = to_utc_datetime(part.get("completed_at"))
        time_taken = max(0.0, (c_dt - s_dt).total_seconds()) if (s_dt and c_dt) else None
        time_limit = float(challenge.get("duration_seconds") or 600) if challenge else 600
        acc_w = float(challenge.get("accuracy_weight", 0.70)) if challenge else 0.70
        spd_w = float(challenge.get("speed_weight", 0.30)) if challenge else 0.30

        completion_text = _format_completion_card(
            total=total,
            correct=correct,
            score=score,
            time_taken_seconds=time_taken,
            time_limit_seconds=time_limit,
            accuracy_weight=acc_w,
            speed_weight=spd_w,
        )
        await _safe_edit_or_reply(query, completion_text, reply_markup=get_challenge_completion_keyboard(ch_id))
        return

    text = _format_question_card(next_q)
    kb = get_question_options_keyboard(
        ch_id,
        next_q["question_number"] - 1,
        next_q["display_keys"],
        next_q["total_questions"],
        next_q.get("answered_indices"),
    )
    await _safe_edit_or_reply(query, text, reply_markup=kb)


async def handle_challenge_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles jumping directly to a specific question via the bottom navigation bar."""
    query = update.callback_query

    parts = query.data.split(":")
    if len(parts) < 3:
        try:
            await query.answer()
        except Exception:
            pass
        return

    ch_id = int(parts[1])
    target_idx = int(parts[2])
    user_id = query.from_user.id

    try:
        await query.answer()
    except Exception:
        pass

    try:
        q_data = await get_next_question_for_participant(ch_id, user_id, question_index=target_idx)
    except Exception as exc:
        logger.exception("get_next_question_for_participant crashed in nav: %s", exc)
        try:
            await query.answer("▪️ Failed to load question. Please try again.", show_alert=True)
        except Exception:
            pass
        return

    if not q_data:
        part = await register_or_get_participant(ch_id, user_id)
        if part.get("status") == "COMPLETED":
            challenge = await get_challenge(ch_id)
            score = part["score"]
            correct = part["correct_count"]
            total = len(part["question_order"])
            s_dt = to_utc_datetime(part.get("started_at"))
            c_dt = to_utc_datetime(part.get("completed_at"))
            time_taken = max(0.0, (c_dt - s_dt).total_seconds()) if (s_dt and c_dt) else None
            time_limit = float(challenge.get("duration_seconds") or 600) if challenge else 600
            acc_w = float(challenge.get("accuracy_weight", 0.70)) if challenge else 0.70
            spd_w = float(challenge.get("speed_weight", 0.30)) if challenge else 0.30

            completion_text = _format_completion_card(
                total=total,
                correct=correct,
                score=score,
                time_taken_seconds=time_taken,
                time_limit_seconds=time_limit,
                accuracy_weight=acc_w,
                speed_weight=spd_w,
            )
            await _safe_edit_or_reply(query, completion_text, reply_markup=get_challenge_completion_keyboard(ch_id))
        else:
            try:
                await query.answer("▪️ Could not load question. Time may have expired.", show_alert=True)
            except Exception:
                pass
        return

    text = _format_question_card(q_data)
    kb = get_question_options_keyboard(
        ch_id,
        q_data["question_number"] - 1,
        q_data["display_keys"],
        q_data["total_questions"],
        q_data.get("answered_indices"),
    )
    await _safe_edit_or_reply(query, text, reply_markup=kb)


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the community challenge leaderboard."""
    if context.bot and update.effective_chat:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        except Exception:
            pass
    challenge = await get_active_challenge()
    if challenge:
        ch_id = challenge["id"]
    else:
        from app.challenge.service import list_challenges
        recent = await list_challenges(status="ENDED", limit=1)
        ch_id = recent[0]["id"] if recent else 0
    user = update.effective_user
    chat = update.effective_chat
    from app.challenge.admin import is_admin_user
    is_admin = await is_admin_user(user.id if user else 0, chat.id if chat else None, context.bot)
    await send_leaderboard_view(update.message.reply_text, ch_id, mode="weekly", page=1, is_admin=is_admin, user_id=user.id if user else None)


async def handle_leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switches leaderboard views and handles next/prev pagination."""
    query = update.callback_query

    if query.data == "noop":
        try:
            await query.answer()
        except Exception:
            pass
        return

    data = query.data.split(":")
    mode_prefix = data[0]
    user = query.from_user
    chat = getattr(query.message, "chat", None)
    chat_id = chat.id if chat else getattr(query.message, "chat_id", None)
    from app.challenge.admin import is_admin_user
    is_admin = await is_admin_user(user.id if user else 0, chat_id, context.bot)
    user_id = user.id if user else None

    ch_id = int(data[1]) if len(data) > 1 and data[1].isdigit() else 0
    page = int(data[2]) if len(data) > 2 and data[2].isdigit() else 1

    if mode_prefix == "lb_weekly":
        try:
            await query.answer("🏆 Loading weekly leaderboard...", show_alert=False)
        except Exception:
            pass
        if ch_id == 0:
            active = await get_active_challenge()
            if active:
                ch_id = active["id"]
            else:
                from app.challenge.service import list_challenges
                recent = await list_challenges(status="ENDED", limit=1)
                ch_id = recent[0]["id"] if recent else 0

        await send_leaderboard_view(query.edit_message_text, ch_id, mode="weekly", page=page, is_admin=is_admin, user_id=user_id)

    elif mode_prefix == "lb_monthly":
        try:
            await query.answer("📅 Loading monthly standings...", show_alert=False)
        except Exception:
            pass
        if ch_id == 0:
            active = await get_active_challenge()
            if active:
                ch_id = active["id"]

        await send_leaderboard_view(query.edit_message_text, ch_id, mode="monthly", page=page, is_admin=is_admin, user_id=user_id)


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


async def send_leaderboard_view(
    sender_func,
    challenge_id: int,
    mode: str = "weekly",
    page: int = 1,
    is_admin: bool = False,
    user_id: Optional[int] = None,
):
    """Renders formatted leaderboard text. For non-admins shows real names only. For admins shows username."""
    is_active = False
    can_review = False

    if mode == "weekly":
        ch = None
        if challenge_id > 0:
            ch = await get_challenge(challenge_id)
            if not ch or (ch.get("status") == "DRAFT" and not is_admin):
                ch = None
                challenge_id = 0

        if challenge_id > 0 and ch:
            title = html.escape(ch["title"])
            lb_data = await get_weekly_leaderboard(challenge_id, limit=10, page=page)
            entries = lb_data["entries"]
            total_pages = lb_data["total_pages"]
            total_count = lb_data["total_count"]

            # Check challenge status
            is_active = bool(ch and ch.get("status") in ("LIVE", "SCHEDULED"))
            remaining_sec, is_capped, ends_at_str = calculate_remaining_exam_seconds(ch, None) if ch else (0, False, None)
            is_ended = bool(ch and (ch.get("status") in ("ENDED", "CANCELLED") or (ends_at_str is not None and remaining_sec <= 0)))

            is_completed = False
            if user_id:
                part = await register_or_get_participant(challenge_id, user_id)
                is_completed = bool(part and part.get("status") == "COMPLETED")

            # Can only review if user completed it OR challenge ended/archived
            can_review = bool(is_completed or is_ended)

            if not entries:
                text = (
                    f"🏆 <b>Weekly Leaderboard: {title}</b>\n\n"
                    f"<i>No completed submissions yet. Be the first to take the challenge!</i>"
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
                    lines.append(f"{rank_icon} {name_display} — <code>{score} pts</code> ({correct}/{total} ✓)")
                text = "\n".join(lines)
        else:
            total_pages = 1
            total_count = 0
            text = (
                f"🏆 <b>Weekly Challenge Leaderboard</b>\n\n"
                f"<i>No active challenge at the moment. Check back soon or view Monthly standings!</i>"
            )
    else:
        if challenge_id > 0:
            ch = await get_challenge(challenge_id)
            is_active = bool(ch and ch.get("status") in ("LIVE", "SCHEDULED"))

        lb_data = await get_monthly_leaderboard(limit=10, page=page)
        entries = lb_data["entries"]
        total_pages = lb_data["total_pages"]
        total_count = lb_data["total_count"]

        if not entries:
            text = (
                f"📅 <b>Monthly Championship Leaderboard</b>\n\n"
                f"<i>No completed challenge data for this season yet.</i>"
            )
        else:
            page_info = f" <i>(Page {page} of {total_pages})</i>" if total_pages > 1 else ""
            lines = [f"📅 <b>Monthly Championship Leaderboard</b>{page_info}\n"]
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
        reply_markup=get_leaderboard_keyboard(
            challenge_id,
            mode=mode,
            page=page,
            total_pages=total_pages,
            can_review=can_review,
            is_active=is_active,
        ),
    )


# ---------------------------------------------------------------------------
# Scoring & Informative Rules
# ---------------------------------------------------------------------------
def get_scoring_rules_text() -> str:
    """Returns formatted explanation of overall exam timing and two-factor scoring."""
    return (
        "✦ <b>How Scoring Works</b>\n\n"
        "<blockquote>⏱️ <b>Exam Timer & Self-Pacing</b>\n"
        "Each challenge has a unified overall test time limit. "
        "Manage your time freely across questions. A live countdown displays on each question.</blockquote>\n\n"
        "<blockquote>🎯 <b>Two-Factor Scoring Formula</b>\n"
        "<b>Score = Raw Points × (0.70 + 0.30 × (1 - Time Used / Allotted Time))</b>\n"
        "▫️ <b>70% Accuracy:</b> Points earned for correct answers\n"
        "▫️ <b>30% Speed:</b> Bonus awarded for faster completion</blockquote>\n\n"
        "◆ <b>Speed Multiplier Scale (10-min exam)</b>\n"
        "‣ 2 mins used › <code>~94%</code> of max points\n"
        "‣ 5 mins used › <code>85%</code> of max points\n"
        "‣ 8 mins used › <code>76%</code> of max points\n"
        "‣ 10 mins used › <code>70%</code> (Accuracy baseline)\n"
        "‣ Overtime › Auto-submits answered questions\n\n"
        "◆ <b>Leaderboards & Tie-Breakers</b>\n"
        "▫️ <b>Weekly Leaderboard:</b> Instant rankings for each quiz\n"
        "▫️ <b>Monthly Championship:</b> Cumulative score across all weeks\n"
        "▫️ <b>Tie-Breaker:</b> Fastest completion time wins\n\n"
        "➤ <i>Compete weekly, master AWS cloud, and climb the leaderboard!</i>"
    )


def get_guidelines_text() -> str:
    """Returns the community guidelines and code of conduct text."""
    return (
        "✦ <b>Community Guidelines & Code of Conduct</b>\n\n"
        "These rules apply to all AWS Builder Challenges to ensure fair competition:\n\n"
        "▫️ <b>Strictly One Account</b> › Secondary accounts will be disqualified\n"
        "▫️ <b>No AI or Automation Assistance</b> › Automated bots and AI tool assistance are prohibited\n"
        "▫️ <b>Single Continuous Attempt</b> › Timer runs continuously once started\n"
        "▫️ <b>Academic Integrity & No Leaks</b> › Do not share or dump questions before challenge ends\n"
        "▫️ <b>Screenshots Disabled</b> › Quiz questions are content protected\n"
        "▫️ <b>Post-Exam Review</b> › Full explanations unlock right after submission\n\n"
        "➤ <i>Fair play ensures equal opportunity for all builders. Good luck!</i>"
    )


async def scoring_rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the scoring rules to the user."""
    if context.bot and update.effective_chat:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        except Exception:
            pass
    challenge = await get_active_challenge()
    ch_id = challenge["id"] if challenge else 0
    await update.message.reply_text(
        get_scoring_rules_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_scoring_rules_keyboard(ch_id),
    )


async def guidelines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the community guidelines to the user."""
    if context.bot and update.effective_chat:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        except Exception:
            pass
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
        try:
            await update.callback_query.answer("🛡️ Loading community guidelines...", show_alert=False)
        except Exception:
            pass
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
    try:
        await query.answer("📖 Loading scoring rules...", show_alert=False)
    except Exception:
        pass
    challenge = await get_active_challenge()
    ch_id = challenge["id"] if challenge else 0
    await query.edit_message_text(
        get_scoring_rules_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=get_scoring_rules_keyboard(ch_id),
    )

