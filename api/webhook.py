import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from telegram import Update
from app.bot import create_application

logger = logging.getLogger(__name__)
bot_app = None


def get_bot_app():
    """Initializes and caches the Telegram application instance for serverless invocations."""
    global bot_app
    if bot_app is None:
        bot_app = create_application()
    return bot_app


class handler(BaseHTTPRequestHandler):
    """Vercel serverless request handler for Telegram webhook events."""

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            update_data = json.loads(post_data.decode("utf-8"))

            app = get_bot_app()
            if not app:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Bot initialization error")
                return

            # Verify secret token if configured
            expected_secret = os.getenv("WEBHOOK_SECRET")
            if expected_secret:
                received_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token")
                if received_secret != expected_secret:
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Unauthorized")
                    return

            async def process():
                if not app._initialized:
                    await app.initialize()
                update = Update.de_json(update_data, app.bot)
                await app.process_update(update)

            asyncio.run(process())

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

        except Exception as e:
            logger.error(f"Error handling Telegram webhook update: {e}", exc_info=True)
            self.send_response(200)
            self.end_headers()

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AWS SBG Community Bot Webhook is active.")
