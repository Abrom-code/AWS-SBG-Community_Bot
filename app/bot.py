import asyncio
import html
import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
)
from app.challenge.keyboards import (
    get_challenge_hub_inline_keyboard,
    get_admin_broadcast_confirm_keyboard,
    get_challenge_manage_keyboard,
    get_admin_schedule_presets_keyboard,
    get_wizard_questions_keyboard,
    get_wizard_skip_desc_keyboard,
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
            ["⚡ Challenge Center", "💬 Feedback & Support"],
            ["🛡️ Community Guidelines", "ℹ️ About Us"],
            ["❓ Help"],
        ],
        resize_keyboard=True,
    )


def get_challenge_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns persistent sub-menu keyboard for the Challenge Center."""
    return ReplyKeyboardMarkup(
        [
            ["🚀 Take Active Challenge", "🏆 Leaderboards"],
            ["📚 Past Challenges", "📖 Scoring & Rules"],
            ["🔙 Main Menu"],
        ],
        resize_keyboard=True,
    )


def get_feedback_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns persistent sub-menu keyboard for Feedback & Support."""
    return ReplyKeyboardMarkup(
        [
            ["📝 Submit Feedback", "ℹ️ About Support"],
            ["🔙 Main Menu"],
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
        "<b>Welcome to the AWS SBG AASTU Community & Challenge Bot!</b>\n\n"
        "✨ <b>What you can do here:</b>\n"
        "    ⚡ <b>Weekly Challenges:</b> Test your cloud skills, earn points, and climb the leaderboard\n"
        "    🏆 <b>Leaderboards:</b> View weekly and monthly season rankings\n"
        "    💬 <b>Feedback & Support:</b> Submit suggestions directly to the core team\n"
        "    🛡️ <b>Community Guidelines:</b> Read our community rules & code of conduct\n"
        "    🤝 <b>Community Help:</b> Connect with AWS Student Builder leads\n\n"
        "Tap <b>⚡ Challenge Center</b>, <b>🛡️ Community Guidelines</b>, or <b>💬 Feedback & Support</b> below to get started!\n\n"
        "📢 <b>Join our community:</b> @AWSAASTU"
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
    """Displays the Challenge Center hub with dedicated sub-menu."""
    hub_text = (
        "⚡ <b>AWS Builder Challenge Center</b>\n\n"
        "Participate in weekly cloud competitions to test your architecture and serverless knowledge.\n\n"
        "• <b>🚀 Take Active Challenge:</b> Start or resume the current quiz\n"
        "• <b>🏆 Leaderboards:</b> View Weekly & Monthly championship standings\n"
        "• <b>📚 Past Challenges:</b> Practice archived quizzes & inspect final standings\n"
        "• <b>📖 Scoring & Rules:</b> Learn how timing and accuracy points work\n\n"
        "<i>Select an option below:</i>"
    )
    cb_query = getattr(update, "callback_query", None)
    if cb_query:
        await cb_query.answer()
        await cb_query.message.reply_text(
            hub_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_menu_keyboard(),
        )
    elif update.message:
        await update.message.reply_text(
            hub_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_menu_keyboard(),
        )


async def feedback_hub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the Feedback & Support hub with dedicated sub-menu."""
    hub_text = (
        "💬 <b>Feedback & Community Support Hub</b>\n\n"
        "Have an idea for upcoming AWS workshops, a feature suggestion, or an issue to report?\n\n"
        "• <b>📝 Submit Feedback:</b> Send a direct ticket to our core admin team\n"
        "• <b>ℹ️ About Support:</b> Learn how our team processes your messages\n\n"
        "<i>Select an action below:</i>"
    )
    await update.message.reply_text(
        hub_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_feedback_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the available visible commands for members."""
    help_text = (
        "📘 <b>AWS SBG Community Bot Shortcuts</b>\n\n"
        "• /start — Open the main welcome menu\n"
        "• /challenge — Open the Challenge Center & start quiz\n"
        "• /archive — Browse & practice past challenges\n"
        "• /leaderboard — View weekly & monthly championship rankings\n"
        "• /rules — See how speed & accuracy scoring is calculated\n"
        "• /guidelines — Read community rules & code of conduct\n"
        "• /feedback — Drop a suggestion or issue for the core team\n"
        "• /about — Learn more about what we do\n"
        "• /cancel — Return to the main menu\n\n"
        "💡 <b>Tip:</b> Tap any /command above to send it directly, or use the menu buttons below!"
    )
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(),
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides details about the bot and community group."""
    about_text = (
        "ℹ️ <b>About AWS SBG AASTU</b>\n\n"
        "The AWS Student Builder Group at AASTU empowers students with practical cloud computing knowledge, "
        "certifications, architectural challenges, and hackathons.\n\n"
        "Participate in our weekly challenges via /challenge to sharpen your AWS expertise!\n\n"
        "📢 <b>Join our community:</b> @AWSAASTU"
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
        "✍️ <b>Please type your feedback, suggestion, or issue below:</b>\n\n"
        "<i>(Type /cancel if you change your mind)</i>",
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
            "🔙 <b>Main Menu</b>\n\nChoose an option below:",
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
    if text in ("⚡ Challenge Center", "⚡ Challenges"):
        return await challenge_hub_command(update, context)
    elif text in ("💬 Feedback & Support", "💬 Feedback", "💬 Support", "Support", "Feedback", "📝 Submit Feedback", "📝 Submit New Feedback"):
        return await feedback_command(update, context)
    elif text in ("ℹ️ About Us", "ℹ️ About Support", "ℹ️ About"):
        return await about_command(update, context)
    elif text == "❓ Help":
        return await help_command(update, context)
    elif text in ("🔙 Main Menu", "❌ Cancel"):
        return await cancel_command(update, context)

    # Handle Challenge Sub-Menu
    elif text in ("🚀 Take Active Challenge", "🚀 Start Challenge"):
        return await challenge_command(update, context)
    elif text in ("🏆 Leaderboards", "🏆 Leaderboard"):
        return await leaderboard_command(update, context)
    elif text in ("📚 Past Challenges", "📚 Archive", "📚 Past Quizzes", "/archive"):
        return await past_challenges_command(update, context)
    elif text in ("📖 Scoring & Rules", "📖 Rules", "ℹ️ Scoring Rules", "📖 How Scoring Works"):
        return await scoring_rules_command(update, context)
    elif text in ("🛡️ Community Guidelines", "🛡️ Guidelines", "Guidelines", "Code of Conduct"):
        return await guidelines_command(update, context)

    # Handle Admin Bottom Navigation Buttons
    chat_id = update.effective_chat.id if update.effective_chat else None
    if await is_admin_user(user_id, chat_id, context.bot):
        if text in ("➕ Create Challenge", "➕ Create New Challenge"):
            await set_user_state(user_id, "WAITING_FOR_CHALLENGE_TITLE")
            await update.message.reply_text(
                "➕ <b>Create Challenge Wizard (Step 1/2: Details)</b>\n\n"
                "Please enter the challenge details in this format:\n"
                "<code>Title | Category | Description</code>\n\n"
                "<b>Example:</b>\n"
                "<code>AWS Serverless Sprint | Serverless | Master Lambda, DynamoDB, API Gateway, and EventBridge.</code>\n\n"
                "<i>Tip: You can also just type the title.</i>",
                parse_mode=ParseMode.HTML,
            )
            return
        elif text in ("📋 Manage Challenges", "📋 Challenge List"):
            challenges = await list_challenges(limit=10)
            if not challenges:
                await update.message.reply_text(
                    "📋 <b>Challenge Management</b>\n\n<i>No challenges found. Create one first!</i>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_admin_panel_keyboard(),
                )
            else:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                buttons = []
                for ch in challenges:
                    status_emoji = {"LIVE": "🟢", "SCHEDULED": "⏳", "DRAFT": "🛠️", "ENDED": "🏁"}.get(ch["status"], "⚡")
                    buttons.append([InlineKeyboardButton(f"{status_emoji} {ch['title'][:30]} ({ch['status']})", callback_data=f"adm_manage_ch:{ch['id']}")])
                buttons.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")])
                await update.message.reply_text(
                    "📋 <b>Select a Challenge to Manage:</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            return
        elif text in ("📊 Monthly Report", "📊 Analytics Report"):
            rep = await get_monthly_analytics_report()
            champions = rep.get("champions", [])
            champs_text = ""
            if champions:
                medals = ["🥇", "🥈", "🥉"]
                for idx, c in enumerate(champions[:3]):
                    name = html.escape(c["user_name"])
                    uname = f" (@{html.escape(c['username'])})" if c.get("username") else ""
                    champs_text += f"• {medals[idx]} <b>{name}</b>{uname} — <code>{c['total_score']} pts</code> ({c['challenges_completed']} quizzes)\n"
            else:
                champs_text = "• <i>No completed challenge attempts recorded yet this month.</i>\n"

            report_card = (
                f"📊 <b>AWS Student Builder Monthly Activity Report</b>\n"
                f"📅 <b>Period:</b> {rep['month_name']}\n\n"
                f"👥 <b>Community Engagement:</b>\n"
                f"• Registered Bot Members: <code>{rep['total_users']}</code>\n"
                f"• Feedback Tickets Received: <code>{rep['feedback_count']}</code>\n"
                f"• Staff Replies Delivered: <code>{rep['reply_count']}</code>\n\n"
                f"⚡ <b>Challenges & Competitions:</b>\n"
                f"• Total Challenges: <code>{rep['total_challenges']}</code>\n"
                f"• Total Submissions: <code>{rep['total_attempts']}</code>\n"
                f"• Community Accuracy: <code>{rep['accuracy_pct']}%</code> ({rep['total_correct']}/{rep['total_answered']})\n"
                f"• Average Score: <code>{rep['avg_score']} pts</code>\n"
                f"• Total Points Earned: <code>{rep['total_score']} pts</code>\n\n"
                f"🏆 <b>Top 3 Builders of the Month:</b>\n"
                f"{champs_text}"
            )
            await update.message.reply_text(
                report_card,
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_report_keyboard(),
            )
            return
        elif text in ("📢 Broadcast Notification", "📢 Broadcast"):
            users = await get_all_broadcast_user_ids()
            count = len(users)
            await update.message.reply_text(
                f"📢 <b>Community Broadcast Center</b>\n\n"
                f"👥 <b>Target Audience:</b> <code>{count}</code> registered members\n\n"
                f"Select an announcement preset or compose a custom broadcast:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_broadcast_presets_keyboard(),
            )
            return
        elif text in ("🚪 Exit Admin", "🚪 Leave Admin"):
            await update.message.reply_text(
                "🔙 <b>Exited Admin Panel.</b>\n\nReturning to member menu:",
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

        # Power-user shortcut: entered multiple fields at once (e.g. Title | Category | Description | Duration)
        if len(parts) >= 2:
            await set_user_state(user_id, None)
            duration_mins = 10
            if len(parts) >= 4:
                title = parts[0]
                category = parts[1] or "Architecture"
                description = parts[2] or "Weekly test on AWS core services and cloud architecture patterns."
                try:
                    duration_mins = int(parts[3].lower().replace("mins", "").replace("min", "").replace("m", "").strip())
                except Exception:
                    duration_mins = 10
            elif len(parts) == 3:
                title = parts[0]
                category = parts[1] or "Architecture"
                description = parts[2] or "Weekly test on AWS core services and cloud architecture patterns."
            else:
                title = parts[0]
                category = parts[1] or "Architecture"
                description = "Weekly test on AWS core services and cloud architecture patterns."

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
                f"✨ <b>Create Challenge Wizard (Step 3/4: Schedule & Start/End Time)</b>\n\n"
                f"📌 <b>Title:</b> <b>{html.escape(title)}</b>\n"
                f"🏗️ <b>Category:</b> {html.escape(category)}\n"
                f"📝 <b>Description:</b> <i>{html.escape(description)}</i>\n"
                f"⏱️ <b>Exam Time Limit:</b> <code>{duration_mins} Minutes</code>\n\n"
                f"⏰ <b>Select Start Schedule & Deadline:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_schedule_presets_keyboard(ch_id, duration_mins),
            )
            return

        # Single Title entered -> Step-by-Step Flow: proceed to Step 2 (Description)
        title = raw
        category = "Architecture"
        description = "Weekly test on AWS core services and cloud architecture patterns."
        duration_mins = 10

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
            f"✨ <b>Create Challenge Wizard (Step 2/4: Description)</b>\n\n"
            f"📌 <b>Title:</b> <b>{html.escape(title)}</b>\n\n"
            f"📝 <b>Please enter the challenge description:</b>\n"
            f"<i>(Explain what community members will learn or test in this challenge)</i>\n\n"
            f"<i>Example:</i> <code>Master EC2, S3, VPC, Lambda, and high-availability design patterns in this weekly challenge.</code>\n\n"
            f"<i>(Or tap below to use default description)</i>",
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
            await update.message.reply_text("⚠️ No active challenge creation session.", reply_markup=get_main_menu_keyboard())
            return

        desc = text.strip()
        await update_challenge_details(ch_id, description=desc)
        ch = await get_challenge(ch_id)
        title = ch.get("title", "AWS Cloud Challenge") if ch else "AWS Cloud Challenge"
        dur_secs = ch.get("duration_seconds") or 600 if ch else 600
        dur_mins = int(dur_secs // 60)

        await update.message.reply_text(
            f"✨ <b>Create Challenge Wizard (Step 3/4: Schedule & Start/End Time)</b>\n\n"
            f"📌 <b>Title:</b> <b>{html.escape(title)}</b>\n"
            f"📝 <b>Description:</b> <i>{html.escape(desc)}</i>\n"
            f"⏱️ <b>Exam Time Limit:</b> <code>{dur_mins} Minutes</code>\n\n"
            f"⏰ <b>Select Start Schedule & Deadline:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_schedule_presets_keyboard(ch_id, dur_mins),
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
            await update.message.reply_text("⚠️ No challenge selected for editing.", reply_markup=get_main_menu_keyboard())
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
            f"✅ <b>Challenge #{ch_id} Updated!</b>\n\n"
            f"⚡ <b>New Title:</b> {html.escape(title)}\n"
            f"🏗️ <b>New Category:</b> {html.escape(category)}",
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
            await update.message.reply_text("⚠️ No challenge selected.", reply_markup=get_main_menu_keyboard())
            return

        raw = text.strip()
        parts = [p.strip() for p in raw.split("to")] if "to" in raw.lower() else [p.strip() for p in raw.split(",")]
        now_dt = datetime.now(timezone.utc)
        starts_at = None
        ends_at = None

        try:
            if len(parts) >= 2:
                s_str = parts[0]
                e_str = parts[1]
                s_dt = datetime.fromisoformat(s_str.replace(" ", "T"))
                e_dt = datetime.fromisoformat(e_str.replace(" ", "T"))
                if s_dt.tzinfo is None:
                    s_dt = s_dt.replace(tzinfo=timezone.utc)
                if e_dt.tzinfo is None:
                    e_dt = e_dt.replace(tzinfo=timezone.utc)
                starts_at = s_dt.isoformat()
                ends_at = e_dt.isoformat()
            else:
                s_dt = datetime.fromisoformat(parts[0].replace(" ", "T"))
                if s_dt.tzinfo is None:
                    s_dt = s_dt.replace(tzinfo=timezone.utc)
                starts_at = s_dt.isoformat()
                ends_at = (s_dt + timedelta(days=7)).isoformat()
        except Exception:
            await update.message.reply_text(
                "⚠️ <b>Invalid Date/Time Format.</b>\n\n"
                "Please use: <code>YYYY-MM-DD HH:MM to YYYY-MM-DD HH:MM</code>\n"
                "<i>Example:</i> <code>2026-09-05 18:00 to 2026-09-12 18:00</code>\n\n"
                "<i>(Or send /cancel to abort)</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        await set_user_state(user_id, None)
        status = "LIVE" if s_dt <= now_dt else "SCHEDULED"
        await update_challenge_details(ch_id, starts_at=starts_at, ends_at=ends_at)
        await update_challenge_status(ch_id, status)

        await update.message.reply_text(
            f"✅ <b>Schedule Updated for Challenge #{ch_id}!</b>\n\n"
            f"🟢 <b>Starts:</b> <code>{starts_at}</code>\n"
            f"🏁 <b>Ends:</b> <code>{ends_at}</code>\n"
            f"🚦 <b>Status:</b> {status}",
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
            await update.message.reply_text("⚠️ No challenge selected.", reply_markup=get_main_menu_keyboard())
            return

        try:
            mins = int(text.strip())
            if mins < 1 or mins > 300:
                raise ValueError("Minutes out of range")
        except Exception:
            await update.message.reply_text(
                "⚠️ <b>Please enter a valid number of minutes</b> (between 1 and 300):\n\n"
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
            f"✅ <b>Exam Time Limit Updated for Challenge #{ch_id}!</b>\n\n"
            f"⏱️ <b>Allowed Test Duration:</b> <code>{mins} minutes total</code>",
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
                "⚠️ <b>Could not parse question format.</b>\n\n"
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
            f"✅ <b>Question #{q_id} Added to Question Bank!</b>\n\n"
            f"❓ <b>Question:</b> {html.escape(parsed['question_text'])}\n"
            f"🎯 <b>Correct Answer:</b> Option {parsed['correct_option']}\n"
            f"🏷️ <b>Category:</b> {html.escape(parsed.get('category', 'General'))} | <b>Difficulty:</b> {parsed.get('difficulty', 'MEDIUM')}\n\n"
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
            err_text = f"\n\n⚠️ <b>Errors Encountered ({len(errors)}):</b>\n{html.escape(err_list)}"

        if imported > 0:
            await update.message.reply_text(
                f"📥 <b>Questions Imported Successfully!</b>\n\n"
                f"✅ <b>Imported:</b> <code>{imported}</code> questions into the Question Bank.{err_text}\n\n"
                f"These questions are now active and available for challenges.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_question_bank_actions_keyboard(),
            )
        else:
            await update.message.reply_text(
                f"⚠️ <b>No valid questions could be imported.</b>{err_text}\n\n"
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
            await update.message.reply_text("⚠️ No challenge selected. Please use /admin to select a challenge.", reply_markup=get_main_menu_keyboard())
            return

        parsed = parse_single_question_text(text)
        if not parsed:
            await update.message.reply_text(
                "⚠️ <b>Could not parse question format.</b>\n\n"
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
            f"✅ <b>Question #{q_id} Added to Challenge #{target_ch_id}!</b>\n\n"
            f"❓ <b>Question:</b> {html.escape(parsed['question_text'])}\n"
            f"🎯 <b>Correct Answer:</b> Option {parsed['correct_option']}\n"
            f"📊 <b>Total Attached Questions:</b> <code>{len(ch_questions)}</code>\n\n"
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
            await update.message.reply_text("⚠️ No challenge selected. Please use /admin to select a challenge.", reply_markup=get_main_menu_keyboard())
            return

        await set_user_state(user_id, None)
        result = await import_questions_for_challenge(target_ch_id, text)
        imported = result["imported"]
        errors = result["errors"]

        err_text = ""
        if errors:
            err_list = "\n".join(errors[:5])
            err_text = f"\n\n⚠️ <b>Errors Encountered ({len(errors)}):</b>\n{html.escape(err_list)}"

        ch_questions = await get_challenge_questions(target_ch_id)

        if imported > 0:
            await update.message.reply_text(
                f"📥 <b>Questions Imported for Challenge #{target_ch_id}!</b>\n\n"
                f"✅ <b>Linked:</b> <code>{imported}</code> questions to this challenge.\n"
                f"📊 <b>Total Attached Questions:</b> <code>{len(ch_questions)}</code>{err_text}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_wizard_questions_keyboard(target_ch_id),
            )
        else:
            await update.message.reply_text(
                f"⚠️ <b>No valid questions could be imported.</b>{err_text}\n\n"
                f"Please ensure your text follows the CSV format:\n"
                f"<code>question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_wizard_questions_keyboard(target_ch_id),
            )
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
        parts = [p.strip() for p in raw.split("to")] if "to" in raw.lower() else [p.strip() for p in raw.split(",")]
        now_dt = datetime.now(timezone.utc)
        starts_at = None
        ends_at = None

        try:
            if len(parts) >= 2:
                s_str = parts[0]
                e_str = parts[1]
                s_dt = datetime.fromisoformat(s_str.replace(" ", "T"))
                e_dt = datetime.fromisoformat(e_str.replace(" ", "T"))
                if s_dt.tzinfo is None:
                    s_dt = s_dt.replace(tzinfo=timezone.utc)
                if e_dt.tzinfo is None:
                    e_dt = e_dt.replace(tzinfo=timezone.utc)
                starts_at = s_dt.isoformat()
                ends_at = e_dt.isoformat()
            elif len(parts) == 1:
                s_dt = datetime.fromisoformat(parts[0].replace(" ", "T"))
                if s_dt.tzinfo is None:
                    s_dt = s_dt.replace(tzinfo=timezone.utc)
                starts_at = s_dt.isoformat()
                ends_at = (s_dt + timedelta(days=7)).isoformat()
        except Exception:
            await update.message.reply_text(
                "⚠️ <b>Invalid date/time format.</b>\n\n"
                "Please use: <code>YYYY-MM-DD HH:MM to YYYY-MM-DD HH:MM</code>\n"
                "Example: <code>2026-09-05 14:00 to 2026-09-12 18:00</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
            return

        status = "LIVE" if datetime.fromisoformat(starts_at.replace("Z", "+00:00")) <= now_dt else "SCHEDULED"

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

        status_text = "🟢 <b>LIVE</b>" if status == "LIVE" else "⏳ <b>SCHEDULED</b>"

        await update.message.reply_text(
            f"✨ <b>Challenge #{ch_id} Configured! (Step 4/4: Add Questions)</b>\n\n"
            f"⚡ <b>Title:</b> {html.escape(title)}\n"
            f"🏗️ <b>Category:</b> {html.escape(category)}\n"
            f"🚦 <b>Status:</b> {status_text}\n"
            f"🟢 <b>Starts:</b> <code>{starts_at}</code>\n"
            f"🏁 <b>Ends:</b> <code>{ends_at}</code>\n"
            f"⏱️ <b>Exam Time Limit:</b> <code>{exam_mins} minutes total</code>\n"
            f"📊 <b>Questions Attached:</b> <code>{q_count}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 <b>Next step: Attach questions to this challenge.</b>\n"
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
            f"📢 <b>BROADCAST PREVIEW (Custom Message)</b>\n"
            f"👥 <b>Target Audience:</b> <code>{count}</code> members\n\n"
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
            f"👤 <b>From:</b> {safe_name} ({safe_username})\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n\n"
            f"💬 <b>Message:</b>\n"
            f"<blockquote>{safe_text}</blockquote>"
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
                "✅ <b>Thank you!</b> Your feedback has been successfully delivered to the AWS Student Builder core team.",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )

        except Exception as e:
            logger.error(f"Failed to forward feedback to admin group: {e}")
            await update.message.reply_text(
                "⚠️ Your feedback was received, but there was an error forwarding it to the team. Please try again later."
            )
    else:
        # Default response if they type random text outside of feedback flow
        await update.message.reply_text(
            "I didn't quite catch that. Use the buttons below or type <code>/challenge</code> to take our weekly quiz!",
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
        f"💬 <b>Response from the AWS Student Builder Core Team</b>\n\n"
        f"<blockquote>{safe_reply}</blockquote>\n\n"
        f"<i>Thank you for reaching out! You can submit more feedback anytime with /feedback.</i>"
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
        f"💬 <b>Response from the AWS Student Builder Core Team</b> <i>(edited)</i>\n\n"
        f"<blockquote>{safe_reply}</blockquote>\n\n"
        f"<i>Thank you for reaching out! You can submit more feedback anytime with /feedback.</i>"
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
        f"👤 <b>From:</b> {safe_name} ({safe_username}) <i>(edited)</i>\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n\n"
        f"💬 <b>Message:</b>\n"
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
        f"❓ <b>Unrecognized Command:</b> <code>{cmd}</code>\n\n"
        f"I didn't recognize that command. Here are the commands you can use:\n\n"
        f"⚡ <b>Challenges:</b>\n"
        f"• /challenge — Take active competition\n"
        f"• /leaderboard — View championship rankings\n"
        f"• /archive — Browse past quizzes & practice\n"
        f"• /rules — Scoring & timing guide\n\n"
        f"💬 <b>Support & Community:</b>\n"
        f"• /feedback — Submit feedback to core team\n"
        f"• /start — Open main menu\n"
        f"• /help — Full bot guide\n"
        f"• /cancel — Return to main menu\n\n"
        f"<i>Tap any command above or choose from the menu below:</i>"
    )
    await update.message.reply_text(
        response_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(),
    )


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
    app = ApplicationBuilder().token(bot_token).request(request).build()

    # Core Navigation Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
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
    app.add_handler(CallbackQueryHandler(handle_past_challenges_callback, pattern=r"^ch_past"))
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




