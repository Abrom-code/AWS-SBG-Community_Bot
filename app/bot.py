import asyncio
import html
import os
import logging
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


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns persistent bottom menu buttons for primary member actions."""
    return ReplyKeyboardMarkup(
        [
            ["Challenges", "Feedback"],
            ["About", "Help"],
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
            ["Submit Feedback", "About Support"],
            ["Main Menu"],
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
        "✦ <b>AWS SBG AASTU Community & Challenge Bot!</b>\n\n"
        "Welcome! Test your cloud skills, track your rank, and connect with fellow builders.\n\n"
        "◆ <b>Features</b>\n"
        "🔹 <b>Challenges</b> › Compete in weekly quizzes & earn points\n"
        "🔹 <b>Leaderboards</b> › Weekly & monthly championship rankings\n"
        "🔹 <b>Feedback & Support</b> › Direct line to the core team\n"
        "🔹 <b>Guidelines</b> › Rules & code of conduct\n\n"
        "➤ <i>Select an option below to get started:</i>\n\n"
        "✦ <b>Join our community:</b> @AWSAASTU"
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
    """Directly displays active community challenge without redundant intermediate menus."""
    return await challenge_command(update, context)


async def feedback_hub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the Feedback & Support hub with dedicated sub-menu."""
    if context.bot and update.effective_chat:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        except Exception:
            pass
    hub_text = (
        "✦ <b>Feedback & Community Support Hub</b>\n\n"
        "Have an idea for workshops, suggestions, or an issue to report?\n\n"
        "🔹 <b>Submit Feedback</b> › Send a direct ticket to the core team\n"
        "🔹 <b>About Support</b> › How our team handles your messages\n\n"
        "➤ <i>Select an option below:</i>"
    )
    await update.message.reply_text(
        hub_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_feedback_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the available visible commands for members."""
    help_text = (
        "✦ <b>AWS SBG Community Bot Shortcuts</b>\n\n"
        "▫️ /start › Welcome menu\n"
        "▫️ /challenge › Challenge center & active quiz\n"
        "▫️ /leaderboard › Weekly & monthly standings\n"
        "▫️ /notifications › Community notifications info\n"
        "▫️ /archive › Past challenges & practice\n"
        "▫️ /rules › Scoring formula & timing\n"
        "▫️ /guidelines › Rules & code of conduct\n"
        "▫️ /feedback › Contact the core team\n"
        "▫️ /about › About AWS SBG AASTU\n"
        "▫️ /admin › Administrator console (restricted)\n"
        "▫️ /cancel › Return to main menu\n\n"
        "➤ <i>Tap any command above or use the menu buttons below.</i>"
    )
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(),
    )


async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explains notification preferences and active broadcast status."""
    await update.message.reply_text(
        "<b>Community Notifications</b>\n\n"
        "You are subscribed to real-time AWS Student Builder updates:\n\n"
        "• <b>New Challenges:</b> Instant alerts when weekly competitions go live\n"
        "• <b>Leaderboards:</b> Weekly standings and monthly championship updates\n"
        "• <b>Community Announcements:</b> Workshops, webinars, and events\n\n"
        "<i>All notifications are delivered directly to this chat. Keep notifications unmuted to never miss an update!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(),
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides details about the bot and community group."""
    about_text = (
        "✦ <b>About AWS SBG AASTU</b>\n\n"
        "The AWS Student Builder Group at AASTU empowers students through hands-on cloud learning, "
        "certifications, architecture challenges, and hackathons.\n\n"
        "▫️ <b>Weekly Quizzes:</b> /challenge\n"
        "▫️ <b>Community Channel:</b> @AWSAASTU"
    )
    await update.message.reply_text(
        about_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(),
    )


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates the feedback collection workflow."""
    user_id = update.effective_user.id
    await set_user_state(user_id, WAITING_FOR_FEEDBACK)

    await update.message.reply_text(
        "✦ <b>Submit Feedback</b>\n\n"
        "Please type your feedback, suggestion, or issue below:\n\n"
        "➤ <i>(Type /cancel if you change your mind)</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the current feedback or broadcast session and returns to the main menu."""
    user_id = update.effective_user.id
    current_state = await get_user_state(user_id)
    if current_state == WAITING_FOR_FEEDBACK:
        await set_user_state(user_id, None)
        await update.message.reply_text(
            "❌ Feedback submission cancelled.",
            reply_markup=get_main_menu_keyboard(),
        )
    elif current_state == "WAITING_FOR_ADMIN_BROADCAST":
        await set_user_state(user_id, None)
        await update.message.reply_text(
            "❌ Broadcast cancelled.",
            reply_markup=get_main_menu_keyboard(),
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
        await update.message.reply_text(
            "❌ Operation cancelled.",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "✦ <b>Main Menu</b>\n\nChoose an option below:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes text messages based on the user's current state and sub-menu navigation."""
    if not update.message or not update.message.text:
        return

    text = update.message.text
    user = update.effective_user
    user_id = user.id
    if user:
        await register_or_update_bot_user(user.id, user.first_name, user.username)

    # Handle Top-Level Navigation
    if text in ("Challenges", "⚡ Challenges", "⚡ Challenge Center", "Challenge Center", "Challenge", "Take Challenge", "Active Challenge", "🚀 Take Active Challenge", "🚀 Start Challenge", "Start Challenge", "Take Active Challenge"):
        return await challenge_command(update, context)
    elif text in ("Feedback", "💬 Feedback", "💬 Feedback & Support", "Feedback & Support", "Submit Feedback", "📝 Submit Feedback", "📝 Submit New Feedback"):
        return await feedback_command(update, context)
    elif text in ("About", "About Us", "ℹ️ About Us", "ℹ️ About Support", "ℹ️ About", "About Support"):
        return await about_command(update, context)
    elif text in ("Help", "❓ Help"):
        return await help_command(update, context)
    elif text in ("Main Menu", "🔙 Main Menu", "❌ Cancel", "Cancel", "Menu"):
        return await cancel_command(update, context)

    # Handle Challenge Sub-Menu
    elif text in ("Leaderboards", "Leaderboard", "🏆 Leaderboards", "🏆 Leaderboard"):
        return await leaderboard_command(update, context)
    elif text in ("Past Challenges", "Archive", "📚 Past Challenges", "📚 Archive", "📚 Past Quizzes", "Past Quizzes"):
        return await past_challenges_command(update, context)
    elif text in ("Scoring Rules", "Scoring & Rules", "Rules", "📖 Scoring & Rules", "📖 Rules", "ℹ️ Scoring Rules", "📖 How Scoring Works", "How Scoring Works"):
        return await scoring_rules_command(update, context)
    elif text in ("Guidelines", "Community Guidelines", "🛡️ Community Guidelines", "🛡️ Guidelines", "Code of Conduct"):
        return await guidelines_command(update, context)

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
        elif text in ("Broadcast", "Broadcast Notification", "📢 Broadcast Notification", "📢 Broadcast"):
            users = await get_all_broadcast_user_ids()
            count = len(users)
            await update.message.reply_text(
                f"<b>Community Broadcast Center</b>\n\n"
                f"• <b>Target Audience:</b> <code>{count}</code> registered members\n\n"
                f"Select an announcement preset or compose a custom broadcast:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_broadcast_presets_keyboard(),
            )
            return
        elif text in ("Exit Admin", "🚪 Exit Admin", "🚪 Leave Admin", "Leave Admin"):
            await update.message.reply_text(
                "<b>Exited Admin Panel</b>\n\nReturning to member menu:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
            return

    # Check user state
    current_state = await get_user_state(user_id)

    # Check if admin is entering challenge title (Wizard Step 1/4)
    if current_state == "WAITING_FOR_CHALLENGE_TITLE":
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not await is_admin_user(user_id, chat_id, context.bot):
            await set_user_state(user_id, None)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        raw = text.strip()
        parts = [p.strip() for p in raw.split("|")]

        # Power-user multi-part shortcut (3 or 4 parts: Title | Category | Description | Duration OR Title | Description | Duration)
        if len(parts) >= 3:
            await set_user_state(user_id, None)
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
            context.user_data["wiz_description"] = description
            context.user_data["wiz_duration_mins"] = duration_mins

            await update.message.reply_text(
                f"<b>Create Challenge Wizard (Step 4/4: Schedule & Start/End Time)</b>\n\n"
                f"<blockquote><b>{html.escape(title)}</b>\n"
                f"Category: {html.escape(category)}\n"
                f"<i>{html.escape(description)}</i></blockquote>\n\n"
                f"• <b>Exam Time Limit:</b> <code>{duration_mins} Minutes</code>\n\n"
                f"Select start schedule & deadline:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_schedule_presets_keyboard(ch_id, duration_mins),
            )
            return

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

        await set_user_state(user_id, None)
        context.user_data["bcast_text"] = text
        users = await get_all_broadcast_user_ids()
        count = len(users)

        preview_text = (
            f"<b>BROADCAST PREVIEW (Custom Message)</b>\n\n"
            f"• <b>Target Audience:</b> <code>{count}</code> members\n\n"
            f"<blockquote>{text}</blockquote>\n\n"
            f"<i>Confirm to deliver this announcement to all community members:</i>"
        )
        await update.message.reply_text(
            preview_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_broadcast_confirm_keyboard("custom"),
        )
        return

    # Check if the user is currently in the feedback-writing state
    if current_state == WAITING_FOR_FEEDBACK:
        # Reset state back to normal
        await set_user_state(user_id, None)

        # Format feedback package for the admin core team
        name = f"{user.first_name} {user.last_name or ''}".strip()
        safe_name = html.escape(name)
        safe_username = f"@{html.escape(user.username)}" if user.username else "<i>No username</i>"
        safe_text = html.escape(text)

        admin_notification = (
            f"✦ <b>New Feedback Ticket</b>\n"
            f"👤 <b>From:</b> {safe_name} ({safe_username})\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n\n"
            f"<blockquote>{safe_text}</blockquote>\n\n"
            f"➤ <i>Reply directly to this message to respond to the user.</i>"
        )

        try:
            # Forward feedback to the student builder core team group
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
                )

            # Restore the standard keyboard for the user
            reply_markup = get_main_menu_keyboard()

            # Confirm submission success to the member
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
    else:
        # Default response if they type random text outside of feedback flow
        await update.message.reply_text(
            "I didn't quite catch that. Use the buttons below or send <code>/challenge</code> to take our weekly quiz!",
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
    response_text = update.message.text or "(reply received)"
    safe_reply = html.escape(response_text)

    reply_message = (
        f"✦ <b>Response from the AWS Student Builder Core Team</b>\n\n"
        f"<blockquote>{safe_reply}</blockquote>\n\n"
        f"➤ <i>Thank you for reaching out! You can submit more feedback anytime with /feedback.</i>"
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

    reply_message = (
        f"✦ <b>Response from the AWS Student Builder Core Team</b> <i>(edited)</i>\n\n"
        f"<blockquote>{safe_reply}</blockquote>\n\n"
        f"➤ <i>Thank you for reaching out! You can submit more feedback anytime with /feedback.</i>"
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
    """Updates the forwarded card in the admin group when a member edits their initial feedback."""
    if not update.edited_message or not update.edited_message.text or ADMIN_GROUP_ID == 0:
        return

    user_msg_id = update.edited_message.message_id
    submission = await get_feedback_submission_by_user_message(user_msg_id)
    if not submission:
        return

    admin_msg_id = submission["message_id"]
    user = update.effective_user
    text = update.edited_message.text

    name = f"{user.first_name} {user.last_name or ''}".strip()
    safe_name = html.escape(name)
    safe_username = f"@{html.escape(user.username)}" if user.username else "<i>No username</i>"
    safe_text = html.escape(text)

    admin_notification = (
        f"✦ <b>Feedback Ticket (edited)</b>\n"
        f"👤 <b>From:</b> {safe_name} ({safe_username}) <i>(edited)</i>\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n\n"
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
        BotCommand("start", "Start the bot & main dashboard"),
        BotCommand("challenge", "Browse & take challenges"),
        BotCommand("leaderboard", "View leaderboard standings"),
        BotCommand("notifications", "Community notification info"),
        BotCommand("rules", "View scoring rules & speed bonus"),
        BotCommand("archive", "Review past challenges & answers"),
        BotCommand("feedback", "Send feedback to the core team"),
        BotCommand("about", "About AWS Student Builder Group"),
        BotCommand("help", "Help & guide"),
        BotCommand("admin", "Admin console & challenge management"),
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
    app.add_handler(CommandHandler("notifications", notifications_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("support", feedback_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    # Challenge & Leaderboard Commands
    app.add_handler(CommandHandler("challenge", challenge_command))
    app.add_handler(CommandHandler("archive", past_challenges_command))
    app.add_handler(CommandHandler("past", past_challenges_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("rules", scoring_rules_command))
    app.add_handler(CommandHandler("guidelines", guidelines_command))
    app.add_handler(CommandHandler("admin", admin_command))

    # Challenge Callbacks
    app.add_handler(CallbackQueryHandler(handle_challenge_start_callback, pattern=r"^ch_start:"))
    app.add_handler(CallbackQueryHandler(handle_challenge_answer_callback, pattern=r"^ch_ans:"))
    app.add_handler(CallbackQueryHandler(handle_challenge_nav_callback, pattern=r"^ch_nav:"))
    app.add_handler(CallbackQueryHandler(handle_challenge_rules_callback, pattern=r"^ch_rules$"))
    app.add_handler(CallbackQueryHandler(handle_guidelines_callback, pattern=r"^ch_guidelines$"))
    app.add_handler(CallbackQueryHandler(challenge_command, pattern=r"^ch_active_view$"))
    app.add_handler(CallbackQueryHandler(handle_challenge_select_callback, pattern=r"^ch_select:"))
    app.add_handler(CallbackQueryHandler(handle_challenge_nav_active_callback, pattern=r"^ch_nav_act:"))
    app.add_handler(CallbackQueryHandler(handle_scheduled_challenge_info_callback, pattern=r"^ch_sched_info:"))
    app.add_handler(CallbackQueryHandler(handle_challenge_refresh_callback, pattern=r"^ch_refresh:"))
    app.add_handler(CallbackQueryHandler(handle_past_challenges_callback, pattern=r"^ch_past"))
    app.add_handler(CallbackQueryHandler(handle_challenge_review_callback, pattern=r"^ch_review:"))
    app.add_handler(CallbackQueryHandler(challenge_hub_command, pattern=r"^ch_hub$"))
    app.add_handler(CallbackQueryHandler(handle_leaderboard_callback, pattern=r"^lb_"))
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

    # User Private Messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & (~filters.COMMAND),
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

    return app




