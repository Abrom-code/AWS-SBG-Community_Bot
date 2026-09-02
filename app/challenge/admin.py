import html
import io
import logging
import math
import os
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.db import get_all_broadcast_user_ids, set_user_state
from app.challenge.service import (
    create_challenge,
    get_challenge,
    get_active_challenge,
    list_challenges,
    update_challenge_status,
    link_questions_to_challenge,
    list_questions,
    create_question,
    import_questions_from_csv,
    get_challenge_questions,
    get_monthly_analytics_report,
    delete_challenge,
    update_challenge_details,
    get_weekly_leaderboard,
    get_monthly_leaderboard,
    add_question_to_challenge,
    import_questions_for_challenge,
    remove_question_from_challenge,
    to_utc_datetime,
    format_datetime_12h,
)
from app.challenge.keyboards import (
    get_admin_menu_keyboard,
    get_admin_panel_keyboard,
    get_challenge_manage_keyboard,
    get_admin_schedule_presets_keyboard,
    get_admin_broadcast_presets_keyboard,
    get_admin_broadcast_confirm_keyboard,
    get_admin_report_keyboard,
    get_wizard_questions_keyboard,
    get_wizard_skip_desc_keyboard,
    get_wizard_category_keyboard,
    get_wizard_timer_keyboard,
    get_challenge_delete_confirm_keyboard,
    get_admin_leaderboard_keyboard,
    get_challenge_questions_view_keyboard,
    get_challenge_schedule_edit_keyboard,
    get_challenge_timer_edit_keyboard,
    get_question_bank_actions_keyboard,
)

logger = logging.getLogger(__name__)

ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_CHAT_ID", "0"))


def get_configured_admin_ids() -> set:
    """Returns the set of explicitly configured admin Telegram user IDs."""
    admin_ids = set()
    raw_ids = os.getenv("ADMIN_USER_IDS", "") or os.getenv("ADMIN_IDS", "")
    for part in raw_ids.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
            admin_ids.add(int(part))
    return admin_ids


_verified_admin_cache: set = set()


async def is_admin_user(user_id: int, chat_id: Optional[int] = None, bot=None) -> bool:
    """Verifies whether a user has administrative permissions with fast in-memory caching."""
    # 0. Fast-path: Check in-memory cache of already verified admins
    if user_id in _verified_admin_cache:
        return True

    # 1. Check explicitly configured admin user IDs
    if user_id in get_configured_admin_ids():
        _verified_admin_cache.add(user_id)
        return True

    # 2. Check if executed directly inside the admin staff group
    if chat_id and ADMIN_GROUP_ID != 0 and chat_id == ADMIN_GROUP_ID:
        _verified_admin_cache.add(user_id)
        return True

    # 3. Check if user is a creator, administrator, or member of the staff group
    if ADMIN_GROUP_ID != 0 and bot:
        try:
            member = await bot.get_chat_member(chat_id=ADMIN_GROUP_ID, user_id=user_id)
            if member.status in ("creator", "administrator", "member"):
                _verified_admin_cache.add(user_id)
                return True
        except Exception as e:
            logger.debug(f"Admin verification check failed for user {user_id}: {e}")

    return False


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entrypoint for the Challenge Administration Panel (restricted to administrators)."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await is_admin_user(user.id, chat.id if chat else None, context.bot):
        await update.message.reply_text(
            "<b>Access Denied:</b> This command is restricted to AWS SBG administrators.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Switch bottom buttons to admin menu (includes Main Menu)
    await update.message.reply_text(
        "<b>AWS SBG Challenge Admin Panel</b>\n\n"
        "Welcome to the challenge operations center. Manage competitions, questions, "
        "leaderboards, and broadcasts using the admin menu below.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_menu_keyboard(),
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes admin dashboard button actions with permission checks and error boundary."""
    try:
        await _handle_admin_callback_impl(update, context)
    except Exception as e:
        logger.error(f"Error in handle_admin_callback: {e}", exc_info=True)
        query = update.callback_query
        if query:
            err_msg = str(e)
            if "HTTP implementation" in err_msg or "Event loop" in err_msg or "attached to a different loop" in err_msg:
                user_alert = "Temporary connection reset. Please tap again."
            else:
                user_alert = f"Error: {err_msg[:60]}"
            try:
                await query.answer(user_alert, show_alert=True)
            except Exception:
                pass
            try:
                await query.message.reply_text(
                    f"<b>An error occurred:</b> {html.escape(str(e))}\n\nPlease try again or check /admin.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_admin_panel_keyboard(),
                )
            except Exception:
                pass


async def _handle_admin_callback_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Internal router for admin dashboard button callbacks."""
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id if query.message else None

    if not await is_admin_user(user.id, chat_id, context.bot):
        try:
            await query.answer("Access Denied: Admin privileges required.", show_alert=True)
        except Exception:
            pass
        return

    data = query.data

    if data == "adm_panel":
        try:
            await query.answer()
        except Exception:
            pass
        await query.edit_message_text(
            "<b>Admin Console</b>\n\n"
            "Select an action below to manage challenges and questions:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard(),
        )

    elif data == "adm_list_ch":
        try:
            await query.answer()
        except Exception:
            pass
        from telegram import InlineKeyboardMarkup
        challenges = await list_challenges(limit=10)
        if not challenges:
            await query.edit_message_text(
                "<b>Challenges</b>\n\nNo challenges found. Click <b>Create Challenge</b> to start.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_panel_keyboard(),
            )
            return

        lines = [
            "<b>Challenges</b>\n",
            "<blockquote>Select a challenge below to edit parameters, link questions, or update lifecycle status.</blockquote>\n",
        ]
        buttons = []
        for ch in challenges:
            title = html.escape(ch["title"])
            status = ch["status"]
            lines.append(f"• <b>#{ch['id']} {title}</b> [{status}]")
            buttons.append([InlineKeyboardButton(f"Manage #{ch['id']} {title[:22]}", callback_data=f"adm_manage:{ch['id']}")])

        buttons.append([InlineKeyboardButton("« Back to Admin", callback_data="adm_panel")])
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data.startswith("adm_manage:") or data.startswith("adm_manage_ch:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        await set_user_state(user.id, None)
        ch = await get_challenge(ch_id)
        if not ch:
            await query.answer("Challenge not found.", show_alert=True)
            return

        questions = await get_challenge_questions(ch_id)
        status = ch["status"]
        title = html.escape(ch["title"])
        category = html.escape(ch["category"])
        starts = format_datetime_12h(ch.get("starts_at"), fallback="Unscheduled (Draft)")
        ends = format_datetime_12h(ch.get("ends_at"), fallback="None")
        dur_secs = ch.get("duration_seconds") or 600
        exam_mins = int(dur_secs // 60) if dur_secs <= 7200 else 10

        manage_text = (
            f"<b>Manage Challenge · #{ch_id}</b>\n\n"
            f"<blockquote><b>{title}</b>\n"
            f"Category: {category}</blockquote>\n\n"
            f"• <b>Status:</b> <code>{status}</code>\n"
            f"• <b>Exam Time Limit:</b> {exam_mins} minutes\n"
            f"• <b>Attached Questions:</b> <code>{len(questions)}</code>\n"
            f"• <b>Starts At:</b> <code>{starts}</code>\n"
            f"• <b>Ends At:</b> <code>{ends}</code>\n\n"
            f"<i>Select an action below to update or change status:</i>"
        )
        await query.edit_message_text(
            manage_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
        )

    elif data.startswith("adm_link_q:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        linked = await link_questions_to_challenge(ch_id)
        ch = await get_challenge(ch_id)
        status = ch["status"] if ch else "LIVE"
        await query.answer(f"Linked questions: {linked}", show_alert=True)
        questions = await get_challenge_questions(ch_id)
        await query.edit_message_text(
            f"<b>Question Bank Linked to Challenge #{ch_id}</b>\n\n"
            f"• <b>Total Questions Attached:</b> <code>{len(questions)}</code>\n\n"
            f"Participants will be tested on these randomized questions.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
        )

    elif data == "adm_cr_custom_date":
        try:
            await query.answer()
        except Exception:
            pass
        await set_user_state(user.id, "WAITING_FOR_ADMIN_SCHEDULE")
        await query.edit_message_text(
            "<b>Set Custom Challenge Schedule</b>\n\n"
            "Please type and send the start and end date/time in one of these formats:\n\n"
            "• <code>2026-09-05 14:00 to 2026-09-12 18:00</code>\n"
            "• <code>2026-09-05 to 2026-09-12</code>\n"
            "• <code>2026-09-05T14:00:00 to 2026-09-12T18:00:00</code>\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data == "adm_qbank":
        try:
            await query.answer()
        except Exception:
            pass
        questions = await list_questions(limit=10)
        count = len(questions)
        if not questions:
            await query.edit_message_text(
                "<b>AWS Question Bank</b>\n\n"
                "• <b>Active Questions:</b> <code>0</code>\n\n"
                "<i>No questions found in repository yet.</i>\n\n"
                "<blockquote>Questions belong directly to weekly topic challenges. "
                "Tap <b>« All Challenges</b> below to create a challenge or add questions.</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_question_bank_actions_keyboard(),
            )
            return

        lines = [f"<b>AWS Question Bank Repository</b> · <code>{count} questions shown</code>:\n"]
        for idx, q in enumerate(questions[:8]):
            q_t = html.escape(q.get("question_text", "Untitled")[:42])
            cat = html.escape(q.get("category", "General"))
            c_opt = q.get("correct_option", "A")
            lines.append(f"<b>{idx+1}.</b> [{cat}] {q_t}... <i>(Ans: {c_opt})</i>")

        lines.append("\n<i>To add new questions or import CSV, select a challenge in <b>« All Challenges</b>.</i>")
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=get_question_bank_actions_keyboard(),
        )

    elif data == "adm_create_ch":
        try:
            await query.answer()
        except Exception:
            pass
        await set_user_state(user.id, "WAITING_FOR_CHALLENGE_TITLE")
        await query.edit_message_text(
            "<b>Create Challenge Wizard (Step 1/4: Title)</b>\n\n"
            "Please enter the Title (or <code>Title | Category</code>) for this challenge:\n\n"
            "<i>Examples:</i>\n"
            "• <code>AWS Solutions Architect Associate Sprint</code>\n"
            "• <code>AWS Solutions Architect Sprint | Architecture</code>\n\n"
            "<blockquote>Tip: Power users can send all in one line:\n"
            "<code>Title | Category | Description | Duration</code></blockquote>\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_wiz_cat_menu:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        current_cat = ch.get("category", "Architecture") if ch else "Architecture"
        await query.edit_message_text(
            f"<b>Create Challenge Wizard (Step 2/4: Choose Category)</b>\n\n"
            f"• <b>Current Category:</b> <code>{html.escape(current_cat)}</code>\n\n"
            f"Tap a category below for this challenge:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_category_keyboard(ch_id),
        )

    elif data.startswith("adm_wiz_set_cat:"):
        try:
            await query.answer()
        except Exception:
            pass
        parts = data.split(":")
        ch_id = int(parts[1])
        new_cat = parts[2]
        await update_challenge_details(ch_id, category=new_cat)
        context.user_data["wiz_category"] = new_cat
        ch = await get_challenge(ch_id)
        title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"
        await query.edit_message_text(
            f"<b>Create Challenge Wizard (Step 2/4: Description)</b>\n\n"
            f"• <b>Title:</b> <b>{html.escape(title)}</b>\n"
            f"• <b>Category:</b> <code>{html.escape(new_cat)}</code>\n\n"
            f"Please enter the challenge description:\n"
            f"<i>(Explain what community members will learn or test in this challenge)</i>\n\n"
            f"<i>Example:</i> <code>Master EC2, S3, VPC, Lambda, and high-availability design patterns in this weekly challenge.</code>\n\n"
            f"<i>(Or tap below to use default description or change category)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_skip_desc_keyboard(ch_id),
        )

    elif data.startswith("adm_wiz_back_desc:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"
        cat = ch.get("category", "Architecture") if ch else "Architecture"
        await set_user_state(user.id, f"WAITING_FOR_CHALLENGE_DESC:{ch_id}")
        await query.edit_message_text(
            f"<b>Create Challenge Wizard (Step 2/4: Description)</b>\n\n"
            f"• <b>Title:</b> <b>{html.escape(title)}</b>\n"
            f"• <b>Category:</b> <code>{html.escape(cat)}</code>\n\n"
            f"Please enter the challenge description:\n"
            f"<i>(Explain what community members will learn or test in this challenge)</i>\n\n"
            f"<i>Example:</i> <code>Master EC2, S3, VPC, Lambda, and high-availability design patterns in this weekly challenge.</code>\n\n"
            f"<i>(Or tap below to use default description or change category)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_skip_desc_keyboard(ch_id),
        )

    elif data.startswith("adm_wiz_custom_cat:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        await set_user_state(user.id, f"WAITING_FOR_CHALLENGE_CUSTOM_CAT:{ch_id}")
        await query.edit_message_text(
            f"<b>Create Challenge Wizard (Step 2/4: Custom Category)</b>\n\n"
            "Please send your custom category name:\n\n"
            "<i>Examples:</i> <code>Generative AI</code>, <code>MLOps</code>, <code>Cybersecurity</code>\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_wiz_skip_desc:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        await set_user_state(user.id, None)
        ch = await get_challenge(ch_id)
        title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"
        category = ch.get("category", "Architecture") if ch else "Architecture"
        desc = ch.get("description", "Weekly test on AWS core services and cloud architecture patterns.") if ch else "Weekly test on AWS core services and cloud architecture patterns."
        await query.edit_message_text(
            f"<b>Create Challenge Wizard (Step 3/4: Exam Time Limit)</b>\n\n"
            f"<blockquote><b>{html.escape(title)}</b>\n"
            f"<i>{html.escape(desc)}</i></blockquote>\n\n"
            f"Select the allowed exam time for community members:\n"
            f"<i>(Timer begins when participant starts the challenge)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_timer_keyboard(ch_id),
        )

    elif data.startswith("adm_wiz_timer:"):
        try:
            await query.answer()
        except Exception:
            pass
        parts = data.split(":")
        ch_id = int(parts[1])
        mins = int(parts[2])
        await update_challenge_details(ch_id, duration_seconds=mins * 60)
        ch = await get_challenge(ch_id)
        title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"
        desc = ch.get("description", "") if ch else ""
        await query.edit_message_text(
            f"<b>Create Challenge Wizard (Step 4/4: Schedule & Start/End Time)</b>\n\n"
            f"<blockquote><b>{html.escape(title)}</b>\n"
            f"<i>{html.escape(desc)}</i></blockquote>\n\n"
            f"• <b>Exam Time Limit:</b> <code>{mins} Minutes</code>\n\n"
            f"Select start schedule & deadline:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_schedule_presets_keyboard(ch_id, mins),
        )

    elif data.startswith("adm_wiz_timer_custom:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        await set_user_state(user.id, f"WAITING_FOR_CHALLENGE_TIMER:{ch_id}")
        await query.edit_message_text(
            f"<b>Custom Exam Time Limit for Challenge #{ch_id}</b>\n\n"
            "Please send the total allowed exam time in minutes (e.g. <code>12</code>, <code>25</code>, <code>60</code>):\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_del_prompt:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        await query.edit_message_text(
            f"<b>Delete Challenge #{ch_id}</b>\n\n"
            f"<blockquote><b>{title}</b></blockquote>\n\n"
            f"Are you sure you want to permanently delete this challenge and all its participant submissions?",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_delete_confirm_keyboard(ch_id),
        )

    elif data.startswith("adm_del_conf:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        await delete_challenge(ch_id)
        await query.edit_message_text(
            f"<b>Challenge #{ch_id} has been permanently deleted.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard(),
        )

    elif data.startswith("adm_edit_title:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        context.user_data["edit_ch_id"] = ch_id
        await set_user_state(user.id, "WAITING_FOR_EDIT_CHALLENGE_TITLE")
        await query.edit_message_text(
            f"<b>Edit Challenge #{ch_id}</b>\n\n"
            f"Please send the new title and category (e.g. <code>AWS Cloud Essentials | General</code>):\n\n"
            f"<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_edit_sched:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        await set_user_state(user.id, f"WAITING_FOR_EDIT_CHALLENGE_SCHEDULE:{ch_id}")
        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        starts_str = ch.get("starts_at") or "Not scheduled"
        ends_str = ch.get("ends_at") or "Not scheduled"
        status = ch.get("status", "DRAFT")

        await query.edit_message_text(
            f"<b>Edit Schedule for Challenge #{ch_id} ({title})</b>\n\n"
            f"• <b>Current Status:</b> <code>{status}</code>\n"
            f"• <b>Starts At:</b> <code>{starts_str}</code>\n"
            f"• <b>Ends At:</b> <code>{ends_str}</code>\n\n"
            f"Select a preset schedule below or enter custom start & end dates:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_schedule_edit_keyboard(ch_id),
        )

    elif data.startswith("adm_sched_set:"):
        try:
            await query.answer("⏳ Updating schedule...", show_alert=False)
        except Exception:
            pass
        parts = data.split(":")
        ch_id = int(parts[1])
        start_opt = parts[2]
        from datetime import datetime, timezone, timedelta
        now_dt = datetime.now(timezone.utc)
        questions = await get_challenge_questions(ch_id)

        if start_opt == "now":
            if not questions:
                try:
                    await query.answer("⚠️ Please attach at least 1 question before going LIVE!", show_alert=True)
                except Exception:
                    pass
                return
            starts_at = now_dt.isoformat()
            ends_at = (now_dt + timedelta(days=7)).isoformat()
            status = "LIVE"
        elif start_opt in ("24h", "tomorrow", "1h"):
            if not questions:
                try:
                    await query.answer("Please attach at least 1 question before scheduling.", show_alert=True)
                except Exception:
                    pass
                return
            s_dt = now_dt + timedelta(days=1)
            starts_at = s_dt.isoformat()
            ends_at = (s_dt + timedelta(days=7)).isoformat()
            status = "SCHEDULED"
        else:
            starts_at = None
            ends_at = None
            status = "DRAFT"

        await update_challenge_details(ch_id, starts_at=starts_at, ends_at=ends_at)
        await update_challenge_status(ch_id, status)
        await set_user_state(user.id, None)

        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        await query.edit_message_text(
            f"<b>Manage Challenge · #{ch_id}</b>\n\n"
            f"<blockquote><b>{title}</b>\n"
            f"Category: {html.escape(ch.get('category', 'Architecture'))}</blockquote>\n\n"
            f"• <b>Status:</b> <code>{status}</code>\n"
            f"• <b>Starts:</b> <code>{format_datetime_12h(starts_at)}</code>\n"
            f"• <b>Ends:</b> <code>{format_datetime_12h(ends_at)}</code>\n\n"
            f"Schedule has been updated.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
        )

    elif data.startswith("adm_sched_custom:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        context.user_data["edit_ch_id"] = ch_id
        await set_user_state(user.id, f"WAITING_FOR_EDIT_CHALLENGE_SCHEDULE:{ch_id}")
        await query.edit_message_text(
            f"<b>Custom Schedule for Challenge #{ch_id}</b>\n\n"
            "Please send the <b>Start Date/Time to End Date/Time</b>:\n\n"
            "<code>2026-09-05 18:00 to 2026-09-12 18:00</code>\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_edit_timer:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        dur_secs = ch.get("duration_seconds") or 600
        mins = int(dur_secs // 60) if dur_secs <= 7200 else 10

        await query.edit_message_text(
            f"<b>Edit Exam Time Limit for Challenge #{ch_id} ({title})</b>\n\n"
            f"• <b>Current Allowed Time:</b> <code>{mins} minutes total</code>\n\n"
            f"Select a preset duration or enter custom minutes:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_timer_edit_keyboard(ch_id),
        )

    elif data.startswith("adm_timer_set:"):
        try:
            await query.answer()
        except Exception:
            pass
        parts = data.split(":")
        ch_id = int(parts[1])
        mins = int(parts[2])
        dur_secs = mins * 60

        await update_challenge_details(ch_id, duration_seconds=dur_secs)

        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        status = ch.get("status", "DRAFT")
        await query.edit_message_text(
            f"<b>Manage Challenge · #{ch_id}</b>\n\n"
            f"<blockquote><b>{title}</b></blockquote>\n\n"
            f"• <b>Exam Time Limit:</b> <code>{mins} minutes total</code>\n"
            f"• <b>Status:</b> <code>{status}</code>\n\n"
            f"Exam duration updated successfully.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
        )

    elif data.startswith("adm_timer_custom:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        context.user_data["edit_ch_id"] = ch_id
        await set_user_state(user.id, "WAITING_FOR_EDIT_CHALLENGE_TIMER")
        await query.edit_message_text(
            f"<b>Custom Exam Time Limit for Challenge #{ch_id}</b>\n\n"
            "Please send the total allowed exam time in minutes (e.g. <code>12</code> or <code>25</code>):\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_cr_sched:"):
        try:
            await query.answer()
        except Exception:
            pass
        parts = data.split(":")
        from datetime import datetime, timezone, timedelta
        now_dt = datetime.now(timezone.utc)

        if len(parts) >= 4:
            ch_id = int(parts[1])
            start_opt = parts[2]
        else:
            ch_id = None
            start_opt = parts[1]

        is_scheduled = False
        if start_opt == "now":
            starts_at = now_dt.isoformat()
            ends_at = (now_dt + timedelta(days=7)).isoformat()
            schedule_note = "• <b>Schedule:</b> Ready to Go Live (Ends in 7 days — Pending questions)"
        elif start_opt in ("24h", "tomorrow", "1h"):
            s_dt = now_dt + timedelta(days=1)
            starts_at = s_dt.isoformat()
            ends_at = (s_dt + timedelta(days=7)).isoformat()
            is_scheduled = True
            schedule_note = "• <b>Schedule:</b> Scheduled for Tomorrow (Starts in 24 hours — Pending questions)"
        else:
            starts_at = None
            ends_at = None
            schedule_note = "• <b>Schedule:</b> DRAFT (Unscheduled)"

        # Challenge ALWAYS remains in DRAFT until questions are attached and it is published!
        status = "DRAFT"

        if ch_id:
            await update_challenge_details(ch_id, starts_at=starts_at, ends_at=ends_at)
            await update_challenge_status(ch_id, status)
            ch = await get_challenge(ch_id)
            title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"
            category = ch.get("category", "General") if ch else "General"
            dur_secs = ch.get("duration_seconds") or 600 if ch else 600
            exam_mins = int(dur_secs // 60)
            questions = await get_challenge_questions(ch_id)
            q_count = len(questions)
        else:
            title = context.user_data.pop("wiz_title", "AWS Cloud Architecture Challenge")
            category = context.user_data.pop("wiz_category", "Architecture")
            description = context.user_data.pop("wiz_description", "Weekly timed AWS challenge on core compute, storage, security, and networking (70% accuracy + 30% speed bonus).")
            dur_mins = context.user_data.pop("wiz_duration_mins", 10)
            dur_secs = dur_mins * 60
            exam_mins = dur_mins
            ch_id = await create_challenge(
                title=title,
                description=description,
                category=category,
                starts_at=starts_at,
                ends_at=ends_at,
                question_time_limit_seconds=60,
                duration_seconds=dur_secs,
                accuracy_weight=0.70,
                speed_weight=0.30,
            )
            await update_challenge_status(ch_id, "DRAFT")
            q_count = 0

        await query.edit_message_text(
            f"<b>Challenge #{ch_id} Configured! (Add Questions)</b>\n\n"
            f"<blockquote><b>{html.escape(title)}</b>\n"
            f"Category: {html.escape(category)}</blockquote>\n\n"
            f"{schedule_note}\n"
            f"• <b>Exam Time Limit:</b> <code>{exam_mins} minutes total</code>\n"
            f"• <b>Questions Attached:</b> <code>{q_count}</code>\n\n"
            f"<b>Next step: Attach questions to this challenge.</b>\n"
            f"Add them one-by-one or bulk import via CSV file below:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_questions_keyboard(ch_id, is_scheduled=is_scheduled),
        )

    elif data.startswith("adm_add_q_to_ch:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        context.user_data["target_ch_id"] = ch_id
        await set_user_state(user.id, f"WAITING_FOR_CHALLENGE_SINGLE_QUESTION:{ch_id}")
        await query.edit_message_text(
            f"<b>Add Question Specifically for Challenge #{ch_id} ({title})</b>\n\n"
            "Please send the question details in the following format:\n\n"
            "<code>What is Amazon DynamoDB?\n"
            "A: Relational database\n"
            "B: Key-value NoSQL database\n"
            "C: In-memory cache\n"
            "D: Object storage\n"
            "Answer: B\n"
            "Category: Database\n"
            "Difficulty: EASY\n"
            "Explanation: DynamoDB is a managed NoSQL key-value store</code>\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_import_csv_to_ch:"):
        try:
            await query.answer()
        except Exception:
            pass
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        context.user_data["target_ch_id"] = ch_id
        await set_user_state(user.id, f"WAITING_FOR_CHALLENGE_CSV:{ch_id}")
        await query.edit_message_text(
            f"<b>Import Questions for Challenge #{ch_id} ({title})</b>\n\n"
            "You can:\n"
            "1. <b>Paste raw CSV lines</b> directly as a message.\n"
            "2. Or <b>upload a .csv file</b> as a Telegram document.\n\n"
            "<b>Format:</b>\n"
            "<code>question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation</code>\n\n"
            "<i>Example:</i>\n"
            "<code>What is S3?,Object Storage,Block Storage,Compute,Database,A,EASY,Storage,10,S3 is scalable object storage</code>\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_view_ch_q:"):
        try:
            await query.answer()
        except Exception:
            pass
        parts = data.split(":")
        ch_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        questions = await get_challenge_questions(ch_id)
        if not questions:
            await query.edit_message_text(
                f"<b>Questions in Challenge #{ch_id} ({title})</b>\n\n"
                "<i>No questions attached to this challenge yet.</i>\n\n"
                "Tap <b>Add Question</b> or <b>Import CSV</b> below to add questions.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_challenge_questions_view_keyboard(ch_id, [], page=1),
            )
            return

        page_size = 4
        total_pages = max(1, math.ceil(len(questions) / page_size))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        page_q = questions[start_idx : start_idx + page_size]

        lines = [
            f"<b>Challenge #{ch_id} Questions</b> <i>(Page {page}/{total_pages} · {len(questions)} Total)</i>\n"
            f"<blockquote><b>{title}</b></blockquote>\n"
        ]

        for offset, q in enumerate(page_q):
            idx = start_idx + offset
            q_id = q.get("id", idx + 1)
            q_t = html.escape(q.get("question_text", "Untitled"))
            opt_a = html.escape(q.get("option_a", ""))
            opt_b = html.escape(q.get("option_b", ""))
            opt_c = html.escape(q.get("option_c", ""))
            opt_d = html.escape(q.get("option_d", ""))
            c_opt = q.get("correct_option", "A")
            cat = html.escape(q.get("category", "General"))
            diff = html.escape(q.get("difficulty", "MEDIUM"))
            pts = q.get("base_points", 10.0)
            exp = html.escape(q.get("explanation", "") or "No explanation provided.")

            lines.append(
                f"<b>Question {idx+1}</b> · <code>ID #{q_id}</code>\n"
                f"<b>{q_t}</b>\n\n"
                f"A. {opt_a}\n"
                f"B. {opt_b}\n"
                f"C. {opt_c}\n"
                f"D. {opt_d}\n\n"
                f"• <b>Correct Answer:</b> Option {c_opt}\n"
                f"• <b>Category:</b> {cat} | <b>Difficulty:</b> {diff} | <b>Points:</b> {pts} pts\n"
                f"• <b>Explanation:</b> {exp}\n"
            )

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_questions_view_keyboard(ch_id, questions, page=page, page_size=page_size),
        )

    elif data.startswith("adm_rm_ch_q:"):
        try:
            await query.answer()
        except Exception:
            pass
        parts = data.split(":")
        ch_id = int(parts[1])
        q_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

        await remove_question_from_challenge(ch_id, q_id)

        questions = await get_challenge_questions(ch_id)
        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        if not questions:
            await query.edit_message_text(
                f"<b>Questions in Challenge #{ch_id} ({title})</b>\n\n"
                "<i>No questions attached to this challenge yet.</i>\n\n"
                "Tap <b>Add Question</b> or <b>Import CSV</b> below to add questions.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_challenge_questions_view_keyboard(ch_id, [], page=1),
            )
            return

        page_size = 4
        total_pages = max(1, math.ceil(len(questions) / page_size))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        page_q = questions[start_idx : start_idx + page_size]

        lines = [
            f"<b>Challenge #{ch_id} Questions</b> <i>(Page {page}/{total_pages} · {len(questions)} Total)</i>\n"
            f"<blockquote><b>{title}</b></blockquote>\n"
        ]

        for offset, q in enumerate(page_q):
            idx = start_idx + offset
            qid = q.get("id", idx + 1)
            q_t = html.escape(q.get("question_text", "Untitled"))
            opt_a = html.escape(q.get("option_a", ""))
            opt_b = html.escape(q.get("option_b", ""))
            opt_c = html.escape(q.get("option_c", ""))
            opt_d = html.escape(q.get("option_d", ""))
            c_opt = q.get("correct_option", "A")
            cat = html.escape(q.get("category", "General"))
            diff = html.escape(q.get("difficulty", "MEDIUM"))
            pts = q.get("base_points", 10.0)
            exp = html.escape(q.get("explanation", "") or "No explanation provided.")

            lines.append(
                f"<b>Question {idx+1}</b> · <code>ID #{qid}</code>\n"
                f"<b>{q_t}</b>\n\n"
                f"A. {opt_a}\n"
                f"B. {opt_b}\n"
                f"C. {opt_c}\n"
                f"D. {opt_d}\n\n"
                f"• <b>Correct Answer:</b> Option {c_opt}\n"
                f"• <b>Category:</b> {cat} | <b>Difficulty:</b> {diff} | <b>Points:</b> {pts} pts\n"
                f"• <b>Explanation:</b> {exp}\n"
            )

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_questions_view_keyboard(ch_id, questions, page=page, page_size=page_size),
        )

    elif data.startswith("adm_pub:"):
        parts = data.split(":")
        ch_id = int(parts[1])
        pub_mode = parts[2] if len(parts) > 2 else "live"

        questions = await get_challenge_questions(ch_id)
        if not questions:
            action_desc = "scheduling" if pub_mode == "sched" else "going LIVE"
            try:
                await query.answer(f"Please attach at least 1 question before {action_desc}.", show_alert=True)
            except Exception:
                pass
            return

        from datetime import datetime, timezone, timedelta
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        ch = await get_challenge(ch_id)

        if pub_mode == "sched":
            try:
                await query.answer()
            except Exception:
                pass
            starts_dt = to_utc_datetime(ch.get("starts_at")) if ch else None
            if not starts_dt or starts_dt <= now_dt:
                starts_iso = (now_dt + timedelta(days=1)).isoformat()
                ends_iso = (now_dt + timedelta(days=8)).isoformat()
            else:
                starts_iso = ch.get("starts_at")
                ends_iso = ch.get("ends_at") or (starts_dt + timedelta(days=7)).isoformat()

            await update_challenge_details(ch_id, starts_at=starts_iso, ends_at=ends_iso)
            await update_challenge_status(ch_id, "SCHEDULED")

            await query.edit_message_text(
                f"<b>Challenge #{ch_id} Scheduled</b>\n\n"
                f"• <b>Questions Attached:</b> <code>{len(questions)}</code>\n"
                f"• <b>Opens:</b> <code>{format_datetime_12h(starts_iso)}</code>\n"
                f"• <b>Ends:</b> <code>{format_datetime_12h(ends_iso)}</code>\n\n"
                f"Challenge will automatically go LIVE at the scheduled opening time.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_challenge_manage_keyboard(ch_id, "SCHEDULED"),
            )
        else:
            try:
                await query.answer()
            except Exception:
                pass
            ends_dt = to_utc_datetime(ch.get("ends_at")) if ch else None
            if not ends_dt or ends_dt <= now_dt:
                end_iso = (now_dt + timedelta(days=7)).isoformat()
            else:
                end_iso = ch.get("ends_at")

            await update_challenge_details(ch_id, starts_at=now_iso, ends_at=end_iso)
            await update_challenge_status(ch_id, "LIVE")

            await query.edit_message_text(
                f"<b>Challenge #{ch_id} is now LIVE!</b>\n\n"
                f"• <b>Questions:</b> <code>{len(questions)}</code>\n"
                f"• <b>Starts:</b> <code>{format_datetime_12h(now_iso)}</code>\n"
                f"• <b>Ends:</b> <code>{format_datetime_12h(end_iso)}</code>\n\n"
                f"Community members can now participate using /challenge.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_challenge_manage_keyboard(ch_id, "LIVE"),
            )

    elif data.startswith("adm_end:"):
        ch_id = int(data.split(":")[1])
        try:
            await query.answer()
        except Exception:
            pass
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        await update_challenge_details(ch_id, ends_at=now_iso)
        await update_challenge_status(ch_id, "ENDED")
        await query.edit_message_text(
            f"<b>Challenge #{ch_id} has Ended</b>\n\n"
            f"Final leaderboard standings are now locked and review answers are available.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, "ENDED"),
        )

    elif data.startswith("adm_can:"):
        ch_id = int(data.split(":")[1])
        try:
            await query.answer()
        except Exception:
            pass
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        await update_challenge_details(ch_id, ends_at=now_iso)
        await update_challenge_status(ch_id, "CANCELLED")
        await query.edit_message_text(
            f"<b>Challenge #{ch_id} has been Cancelled</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, "CANCELLED"),
        )

    elif data == "adm_report":
        try:
            await query.answer()
        except Exception:
            pass

        rep = await get_monthly_analytics_report()
        month = rep["month_name"]
        users = rep["total_users"]
        challenges = rep["total_challenges"]
        attempts = rep["total_attempts"]
        total_score = rep["total_score"]
        avg_score = rep["avg_score"]
        accuracy = rep["accuracy_pct"]
        correct = rep["total_correct"]
        answered = rep["total_answered"]
        feedbacks = rep["feedback_count"]
        replies = rep["reply_count"]
        questions = rep["question_count"]
        champions = rep["champions"]

        champs_text = ""
        if champions:
            for idx, c in enumerate(champions[:3], 1):
                name = html.escape(c["user_name"])
                uname = f" (@{html.escape(c['username'])})" if c.get("username") else ""
                champs_text += f"• {idx}. <b>{name}</b>{uname} — <code>{c['total_score']} pts</code> ({c['challenges_completed']} quizzes)\n"
        else:
            champs_text = "• <i>No completed challenge attempts recorded yet this month.</i>\n"

        report_card = (
            f"<b>AWS Student Builder Monthly Activity Report</b>\n"
            f"<b>Period:</b> {month}\n\n"
            f"<b>Community Engagement:</b>\n"
            f"• Registered Bot Members: <code>{users}</code>\n"
            f"• Feedback Tickets Received: <code>{feedbacks}</code>\n"
            f"• Staff Replies Delivered: <code>{replies}</code>\n\n"
            f"<b>Challenges & Competitions:</b>\n"
            f"• Total Challenges: <code>{challenges}</code>\n"
            f"• Total Submissions: <code>{attempts}</code>\n"
            f"• Community Accuracy: <code>{accuracy}%</code> ({correct}/{answered})\n"
            f"• Average Score: <code>{avg_score} pts</code>\n"
            f"• Total Points Earned: <code>{total_score} pts</code>\n"
            f"• Active Questions in Bank: <code>{questions}</code>\n\n"
            f"<b>Top 3 Builders of the Month:</b>\n"
            f"{champs_text}\n"
            f"<i>AWS Student Builder Group · AASTU</i>"
        )
        await query.edit_message_text(
            report_card,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_report_keyboard(),
        )

    elif data == "adm_leaderboards":
        try:
            await query.answer()
        except Exception:
            pass
        active_ch = await get_active_challenge()
        active_ch_id = active_ch["id"] if active_ch else 0
        await query.edit_message_text(
            "<b>Admin Leaderboard & Builder Standings</b>\n\n"
            "View live participant scores, ranks, and monthly cumulative standings:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_leaderboard_keyboard(active_ch_id),
        )

    elif data.startswith("adm_lb_view:"):
        try:
            await query.answer()
        except Exception:
            pass
        parts = data.split(":")
        mode = parts[1]
        target_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

        if mode == "weekly" and target_id > 0:
            ch = await get_challenge(target_id)
            title = html.escape(ch["title"]) if ch else f"#{target_id}"
            lb_data = await get_weekly_leaderboard(target_id, limit=20)
            entries = lb_data["entries"]

            if not entries:
                text = (
                    f"<b>Active Challenge Leaderboard</b>\n"
                    f"<blockquote><b>{title}</b></blockquote>\n\n"
                    f"<i>No completed submissions yet.</i>"
                )
            else:
                lines = [
                    f"<b>Active Challenge Leaderboard</b>",
                    f"<blockquote><b>{title}</b></blockquote>\n",
                    f"• <b>Total Completed Participants:</b> <code>{lb_data['total_count']}</code>\n",
                ]
                for row in entries:
                    rank_str = f"<b>{row['rank']}.</b>"
                    name = html.escape(row["user_name"])
                    uname = f" (@{html.escape(row['username'])})" if row.get("username") else ""
                    uid = row["telegram_user_id"]
                    score = row["score"]
                    correct = row["correct_count"]
                    total = row["answered_count"]
                    lines.append(f"{rank_str} <b>{name}</b>{uname} [<code>{uid}</code>] — <b>{score} pts</b> ({correct}/{total} correct)")
                text = "\n".join(lines)
        else:
            lb_data = await get_monthly_leaderboard(limit=20)
            entries = lb_data["entries"]

            if not entries:
                text = (
                    "<b>Monthly Season Championship Standings</b>\n\n"
                    "<i>No completed challenge data recorded yet this season.</i>"
                )
            else:
                lines = [
                    "<b>Monthly Season Championship Standings</b>",
                    "<b>Top Builders of the Month</b>\n",
                    f"• <b>Total Ranked Builders:</b> <code>{lb_data['total_count']}</code>\n",
                ]
                for row in entries:
                    rank_str = f"<b>{row['rank']}.</b>"
                    name = html.escape(row["user_name"])
                    uname = f" (@{html.escape(row['username'])})" if row.get("username") else ""
                    uid = row["telegram_user_id"]
                    total_pts = row["total_score"]
                    completed = row["challenges_completed"]
                    lines.append(f"{rank_str} <b>{name}</b>{uname} [<code>{uid}</code>] — <b>{total_pts} pts</b> ({completed} quizzes)")
                text = "\n".join(lines)

        from telegram import InlineKeyboardMarkup
        back_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back to Leaderboards", callback_data="adm_leaderboards")],
            [InlineKeyboardButton("« Back to Admin", callback_data="adm_panel")],
        ])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb)

    elif data == "adm_broadcast":
        try:
            await query.answer()
        except Exception:
            pass
        users = await get_all_broadcast_user_ids()
        count = len(users)
        await query.edit_message_text(
            f"<b>Community Broadcast System</b>\n\n"
            f"Deliver an announcement notification to all registered bot participants.\n\n"
            f"• <b>Active Members in Reach:</b> <code>{count}</code>\n\n"
            f"Select a preset below or compose a custom message:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_broadcast_presets_keyboard(),
        )

    elif data == "adm_bcast_custom":
        try:
            await query.answer()
        except Exception:
            pass
        await set_user_state(user.id, "WAITING_FOR_ADMIN_BROADCAST")
        await query.edit_message_text(
            "<b>Custom Announcement Broadcast</b>\n\n"
            "Please type and send the announcement text now.\n\n"
            "• Supports HTML formatting (<b>bold</b>, <i>italic</i>, <code>code</code>)\n"
            "• Supports URLs and links\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data == "adm_bcast_preset:challenge":
        try:
            await query.answer()
        except Exception:
            pass
        active_ch = await get_active_challenge()
        users = await get_all_broadcast_user_ids()
        count = len(users)
        if not active_ch:
            await query.answer("No live or scheduled challenge found.", show_alert=True)
            return

        title = active_ch["title"]
        cat = active_ch["category"]
        time_l = active_ch["question_time_limit_seconds"]
        bcast_text = (
            f"<b>AWS Builder Challenge Announcement</b>\n\n"
            f"A cloud competition is active:\n"
            f"<b>{html.escape(title)}</b>\n"
            f"• <b>Category:</b> {html.escape(cat)}\n"
            f"• <b>Time Limit:</b> {time_l}s per question\n\n"
            f"Open /challenge in the bot now to take the quiz and climb the leaderboard.\n\n"
            f"@AWSAASTU"
        )
        context.user_data["bcast_text"] = bcast_text

        preview_text = (
            f"<b>BROADCAST PREVIEW</b>\n"
            f"• <b>Target Audience:</b> <code>{count}</code> members\n\n"
            f"<blockquote>{bcast_text}</blockquote>\n\n"
            f"Ready to deliver this notification?"
        )
        await query.edit_message_text(
            preview_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_broadcast_confirm_keyboard("preset_challenge"),
        )

    elif data == "adm_bcast_preset:leaderboard":
        try:
            await query.answer()
        except Exception:
            pass
        users = await get_all_broadcast_user_ids()
        count = len(users)
        bcast_text = (
            "<b>AWS Builder Championship Standings Updated</b>\n\n"
            "The Weekly & Monthly championship leaderboards are refreshed with latest scores.\n\n"
            "Check where you rank among student cloud builders.\n\n"
            "Send /leaderboard to view the rankings.\n\n"
            "@AWSAASTU"
        )
        context.user_data["bcast_text"] = bcast_text

        preview_text = (
            f"<b>BROADCAST PREVIEW</b>\n"
            f"• <b>Target Audience:</b> <code>{count}</code> members\n\n"
            f"<blockquote>{bcast_text}</blockquote>\n\n"
            f"Ready to deliver this notification?"
        )
        await query.edit_message_text(
            preview_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_broadcast_confirm_keyboard("preset_leaderboard"),
        )

    elif data == "adm_bcast_preset:report":
        try:
            await query.answer()
        except Exception:
            pass
        rep = await get_monthly_analytics_report()
        month = rep["month_name"]
        champions = rep["champions"]
        champs_text = ""
        if champions:
            for idx, c in enumerate(champions[:3], 1):
                name = html.escape(c["user_name"])
                uname = f" (@{html.escape(c['username'])})" if c.get("username") else ""
                champs_text += f"• {idx}. <b>{name}</b>{uname} — <code>{c['total_score']} pts</code>\n"
        else:
            champs_text = "• <i>Check /leaderboard for latest championship rankings!</i>\n"

        bcast_text = (
            f"<b>AWS SBG Monthly Season Wrap-Up ({month})</b>\n\n"
            f"Here is what our community achieved this month:\n\n"
            f"• <b>Active Members:</b> <code>{rep['total_users']}</code>\n"
            f"• <b>Challenges Completed:</b> <code>{rep['total_attempts']}</code>\n"
            f"• <b>Community Accuracy:</b> <code>{rep['accuracy_pct']}%</code>\n"
            f"• <b>Total Points Earned:</b> <code>{rep['total_score']} pts</code>\n\n"
            f"<b>Top 3 Builders of the Month:</b>\n"
            f"{champs_text}\n"
            f"Use /challenge and /leaderboard to participate in upcoming events.\n\n"
            f"@AWSAASTU"
        )
        context.user_data["bcast_text"] = bcast_text
        users = await get_all_broadcast_user_ids()
        preview_text = (
            f"<b>BROADCAST PREVIEW (Monthly Report)</b>\n"
            f"• <b>Target Audience:</b> <code>{len(users)}</code> members\n\n"
            f"<blockquote>{bcast_text}</blockquote>\n\n"
            f"Ready to deliver this report announcement to the community?"
        )
        await query.edit_message_text(
            preview_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_broadcast_confirm_keyboard("preset_report"),
        )

    elif data.startswith("adm_bcast_send:"):
        try:
            await query.answer()
        except Exception:
            pass
        bcast_text = context.user_data.get("bcast_text")
        if not bcast_text:
            await query.answer("No broadcast message prepared.", show_alert=True)
            return

        users = await get_all_broadcast_user_ids()
        logger.info(f"Initiating broadcast to {len(users)} registered users: {users}")

        if not users:
            await query.edit_message_text(
                "<b>No Registered Bot Members Found</b>\n\n"
                "Telegram requires members to send /start to the bot at least once before the bot can message them.\n\n"
                "Once members interact with the bot, they will be reachable via broadcast.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_panel_keyboard(),
            )
            return

        sent = 0
        failed = 0
        fail_reasons = []

        for uid in users:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=bcast_text,
                    parse_mode=ParseMode.HTML,
                )
                sent += 1
                logger.info(f"Broadcast delivered to user_id={uid}")
            except Exception as e:
                logger.warning(f"Broadcast send failed for user {uid}: {e}")
                failed += 1
                fail_reasons.append(f"• ID <code>{uid}</code>: {html.escape(str(e))}")

        context.user_data.pop("bcast_text", None)

        err_block = ""
        if fail_reasons:
            preview_errs = "\n".join(fail_reasons[:3])
            err_block = f"\n\n<b>Delivery Issues ({failed}):</b>\n{preview_errs}"

        await query.edit_message_text(
            f"<b>Broadcast Complete</b>\n\n"
            f"• <b>Delivered Successfully:</b> <code>{sent}</code> members\n"
            f"• <b>Failed / Blocked:</b> <code>{failed}</code>{err_block}\n\n"
            f"The announcement has been broadcast to all reachable community members.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard(),
        )


async def handle_admin_csv_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes uploaded CSV/TSV document files to bulk-import questions into challenges or question bank."""
    if not update.message or not update.message.document:
        return

    user = update.effective_user
    chat = update.effective_chat
    if not user or not await is_admin_user(user.id, chat.id if chat else None, context.bot):
        return

    doc = update.message.document
    filename = (doc.file_name or "").lower()
    mime = (doc.mime_type or "").lower()
    is_csv_like = (
        filename.endswith((".csv", ".txt", ".tsv", ".tab"))
        or "csv" in mime
        or "text" in mime
        or "tab-separated" in mime
        or "comma-separated" in mime
    )
    if not is_csv_like:
        await update.message.reply_text(
            "<b>Unsupported file format.</b>\nPlease upload a <b>.csv</b>, <b>.tsv</b>, or <b>.txt</b> file.",
            parse_mode=ParseMode.HTML,
        )
        return

    if context.bot and update.effective_chat:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        except Exception:
            pass

    loading_msg = None
    try:
        loading_msg = await update.message.reply_text(
            "<b>Processing CSV Document...</b>\n<i>Downloading, parsing headers, and validating question bank entries...</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()
    try:
        csv_text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_text = file_bytes.decode("latin-1")
        except Exception:
            csv_text = file_bytes.decode("utf-8", errors="replace")

    # Resolve target challenge ID: in-memory user_data -> persistent DB user_state -> active challenge
    target_ch_id = context.user_data.get("target_ch_id")
    if not target_ch_id:
        user_state = await get_user_state(user.id)
        if user_state and user_state.startswith("WAITING_FOR_CHALLENGE_CSV:"):
            try:
                target_ch_id = int(user_state.split(":")[1])
            except Exception:
                target_ch_id = None

    if not target_ch_id:
        # Fallback: check if there's an active or latest challenge
        active_ch = await get_active_challenge()
        if active_ch:
            target_ch_id = active_ch["id"]

    await set_user_state(user.id, None)

    if target_ch_id:
        result = await import_questions_for_challenge(target_ch_id, csv_text)
        imported = result["imported"]
        errors = result["errors"]

        err_text = ""
        if errors:
            err_list = "\n".join(errors[:5])
            err_text = f"\n\n<b>Errors Encountered ({len(errors)}):</b>\n{html.escape(err_list)}"

        ch = await get_challenge(target_ch_id)
        ch_status = ch["status"] if ch else "DRAFT"
        ch_questions = await get_challenge_questions(target_ch_id)

        if imported > 0:
            final_text = (
                f"<b>CSV Import Complete for Challenge #{target_ch_id}</b>\n\n"
                f"• <b>Successfully Linked:</b> <code>{imported}</code> questions to this challenge.\n"
                f"• <b>Total Attached Questions:</b> <code>{len(ch_questions)}</code>{err_text}"
            )
            markup = get_challenge_manage_keyboard(target_ch_id, ch_status)
        else:
            final_text = (
                f"<b>No valid questions could be imported.</b>{err_text}\n\n"
                f"Please ensure your CSV contains headers like:\n"
                f"<code>question,option_a,option_b,option_c,option_d,correct_option,explanation</code>"
            )
            markup = get_challenge_manage_keyboard(target_ch_id, ch_status)

        if loading_msg:
            try:
                await loading_msg.edit_text(final_text, parse_mode=ParseMode.HTML, reply_markup=markup)
                return
            except Exception:
                pass
        await update.message.reply_text(final_text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        result = await import_questions_from_csv(csv_text)
        imported = result["imported"]
        errors = result["errors"]

        err_text = ""
        if errors:
            err_list = "\n".join(errors[:5])
            err_text = f"\n\n<b>Errors Encountered ({len(errors)}):</b>\n{html.escape(err_list)}"

        if imported > 0:
            final_text = (
                f"<b>CSV Import Complete</b>\n\n"
                f"• <b>Successfully Imported:</b> <code>{imported}</code> questions into Question Bank{err_text}"
            )
            markup = get_admin_panel_keyboard()
        else:
            final_text = (
                f"<b>No valid questions could be imported.</b>{err_text}\n\n"
                f"Please ensure your CSV follows the standard question structure."
            )
            markup = get_admin_panel_keyboard()

        if loading_msg:
            try:
                await loading_msg.edit_text(final_text, parse_mode=ParseMode.HTML, reply_markup=markup)
                return
            except Exception:
                pass
        await update.message.reply_text(final_text, parse_mode=ParseMode.HTML, reply_markup=markup)
