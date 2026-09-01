import json
import os
import asyncio
import logging
from http.server import BaseHTTPRequestHandler
from telegram import Update
from app.bot import create_application
from app.db import init_db

logger = logging.getLogger(__name__)

bot_app = None

def get_event_loop():
    """Gets the active loop or creates and attaches a new one for the current thread."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop

def get_bot_app():
    """Initializes and caches the Telegram application instance."""
    global bot_app
    if bot_app is None:
        bot_app = create_application()
        loop = get_event_loop()
        loop.run_until_complete(init_db())
        loop.run_until_complete(bot_app.initialize())
    return bot_app

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            app = get_bot_app()
            update_data = json.loads(post_data.decode("utf-8"))
            update = Update.de_json(update_data, app.bot)
            
            loop = get_event_loop()
            loop.run_until_complete(app.process_update(update))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        except Exception as e:
            logger.error(f"Webhook processing error: {e}", exc_info=True)
            # Always return 200 to Telegram to prevent infinite retry loops on bad payloads
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "error_handled"}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AWS SBG Community Bot Webhook is active and running!")
