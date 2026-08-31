import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.bot as bot
import app.db as db
from telegram.constants import ParseMode


class FakeUser:
    def __init__(self, user_id=42, first_name="Test", last_name=None, username="tester"):
        self.id = user_id
        self.first_name = first_name
        self.last_name = last_name
        self.username = username


class FakeMessage:
    def __init__(self, text="", chat_id=1, message_id=50):
        self.text = text
        self.chat_id = chat_id
        self.message_id = message_id
        self.reply_text_calls = []
        self.reply_photo_calls = []
        self.reply_to_message = None

    async def reply_text(self, text, parse_mode=None, reply_markup=None):
        self.reply_text_calls.append(
            {
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )

    async def reply_photo(self, photo, caption=None, parse_mode=None, reply_markup=None):
        self.reply_photo_calls.append(
            {
                "photo": photo,
                "caption": caption,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )


class FakeUpdate:
    def __init__(self, user_id=42, text="", chat_id=1, reply_to_message_id=None, is_edited=False):
        self.effective_user = FakeUser(user_id=user_id)
        msg = FakeMessage(text=text, chat_id=chat_id)
        if reply_to_message_id is not None:
            msg.reply_to_message = type(
                "ReplyToMessage", (), {"message_id": reply_to_message_id}
            )()
        if is_edited:
            self.message = None
            self.edited_message = msg
        else:
            self.message = msg
            self.edited_message = None


class FakeBot:
    def __init__(self):
        self.sent_messages = []
        self.edited_messages = []

    async def send_message(self, chat_id, text, parse_mode=None):
        message_id = len(self.sent_messages) + 1
        self.sent_messages.append((chat_id, text, message_id, parse_mode))
        return type("SentMessage", (), {"message_id": message_id})()

    async def edit_message_text(self, chat_id, message_id, text, parse_mode=None):
        self.edited_messages.append((chat_id, message_id, text, parse_mode))
        return type("SentMessage", (), {"message_id": message_id})()


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()


def test_get_main_menu_keyboard_contains_expected_actions():
    keyboard = bot.get_main_menu_keyboard()

    labels = [
        [button.text for button in row]
        for row in keyboard.keyboard
    ]

    assert labels == [
        ["📝 Submit Feedback", "ℹ️ About"],
        ["❓ Help"],
        ["❌ Cancel"],
    ]


def test_clear_proxy_environment_removes_proxy_variables_and_sets_no_proxy():
    os.environ["HTTP_PROXY"] = "http://example.com"
    os.environ["HTTPS_PROXY"] = "http://example.com"
    os.environ["ALL_PROXY"] = "http://example.com"
    os.environ["no_proxy"] = "localhost"

    bot.clear_proxy_environment()

    assert "HTTP_PROXY" not in os.environ
    assert "HTTPS_PROXY" not in os.environ
    assert "ALL_PROXY" not in os.environ
    assert os.environ["NO_PROXY"] == "*"
    assert os.environ["no_proxy"] == "*"


def test_help_command_returns_expected_shortcuts():
    update = FakeUpdate(user_id=555)
    context = FakeContext()

    asyncio.run(bot.help_command(update, context))

    assert update.message.reply_text_calls[0]["text"].startswith("📘")
    assert "<code>/start</code>" in update.message.reply_text_calls[0]["text"]
    assert update.message.reply_text_calls[0]["parse_mode"] == ParseMode.HTML


def test_feedback_command_sets_waiting_state_and_removes_keyboard():
    asyncio.run(db.reset_db())
    update = FakeUpdate(user_id=111)
    context = FakeContext()

    asyncio.run(bot.feedback_command(update, context))

    state = asyncio.run(db.get_user_state(111))
    assert state == bot.WAITING_FOR_FEEDBACK
    assert update.message.reply_text_calls[0]["reply_markup"] is not None
    assert update.message.reply_text_calls[0]["parse_mode"] == ParseMode.HTML


def test_cancel_command_clears_feedback_state_and_restores_keyboard():
    asyncio.run(db.reset_db())
    update = FakeUpdate(user_id=222)
    context = FakeContext()
    asyncio.run(db.set_user_state(222, bot.WAITING_FOR_FEEDBACK))

    asyncio.run(bot.cancel_command(update, context))

    state = asyncio.run(db.get_user_state(222))
    assert state is None
    assert update.message.reply_text_calls[0]["text"] == "❌ Feedback submission cancelled."

    labels = [
        [button.text for button in row]
        for row in update.message.reply_text_calls[0]["reply_markup"].keyboard
    ]
    assert labels == [
        ["📝 Submit Feedback", "ℹ️ About"],
        ["❓ Help"],
        ["❌ Cancel"],
    ]


def test_handle_message_forwards_feedback_to_admin_group_and_returns_success():
    asyncio.run(db.reset_db())
    original_admin_group_id = bot.ADMIN_GROUP_ID
    bot.ADMIN_GROUP_ID = 999

    update = FakeUpdate(user_id=333, text="This is a test feedback message")
    context = FakeContext()
    asyncio.run(db.set_user_state(333, bot.WAITING_FOR_FEEDBACK))

    asyncio.run(bot.handle_message(update, context))

    assert len(context.bot.sent_messages) == 1
    chat_id, text, message_id, parse_mode = context.bot.sent_messages[0]
    assert chat_id == 999
    assert parse_mode == ParseMode.HTML
    assert "📥 <b>New AWS Community Feedback</b>" in text
    assert "<blockquote>This is a test feedback message</blockquote>" in text
    
    submission = asyncio.run(db.get_feedback_submission(message_id))
    assert submission["sender_chat_id"] == 333
    assert update.message.reply_text_calls[-1]["text"].startswith("✅ <b>Thank you!")
    assert update.message.reply_text_calls[-1]["parse_mode"] == ParseMode.HTML
    
    state = asyncio.run(db.get_user_state(333))
    assert state is None

    bot.ADMIN_GROUP_ID = original_admin_group_id


def test_handle_admin_reply_routes_multiple_staff_replies_to_original_member():
    asyncio.run(db.reset_db())
    context = FakeContext()
    
    # 1. First admin reply to the original message (ID 7)
    update1 = FakeUpdate(user_id=444, text="Thanks for sharing this.")
    update1.message.message_id = 50
    update1.message.reply_to_message = type(
        "ReplyToMessage", (), {"message_id": 7}
    )()
    asyncio.run(db.save_feedback_submission(7, 444, "Original User"))

    asyncio.run(bot.handle_admin_reply(update1, context))

    assert len(context.bot.sent_messages) == 1
    chat_id, text, _, parse_mode = context.bot.sent_messages[0]
    assert chat_id == 444
    assert parse_mode == ParseMode.HTML
    assert "💬 <b>Response from the AWS Student Builder Core Team</b>" in text
    assert "<blockquote>Thanks for sharing this.</blockquote>" in text
    
    # 2. Second admin reply to the same original message (ID 7)
    update2 = FakeUpdate(user_id=444, text="Here is a follow-up answer.")
    update2.message.message_id = 51
    update2.message.reply_to_message = type(
        "ReplyToMessage", (), {"message_id": 7}
    )()

    asyncio.run(bot.handle_admin_reply(update2, context))

    assert len(context.bot.sent_messages) == 2
    chat_id2, text2, _, _ = context.bot.sent_messages[1]
    assert chat_id2 == 444
    assert "<blockquote>Here is a follow-up answer.</blockquote>" in text2

    # 3. Third admin reply replying to the admin's reply in the thread (ID 50)
    update3 = FakeUpdate(user_id=444, text="Adding to what my colleague mentioned above.")
    update3.message.message_id = 52
    update3.message.reply_to_message = type(
        "ReplyToMessage", (), {"message_id": 50}
    )()

    asyncio.run(bot.handle_admin_reply(update3, context))

    assert len(context.bot.sent_messages) == 3
    chat_id3, text3, _, _ = context.bot.sent_messages[2]
    assert chat_id3 == 444
    assert "<blockquote>Adding to what my colleague mentioned above.</blockquote>" in text3


def test_start_command_sends_photo_when_logo_exists(monkeypatch):
    update = FakeUpdate(user_id=123)
    context = FakeContext()
    
    monkeypatch.setattr(os.path, "exists", lambda path: True)
    
    from unittest.mock import mock_open
    m = mock_open(read_data=b"fake photo data")
    monkeypatch.setattr("builtins.open", m)
    
    asyncio.run(bot.start_command(update, context))
    
    assert len(update.message.reply_photo_calls) == 1
    assert "AWS SBG AASTU Support Bot!" in update.message.reply_photo_calls[0]["caption"]
    assert "<b>Join our community:</b> @AWSAASTU" in update.message.reply_photo_calls[0]["caption"]
    assert update.message.reply_photo_calls[0]["parse_mode"] == ParseMode.HTML


def test_start_command_falls_back_to_text_when_logo_missing(monkeypatch):
    update = FakeUpdate(user_id=123)
    context = FakeContext()
    
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    
    asyncio.run(bot.start_command(update, context))
    
    assert len(update.message.reply_photo_calls) == 0
    assert len(update.message.reply_text_calls) == 1
    assert "AWS SBG AASTU Support Bot!" in update.message.reply_text_calls[0]["text"]
    assert "<b>Join our community:</b> @AWSAASTU" in update.message.reply_text_calls[0]["text"]
    assert update.message.reply_text_calls[0]["parse_mode"] == ParseMode.HTML


def test_create_application_initializes_handlers():
    app = bot.create_application(token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    assert app is not None


def test_handle_admin_edited_reply_updates_member_chat():
    asyncio.run(db.reset_db())
    context = FakeContext()
    
    # Pre-populate mapping
    asyncio.run(db.save_admin_reply_mapping(admin_message_id=88, user_chat_id=777, delivered_message_id=99))
    
    edit_update = FakeUpdate(user_id=1, text="Here is the corrected response.", is_edited=True)
    edit_update.edited_message.message_id = 88

    asyncio.run(bot.handle_admin_edited_reply(edit_update, context))

    assert len(context.bot.edited_messages) == 1
    chat_id, message_id, text, parse_mode = context.bot.edited_messages[0]
    assert chat_id == 777
    assert message_id == 99
    assert "<i>(edited)</i>" in text
    assert "<blockquote>Here is the corrected response.</blockquote>" in text
    assert parse_mode == ParseMode.HTML


def test_handle_user_edited_feedback_updates_admin_group_card():
    asyncio.run(db.reset_db())
    context = FakeContext()
    original_admin_group_id = bot.ADMIN_GROUP_ID
    bot.ADMIN_GROUP_ID = 999
    
    # Save submission with user_message_id
    asyncio.run(db.save_feedback_submission(message_id=100, sender_chat_id=555, sender_name="Jane", user_message_id=200))
    
    edit_update = FakeUpdate(user_id=555, text="Updated feedback description.", is_edited=True)
    edit_update.edited_message.message_id = 200
    edit_update.effective_user.first_name = "Jane"
    edit_update.effective_user.username = "jane_doe"

    asyncio.run(bot.handle_user_edited_feedback(edit_update, context))

    assert len(context.bot.edited_messages) == 1
    chat_id, message_id, text, parse_mode = context.bot.edited_messages[0]
    assert chat_id == 999
    assert message_id == 100
    assert "<i>(edited by user)</i>" in text
    assert "<blockquote>Updated feedback description.</blockquote>" in text
    assert parse_mode == ParseMode.HTML
    
    bot.ADMIN_GROUP_ID = original_admin_group_id





