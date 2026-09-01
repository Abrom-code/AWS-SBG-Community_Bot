import json
import os
import asyncio
import logging
from http.server import BaseHTTPRequestHandler
from telegram import Update
from app.bot import create_application
from app.db import init_db

logger = logging.getLogger(__name__)

_global_loop = None
_global_app = None


def get_loop_and_app():
    """Returns the persistent event loop and initialized Telegram application instance."""
    global _global_loop, _global_app
    if _global_loop is None or _global_loop.is_closed():
        _global_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_global_loop)
        _global_app = None

    if _global_app is None:
        _global_app = create_application()
        _global_loop.run_until_complete(init_db())
        _global_loop.run_until_complete(_global_app.initialize())

    return _global_loop, _global_app


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            loop, app = get_loop_and_app()
            update_data = json.loads(post_data.decode("utf-8"))
            update = Update.de_json(update_data, app.bot)

            loop.run_until_complete(app.process_update(update))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        except Exception as e:
            logger.error(f"Webhook processing error: {e}", exc_info=True)
            # Reset global instances on error so next request cleanly binds to a fresh loop
            global _global_app, _global_loop
            _global_app = None
            _global_loop = None

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

