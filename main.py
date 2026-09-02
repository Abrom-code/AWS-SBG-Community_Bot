import asyncio
import logging
import os
import sys

# On Windows, psycopg async requires SelectorEventLoop instead of ProactorEventLoop
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from app.bot import (
    clear_proxy_environment,
    create_application,
    logger,
)
from app.db import close_pool


def main():
    """Creates the Telegram application and starts it in webhook or polling mode."""
    clear_proxy_environment()

    app = create_application()
    if not app:
        return

    webhook_url = os.getenv("WEBHOOK_URL")

    try:
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
            app.run_polling(
                drop_pending_updates=True,
                bootstrap_retries=10,
                timeout=30,
            )
    finally:
        # Gracefully close the database connection pool on shutdown
        try:
            asyncio.get_event_loop().run_until_complete(close_pool())
        except Exception:
            pass


if __name__ == "__main__":
    main()