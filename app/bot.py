import html
import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
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
    past_challenges_command,
    handle_challenge_start_callback,
    handle_challenge_answer_callback,
    handle_leaderboard_callback,
    handle_challenge_rules_callback,
    handle_past_challenges_callback,
)
from app.challenge.keyboards import (
    get_challenge_hub_inline_keyboard,
    get_admin_broadcast_confirm_keyboard,
)
from app.challenge.admin import (
    admin_command,
    handle_admin_callback,
    handle_admin_csv_document,
    is_admin_user,
)

# Load environment variables from .env file
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_CHAT_ID", "0"))

# Enable logging to track activity and debug issues
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# State constants
WAITING_FOR_FEEDBACK = "WAITING_FOR_FEEDBACK"


def get_main_menu_keyboard():
    """Returns the top-level member menu keyboard."""
    return ReplyKeyboardMarkup(
        [
            ["⚡ Challenge Center", "💬 Feedback & Support"],
            ["ℹ️ About Us", "❓ Help"],
        ],
        resize_keyboard=True,
    )


def get_challenge_menu_keyboard():
    """Returns the challenge-specific sub-menu keyboard."""
    return ReplyKeyboardMarkup(
        [
            ["🚀 Take Active Challenge", "🏆 Leaderboards"],
            ["📚 Past Challenges", "📖 Scoring & Rules"],
            ["🔙 Main Menu"],
        ],
        resize_keyboard=True,
    )


def get_feedback_menu_keyboard():
    """Returns the feedback-specific sub-menu keyboard."""
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
    if user:
        await register_or_update_bot_user(user.id, user.first_name, user.username)

    welcome_text = (
        "<b>Welcome to the AWS SBG AASTU Community & Challenge Bot!</b>\n\n"
        "✨ <b>What you can do here:</b>\n"
        "    ⚡ <b>Weekly Challenges:</b> Test your cloud skills, earn points, and climb the leaderboard\n"
        "    🏆 <b>Leaderboards:</b> View weekly and monthly season rankings\n"
        "    💬 <b>Feedback & Support:</b> Submit suggestions directly to the core team\n"
        "    🤝 <b>Community Help:</b> Connect with AWS Student Builder leads\n\n"
        "Tap <b>⚡ Challenge Center</b> or <b>💬 Feedback & Support</b> below to get started!\n\n"
        "📢 <b>Join our community:</b> @AWSAASTU"
    )

    logo_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets",
        "logo.jpg",
    )

    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=welcome_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_main_menu_keyboard(),
                )
        except Exception as e:
            logger.error(f"Failed to send logo photo: {e}")
            await update.message.reply_text(
                welcome_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
    else:
        logger.warning(f"Logo photo not found at: {logo_path}")
        await update.message.reply_text(
            welcome_text,
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
    elif text in ("💬 Feedback & Support", "💬 Feedback"):
        return await feedback_hub_command(update, context)
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
    elif text in ("📖 Scoring & Rules", "📖 Rules", "ℹ️ Scoring Rules"):
        return await scoring_rules_command(update, context)

    # Handle Feedback Sub-Menu
    elif text in ("📝 Submit Feedback", "📝 Submit New Feedback"):
        return await feedback_command(update, context)

    # Check user state
    current_state = await get_user_state(user_id)

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
            f"📥 <b>New AWS Community Feedback</b>\n\n"
            f"👤 <b>From:</b> {safe_name} ({safe_username})\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n\n"
            f"💬 <b>Message:</b>\n"
            f"<blockquote>{safe_text}</blockquote>\n\n"
            f"<i>💡 Reply directly to this message to send an answer to the member.</i>"
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
        f"📥 <b>New AWS Community Feedback</b> <i>(edited by user)</i>\n\n"
        f"👤 <b>From:</b> {safe_name} ({safe_username})\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n\n"
        f"💬 <b>Message:</b>\n"
        f"<blockquote>{safe_text}</blockquote>\n\n"
        f"<i>💡 Reply directly to this message to send an answer to the member.</i>"
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
    app.add_handler(CommandHandler("cancel", cancel_command))

    # Challenge & Leaderboard Commands
    app.add_handler(CommandHandler("challenge", challenge_command))
    app.add_handler(CommandHandler("archive", past_challenges_command))
    app.add_handler(CommandHandler("past", past_challenges_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("rules", scoring_rules_command))
    app.add_handler(CommandHandler("admin", admin_command))

    # Challenge Callbacks
    app.add_handler(CallbackQueryHandler(handle_challenge_start_callback, pattern=r"^ch_start:"))
    app.add_handler(CallbackQueryHandler(handle_challenge_answer_callback, pattern=r"^ch_ans:"))
    app.add_handler(CallbackQueryHandler(handle_challenge_rules_callback, pattern=r"^ch_rules$"))
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

    return app




