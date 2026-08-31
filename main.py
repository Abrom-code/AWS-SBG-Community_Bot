import logging
import os

from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.bot import (
    ADMIN_GROUP_ID,
    TELEGRAM_TOKEN,
    about_command,
    cancel_command,
    clear_proxy_environment,
    feedback_command,
    handle_admin_reply,
    handle_message,
    help_command,
    logger,
    start_command,
)


def main():
    """Creates the Telegram application and starts it in webhook or polling mode."""
    clear_proxy_environment()

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is missing in environment variables.")
        return

    request = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Chat(ADMIN_GROUP_ID) & (~filters.COMMAND),
            handle_admin_reply,
        )
    )

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    webhook_url = os.getenv("WEBHOOK_URL")

    if webhook_url:
        secret_token = os.getenv("WEBHOOK_SECRET")
        port_env = os.getenv("PORT", "8443")
        port = int(port_env) if port_env.isdigit() else 8443
        logger.info("Starting Telegram bot in webhook mode...")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
            secret_token=secret_token,
            drop_pending_updates=True,
        )
    else:
        logger.info("AWS Student Builder Feedback Bot is up and running...")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()