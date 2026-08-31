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
)
from app.challenge.handlers import (
    challenge_command,
    leaderboard_command,
    handle_challenge_start_callback,
    handle_challenge_answer_callback,
    handle_leaderboard_callback,
)
from app.challenge.admin import (
    admin_command,
    handle_admin_callback,
    handle_admin_csv_document,
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
    """Returns the member-facing menu keyboard with command shortcuts."""
    return ReplyKeyboardMarkup(
        [
            ["⚡ Challenges", "🏆 Leaderboard"],
            ["📝 Submit Feedback", "ℹ️ About"],
            ["❓ Help", "❌ Cancel"],
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
    welcome_text = (
        "<b>Welcome to the AWS SBG AASTU Community & Challenge Bot!</b>\n\n"
        "✨ <b>What you can do here:</b>\n"
        "    ⚡ <b>Weekly Challenges:</b> Test your cloud skills and climb the leaderboard\n"
        "    🏆 <b>Leaderboards:</b> Track weekly & monthly season rankings\n"
        "    💬 <b>Feedback & Suggestions:</b> Direct channel to core team\n"
        "    🤝 <b>Community Support:</b> Get answers from student builder leads\n\n"
        "Use the menu below or type <code>/challenge</code> to begin!\n\n"
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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the available visible commands for members."""
    help_text = (
        "📘 <b>AWS SBG Community Bot Shortcuts</b>\n\n"
        "• <code>/start</code> — Open the main welcome menu\n"
        "• <code>/challenge</code> — Take the active weekly AWS cloud quiz\n"
        "• <code>/leaderboard</code> — View weekly & monthly championship rankings\n"
        "• <code>/feedback</code> — Drop a suggestion, idea, or issue for the core team\n"
        "• <code>/about</code> — Learn more about what we do\n"
        "• <code>/cancel</code> — Stop your current feedback draft\n\n"
        "💡 <b>Tip:</b> You can also tap the quick-action buttons at the bottom of your screen anytime!"
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
        "Participate in our weekly challenges via <code>/challenge</code> to sharpen your AWS expertise!"
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
    """Cancels the current feedback session."""
    user_id = update.effective_user.id
    current_state = await get_user_state(user_id)
    if current_state == WAITING_FOR_FEEDBACK:
        await set_user_state(user_id, None)
        await update.message.reply_text(
            "❌ Feedback submission cancelled.",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "No active action to cancel. Tap <b>Submit Feedback</b> or type <code>/feedback</code> to start.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(),
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes text messages based on the user's current state."""
    if not update.message or not update.message.text:
        return

    text = update.message.text
    user = update.effective_user
    user_id = user.id

    # Handle button clicks text aliases
    if text == "⚡ Challenges":
        return await challenge_command(update, context)
    elif text == "🏆 Leaderboard":
        return await leaderboard_command(update, context)
    elif text == "📝 Submit Feedback":
        return await feedback_command(update, context)
    elif text == "ℹ️ About":
        return await about_command(update, context)
    elif text == "❓ Help":
        return await help_command(update, context)

    # Check if the user is currently in the feedback-writing state
    current_state = await get_user_state(user_id)
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
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("admin", admin_command))

    # Challenge Callbacks
    app.add_handler(CallbackQueryHandler(handle_challenge_start_callback, pattern=r"^ch_start:"))
    app.add_handler(CallbackQueryHandler(handle_challenge_answer_callback, pattern=r"^ch_ans:"))
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




