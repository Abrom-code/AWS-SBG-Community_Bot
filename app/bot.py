from __future__ import annotations

import asyncio
import html
import os
import logging
from typing import Optional, Any, Dict, List, Set
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    BotCommand,
    MenuButtonCommands,
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    ContextTypes,
)
from dotenv import load_dotenv

from app.db import (
    get_user_state,
    set_user_state,
    save_feedback_submission,
    get_feedback_submission,
    get_feedback_submission_by_user_message,
    delete_feedback_submission,
    save_admin_reply_mapping,
    get_admin_reply_mapping,
    get_all_broadcast_user_ids,
    register_or_update_bot_user,
)
from app.community import (
    about_command as comm_about_command,
    education_command,
    events_command,
    challenge_paused_command,
    handle_community_callback,
    get_support_info_text,
)
from app.challenge.handlers import (
    challenge_command,
    leaderboard_command,
    scoring_rules_command,
    guidelines_command,
    past_challenges_command,
    handle_challenge_start_callback,
    handle_challenge_answer_callback,
    handle_challenge_nav_callback,
    handle_leaderboard_callback,
    handle_challenge_rules_callback,
    handle_guidelines_callback,
    handle_past_challenges_callback,
    handle_challenge_review_callback,
    handle_challenge_select_callback,
    handle_challenge_nav_active_callback,
    handle_scheduled_challenge_info_callback,
    handle_challenge_refresh_callback,
)
from app.challenge.service import (
    create_challenge,
    get_challenge,
    link_questions_to_challenge,
    update_challenge_status,
    update_challenge_details,
    create_question,
    import_questions_from_csv,
    parse_single_question_text,
    add_question_to_challenge,
    import_questions_for_challenge,
    get_challenge_questions,
    get_monthly_analytics_report,
    list_challenges,
    get_active_challenge,
    format_datetime_12h,
    LOCAL_TZ,
    BOT_TIMEZONE_NAME,
)
from app.challenge.keyboards import (
    get_challenge_hub_inline_keyboard,
    get_admin_broadcast_confirm_keyboard,
    get_challenge_manage_keyboard,
    get_admin_schedule_presets_keyboard,
    get_wizard_questions_keyboard,
    get_wizard_skip_desc_keyboard,
    get_wizard_timer_keyboard,
    get_question_bank_actions_keyboard,
    get_admin_menu_keyboard,
    get_admin_panel_keyboard,
    get_admin_report_keyboard,
    get_admin_broadcast_presets_keyboard,
    get_admin_leaderboard_keyboard,
)
from app.challenge.admin import (
    admin_command,
    handle_admin_callback,
    handle_admin_csv_document,
    is_admin_user,
)
from datetime import datetime, timezone, timedelta

# Load environment variables from .env file
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
ADMIN_GROUP_CHAT_ID = int(os.getenv("ADMIN_GROUP_CHAT_ID", "0"))
ADMIN_GROUP_ID = ADMIN_GROUP_CHAT_ID

# Enable logging to track activity and debug issues
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# State constants
WAITING_FOR_FEEDBACK = "WAITING_FOR_FEEDBACK"
WAITING_FOR_QUESTION = "WAITING_FOR_QUESTION"


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns persistent bottom menu buttons for primary member actions."""
    return ReplyKeyboardMarkup(
        [
            ["Education", "Next Event"],
            ["Ask Question", "Feedback"],
            ["About Us", "Help"],
        ],
        resize_keyboard=True,
    )


def get_challenge_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns persistent sub-menu keyboard for the Challenge Center."""
    return ReplyKeyboardMarkup(
        [
            ["Leaderboards", "Past Challenges"],
            ["Scoring Rules", "Guidelines"],
            ["Main Menu"],
        ],
        resize_keyboard=True,
    )


def get_feedback_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns persistent sub-menu keyboard for Feedback & Support."""
    return ReplyKeyboardMarkup(
        [
            ["Ask Question", "Feedback"],
            ["About Support", "Main Menu"],
        ],
        resize_keyboard=True,
    )


def clear_proxy_environment():
    """Disables inherited proxy environment variables that can block Telegram API access."""
    for key in list(os.environ):
        if "proxy" in key.lower():
            os.environ.pop(key, None)

    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message with the bot logo and a persistent keyboard option."""
    user = update.effective_user
    chat = update.effective_chat
    if user:
        await register_or_update_bot_user(user.id, user.first_name, user.username)

    welcome_text = (
        "<b>AWS SBG AASTU Community Bot</b>\n\n"
        "Welcome! Learn cloud computing, follow our structured tracks, and stay up to date with events.\n\n"
        "• Education — Track schedules, syllabus, and class times\n"
        "• Next Event — Upcoming workshops, bootcamps, and meetups\n"
        "• Ask Question — Message our technical leads and mentors\n"
        "• Feedback — Share suggestions with the team\n"
        "• About Us — Mission, leads, and community info\n\n"
        "<b>Join our community:</b> @AWSAASTU\n\n"
        "<i>Select an option below to get started:</i>"
    )

    logo_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets",
        "logo.jpg",
    )

    chat_id = chat.id if chat else (user.id if user else None)
    if not chat_id:
        return

    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as photo:
                if update.message:
                    try:
                        await update.message.reply_photo(
                            photo=photo,
                            caption=welcome_text,
                            parse_mode=ParseMode.HTML,
                            reply_markup=get_main_menu_keyboard(),
                        )
                        return
                    except Exception:
                        pass
                if context.bot:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=welcome_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_main_menu_keyboard(),
                    )
                    return
        except Exception as e:
            logger.error(f"Failed to send logo photo: {e}")

    if update.message:
        try:
            await update.message.reply_text(
                welcome_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
            return
        except Exception:
            pass

    if context.bot:
        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )


async def challenge_hub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gracefully informs members that challenges are currently paused in favor of the Education Track."""
    return await challenge_paused_command(update, context)


async def send_response(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    """Safely responds to either a direct message update or a callback query."""
    target_msg = update.effective_message or update.message
    if target_msg:
        return await target_msg.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    elif update.effective_chat and context.bot:
        return await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


async def feedback_hub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the Feedback & Support hub with dedicated sub-menu."""
    if context.bot and update.effective_chat:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        except Exception:
            pass
    hub_text = (
        "<b>Feedback & Community Support Hub</b>\n\n"
        "How can the AWS Student Builder team help you?\n\n"
        "• Ask Question — Get help with the Education Track, labs, or cloud concepts\n"
        "• Feedback — Share ideas, suggestions, or topics you want covered\n"
        "• About Support — Learn how our leadership team responds\n\n"
        "<i>Select an option below:</i>"
    )
    await send_response(
        update,
        context,
        hub_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_feedback_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the available visible commands for members."""
    help_text = (
        "✦ <b>Available Commands</b>\n\n"
        "/start — Main menu & dashboard\n"
        "/education — Education tracks & schedule\n"
        "/events — Next event & live sessions\n"
        "/about — About AWS SBG AASTU\n"
        "/ask — Ask a question to mentors & leads\n"
        "/feedback — Share community feedback\n"
        "/help — This command guide\n\n"
        "<i>Or use the menu buttons below to navigate.</i>"
    )
    await send_response(
        update,
        context,
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(),
    )


async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explains notification preferences and active broadcast status."""
    await send_response(
        update,
        context,
        "<b>Community Notifications</b>\n\n"
        "You are subscribed to real-time AWS Student Builder updates:\n\n"
        "• <b>Education Track:</b> Session schedules, lab walk-throughs, and recordings\n"
        "• <b>Community Announcements:</b> Workshops, webinars, bootcamps, and hackathons\n"
        "• <b>Direct Support:</b> Real-time replies from the core team\n\n"
        "<i>All notifications are delivered directly to this chat. Keep notifications unmuted to never miss an update!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(),
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides details about the bot and community group."""
    return await comm_about_command(update, context)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct command for administrators to broadcast an announcement to all registered members."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await is_admin_user(user.id, chat.id if chat else None, context.bot):
        await send_response(
            update,
            context,
            "<b>Access Denied:</b> This command is restricted to AWS SBG administrators.",
            parse_mode=ParseMode.HTML,
        )
        return

    users = await get_all_broadcast_user_ids()
    count = len(users)
    await set_user_state(user.id, "WAITING_FOR_ADMIN_BROADCAST")
    await send_response(
        update,
        context,
        f"✦ <b>Community Broadcast Center</b>\n\n"
        f"• <b>Active Reach:</b> <code>{count}</code> registered members\n\n"
        f"Please type, paste, or send the announcement message you wish to broadcast.\n\n"
        f"• Supports HTML formatting (<b>bold</b>, <i>italic</i>, <code>code</code>, links)\n"
        f"• You can also send a photo with a caption\n"
        f"• Send directly as a message in this chat\n\n"
        f"<i>(Type /cancel to abort)</i>",
        parse_mode=ParseMode.HTML,
    )


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates member feedback / suggestions workflow."""
    user = update.effective_user
    user_id = user.id if user else 0
    await set_user_state(user_id, WAITING_FOR_FEEDBACK)

    await send_response(
        update,
        context,
        "✦ <b>Submit Feedback & Suggestions</b>\n\n"
        "We'd love to hear your thoughts, ideas, or suggestions for our AWS community!\n\n"
        "Please type your message below:\n\n"
        "➤ <i>(Type /cancel if you change your mind)</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates member question / support workflow."""
    user = update.effective_user
    user_id = user.id if user else 0
    await set_user_state(user_id, WAITING_FOR_QUESTION)

    await send_response(
        update,
        context,
        "✦ <b>Ask a Question / Support</b>\n\n"
        "Have a question about the Education Track, workshops, AWS certification, or need technical help?\n\n"
        "Please type your question below:\n\n"
        "➤ <i>(Type /cancel if you change your mind)</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the current feedback, question, or broadcast session and returns to the main menu."""
    user = update.effective_user
    user_id = user.id if user else 0
    current_state = await get_user_state(user_id)
    if current_state == WAITING_FOR_FEEDBACK:
        await set_user_state(user_id, None)
        await send_response(
            update,
            context,
            "▪️ Feedback submission cancelled.",
            reply_markup=get_main_menu_keyboard(),
        )
    elif current_state in (WAITING_FOR_QUESTION, "WAITING_FOR_SUPPORT"):
        await set_user_state(user_id, None)
        await send_response(
            update,
            context,
            "▪️ Question submission cancelled.",
            reply_markup=get_main_menu_keyboard(),
        )
    elif current_state == "WAITING_FOR_ADMIN_BROADCAST":
        await set_user_state(user_id, None)
        context.user_data.pop("bcast_text", None)
        context.user_data.pop("bcast_photo", None)
        await send_response(
            update,
            context,
            "▪️ Broadcast cancelled.",
            reply_markup=get_main_menu_keyboard(),
        )
    elif current_state == "WAITING_FOR_ADMIN_UPDATE_EDU":
        await set_user_state(user_id, None)
        context.user_data.pop("staged_edu", None)
        await send_response(
            update,
            context,
            "▪️ Education Track update cancelled.",
            reply_markup=get_admin_menu_keyboard(),
        )
    elif current_state == "WAITING_FOR_ADMIN_NEW_TRACK":
        await set_user_state(user_id, None)
        context.user_data.pop("staged_new_track", None)
        await send_response(
            update,
            context,
            "▪️ Adding new Education Track cancelled.",
            reply_markup=get_admin_menu_keyboard(),
        )
    elif current_state and current_state.startswith("WAITING_FOR_ADMIN_EDIT_TRACK"):
        await set_user_state(user_id, None)
        for k in list(context.user_data.keys()):
            if k.startswith("staged_edit_track:"):
                context.user_data.pop(k, None)
        await send_response(
            update,
            context,
            "▪️ Education Track editing cancelled.",
            reply_markup=get_admin_menu_keyboard(),
        )
    elif current_state == "WAITING_FOR_ADMIN_UPDATE_EVENT":
        await set_user_state(user_id, None)
        context.user_data.pop("staged_event", None)
        await send_response(
            update,
            context,
            "▪️ Next Event update cancelled.",
            reply_markup=get_admin_menu_keyboard(),
        )
    elif current_state and any(current_state.startswith(s) for s in (
        "WAITING_FOR_ADMIN_SCHEDULE",
        "WAITING_FOR_CHALLENGE_TITLE",
        "WAITING_FOR_CHALLENGE_DESC",
        "WAITING_FOR_CHALLENGE_TIMER",
        "WAITING_FOR_CHALLENGE_CUSTOM_CAT",
        "WAITING_FOR_EDIT_CHALLENGE_TITLE",
        "WAITING_FOR_EDIT_CHALLENGE_SCHEDULE",
        "WAITING_FOR_EDIT_CHALLENGE_TIMER",
        "WAITING_FOR_ADMIN_SINGLE_QUESTION",
        "WAITING_FOR_ADMIN_CSV",
        "WAITING_FOR_CHALLENGE_SINGLE_QUESTION",
        "WAITING_FOR_CHALLENGE_CSV",
    )):
        await set_user_state(user_id, None)
        context.user_data.pop("target_ch_id", None)
        context.user_data.pop("edit_ch_id", None)
        await send_response(
            update,
            context,
            "▪️ Operation cancelled.",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await send_response(
            update,
            context,
            "✦ <b>Main Menu</b>\n\nChoose an option below:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes text and photo messages based on the user's current state and sub-menu navigation."""
    if not update.message or (not update.message.text and not getattr(update.message, "photo", None)):
        return

    try:
        await _handle_message_inner(update, context)
    except Exception as exc:
        logger.exception("Unhandled error in handle_message: %s", exc)
        try:
            await update.message.reply_text(
                f"⚠️ An unexpected error occurred. Please try again.\n\n<code>{html.escape(str(exc)[:500])}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


async def _handle_message_inner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inner handler that does the actual work. Exceptions bubble up to handle_message."""
    photo_id = update.message.photo[-1].file_id if getattr(update.message, "photo", None) else None

    # Extract text or caption, preserving rich formatting (HTML / entities)
    if getattr(update.message, "caption", None):
        text = update.message.caption_html if getattr(update.message, "caption_entities", None) else update.message.caption
    elif getattr(update.message, "text", None):
        text = update.message.text_html if getattr(update.message, "entities", None) else update.message.text
    else:
        text = ""

    user = update.effective_user
    user_id = user.id
    if user:
        await register_or_update_bot_user(user.id, user.first_name, user.username)

    # Handle Top-Level Navigation
    if text in (
        "Feedback", "🔹 Feedback", "📝 Feedback", "Submit Feedback", "🔹 Submit Feedback",
        "📝 Submit Feedback", "💬 Feedback", "💬 Submit Feedback", "Submit New Feedback"
    ):
        return await feedback_command(update, context)
    elif text in (
        "Ask Question", "🔹 Ask Question", "❓ Ask Question", "Ask a Question", "❓ Ask a Question",
        "Support", "💬 Support", "Helpdesk", "Question", "Questions", "Ask",
        "Ask Support", "❓ Ask", "💬 Ask Question"
    ):
        return await support_command(update, context)
    elif text in ("Feedback & Support", "💬 Feedback & Support"):
        return await feedback_hub_command(update, context)
    elif text in ("Education Track", "🔹 Education Track", "📚 Education Track", "Education", "Track", "Curriculum"):
        return await education_command(update, context)
    elif text in ("Next Event", "🔹 Next Event", "📅 Next Event", "Events", "Upcoming Events", "Programs", "Event"):
        return await events_command(update, context)
    elif text in ("About", "About Us", "▫️ About Us", "ℹ️ About Us", "ℹ️ About", "About Support", "▫️ About Support", "ℹ️ About Support"):
        if text in ("About Support", "▫️ About Support", "ℹ️ About Support"):
            return await update.message.reply_text(
                get_support_info_text(),
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
        return await about_command(update, context)
    elif text in ("Help", "▫️ Help", "❓ Help"):
        return await help_command(update, context)
    elif text in ("Main Menu", "▫️ Main Menu", "🔙 Main Menu", "❌ Cancel", "▪️ Cancel", "Cancel", "Menu"):
        return await cancel_command(update, context)

    # Paused Challenge Navigation (Graceful Fallback)
    elif text in (
        "Challenges", "⚡ Challenges", "⚡ Challenge Center", "Challenge Center", "Challenge",
        "Take Challenge", "Active Challenge", "🚀 Take Active Challenge", "🚀 Start Challenge",
        "Start Challenge", "Take Active Challenge", "Leaderboards", "Leaderboard",
        "🏆 Leaderboards", "🏆 Leaderboard", "Past Challenges", "Archive",
        "📚 Past Challenges", "📚 Archive", "📚 Past Quizzes", "Past Quizzes",
        "Scoring Rules", "Scoring & Rules", "Rules", "📖 Scoring & Rules",
        "📖 Rules", "ℹ️ Scoring Rules", "📖 How Scoring Works", "How Scoring Works",
        "Guidelines", "Community Guidelines", "🛡️ Community Guidelines", "🛡️ Guidelines", "Code of Conduct"
    ):
        return await challenge_paused_command(update, context)

    # Handle Admin Bottom Navigation Buttons
    chat_id = update.effective_chat.id if update.effective_chat else None
    if await is_admin_user(user_id, chat_id, context.bot):
        if text in ("Create Challenge", "➕ Create Challenge", "➕ Create New Challenge", "Create New Challenge"):
            await set_user_state(user_id, "WAITING_FOR_CHALLENGE_TITLE")
            await update.message.reply_text(
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
            return
        elif text in ("Manage Challenges", "📋 Manage Challenges", "📋 Challenge List", "Challenge List"):
            challenges = await list_challenges(limit=10)
            if not challenges:
                await update.message.reply_text(
                    "<b>Challenge Management</b>\n\n<i>No challenges found. Create one first.</i>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_admin_panel_keyboard(),
                )
            else:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                buttons = []
                for ch in challenges:
                    status = ch["status"]
                    title = ch["title"]
                    buttons.append([InlineKeyboardButton(f"#{ch['id']} {title[:24]} [{status}]", callback_data=f"adm_manage:{ch['id']}")])
                buttons.append([InlineKeyboardButton("« Back to Admin", callback_data="adm_panel")])
                await update.message.reply_text(
                    "<b>Challenge Management</b>\n\nSelect a challenge below to manage:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            return
        elif text in ("Leaderboards", "🏆 Leaderboards", "Admin Leaderboards"):
            active_ch = await get_active_challenge()
            active_ch_id = active_ch["id"] if active_ch else 0
            await update.message.reply_text(
                "<b>Admin Leaderboard & Builder Standings</b>\n\n"
                "View live participant scores, ranks, and monthly cumulative standings:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_leaderboard_keyboard(active_ch_id),
            )
            return
        elif text in ("Monthly Report", "📊 Monthly Report", "📊 Analytics Report", "Analytics Report"):
            rep = await get_monthly_analytics_report()
            champions = rep.get("champions", [])
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
                f"<b>Period:</b> {rep['month_name']}\n\n"
                f"<b>Community Engagement</b>\n"
                f"• Registered Members: <code>{rep['total_users']}</code>\n"
                f"• Feedback Tickets: <code>{rep['feedback_count']}</code>\n"
                f"• Staff Replies: <code>{rep['reply_count']}</code>\n\n"
                f"<b>Challenges & Quizzes</b>\n"
                f"• Quizzes Hosted: <code>{rep['total_challenges']}</code>\n"
                f"• Submissions: <code>{rep['total_attempts']}</code>\n"
                f"• Accuracy: <code>{rep['accuracy_pct']}%</code>\n"
                f"• Average Score: <code>{rep['avg_score']} pts</code>\n"
                f"• Points Awarded: <code>{rep['total_score']} pts</code>\n\n"
                f"<b>Top 3 Builders</b>\n"
                f"{champs_text}"
            )
            await update.message.reply_text(
                report_card,
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_report_keyboard(),
            )
            return
        elif text in ("Manage Education Track", "🔹 Manage Education Track", "Manage Education"):
            from app.challenge.admin import render_admin_edu_dashboard_text
            from app.challenge.keyboards import get_admin_edu_manage_keyboard
            from app.db import list_education_tracks, seed_default_education_tracks_if_empty
            await seed_default_education_tracks_if_empty()
            tracks = await list_education_tracks(active_only=False)
            dashboard_text = await render_admin_edu_dashboard_text()
            return await update.message.reply_text(
                dashboard_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_edu_manage_keyboard(tracks),
            )
        elif text in ("Manage Next Event", "🔹 Manage Next Event", "Manage Event"):
            from app.challenge.admin import render_admin_event_dashboard_text
            from app.challenge.keyboards import get_admin_event_manage_keyboard
            dashboard_text = await render_admin_event_dashboard_text()
            return await update.message.reply_text(
                dashboard_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_event_manage_keyboard(),
            )
        elif text in ("Broadcast", "Broadcast Notification", "📢 Broadcast Notification", "📢 Broadcast", "📢 Broadcast Announcement", "🔹 Broadcast Announcement", "🔹 Broadcast", "Send Broadcast"):
            return await broadcast_command(update, context)
        elif text in ("Community Stats", "📊 Community Stats", "Stats", "📊 Stats", "▫️ Community Stats", "🔹 Community Stats"):
            from app.challenge.admin import get_configured_admin_ids
            from app.db import is_postgres
            users = await get_all_broadcast_user_ids()
            count = len(users)
            admin_count = len(get_configured_admin_ids())
            db_mode = "PostgreSQL (Supabase Pool)" if is_postgres() else "Local SQLite (bot.db)"
            return await update.message.reply_text(
                "✦ <b>AWS SBG Community Statistics</b>\n\n"
                f"• <b>Registered Members Reach:</b> <code>{count}</code>\n"
                f"• <b>Configured Administrators:</b> <code>{admin_count}</code>\n"
                f"• <b>Database Mode:</b> <code>{db_mode}</code>\n"
                f"• <b>Bot Status:</b> <code>Active & Live</code>\n\n"
                f"All registered members are reachable via broadcast announcements.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_menu_keyboard(),
            )
        elif text in ("Support Info", "💬 Support Info", "▫️ Support Info", "🔹 Support Info"):
            return await update.message.reply_text(
                get_support_info_text(),
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_menu_keyboard(),
            )
        elif text in ("Exit Admin", "🚪 Exit Admin", "🚪 Leave Admin", "Leave Admin", "▪️ Exit Admin"):
            await update.message.reply_text(
                "<b>Exited Admin Panel</b>\n\nReturning to member menu:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
            return

    # Check user state first before running any loose message shortcuts
    current_state = await get_user_state(user_id)

    # Power-User Direct Challenge Creation Shortcut
    # Only valid when not in another active conversation state (like broadcast, track edit, feedback, support)
    # and text is concise and formatted specifically as a single-line challenge shortcut
    raw = text.strip()
    parts = [p.strip() for p in raw.split("|")]
    chat_id = update.effective_chat.id if update.effective_chat else None

    is_concise_shortcut = (
        len(parts) in (3, 4)
        and raw.count("\n") <= 1
        and len(raw) <= 250
        and len(parts[0]) <= 80
    )

    if (
        is_concise_shortcut
        and current_state in (None, "WAITING_FOR_CHALLENGE_TITLE")
        and await is_admin_user(user_id, chat_id, context.bot)
    ):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        duration_mins = 10
        category = "Architecture"
        description = "Weekly timed AWS challenge on core compute, storage, and cloud architecture (70% accuracy + 30% speed bonus)."
        title = parts[0]

        def _parse_dur(val: str) -> Optional[int]:
            cleaned = val.lower().replace("minutes", "").replace("minute", "").replace("mins", "").replace("min", "").replace("m", "").strip()
            return int(cleaned) if cleaned.isdigit() else None

        if len(parts) >= 4:
            # Format: Title | Category | Description | Duration
            category = parts[1] or "Architecture"
            description = parts[2] or description
            duration_mins = _parse_dur(parts[3]) or 10
        elif len(parts) == 3:
            # Format: Title | Description | Duration  OR  Title | Category | Description
            dur = _parse_dur(parts[2])
            if dur is not None:
                # Power user: Title | Description | Duration
                description = parts[1] or description
                duration_mins = dur
            else:
                # Power user: Title | Category | Description
                category = parts[1] or "Architecture"
                description = parts[2] or description

        duration_mins = max(1, min(300, duration_mins))

        try:
            ch_id = await create_challenge(
                title=title,
                description=description,
                category=category,
                starts_at=None,
                ends_at=None,
                question_time_limit_seconds=60,
                duration_seconds=duration_mins * 60,
                accuracy_weight=0.70,
                speed_weight=0.30,
                created_by=user_id,
            )

            context.user_data["wiz_ch_id"] = ch_id
            context.user_data["wiz_title"] = title
            context.user_data["wiz_category"] = category
            context.user_data["wiz_description"] = description
            context.user_data["wiz_duration_mins"] = duration_mins

            await set_user_state(user_id, f"WAITING_FOR_EDIT_CHALLENGE_SCHEDULE:{ch_id}")

            await update.message.reply_text(
                f"<b>Create Challenge Wizard (Step 4/4: Schedule & Start/End Time)</b>\n\n"
                f"<blockquote><b>{html.escape(title)}</b>\n"
                f"Category: {html.escape(category)}\n"
                f"<i>{html.escape(description)}</i></blockquote>\n\n"
                f"• <b>Exam Time Limit:</b> <code>{duration_mins} Minutes</code>\n\n"
                f"Select start schedule & deadline (or type custom start & end dates in EAT):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_schedule_presets_keyboard(ch_id, duration_mins),
            )
        except Exception as exc:
            logger.exception("Failed to create challenge via shortcut: %s", exc)
            await update.message.reply_text(
                f"⚠️ <b>Failed to create challenge:</b> {html.escape(str(exc))}\n\nPlease try again or use the step-by-step wizard.",
                parse_mode=ParseMode.HTML,
            )
        return

    # Check if admin is entering challenge title (Wizard Step 1/4)
    if current_state == "WAITING_FOR_CHALLENGE_TITLE":
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            await update.message.reply_text(
                "⛔ <b>Access Denied:</b> This action requires administrator permissions.",
                parse_mode=ParseMode.HTML,
            )
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        raw = text.strip()
        parts = [p.strip() for p in raw.split("|")]

        # Step-by-Step Flow: (1 part: Title  OR  2 parts: Title | Category)
        if len(parts) == 2:
            title = parts[0]
            # Check if second part was duration (e.g. Title | 15) or category
            def _parse_dur_single(val: str) -> Optional[int]:
                cleaned = val.lower().replace("minutes", "").replace("minute", "").replace("mins", "").replace("min", "").replace("m", "").strip()
                return int(cleaned) if cleaned.isdigit() else None

            dur = _parse_dur_single(parts[1])
            if dur is not None:
                category = "Architecture"
                duration_mins = dur
            else:
                category = parts[1] or "Architecture"
                duration_mins = 10
        else:
            title = raw
            category = "Architecture"
            duration_mins = 10

        description = "Weekly timed AWS challenge on core compute, storage, and cloud architecture (70% accuracy + 30% speed bonus)."

        ch_id = await create_challenge(
            title=title,
            description=description,
            category=category,
            starts_at=None,
            ends_at=None,
            question_time_limit_seconds=60,
            duration_seconds=duration_mins * 60,
            accuracy_weight=0.70,
            speed_weight=0.30,
            created_by=user_id,
        )

        context.user_data["wiz_title"] = title
        context.user_data["wiz_category"] = category
        context.user_data["wiz_duration_mins"] = duration_mins

        await set_user_state(user_id, f"WAITING_FOR_CHALLENGE_DESC:{ch_id}")
        await update.message.reply_text(
            f"<b>Create Challenge Wizard (Step 2/4: Description)</b>\n\n"
            f"• <b>Title:</b> <b>{html.escape(title)}</b>\n"
            f"• <b>Category:</b> <code>{html.escape(category)}</code>\n\n"
            f"Please enter the challenge description:\n"
            f"<i>(Explain what community members will learn or test in this challenge)</i>\n\n"
            f"<i>Example:</i> <code>Master EC2, S3, VPC, Lambda, and high-availability design patterns in this weekly challenge.</code>\n\n"
            f"<i>(Or tap below to use default description or change category)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_skip_desc_keyboard(ch_id),
        )
        return

    # Check if admin is entering challenge description (Wizard Step 2/4)
    if current_state and current_state.startswith("WAITING_FOR_CHALLENGE_DESC"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await set_user_state(user_id, None)
        parts = current_state.split(":")
        ch_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else context.user_data.get("wiz_ch_id")
        if not ch_id:
            await update.message.reply_text("No active challenge creation session.", reply_markup=get_main_menu_keyboard())
            return

        desc = text.strip()
        await update_challenge_details(ch_id, description=desc)
        ch = await get_challenge(ch_id)
        title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"
        dur_secs = ch.get("duration_seconds") or 600 if ch else 600
        dur_mins = int(dur_secs // 60)

        await update.message.reply_text(
            f"<b>Create Challenge Wizard (Step 3/4: Exam Time Limit)</b>\n\n"
            f"<blockquote><b>{html.escape(title)}</b>\n"
            f"Category: {html.escape(ch.get('category', 'Architecture'))}\n"
            f"<i>{html.escape(desc)}</i></blockquote>\n\n"
            f"Select the allowed exam time for community members:\n"
            f"<i>(Timer begins when participant starts the challenge)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_timer_keyboard(ch_id),
        )
        return

    # Check if admin is entering custom category in wizard
    if current_state and current_state.startswith("WAITING_FOR_CHALLENGE_CUSTOM_CAT"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        parts = current_state.split(":")
        ch_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else context.user_data.get("wiz_ch_id")
        if not ch_id:
            await set_user_state(user_id, None)
            await update.message.reply_text("No active challenge creation session.", reply_markup=get_main_menu_keyboard())
            return

        new_cat = text.strip()
        await update_challenge_details(ch_id, category=new_cat)
        context.user_data["wiz_category"] = new_cat
        ch = await get_challenge(ch_id)
        title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"

        await set_user_state(user_id, f"WAITING_FOR_CHALLENGE_DESC:{ch_id}")
        await update.message.reply_text(
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
        return

    # Check if admin is entering exam time limit in wizard
    if current_state and current_state.startswith("WAITING_FOR_CHALLENGE_TIMER"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        parts = current_state.split(":")
        ch_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else context.user_data.get("wiz_ch_id")
        if not ch_id:
            await set_user_state(user_id, None)
            await update.message.reply_text("No active challenge creation session.", reply_markup=get_main_menu_keyboard())
            return

        try:
            mins = int(text.strip())
            if mins < 1 or mins > 300:
                raise ValueError("Minutes out of range")
        except Exception:
            await update.message.reply_text(
                "<b>Please enter a valid number of minutes</b> (between 1 and 300):\n\n"
                "<i>Example:</i> <code>15</code>\n\n"
                "<i>(Or send /cancel to abort)</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        await set_user_state(user_id, None)
        dur_secs = mins * 60
        await update_challenge_details(ch_id, duration_seconds=dur_secs)
        ch = await get_challenge(ch_id)
        title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"
        desc = ch.get("description", "") if ch else ""

        await update.message.reply_text(
            f"<b>Create Challenge Wizard (Step 4/4: Schedule & Start/End Time)</b>\n\n"
            f"<blockquote><b>{html.escape(title)}</b>\n"
            f"<i>{html.escape(desc)}</i></blockquote>\n\n"
            f"• <b>Exam Time Limit:</b> <code>{mins} Minutes</code>\n\n"
            f"Select start schedule & deadline:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_schedule_presets_keyboard(ch_id, mins),
        )
        return

    # Check if admin is editing challenge title/category
    if current_state and current_state.startswith("WAITING_FOR_EDIT_CHALLENGE_TITLE"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await set_user_state(user_id, None)
        parts = current_state.split(":")
        ch_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else context.user_data.pop("edit_ch_id", None)
        if not ch_id:
            await update.message.reply_text("No challenge selected for editing.", reply_markup=get_main_menu_keyboard())
            return

        raw = text.strip()
        if "|" in raw:
            title_part, cat_part = raw.split("|", 1)
            title = title_part.strip()
            category = cat_part.strip() or "General"
        else:
            title = raw
            category = "General"

        await update_challenge_details(ch_id, title=title, category=category)
        ch = await get_challenge(ch_id)
        status = ch.get("status", "LIVE") if ch else "LIVE"
        await update.message.reply_text(
            f"<b>Challenge #{ch_id} Updated</b>\n\n"
            f"• <b>New Title:</b> {html.escape(title)}\n"
            f"• <b>New Category:</b> {html.escape(category)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
        )
        return

    # Check if admin is updating schedule with custom dates
    if current_state and current_state.startswith("WAITING_FOR_EDIT_CHALLENGE_SCHEDULE"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        parts = current_state.split(":")
        ch_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else context.user_data.pop("edit_ch_id", None)
        if not ch_id:
            await set_user_state(user_id, None)
            await update.message.reply_text("No challenge selected.", reply_markup=get_main_menu_keyboard())
            return

        raw = text.strip()
        import re
        m = re.search(
            r"(\d{4}-\d{2}-\d{2}(?:[T\s]\d{1,2}:\d{2})?)\s*(?:to|,|--|-)\s*(\d{4}-\d{2}-\d{2}(?:[T\s]\d{1,2}:\d{2})?)",
            raw,
            re.IGNORECASE,
        )
        if m:
            s_str, e_str = m.group(1).strip(), m.group(2).strip()
        else:
            parts = [p.strip() for p in raw.split("to")] if "to" in raw.lower() else [p.strip() for p in raw.split(",")]
            if len(parts) >= 2:
                s_str, e_str = parts[0], parts[1]
            elif len(parts) == 1 and parts[0]:
                s_str, e_str = parts[0], None
            else:
                s_str, e_str = None, None

        now_dt = datetime.now(timezone.utc)
        starts_at = None
        ends_at = None

        try:
            if not s_str:
                raise ValueError("No start date provided")
            s_clean = s_str.replace(" ", "T") if "T" in s_str or " " in s_str else f"{s_str}T00:00"
            s_dt = datetime.fromisoformat(s_clean)
            if s_dt.tzinfo is None:
                s_dt = s_dt.replace(tzinfo=LOCAL_TZ)
            s_utc = s_dt.astimezone(timezone.utc)
            starts_at = s_utc.isoformat()

            if e_str:
                e_clean = e_str.replace(" ", "T") if "T" in e_str or " " in e_str else f"{e_str}T23:59"
                e_dt = datetime.fromisoformat(e_clean)
                if e_dt.tzinfo is None:
                    e_dt = e_dt.replace(tzinfo=LOCAL_TZ)
                e_utc = e_dt.astimezone(timezone.utc)
                ends_at = e_utc.isoformat()
            else:
                e_dt = s_dt + timedelta(days=7)
                ends_at = e_dt.astimezone(timezone.utc).isoformat()
        except Exception:
            await update.message.reply_text(
                f"<b>Invalid Date/Time Format.</b>\n\n"
                f"Please use: <code>YYYY-MM-DD HH:MM to YYYY-MM-DD HH:MM</code> ({BOT_TIMEZONE_NAME})\n"
                f"<i>Example:</i> <code>2026-09-05 18:00 to 2026-09-12 18:00</code>\n\n"
                f"<i>(Or send /cancel to abort)</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        await set_user_state(user_id, None)
        status = "LIVE" if s_utc <= now_dt else "SCHEDULED"
        await update_challenge_details(ch_id, starts_at=starts_at, ends_at=ends_at)
        await update_challenge_status(ch_id, status)

        await update.message.reply_text(
            f"<b>Schedule Updated for Challenge #{ch_id}</b>\n\n"
            f"• <b>Starts:</b> <code>{format_datetime_12h(starts_at)}</code>\n"
            f"• <b>Ends:</b> <code>{format_datetime_12h(ends_at)}</code>\n"
            f"• <b>Status:</b> <code>{status}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
        )
        return

    # Check if admin is updating allowed exam time limit
    if current_state and current_state.startswith("WAITING_FOR_EDIT_CHALLENGE_TIMER"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        parts = current_state.split(":")
        ch_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else context.user_data.pop("edit_ch_id", None)
        if not ch_id:
            await set_user_state(user_id, None)
            await update.message.reply_text("No challenge selected.", reply_markup=get_main_menu_keyboard())
            return

        try:
            mins = int(text.strip())
            if mins < 1 or mins > 300:
                raise ValueError("Minutes out of range")
        except Exception:
            await update.message.reply_text(
                "<b>Please enter a valid number of minutes</b> (between 1 and 300):\n\n"
                "<i>Example:</i> <code>15</code>\n\n"
                "<i>(Or send /cancel to abort)</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        await set_user_state(user_id, None)
        dur_secs = mins * 60
        await update_challenge_details(ch_id, duration_seconds=dur_secs)
        ch = await get_challenge(ch_id)
        status = ch.get("status", "DRAFT") if ch else "DRAFT"

        await update.message.reply_text(
            f"<b>Exam Time Limit Updated for Challenge #{ch_id}</b>\n\n"
            f"• <b>Allowed Test Duration:</b> <code>{mins} minutes total</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
        )
        return

    # Check if admin is adding a single question interactively
    if current_state == "WAITING_FOR_ADMIN_SINGLE_QUESTION":
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        parsed = parse_single_question_text(text)
        if not parsed:
            await update.message.reply_text(
                "<b>Could not parse question format.</b>\n\n"
                "Please make sure your message includes the question and 4 options:\n\n"
                "<code>What is Amazon DynamoDB?\n"
                "A: Relational database\n"
                "B: Key-value NoSQL database\n"
                "C: In-memory cache\n"
                "D: Object storage\n"
                "Answer: B\n"
                "Category: Database\n"
                "Difficulty: EASY\n"
                "Explanation: DynamoDB is a managed NoSQL key-value store</code>\n\n"
                "<i>(Or send /cancel to abort)</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_question_bank_actions_keyboard(),
            )
            return

        await set_user_state(user_id, None)
        q_id = await create_question(
            question_text=parsed["question_text"],
            option_a=parsed["option_a"],
            option_b=parsed["option_b"],
            option_c=parsed["option_c"],
            option_d=parsed["option_d"],
            correct_option=parsed["correct_option"],
            category=parsed.get("category", "General"),
            difficulty=parsed.get("difficulty", "MEDIUM"),
            base_points=parsed.get("base_points", 10.0),
            explanation=parsed.get("explanation", ""),
        )

        await update.message.reply_text(
            f"<b>Question #{q_id} Added to Question Bank</b>\n\n"
            f"• <b>Question:</b> {html.escape(parsed['question_text'])}\n"
            f"• <b>Correct Answer:</b> Option {parsed['correct_option']}\n"
            f"• <b>Category:</b> {html.escape(parsed.get('category', 'General'))} | <b>Difficulty:</b> {parsed.get('difficulty', 'MEDIUM')}\n\n"
            f"<i>This question is now available in your Question Bank to be linked to challenges.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_question_bank_actions_keyboard(),
        )
        return

    # Check if admin is importing questions via CSV text
    if current_state == "WAITING_FOR_ADMIN_CSV":
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await set_user_state(user_id, None)
        result = await import_questions_from_csv(text)
        imported = result["imported"]
        errors = result["errors"]

        err_text = ""
        if errors:
            err_list = "\n".join(errors[:5])
            err_text = f"\n\n<b>Errors Encountered ({len(errors)}):</b>\n{html.escape(err_list)}"

        if imported > 0:
            await update.message.reply_text(
                f"<b>Questions Imported Successfully</b>\n\n"
                f"• <b>Imported:</b> <code>{imported}</code> questions into the Question Bank.{err_text}\n\n"
                f"These questions are now active and available for challenges.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_question_bank_actions_keyboard(),
            )
        else:
            await update.message.reply_text(
                f"<b>No valid questions could be imported.</b>{err_text}\n\n"
                f"Please ensure your text follows the CSV format:\n"
                f"<code>question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_question_bank_actions_keyboard(),
            )
        return

    # Check if admin is adding a single question specifically for a challenge
    if current_state and current_state.startswith("WAITING_FOR_CHALLENGE_SINGLE_QUESTION"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        parts = current_state.split(":")
        target_ch_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else context.user_data.get("target_ch_id")
        if not target_ch_id:
            active_ch = await get_active_challenge()
            target_ch_id = active_ch["id"] if active_ch else 0

        if not target_ch_id:
            await set_user_state(user_id, None)
            await update.message.reply_text("No challenge selected. Please use /admin to select a challenge.", reply_markup=get_main_menu_keyboard())
            return

        parsed = parse_single_question_text(text)
        if not parsed:
            await update.message.reply_text(
                "<b>Could not parse question format.</b>\n\n"
                "Please format your question as follows:\n\n"
                "<code>What is Amazon DynamoDB?\n"
                "A: Relational database\n"
                "B: Key-value NoSQL database\n"
                "C: In-memory cache\n"
                "D: Object storage\n"
                "Answer: B\n"
                "Category: Database\n"
                "Difficulty: EASY\n"
                "Explanation: DynamoDB is a managed NoSQL key-value store</code>\n\n"
                "<i>(Or send /cancel to abort)</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        await set_user_state(user_id, None)
        q_id = await add_question_to_challenge(target_ch_id, parsed)
        ch_questions = await get_challenge_questions(target_ch_id)

        await update.message.reply_text(
            f"<b>Question #{q_id} Added to Challenge #{target_ch_id}!</b>\n\n"
            f"• <b>Question:</b> {html.escape(parsed['question_text'])}\n"
            f"• <b>Correct Answer:</b> Option {parsed['correct_option']}\n"
            f"• <b>Total Attached Questions:</b> <code>{len(ch_questions)}</code>\n\n"
            f"<i>You can add another question, import CSV, or publish the challenge.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_questions_keyboard(target_ch_id),
        )
        return

    # Check if admin is importing questions for a specific challenge via CSV
    if current_state and current_state.startswith("WAITING_FOR_CHALLENGE_CSV"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        parts = current_state.split(":")
        target_ch_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else context.user_data.get("target_ch_id")
        if not target_ch_id:
            active_ch = await get_active_challenge()
            target_ch_id = active_ch["id"] if active_ch else 0

        if not target_ch_id:
            await set_user_state(user_id, None)
            await update.message.reply_text("No challenge selected. Please use /admin to select a challenge.", reply_markup=get_main_menu_keyboard())
            return

        loading_msg = None
        try:
            loading_msg = await update.message.reply_text(
                "<b>Processing CSV lines...</b>\n<i>Parsing questions and linking to challenge...</i>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        await set_user_state(user_id, None)
        result = await import_questions_for_challenge(target_ch_id, text)
        imported = result["imported"]
        errors = result["errors"]

        err_text = ""
        if errors:
            err_list = "\n".join(errors[:5])
            err_text = f"\n\n<b>Errors Encountered ({len(errors)}):</b>\n{html.escape(err_list)}"

        ch_questions = await get_challenge_questions(target_ch_id)

        if imported > 0:
            final_text = (
                f"<b>Questions Imported for Challenge #{target_ch_id}!</b>\n\n"
                f"• <b>Linked:</b> <code>{imported}</code> questions to this challenge.\n"
                f"• <b>Total Attached Questions:</b> <code>{len(ch_questions)}</code>{err_text}"
            )
        else:
            final_text = (
                f"<b>No valid questions could be imported.</b>{err_text}\n\n"
                f"Please ensure your text follows the CSV format:\n"
                f"<code>question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation</code>"
            )
        markup = get_wizard_questions_keyboard(target_ch_id)

        if loading_msg:
            try:
                await loading_msg.edit_text(final_text, parse_mode=ParseMode.HTML, reply_markup=markup)
                return
            except Exception:
                pass
        await update.message.reply_text(final_text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return

    # Check if admin is scheduling a custom date/time for a challenge
    if current_state and current_state.startswith("WAITING_FOR_ADMIN_SCHEDULE"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        parts_state = current_state.split(":")
        existing_ch_id = int(parts_state[1]) if len(parts_state) > 1 and parts_state[1].isdigit() else None
        await set_user_state(user_id, None)

        raw = text.strip()
        import re
        m = re.search(
            r"(\d{4}-\d{2}-\d{2}(?:[T\s]\d{1,2}:\d{2})?)\s*(?:to|,|--|-)\s*(\d{4}-\d{2}-\d{2}(?:[T\s]\d{1,2}:\d{2})?)",
            raw,
            re.IGNORECASE,
        )
        if m:
            s_str, e_str = m.group(1).strip(), m.group(2).strip()
        else:
            parts = [p.strip() for p in raw.split("to")] if "to" in raw.lower() else [p.strip() for p in raw.split(",")]
            if len(parts) >= 2:
                s_str, e_str = parts[0], parts[1]
            elif len(parts) == 1 and parts[0]:
                s_str, e_str = parts[0], None
            else:
                s_str, e_str = None, None

        now_dt = datetime.now(timezone.utc)
        starts_at = None
        ends_at = None

        try:
            if not s_str:
                raise ValueError("No start date provided")
            s_clean = s_str.replace(" ", "T") if "T" in s_str or " " in s_str else f"{s_str}T00:00"
            s_dt = datetime.fromisoformat(s_clean)
            if s_dt.tzinfo is None:
                s_dt = s_dt.replace(tzinfo=LOCAL_TZ)
            s_utc = s_dt.astimezone(timezone.utc)
            starts_at = s_utc.isoformat()

            if e_str:
                e_clean = e_str.replace(" ", "T") if "T" in e_str or " " in e_str else f"{e_str}T23:59"
                e_dt = datetime.fromisoformat(e_clean)
                if e_dt.tzinfo is None:
                    e_dt = e_dt.replace(tzinfo=LOCAL_TZ)
                e_utc = e_dt.astimezone(timezone.utc)
                ends_at = e_utc.isoformat()
            else:
                e_dt = s_dt + timedelta(days=7)
                ends_at = e_dt.astimezone(timezone.utc).isoformat()
        except Exception:
            await update.message.reply_text(
                f"<b>Invalid date/time format.</b>\n\n"
                f"Please use: <code>YYYY-MM-DD HH:MM to YYYY-MM-DD HH:MM</code> ({BOT_TIMEZONE_NAME})\n"
                f"Example: <code>2026-09-05 14:00 to 2026-09-12 18:00</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
            return

        status = "LIVE" if s_utc <= now_dt else "SCHEDULED"

        if existing_ch_id:
            ch_id = existing_ch_id
            await update_challenge_details(ch_id, starts_at=starts_at, ends_at=ends_at)
            await update_challenge_status(ch_id, status)
            ch = await get_challenge(ch_id)
            title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"
            category = ch.get("category", "Architecture") if ch else "Architecture"
            dur_secs = ch.get("duration_seconds") or 600 if ch else 600
            exam_mins = int(dur_secs // 60)
            questions = await get_challenge_questions(ch_id)
            q_count = len(questions)
        else:
            title = context.user_data.pop("wiz_title", "AWS Cloud Architecture Challenge")
            category = context.user_data.pop("wiz_category", "Architecture")
            description = context.user_data.pop("wiz_description", "Weekly test on AWS core services and cloud architecture patterns.")
            dur_mins = context.user_data.pop("wiz_duration_mins", 10)
            exam_mins = dur_mins

            ch_id = await create_challenge(
                title=title,
                description=description,
                category=category,
                starts_at=starts_at,
                ends_at=ends_at,
                question_time_limit_seconds=60,
                duration_seconds=dur_mins * 60,
                accuracy_weight=0.70,
                speed_weight=0.30,
            )
            if status != "DRAFT":
                await update_challenge_status(ch_id, status)
            q_count = 0

        status_text = f"<code>{status}</code>"

        await update.message.reply_text(
            f"<b>Challenge #{ch_id} Configured! (Step 4/4: Add Questions)</b>\n\n"
            f"<blockquote><b>{html.escape(title)}</b>\n"
            f"Category: {html.escape(category)}</blockquote>\n\n"
            f"• <b>Status:</b> {status_text}\n"
            f"• <b>Starts:</b> <code>{format_datetime_12h(starts_at)}</code>\n"
            f"• <b>Ends:</b> <code>{format_datetime_12h(ends_at)}</code>\n"
            f"• <b>Exam Time Limit:</b> <code>{exam_mins} minutes total</code>\n"
            f"• <b>Questions Attached:</b> <code>{q_count}</code>\n\n"
            f"<b>Next step: Attach questions to this challenge.</b>\n"
            f"Add questions one-by-one or bulk import via CSV file below:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_questions_keyboard(ch_id),
        )
        return

    # Check if admin is sending a custom broadcast announcement
    if current_state == "WAITING_FOR_ADMIN_BROADCAST":
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        if not text and not photo_id:
            await update.message.reply_text(
                "▪️ Please provide announcement text or an image with a caption to broadcast.\n\n<i>(Type /cancel to abort)</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        context.user_data["bcast_text"] = text
        context.user_data["bcast_photo"] = photo_id
        users = await get_all_broadcast_user_ids()
        count = len(users)

        preview_body = text
        if len(preview_body) > 3000:
            preview_body = preview_body[:3000] + "...\n\n<i>(Preview truncated; full announcement will be delivered)</i>"

        media_badge = "• <b>Attached Media:</b> 📷 Photo included\n" if photo_id else ""
        content_preview = f"<blockquote>{preview_body}</blockquote>\n\n" if preview_body else "<i>(Photo announcement without text caption)</i>\n\n"

        preview_text = (
            f"✦ <b>BROADCAST PREVIEW</b>\n\n"
            f"• <b>Target Audience:</b> <code>{count}</code> registered members\n"
            f"{media_badge}"
            f"• <b>Message Length:</b> <code>{len(text)}</code> characters\n\n"
            f"{content_preview}"
            f"<i>Are you sure you want to broadcast this {'photo & announcement' if photo_id else 'message'} to all registered members?</i>"
        )
        try:
            await update.message.reply_text(
                preview_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_broadcast_confirm_keyboard("custom"),
            )
        except Exception:
            # Fallback if custom text contained unescaped HTML characters (<, >, &)
            safe_preview = html.escape(preview_body)
            safe_content = f"<blockquote>{safe_preview}</blockquote>\n\n" if safe_preview else "<i>(Photo announcement without text caption)</i>\n\n"
            safe_text = (
                f"✦ <b>BROADCAST PREVIEW</b>\n\n"
                f"• <b>Target Audience:</b> <code>{count}</code> registered members\n"
                f"{media_badge}"
                f"• <b>Message Length:</b> <code>{len(text)}</code> characters\n\n"
                f"{safe_content}"
                f"<i>Are you sure you want to broadcast this {'photo & announcement' if photo_id else 'message'} to all registered members?</i>"
            )
            await update.message.reply_text(
                safe_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_broadcast_confirm_keyboard("custom"),
            )
        await set_user_state(user_id, None)
        return

    # Check if admin is updating Education Track details
    if current_state == "WAITING_FOR_ADMIN_UPDATE_EDU":
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        from app.challenge.admin import parse_education_track_input
        from app.challenge.keyboards import get_admin_confirm_update_keyboard
        from app.community import get_education_track_text
        from app.db import get_all_community_settings

        parsed = parse_education_track_input(text)
        if not parsed:
            await update.message.reply_text(
                "▪️ No valid Education Track fields recognized. Please try again with <code>Key: Value</code> format.",
                parse_mode=ParseMode.HTML,
            )
            return

        current_settings = await get_all_community_settings()
        merged = {**current_settings, **parsed}
        context.user_data["staged_edu"] = parsed
        preview_text = get_education_track_text(merged)

        await update.message.reply_text(
            f"✦ <b>Education Track Update Preview</b>\n\n"
            f"{preview_text}\n\n"
            f"➤ <i>Check the preview above. Tap 'Confirm & Save' to publish live to all members.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_confirm_update_keyboard("edu"),
        )
        return

    # Check if admin is adding a new Education Track
    if current_state == "WAITING_FOR_ADMIN_NEW_TRACK":
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        from app.challenge.admin import parse_track_input
        from app.challenge.keyboards import get_admin_confirm_update_keyboard
        from app.community import format_track_card

        parsed = parse_track_input(text)
        if not parsed:
            await update.message.reply_text(
                "▪️ Could not parse track information. Please enter details or type /cancel.",
                parse_mode=ParseMode.HTML,
            )
            return

        context.user_data["staged_new_track"] = parsed
        preview_text = format_track_card(parsed, track_index=1, total_tracks=1)

        await update.message.reply_text(
            f"✦ <b>New Track Preview</b>\n\n"
            f"{preview_text}\n\n"
            f"➤ <i>Check the preview above. Any omitted or skipped fields are excluded automatically. Tap 'Confirm & Save' to publish live!</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_confirm_update_keyboard("new_track"),
        )
        return

    # Check if admin is editing an existing Education Track
    if current_state and current_state.startswith("WAITING_FOR_ADMIN_EDIT_TRACK:"):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        track_id_str = current_state.split(":")[1]
        try:
            track_id = int(track_id_str)
        except ValueError:
            await set_user_state(user_id, None)
            return

        from app.challenge.admin import parse_track_input
        from app.challenge.keyboards import get_admin_confirm_update_keyboard
        from app.community import format_track_card
        from app.db import get_education_track

        current_track = await get_education_track(track_id)
        if not current_track:
            await update.message.reply_text("▪️ Track not found.", parse_mode=ParseMode.HTML)
            await set_user_state(user_id, None)
            return

        parsed = parse_track_input(text)
        merged = {**current_track, **parsed}
        context.user_data[f"staged_edit_track:{track_id}"] = parsed
        preview_text = format_track_card(merged, track_index=1, total_tracks=1)

        await update.message.reply_text(
            f"✦ <b>Updated Track Preview</b>\n\n"
            f"{preview_text}\n\n"
            f"➤ <i>Check the preview above. Tap 'Confirm & Save' to apply changes live!</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_confirm_update_keyboard(f"edit_track:{track_id}"),
        )
        return

    # Check if admin is updating Next Event details
    if current_state == "WAITING_FOR_ADMIN_UPDATE_EVENT":
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        from app.challenge.admin import parse_next_event_input
        from app.challenge.keyboards import get_admin_confirm_update_keyboard
        from app.community import get_next_event_text
        from app.db import get_all_community_settings

        parsed = parse_next_event_input(text)
        if not parsed:
            await update.message.reply_text(
                "▪️ No valid Next Event fields recognized. Please try again with <code>Key: Value</code> format.",
                parse_mode=ParseMode.HTML,
            )
            return

        current_settings = await get_all_community_settings()
        merged = {**current_settings, **parsed}
        context.user_data["staged_event"] = parsed
        preview_text = get_next_event_text(merged)

        await update.message.reply_text(
            f"✦ <b>Next Event Update Preview</b>\n\n"
            f"{preview_text}\n\n"
            f"➤ <i>Check the preview above. Tap 'Confirm & Save' to publish live to all members.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_confirm_update_keyboard("event"),
        )
        return

    # Check if the user is currently in the feedback-writing state
    if current_state == WAITING_FOR_FEEDBACK:
        await set_user_state(user_id, None)

        name = f"{user.first_name} {user.last_name or ''}".strip()
        safe_name = html.escape(name)
        safe_username = f"@{html.escape(user.username)}" if user.username else "<i>No username</i>"
        safe_text = html.escape(text)

        admin_notification = (
            "✦ <b>Feedback</b>\n"
            f"• <b>From:</b> {safe_name} ({safe_username})\n"
            f"• <b>User ID:</b> <code>{user_id}</code>\n\n"
            f"<blockquote>{safe_text}</blockquote>\n\n"
            "➤ <i>Reply directly to this message to respond to the user.</i>"
        )

        try:
            if ADMIN_GROUP_ID != 0:
                sent_message = await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    text=admin_notification,
                    parse_mode=ParseMode.HTML,
                )
                await save_feedback_submission(
                    sent_message.message_id,
                    user_id,
                    user.first_name,
                    user_message_id=update.message.message_id,
                    ticket_type="feedback",
                )

            reply_markup = get_main_menu_keyboard()

            await update.message.reply_text(
                "✓ <b>Thank you!</b> Your feedback has been successfully delivered to the AWS Student Builder core team.",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )

        except Exception as e:
            logger.error(f"Failed to forward feedback to admin group: {e}")
            await update.message.reply_text(
                "▪️ Your feedback was received, but there was an error forwarding it to the team. Please try again later."
            )

    elif current_state in (WAITING_FOR_QUESTION, "WAITING_FOR_SUPPORT"):
        await set_user_state(user_id, None)

        name = f"{user.first_name} {user.last_name or ''}".strip()
        safe_name = html.escape(name)
        safe_username = f"@{html.escape(user.username)}" if user.username else "<i>No username</i>"
        safe_text = html.escape(text)

        admin_notification = (
            "✦ <b>Question</b>\n"
            f"• <b>From:</b> {safe_name} ({safe_username})\n"
            f"• <b>User ID:</b> <code>{user_id}</code>\n\n"
            f"<blockquote>{safe_text}</blockquote>\n\n"
            "➤ <i>Reply directly to this message to answer the user.</i>"
        )

        try:
            if ADMIN_GROUP_ID != 0:
                sent_message = await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    text=admin_notification,
                    parse_mode=ParseMode.HTML,
                )
                await save_feedback_submission(
                    sent_message.message_id,
                    user_id,
                    user.first_name,
                    user_message_id=update.message.message_id,
                    ticket_type="question",
                )

            reply_markup = get_main_menu_keyboard()

            await update.message.reply_text(
                "✓ <b>Thank you!</b> Your question has been delivered to the AWS Student Builder core team. An admin will reply directly back to this chat.",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )

        except Exception as e:
            logger.error(f"Failed to forward question to admin group: {e}")
            await update.message.reply_text(
                "▪️ Your question was received, but there was an error forwarding it to the team. Please try again later."
            )
    else:
        # Default response if they type random text outside of feedback/question flows
        await update.message.reply_text(
            "I didn't quite catch that. Use the buttons below to explore our <b>Education Track</b>, <b>Next Event</b>, <b>Feedback</b>, or <b>Ask Question</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forwards an admin reply in the staff group back to the original member."""
    if not update.message or not update.message.reply_to_message:
        return

    replied_message_id = update.message.reply_to_message.message_id
    logger.info(
        f"Admin reply received for message_id={replied_message_id} "
        f"from user={update.effective_user.id if update.effective_user else 'unknown'} "
        f"in chat={update.effective_chat.id if update.effective_chat else 'unknown'}"
    )

    submission = await get_feedback_submission(replied_message_id)
    if not submission:
        logger.warning(f"No active feedback submission found for replied message_id={replied_message_id}")
        return

    sender_chat_id = submission["sender_chat_id"]
    ticket_type = submission.get("ticket_type", "feedback")
    response_text = update.message.text or "(reply received)"
    safe_reply = html.escape(response_text)

    if ticket_type == "question":
        header = "Answer from the AWS Student Builder Core Team"
        footer = "Have another question? Send /ask or tap 🔹 Ask Question anytime!"
    else:
        header = "Response from the AWS Student Builder Core Team"
        footer = "Thank you for reaching out! You can submit more feedback anytime with /feedback."

    reply_message = (
        f"✦ <b>{header}</b>\n\n"
        f"<blockquote>{safe_reply}</blockquote>\n\n"
        f"➤ <i>{footer}</i>"
    )

    try:
        delivered_msg = await context.bot.send_message(
            chat_id=sender_chat_id,
            text=reply_message,
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"Successfully sent admin response to member {sender_chat_id}")

        # Link this admin reply message ID to the ticket so follow-up thread replies and edits route to the user
        if getattr(update.message, "message_id", None):
            await save_feedback_submission(
                update.message.message_id,
                sender_chat_id,
                submission.get("sender_name", ""),
                user_message_id=submission.get("user_message_id"),
                ticket_type=ticket_type,
            )
            await save_admin_reply_mapping(
                update.message.message_id,
                sender_chat_id,
                delivered_msg.message_id,
            )
    except Exception as e:
        logger.error(f"Failed to deliver admin reply to member {sender_chat_id}: {e}")


async def handle_admin_edited_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edits the forwarded reply in the member's private chat when an admin edits their reply."""
    if not update.edited_message or not update.edited_message.text:
        return

    admin_msg_id = update.edited_message.message_id
    mapping = await get_admin_reply_mapping(admin_msg_id)
    if not mapping:
        return

    user_chat_id = mapping["user_chat_id"]
    delivered_msg_id = mapping["delivered_message_id"]
    response_text = update.edited_message.text
    safe_reply = html.escape(response_text)

    submission = await get_feedback_submission(admin_msg_id)
    ticket_type = submission.get("ticket_type", "feedback") if submission else "feedback"

    if ticket_type == "question":
        header = "Answer from the AWS Student Builder Core Team"
        footer = "Have another question? Send /ask or tap 🔹 Ask Question anytime!"
    else:
        header = "Response from the AWS Student Builder Core Team"
        footer = "Thank you for reaching out! You can submit more feedback anytime with /feedback."

    reply_message = (
        f"✦ <b>{header}</b> <i>(edited)</i>\n\n"
        f"<blockquote>{safe_reply}</blockquote>\n\n"
        f"➤ <i>{footer}</i>"
    )

    try:
        await context.bot.edit_message_text(
            chat_id=user_chat_id,
            message_id=delivered_msg_id,
            text=reply_message,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to update edited admin reply in member chat: {e}")


async def handle_user_edited_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Updates the forwarded card in the admin group when a member edits their initial feedback or question."""
    if not update.edited_message or not update.edited_message.text or ADMIN_GROUP_ID == 0:
        return

    user_msg_id = update.edited_message.message_id
    submission = await get_feedback_submission_by_user_message(user_msg_id)
    if not submission:
        return

    admin_msg_id = submission["message_id"]
    ticket_type = submission.get("ticket_type", "feedback")
    user = update.effective_user
    text = update.edited_message.text

    name = f"{user.first_name} {user.last_name or ''}".strip()
    safe_name = html.escape(name)
    safe_username = f"@{html.escape(user.username)}" if user.username else "<i>No username</i>"
    safe_text = html.escape(text)

    if ticket_type == "question":
        header_line = "✦ <b>Question</b> <i>(edited)</i>"
    else:
        header_line = "✦ <b>Feedback</b> <i>(edited)</i>"

    admin_notification = (
        f"{header_line}\n"
        f"• <b>From:</b> {safe_name} ({safe_username}) <i>(edited)</i>\n"
        f"• <b>User ID:</b> <code>{user.id}</code>\n\n"
        f"<blockquote>{safe_text}</blockquote>"
    )

    try:
        await context.bot.edit_message_text(
            chat_id=ADMIN_GROUP_ID,
            message_id=admin_msg_id,
            text=admin_notification,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to update edited feedback card in admin group: {e}")


async def unknown_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gracefully handles any unrecognized slash commands (e.g. /noti, /unknown)."""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    if user:
        await register_or_update_bot_user(user.id, user.first_name, user.username)

    raw_text = update.message.text.strip()
    cmd = html.escape(raw_text.split()[0])

    response_text = (
        f"✦ <b>Unrecognized Command:</b> <code>{cmd}</code>\n\n"
        f"Available shortcuts:\n\n"
        f"◆ <b>Challenges</b>\n"
        f"▫️ /challenge › Active quiz\n"
        f"▫️ /leaderboard › Championship rankings\n"
        f"▫️ /archive › Past quizzes & practice\n"
        f"▫️ /rules › Scoring & timing guide\n\n"
        f"◆ <b>Support & Community</b>\n"
        f"▫️ /feedback › Submit feedback\n"
        f"▫️ /ask › Ask a question\n"
        f"▫️ /support › Helpdesk & support info\n"
        f"▫️ /start › Main menu\n"
        f"▫️ /help › Full bot guide\n"
        f"▫️ /cancel › Return to main menu\n\n"
        f"➤ <i>Tap any command above or use the menu below.</i>"
    )
    await update.message.reply_text(
        response_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(),
    )


async def setup_bot_commands(bot) -> None:
    """Registers recommended workable bot commands and sets the chat menu button."""
    commands = [
        BotCommand("start", "Main menu & dashboard"),
        BotCommand("education", "Education tracks & schedules"),
        BotCommand("events", "Next event & upcoming programs"),
        BotCommand("about", "About AWS Student Builder Group"),
        BotCommand("ask", "Ask a question to the core team"),
        BotCommand("feedback", "Submit community feedback & suggestions"),
        BotCommand("help", "Help & guide"),
        BotCommand("admin", "Admin console (Staff)"),
    ]
    await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def post_init(application) -> None:
    """Post-initialization hook called by PTB after application startup."""
    try:
        await setup_bot_commands(application.bot)
        logger.info("Bot commands menu and MenuButtonCommands registered successfully.")
    except Exception as e:
        logger.warning(f"Could not register bot commands menu: {e}")


def create_application(token: str = None):
    """Factory function to build and configure the Telegram application instance."""
    bot_token = token or TELEGRAM_TOKEN
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is missing in environment variables.")
        return None

    from telegram.request import HTTPXRequest
    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        CallbackQueryHandler,
        MessageHandler,
        filters,
    )

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
        http_version="1.1",
    )
    app = (
        ApplicationBuilder()
        .token(bot_token)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # Core Navigation Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("education", education_command))
    app.add_handler(CommandHandler("track", education_command))
    app.add_handler(CommandHandler("events", events_command))
    app.add_handler(CommandHandler("event", events_command))
    app.add_handler(CommandHandler("nextevent", events_command))
    app.add_handler(CommandHandler("notifications", notifications_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("ask", support_command))
    app.add_handler(CommandHandler("question", support_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # Admin Operations & Broadcast
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("bcast", broadcast_command))

    # Community Callbacks
    app.add_handler(CallbackQueryHandler(handle_community_callback, pattern=r"^comm_"))

    # Paused Challenge Commands (Gracefully inform user and redirect)
    app.add_handler(CommandHandler("challenge", challenge_paused_command))
    app.add_handler(CommandHandler("challenges", challenge_paused_command))
    app.add_handler(CommandHandler("archive", challenge_paused_command))
    app.add_handler(CommandHandler("past", challenge_paused_command))
    app.add_handler(CommandHandler("leaderboard", challenge_paused_command))
    app.add_handler(CommandHandler("rules", challenge_paused_command))
    app.add_handler(CommandHandler("guidelines", challenge_paused_command))

    # Challenge Callbacks (Gracefully inform if old inline buttons are tapped)
    app.add_handler(CallbackQueryHandler(challenge_paused_command, pattern=r"^ch_"))
    app.add_handler(CallbackQueryHandler(challenge_paused_command, pattern=r"^lb_"))
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^adm_"))

    # Admin CSV Document Upload
    app.add_handler(MessageHandler(filters.Document.ALL, handle_admin_csv_document))

    # Admin Feedback Replies
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.REPLY & (~filters.COMMAND),
            handle_admin_reply,
        )
    )

    # Edited Admin Replies
    app.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & filters.ChatType.GROUPS & (~filters.COMMAND),
            handle_admin_edited_reply,
        )
    )

    # Edited User Feedback
    app.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & filters.ChatType.PRIVATE & (~filters.COMMAND),
            handle_user_edited_feedback,
        )
    )

    # User Private Messages (Text or Media like Photos)
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO) & filters.ChatType.PRIVATE & (~filters.COMMAND),
            handle_message,
        )
    )

    # Fallback Unrecognized Commands
    app.add_handler(
        MessageHandler(
            filters.COMMAND & filters.ChatType.PRIVATE,
            unknown_command_handler,
        )
    )

    # Global error handler — sends error details to admin and logs
    async def error_handler(update, context):
        logger.error("PTB caught an exception:", exc_info=context.error)
        if update and update.effective_user:
            try:
                err_msg = str(context.error)[:500]
                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text=f"⚠️ An error occurred processing your request:\n\n<code>{html.escape(err_msg)}</code>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

    app.add_error_handler(error_handler)

    return app




