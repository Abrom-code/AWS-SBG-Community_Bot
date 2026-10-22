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


class FakePhotoSize:
    def __init__(self, file_id="fake_photo_123"):
        self.file_id = file_id


class FakeMessage:
    def __init__(self, text="", chat_id=1, message_id=50, parent=None, photo=None, caption=None, caption_entities=None, entities=None):
        self.text = text
        self.chat_id = chat_id
        self.message_id = message_id
        self.parent = parent
        self.photo = photo
        self.caption = caption
        self.caption_entities = caption_entities or []
        self.entities = entities or []
        self.reply_text_calls = []
        self.reply_photo_calls = []
        self.reply_to_message = None
        self.edited_text = None

    @property
    def caption_html(self):
        return self.caption

    @property
    def text_html(self):
        return self.text

    async def reply_text(self, text, parse_mode=None, reply_markup=None, protect_content=None, **kwargs):
        msg = FakeMessage(text=text, chat_id=self.chat_id, message_id=self.message_id + len(self.reply_text_calls) + 1, parent=self)
        self.reply_text_calls.append(
            {
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "protect_content": protect_content,
            }
        )
        return msg

    async def edit_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.edited_text = text
        self.text = text
        self.reply_text_calls.append(
            {
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )
        if self.parent:
            self.parent.reply_text_calls.append(
                {
                    "text": text,
                    "parse_mode": parse_mode,
                    "reply_markup": reply_markup,
                }
            )
        return self

    async def reply_photo(self, photo, caption=None, parse_mode=None, reply_markup=None, protect_content=None, **kwargs):
        self.reply_photo_calls.append(
            {
                "photo": photo,
                "caption": caption,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "protect_content": protect_content,
            }
        )
        return self


class FakeChat:
    def __init__(self, chat_id=1, chat_type="private"):
        self.id = chat_id
        self.type = chat_type


class FakeCallbackQuery:
    def __init__(self, user_id=42, data="", message=None):
        self.from_user = FakeUser(user_id=user_id)
        self.data = data
        self.message = message or FakeMessage(chat_id=1, message_id=1)
        self.answered = False
        self.answered_text = None
        self.edited_text = None
        self.reply_markup = None

    async def answer(self, text=None, show_alert=False):
        self.answered = True
        self.answered_text = text

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
        self.edited_text = text
        self.reply_markup = reply_markup


class FakeUpdate:
    def __init__(self, user_id=42, text="", chat_id=1, reply_to_message_id=None, is_edited=False, chat_type="private", callback_query=None, photo=None, caption=None, caption_entities=None, entities=None):
        self.effective_user = FakeUser(user_id=user_id)
        self.effective_chat = FakeChat(chat_id=chat_id, chat_type=chat_type)
        self.callback_query = callback_query
        msg = FakeMessage(text=text, chat_id=chat_id, photo=photo, caption=caption, caption_entities=caption_entities, entities=entities)
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
        self.send_message_calls = []
        self.send_photo_calls = []
        self.edited_messages = []
        self.deleted_messages = []

    async def send_chat_action(self, chat_id, action, **kwargs):
        pass

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, protect_content=None, **kwargs):
        message_id = len(self.sent_messages) + 1
        self.sent_messages.append((chat_id, text, message_id, parse_mode))
        self.send_message_calls.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return type("SentMessage", (), {"message_id": message_id})()

    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None, protect_content=None, **kwargs):
        message_id = len(self.sent_messages) + 1
        self.sent_messages.append((chat_id, caption, message_id, parse_mode))
        self.send_photo_calls.append({"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": parse_mode})
        return type("SentMessage", (), {"message_id": message_id})()

    async def edit_message_text(self, chat_id, message_id, text, parse_mode=None, reply_markup=None):
        self.edited_messages.append((chat_id, message_id, text, parse_mode))
        return type("SentMessage", (), {"message_id": message_id})()

    async def delete_message(self, chat_id, message_id):
        self.deleted_messages.append((chat_id, message_id))
        return True

    async def delete_messages(self, chat_id, message_ids):
        for mid in message_ids:
            self.deleted_messages.append((chat_id, mid))
        return True

    async def set_my_commands(self, commands):
        self.commands = commands
        return True

    async def set_chat_menu_button(self, menu_button=None, chat_id=None):
        self.menu_button = menu_button
        return True


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()
        self.user_data = {}


def test_get_main_menu_keyboard_contains_expected_actions():
    keyboard = bot.get_main_menu_keyboard()

    labels = [
        [button.text for button in row]
        for row in keyboard.keyboard
    ]

    assert labels == [
        ["Education", "Next Event"],
        ["Ask Question", "Feedback"],
        ["About Us", "Help"],
    ]

    ch_keyboard = bot.get_challenge_menu_keyboard()
    ch_labels = [[button.text for button in row] for row in ch_keyboard.keyboard]
    assert ch_labels == [
        ["Leaderboards", "Past Challenges"],
        ["Scoring Rules", "Guidelines"],
        ["Main Menu"],
    ]

    fb_keyboard = bot.get_feedback_menu_keyboard()
    fb_labels = [[button.text for button in row] for row in fb_keyboard.keyboard]
    assert fb_labels == [
        ["Ask Question", "Feedback"],
        ["About Support", "Main Menu"],
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

    assert update.message.reply_text_calls[0]["text"].startswith("✦")
    assert "/start" in update.message.reply_text_calls[0]["text"]
    assert "/education" in update.message.reply_text_calls[0]["text"]
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


def test_support_command_sets_waiting_state_and_removes_keyboard():
    asyncio.run(db.reset_db())
    update = FakeUpdate(user_id=112)
    context = FakeContext()

    asyncio.run(bot.support_command(update, context))

    state = asyncio.run(db.get_user_state(112))
    assert state == bot.WAITING_FOR_QUESTION
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
    assert update.message.reply_text_calls[0]["text"] == "▪️ Feedback submission cancelled."

    labels = [
        [button.text for button in row]
        for row in update.message.reply_text_calls[0]["reply_markup"].keyboard
    ]
    assert labels == [
        ["Education", "Next Event"],
        ["Ask Question", "Feedback"],
        ["About Us", "Help"],
    ]


def test_cancel_command_clears_question_state_and_restores_keyboard():
    asyncio.run(db.reset_db())
    update = FakeUpdate(user_id=223)
    context = FakeContext()
    asyncio.run(db.set_user_state(223, bot.WAITING_FOR_QUESTION))

    asyncio.run(bot.cancel_command(update, context))

    state = asyncio.run(db.get_user_state(223))
    assert state is None
    assert update.message.reply_text_calls[0]["text"] == "▪️ Question submission cancelled."


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
    assert "✦ <b>Feedback</b>" in text
    assert "• <b>From:</b>" in text
    assert "• <b>User ID:</b> <code>333</code>" in text
    assert "<blockquote>This is a test feedback message</blockquote>" in text
    
    submission = asyncio.run(db.get_feedback_submission(message_id))
    assert submission["sender_chat_id"] == 333
    assert submission["ticket_type"] == "feedback"
    assert update.message.reply_text_calls[-1]["text"].startswith("✓ <b>Thank you!")
    assert "feedback" in update.message.reply_text_calls[-1]["text"].lower()
    assert update.message.reply_text_calls[-1]["parse_mode"] == ParseMode.HTML
    
    state = asyncio.run(db.get_user_state(333))
    assert state is None

    bot.ADMIN_GROUP_ID = original_admin_group_id


def test_handle_message_forwards_question_to_admin_group_and_returns_success():
    asyncio.run(db.reset_db())
    original_admin_group_id = bot.ADMIN_GROUP_ID
    bot.ADMIN_GROUP_ID = 999

    update = FakeUpdate(user_id=334, text="How do I join the Saturday Education Track stream?")
    context = FakeContext()
    asyncio.run(db.set_user_state(334, bot.WAITING_FOR_QUESTION))

    asyncio.run(bot.handle_message(update, context))

    assert len(context.bot.sent_messages) == 1
    chat_id, text, message_id, parse_mode = context.bot.sent_messages[0]
    assert chat_id == 999
    assert parse_mode == ParseMode.HTML
    assert "✦ <b>Question</b>" in text
    assert "• <b>From:</b>" in text
    assert "• <b>User ID:</b> <code>334</code>" in text
    assert "<blockquote>How do I join the Saturday Education Track stream?</blockquote>" in text
    
    submission = asyncio.run(db.get_feedback_submission(message_id))
    assert submission["sender_chat_id"] == 334
    assert submission["ticket_type"] == "question"
    assert update.message.reply_text_calls[-1]["text"].startswith("✓ <b>Thank you!")
    assert "question" in update.message.reply_text_calls[-1]["text"].lower()
    assert update.message.reply_text_calls[-1]["parse_mode"] == ParseMode.HTML
    
    state = asyncio.run(db.get_user_state(334))
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
    assert "✦ <b>Response from the AWS Student Builder Core Team</b>" in text
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
    assert "AWS SBG AASTU Community Bot" in update.message.reply_photo_calls[0]["caption"]
    assert "<b>Join our community:</b> @AWSAASTU" in update.message.reply_photo_calls[0]["caption"]
    assert update.message.reply_photo_calls[0]["parse_mode"] == ParseMode.HTML


def test_start_command_falls_back_to_text_when_logo_missing(monkeypatch):
    update = FakeUpdate(user_id=123)
    context = FakeContext()
    
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    
    asyncio.run(bot.start_command(update, context))
    
    assert len(update.message.reply_photo_calls) == 0
    assert len(update.message.reply_text_calls) == 1
    assert "AWS SBG AASTU Community Bot" in update.message.reply_text_calls[0]["text"]
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
    assert "✦ <b>Feedback</b> <i>(edited)</i>" in text
    assert "• <b>User ID:</b> <code>555</code>" in text
    assert "<blockquote>Updated feedback description.</blockquote>" in text

def test_challenge_hub_and_feedback_hub_commands():
    asyncio.run(db.reset_db())
    update = FakeUpdate(user_id=123)
    context = FakeContext()

    asyncio.run(bot.challenge_hub_command(update, context))
    assert len(update.message.reply_text_calls) == 1
    assert "Challenge Center Update" in update.message.reply_text_calls[0]["text"]
    assert "Education Track" in update.message.reply_text_calls[0]["text"]

    asyncio.run(bot.feedback_hub_command(update, context))
    assert len(update.message.reply_text_calls) == 2
    assert "Feedback & Community Support Hub" in update.message.reply_text_calls[1]["text"]
    assert any("Feedback" in b.text for row in update.message.reply_text_calls[1]["reply_markup"].keyboard for b in row)


def test_main_menu_challenges_click_displays_active_challenges_directly():
    """Verifies that clicking 'Challenges' informs the user that challenges are paused and directs to education track."""
    asyncio.run(db.reset_db())
    update = FakeUpdate(user_id=123, text="Challenges")
    context = FakeContext()

    asyncio.run(bot.handle_message(update, context))
    assert len(update.message.reply_text_calls) == 1
    assert "Challenge Center Update" in update.message.reply_text_calls[0]["text"]
    assert "Education Track" in update.message.reply_text_calls[0]["text"]


def test_direct_feedback_and_support_navigation():
    asyncio.run(db.reset_db())
    
    # Test 1: Clicking "🔹 Feedback" starts feedback flow
    update1 = FakeUpdate(user_id=777, text="🔹 Feedback")
    context1 = FakeContext()
    asyncio.run(bot.handle_message(update1, context1))
    assert len(update1.message.reply_text_calls) == 1
    assert "Please type your message below" in update1.message.reply_text_calls[0]["text"]
    state1 = asyncio.run(db.get_user_state(777))
    assert state1 == bot.WAITING_FOR_FEEDBACK

    # Test 2: Clicking "🔹 Ask Question" starts question flow
    update2 = FakeUpdate(user_id=778, text="🔹 Ask Question")
    context2 = FakeContext()
    asyncio.run(bot.handle_message(update2, context2))
    assert len(update2.message.reply_text_calls) == 1
    assert "Please type your question below" in update2.message.reply_text_calls[0]["text"]
    state2 = asyncio.run(db.get_user_state(778))
    assert state2 == bot.WAITING_FOR_QUESTION

    # Test 3: Legacy "💬 Feedback & Support" opens hub menu with options
    update3 = FakeUpdate(user_id=779, text="💬 Feedback & Support")
    context3 = FakeContext()
    asyncio.run(bot.handle_message(update3, context3))
    assert len(update3.message.reply_text_calls) == 1
    assert "Feedback & Community Support Hub" in update3.message.reply_text_calls[0]["text"]


def test_handle_admin_reply_to_question_ticket():
    asyncio.run(db.reset_db())
    context = FakeContext()
    
    # Save submission with ticket_type="question"
    asyncio.run(db.save_feedback_submission(15, 888, "Question Asker", ticket_type="question"))

    update = FakeUpdate(user_id=1, text="The education track begins at 2:00 PM this Saturday.")
    update.message.message_id = 99
    update.message.reply_to_message = type("ReplyToMessage", (), {"message_id": 15})()

    asyncio.run(bot.handle_admin_reply(update, context))

    assert len(context.bot.sent_messages) == 1
    chat_id, text, _, parse_mode = context.bot.sent_messages[0]
    assert chat_id == 888
    assert "✦ <b>Answer from the AWS Student Builder Core Team</b>" in text
    assert "The education track begins at 2:00 PM this Saturday." in text


def test_handle_user_edited_question_updates_admin_group_card():
    asyncio.run(db.reset_db())
    context = FakeContext()
    original_admin_group_id = bot.ADMIN_GROUP_ID
    bot.ADMIN_GROUP_ID = 999
    
    # Save question submission with user_message_id
    asyncio.run(db.save_feedback_submission(message_id=101, sender_chat_id=666, sender_name="John", user_message_id=300, ticket_type="question"))
    
    edit_update = FakeUpdate(user_id=666, text="Updated question details.", is_edited=True)
    edit_update.edited_message.message_id = 300
    edit_update.effective_user.first_name = "John"
    edit_update.effective_user.username = "john_dev"

    asyncio.run(bot.handle_user_edited_feedback(edit_update, context))

    assert len(context.bot.edited_messages) == 1
    chat_id, message_id, text, parse_mode = context.bot.edited_messages[0]
    assert "✦ <b>Question</b> <i>(edited)</i>" in text
    assert "<i>(edited)</i>" in text
    assert "• <b>User ID:</b> <code>666</code>" in text
    assert "<blockquote>Updated question details.</blockquote>" in text
    bot.ADMIN_GROUP_ID = original_admin_group_id


def test_scoring_rules_command_renders_guide():
    from app.challenge.handlers import scoring_rules_command
    update = FakeUpdate(user_id=123)
    context = FakeContext()
    asyncio.run(scoring_rules_command(update, context))
    assert len(update.message.reply_text_calls) == 1
    call = update.message.reply_text_calls[0]
    assert "How Scoring Works" in call["text"]
    assert "Two-Factor Scoring Formula" in call["text"]
    assert call["reply_markup"] is not None


def test_guidelines_command_and_callback():
    from app.challenge.handlers import guidelines_command, handle_guidelines_callback, challenge_command
    from app.challenge.keyboards import get_challenge_start_keyboard
    from app.challenge.service import create_challenge, update_challenge_status

    # Test /guidelines command
    update = FakeUpdate(user_id=123)
    context = FakeContext()
    asyncio.run(guidelines_command(update, context))
    assert len(update.message.reply_text_calls) == 1
    call = update.message.reply_text_calls[0]
    assert "Community Guidelines & Code of Conduct" in call["text"]
    assert "Strictly One Account" in call["text"]
    assert "No AI or Automation" in call["text"]
    assert "Screenshots Disabled" in call["text"]
    assert call["reply_markup"] is not None

    # Test start keyboard only has the contextual Start button (other actions on bottom menu)
    kb = get_challenge_start_keyboard(challenge_id=99)
    button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Start Challenge" in button_texts
    assert len(button_texts) == 1

    # Test callback query
    cb_query = FakeCallbackQuery(data="ch_guidelines", user_id=123)
    cb_update = FakeUpdate(callback_query=cb_query)
    asyncio.run(handle_guidelines_callback(cb_update, context))
    assert cb_query.answered is True
    assert cb_query.edited_text is not None
    assert "Community Guidelines & Code of Conduct" in cb_query.edited_text


def test_admin_command_security_restrictions(monkeypatch):
    from app.challenge.admin import admin_command

    # 1. Non-admin user tries to access /admin
    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    monkeypatch.setenv("ADMIN_GROUP_CHAT_ID", "-1001234567")

    user_update = FakeUpdate(user_id=123)
    user_context = FakeContext()
    asyncio.run(admin_command(user_update, user_context))

    assert len(user_update.message.reply_text_calls) == 1
    assert "Access Denied" in user_update.message.reply_text_calls[0]["text"]

    # 2. Authorized admin accesses /admin
    admin_update = FakeUpdate(user_id=99999)
    admin_context = FakeContext()
    asyncio.run(admin_command(admin_update, admin_context))

    assert len(admin_update.message.reply_text_calls) == 1
    assert "AWS SBG Admin Operations Center" in admin_update.message.reply_text_calls[0]["text"]
    assert admin_update.message.reply_text_calls[0]["reply_markup"] is not None


def test_past_challenges_command_and_shortcuts():
    from app.challenge.handlers import past_challenges_command
    from app.challenge.service import create_challenge, update_challenge_status

    update = FakeUpdate(user_id=123)
    context = FakeContext()

    # Create an ended past challenge
    ch_id = asyncio.run(create_challenge(title="Archived Cloud Challenge"))
    asyncio.run(update_challenge_status(ch_id, "ENDED"))

    asyncio.run(past_challenges_command(update, context))

    assert len(update.message.reply_text_calls) == 1
    assert "AWS Builder Challenge Archive" in update.message.reply_text_calls[0]["text"]
    assert update.message.reply_text_calls[0]["reply_markup"] is not None


def test_admin_broadcast_presets_and_workflow(monkeypatch):
    from app.challenge.admin import handle_admin_callback

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")

    # 1. Populate community audience
    asyncio.run(db.set_user_state(501, "ACTIVE"))
    asyncio.run(db.set_user_state(502, "ACTIVE"))

    # 2. Click broadcast -> directly prompts to enter announcement text
    q1 = FakeCallbackQuery(user_id=99999, data="adm_broadcast")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    ctx1 = FakeContext()

    asyncio.run(handle_admin_callback(up1, ctx1))
    assert "Community Broadcast Center" in q1.edited_text
    state = asyncio.run(db.get_user_state(99999))
    assert state == "WAITING_FOR_ADMIN_BROADCAST"

    # 3. Admin sends the announcement message text
    up_msg = FakeUpdate(user_id=99999, text="🏆 Important AWS Education Track Announcement!")
    asyncio.run(bot.handle_message(up_msg, ctx1))
    assert "BROADCAST PREVIEW" in up_msg.message.reply_text_calls[0]["text"]
    assert ctx1.user_data["bcast_text"] == "🏆 Important AWS Education Track Announcement!"

    # 4. Confirm & Send to all
    q3 = FakeCallbackQuery(user_id=99999, data="adm_bcast_send:custom")
    up3 = FakeUpdate(user_id=99999, callback_query=q3)

    asyncio.run(handle_admin_callback(up3, ctx1))
    assert "Broadcast Complete" in q3.edited_text
    assert len(ctx1.bot.send_message_calls) >= 2


def test_admin_monthly_report_callback_and_broadcast(monkeypatch):
    from app.challenge.admin import handle_admin_callback

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")

    # 1. Open monthly report
    q1 = FakeCallbackQuery(user_id=99999, data="adm_report")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    ctx1 = FakeContext()

    asyncio.run(handle_admin_callback(up1, ctx1))
    assert "AWS Student Builder Monthly Activity Report" in q1.edited_text
    assert q1.reply_markup is not None

    # 2. Select broadcast report preset
    q2 = FakeCallbackQuery(user_id=99999, data="adm_bcast_preset:report")
    up2 = FakeUpdate(user_id=99999, callback_query=q2)
    ctx2 = FakeContext()

    asyncio.run(handle_admin_callback(up2, ctx2))
    assert "BROADCAST PREVIEW (Monthly Report)" in q2.edited_text
    assert "bcast_text" in ctx2.user_data


def test_unknown_command_fallback_replies_gracefully():
    update = FakeUpdate(user_id=12345, text="/notification")
    context = FakeContext()

    asyncio.run(bot.unknown_command_handler(update, context))

    assert len(update.message.reply_text_calls) == 1
    resp = update.message.reply_text_calls[0]["text"]
    assert "Unrecognized Command" in resp
    assert "/notification" in resp
    assert "/challenge" in resp
    assert "/feedback" in resp
    assert update.message.reply_text_calls[0]["reply_markup"] is not None


def test_custom_date_challenge_creation_flow(monkeypatch):
    from app.challenge.admin import handle_admin_callback

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")

    # 1. Trigger custom date schedule callback
    q = FakeCallbackQuery(user_id=99999, data="adm_cr_custom_date")
    up = FakeUpdate(user_id=99999, callback_query=q)
    ctx = FakeContext()

    asyncio.run(handle_admin_callback(up, ctx))
    assert "Set Custom Challenge Schedule" in q.edited_text

    state = asyncio.run(db.get_user_state(99999))
    assert state == "WAITING_FOR_ADMIN_SCHEDULE"

    # 2. Send custom date range
    up_msg = FakeUpdate(user_id=99999, text="2026-09-10 14:00 to 2026-09-17 18:00")
    ctx_msg = FakeContext()

    asyncio.run(bot.handle_message(up_msg, ctx_msg))

    resp = up_msg.message.reply_text_calls[0]["text"]
    assert "Challenge" in resp
    assert "Sep 10, 2026" in resp
    assert up_msg.message.reply_text_calls[0]["reply_markup"] is not None


def test_admin_panel_keyboard_layout_and_no_question_bank():
    from app.challenge.keyboards import get_admin_panel_keyboard
    kb = get_admin_panel_keyboard()
    button_rows = [[btn.text for btn in row] for row in kb.inline_keyboard]
    flat_buttons = [btn.text for row in kb.inline_keyboard for btn in row]

    # Verify only contextual actions remain inline (rest on bottom menu)
    assert flat_buttons in (
        [
            "🔹 Send Community Broadcast",
            "🔹 Manage Education",
            "🔹 Manage Next Event",
            "▫️ Community Stats",
        ],
        [
            "📢 Send Community Broadcast",
            "🔹 Manage Education",
            "🔹 Manage Next Event",
            "📊 Community Stats",
        ],
    )
    # Question Bank must NOT be in the admin panel
    assert not any("Question Bank" in b for b in flat_buttons)


def test_admin_interactive_wizard_and_single_question_flow(monkeypatch):
    from app.challenge.admin import handle_admin_callback

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")

    # 1. Start Challenge Wizard
    q1 = FakeCallbackQuery(user_id=99999, data="adm_create_ch")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    ctx1 = FakeContext()

    asyncio.run(handle_admin_callback(up1, ctx1))
    assert "Create Challenge Wizard" in q1.edited_text

    # 2. Enter Title & Category
    up2 = FakeUpdate(user_id=99999, text="AWS Lambda & EventBridge Masterclass | Serverless")
    ctx2 = FakeContext()
    asyncio.run(bot.handle_message(up2, ctx2))

    assert len(up2.message.reply_text_calls) == 1
    assert "AWS Lambda &amp; EventBridge Masterclass" in up2.message.reply_text_calls[0]["text"]
    assert ctx2.user_data.get("wiz_title") == "AWS Lambda & EventBridge Masterclass"
    assert ctx2.user_data.get("wiz_category") == "Serverless"

    # 3. Schedule Challenge
    q_sched = FakeCallbackQuery(user_id=99999, data="adm_cr_sched:now")
    up_sched = FakeUpdate(user_id=99999, callback_query=q_sched)
    asyncio.run(handle_admin_callback(up_sched, ctx2))
    assert "Challenge" in q_sched.edited_text

    # 4. Add Question Specifically to this Challenge
    q_single = FakeCallbackQuery(user_id=99999, data="adm_add_q_to_ch:1")
    up_s = FakeUpdate(user_id=99999, callback_query=q_single)
    ctx_s = FakeContext()
    asyncio.run(handle_admin_callback(up_s, ctx_s))
    assert "Add Question Specifically for Challenge #1" in q_single.edited_text

    question_text = (
        "What is Amazon EventBridge?\n"
        "A: A managed relational database\n"
        "B: A serverless event bus\n"
        "C: A compute container service\n"
        "D: A content delivery network\n"
        "Answer: B\n"
        "Category: Serverless\n"
        "Difficulty: EASY\n"
        "Explanation: EventBridge is a serverless event bus service."
    )
    up_q = FakeUpdate(user_id=99999, text=question_text)
    asyncio.run(bot.handle_message(up_q, ctx_s))

    assert len(up_q.message.reply_text_calls) == 1
    assert "Added to Challenge #1!" in up_q.message.reply_text_calls[0]["text"]


def test_admin_challenge_edit_and_delete_flow(monkeypatch):
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import create_challenge, get_challenge

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")

    ch_id = asyncio.run(create_challenge(title="Initial Title", category="Compute"))

    # 1. Edit Title
    q_edit = FakeCallbackQuery(user_id=99999, data=f"adm_edit_title:{ch_id}")
    up_e = FakeUpdate(user_id=99999, callback_query=q_edit)
    ctx_e = FakeContext()
    asyncio.run(handle_admin_callback(up_e, ctx_e))

    up_e_msg = FakeUpdate(user_id=99999, text="Updated Architecture Sprint | Networking")
    ctx_e_msg = FakeContext()
    ctx_e_msg.user_data["edit_ch_id"] = ch_id
    asyncio.run(bot.handle_message(up_e_msg, ctx_e_msg))

    ch_updated = asyncio.run(get_challenge(ch_id))
    assert ch_updated["title"] == "Updated Architecture Sprint"
    assert ch_updated["category"] == "Networking"

    # 2. Delete Challenge
    q_del = FakeCallbackQuery(user_id=99999, data=f"adm_del_conf:{ch_id}")
    up_d = FakeUpdate(user_id=99999, callback_query=q_del)
    ctx_d = FakeContext()
    asyncio.run(handle_admin_callback(up_d, ctx_d))

    assert "permanently deleted" in q_del.edited_text
    assert asyncio.run(get_challenge(ch_id)) is None


def test_admin_challenge_schedule_and_timer_edit_flow(monkeypatch):
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import create_challenge, get_challenge

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    asyncio.run(db.reset_db())

    ch_id = asyncio.run(create_challenge(title="Schedule & Timer Test", category="Testing"))
    from app.challenge.service import add_question_to_challenge
    asyncio.run(add_question_to_challenge(ch_id, {
        "question_text": "Sample test question?",
        "option_a": "Option A", "option_b": "Option B", "option_c": "Option C", "option_d": "Option D",
        "correct_option": "A", "category": "Testing", "explanation": "Explanation",
    }))

    # 1. Edit Schedule via Preset
    q_s1 = FakeCallbackQuery(user_id=99999, data=f"adm_sched_set:{ch_id}:now:7d")
    up_s1 = FakeUpdate(user_id=99999, callback_query=q_s1)
    ctx = FakeContext()
    asyncio.run(handle_admin_callback(up_s1, ctx))
    ch1 = asyncio.run(get_challenge(ch_id))
    assert ch1["status"] == "LIVE"
    assert ch1["starts_at"] is not None

    # 2. Edit Schedule via Custom Input
    q_s2 = FakeCallbackQuery(user_id=99999, data=f"adm_sched_custom:{ch_id}")
    up_s2 = FakeUpdate(user_id=99999, callback_query=q_s2)
    asyncio.run(handle_admin_callback(up_s2, ctx))
    assert "Custom Schedule" in q_s2.edited_text

    up_msg_s = FakeUpdate(user_id=99999, text="2026-10-01 10:00 to 2026-10-08 10:00")
    asyncio.run(bot.handle_message(up_msg_s, ctx))
    assert "Schedule Updated" in up_msg_s.message.reply_text_calls[0]["text"]

    ch2 = asyncio.run(get_challenge(ch_id))
    assert "2026-10-01" in ch2["starts_at"]
    assert "2026-10-08" in ch2["ends_at"]

    # 3. Edit Timer via Preset (15 mins)
    q_t1 = FakeCallbackQuery(user_id=99999, data=f"adm_timer_set:{ch_id}:15")
    up_t1 = FakeUpdate(user_id=99999, callback_query=q_t1)
    asyncio.run(handle_admin_callback(up_t1, ctx))
    ch3 = asyncio.run(get_challenge(ch_id))
    assert ch3["duration_seconds"] == 900

    # 4. Edit Timer via Custom Minutes
    q_t2 = FakeCallbackQuery(user_id=99999, data=f"adm_timer_custom:{ch_id}")
    up_t2 = FakeUpdate(user_id=99999, callback_query=q_t2)
    asyncio.run(handle_admin_callback(up_t2, ctx))
    assert "Custom Exam Time Limit" in q_t2.edited_text

    up_msg_t = FakeUpdate(user_id=99999, text="25")
    asyncio.run(bot.handle_message(up_msg_t, ctx))
    assert "25 minutes" in up_msg_t.message.reply_text_calls[0]["text"]

    ch4 = asyncio.run(get_challenge(ch_id))
    assert ch4["duration_seconds"] == 1500



def test_admin_leaderboard_view_and_monthly_report_top3_builders(monkeypatch):
    from app.challenge.admin import handle_admin_callback
    from app.challenge import service
    from app.challenge.service import (
        create_challenge,
        register_or_get_participant,
        start_participant_quiz,
        get_next_question_for_participant,
        record_answer_and_advance,
        link_questions_to_challenge,
        update_challenge_status,
        create_question,
    )

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    asyncio.run(db.reset_db())

    # Create questions and challenge
    asyncio.run(create_question(
        question_text="What is S3?",
        option_a="Object Storage",
        option_b="Compute",
        option_c="Database",
        option_d="Network",
        correct_option="A",
    ))
    ch_id = asyncio.run(create_challenge(title="Storage Deep Dive"))
    asyncio.run(link_questions_to_challenge(ch_id))
    asyncio.run(update_challenge_status(ch_id, "LIVE"))

    # Participant 1: Dawit
    asyncio.run(register_or_get_participant(ch_id, 101, "Dawit Tadesse", username="dawit_cloud"))
    asyncio.run(start_participant_quiz(ch_id, 101))
    asyncio.run(get_next_question_for_participant(ch_id, 101))
    p1_d = asyncio.run(register_or_get_participant(ch_id, 101))
    asyncio.run(record_answer_and_advance(ch_id, 101, p1_d["current_option_order"]["_display_correct"], 0))

    # Participant 2: Bethlehem
    asyncio.run(register_or_get_participant(ch_id, 102, "Bethlehem Hailu", username="betty_dev"))
    asyncio.run(start_participant_quiz(ch_id, 102))
    asyncio.run(get_next_question_for_participant(ch_id, 102))
    p2_d = asyncio.run(register_or_get_participant(ch_id, 102))
    asyncio.run(record_answer_and_advance(ch_id, 102, p2_d["current_option_order"]["_display_correct"], 0))

    # 1. Admin views Monthly Report
    q_rep = FakeCallbackQuery(user_id=99999, data="adm_report")
    up_rep = FakeUpdate(user_id=99999, callback_query=q_rep)
    ctx_rep = FakeContext()
    asyncio.run(handle_admin_callback(up_rep, ctx_rep))

    assert "Top 3 Builders of the Month:" in q_rep.edited_text
    assert "Dawit Tadesse" in q_rep.edited_text

    # 2. Admin views Leaderboards menu
    q_lb = FakeCallbackQuery(user_id=99999, data="adm_leaderboards")
    up_lb = FakeUpdate(user_id=99999, callback_query=q_lb)
    ctx_lb = FakeContext()
    asyncio.run(handle_admin_callback(up_lb, ctx_lb))
    assert "Admin Leaderboard & Builder Standings" in q_lb.edited_text

    # 3. Admin views Active Challenge leaderboard
    q_weekly = FakeCallbackQuery(user_id=99999, data=f"adm_lb_view:weekly:{ch_id}")
    up_w = FakeUpdate(user_id=99999, callback_query=q_weekly)
    ctx_w = FakeContext()
    asyncio.run(handle_admin_callback(up_w, ctx_w))
    assert "Active Challenge Leaderboard" in q_weekly.edited_text
    assert "Dawit Tadesse" in q_weekly.edited_text
    assert "[<code>101</code>]" in q_weekly.edited_text


def test_admin_paste_csv_text_import(monkeypatch):
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import create_challenge, get_challenge_questions

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    asyncio.run(db.reset_db())

    ch_id = asyncio.run(create_challenge(title="Storage Challenge", category="Storage"))

    # 1. Tap Import CSV to Challenge button
    q_csv = FakeCallbackQuery(user_id=99999, data=f"adm_import_csv_to_ch:{ch_id}")
    up_csv = FakeUpdate(user_id=99999, callback_query=q_csv)
    ctx_csv = FakeContext()
    asyncio.run(handle_admin_callback(up_csv, ctx_csv))
    assert f"Import Questions for Challenge #{ch_id}" in q_csv.edited_text

    # 2. Paste raw CSV lines
    csv_payload = (
        "What is DynamoDB?,NoSQL Database,Relational DB,Object Storage,Queue,A,MEDIUM,Database,10,Managed NoSQL\n"
        "What is SQS?,Message Queue,Compute,Cache,DNS,A,EASY,Application,10,Decoupled queue"
    )
    up_msg = FakeUpdate(user_id=99999, text=csv_payload)
    asyncio.run(bot.handle_message(up_msg, ctx_csv))

    assert len(up_msg.message.reply_text_calls) > 0
    all_responses = " ".join([c["text"] for c in up_msg.message.reply_text_calls])
    assert f"Questions Imported for Challenge #{ch_id}!" in all_responses
    assert "<code>2</code>" in all_responses

    questions = asyncio.run(get_challenge_questions(ch_id))
    assert len(questions) == 2


def test_admin_challenge_specific_question_flow(monkeypatch):
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import create_challenge, get_challenge_questions

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    asyncio.run(db.reset_db())

    # Create challenge
    ch_id = asyncio.run(create_challenge(title="VPC & Networking Sprint", category="Networking"))

    # 1. Admin taps Add Question to Challenge
    q_cb = FakeCallbackQuery(user_id=99999, data=f"adm_add_q_to_ch:{ch_id}")
    up_cb = FakeUpdate(user_id=99999, callback_query=q_cb)
    ctx = FakeContext()
    asyncio.run(handle_admin_callback(up_cb, ctx))
    assert f"Add Question Specifically for Challenge #{ch_id}" in q_cb.edited_text

    # 2. Admin sends question text
    q_text_input = """What is an Amazon VPC?
A: Virtual Private Cloud
B: Virtual Public Container
C: Volume Partition Cluster
D: Vector Processing Core
Answer: A
Category: Networking
Difficulty: EASY
Explanation: Amazon VPC lets you provision a logically isolated section of the AWS Cloud."""

    up_msg = FakeUpdate(user_id=99999, text=q_text_input)
    asyncio.run(bot.handle_message(up_msg, ctx))

    assert len(up_msg.message.reply_text_calls) > 0
    resp_text = up_msg.message.reply_text_calls[0]["text"]
    assert f"Added to Challenge #{ch_id}!" in resp_text

    # Verify questions attached specifically to this challenge
    ch_q = asyncio.run(get_challenge_questions(ch_id))
    assert len(ch_q) == 1
    assert ch_q[0]["question_text"] == "What is an Amazon VPC?"
    assert ch_q[0]["correct_option"] == "A"

    # 3. View questions in challenge
    q_view = FakeCallbackQuery(user_id=99999, data=f"adm_view_ch_q:{ch_id}")
    up_view = FakeUpdate(user_id=99999, callback_query=q_view)
    asyncio.run(handle_admin_callback(up_view, ctx))
    assert "What is an Amazon VPC?" in q_view.edited_text


def test_admin_bottom_menu_navigation_buttons(monkeypatch):
    """Verifies that all 6 bottom reply keyboard buttons for Admin function properly."""
    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    ctx = FakeContext()

    # 1. ➕ Create Challenge
    up = FakeUpdate(user_id=99999, text="➕ Create Challenge")
    asyncio.run(bot.handle_message(up, ctx))
    assert "Create Challenge Wizard" in up.message.reply_text_calls[0]["text"]

    # 2. 📋 Manage Challenges
    up2 = FakeUpdate(user_id=99999, text="📋 Manage Challenges")
    asyncio.run(bot.handle_message(up2, ctx))
    assert len(up2.message.reply_text_calls) > 0

    # 3. 📊 Monthly Report
    up3 = FakeUpdate(user_id=99999, text="📊 Monthly Report")
    asyncio.run(bot.handle_message(up3, ctx))
    assert "AWS Student Builder Monthly Activity Report" in up3.message.reply_text_calls[0]["text"]

    # 4. 📢 Broadcast Notification
    up4 = FakeUpdate(user_id=99999, text="📢 Broadcast Notification")
    asyncio.run(bot.handle_message(up4, ctx))
    assert "Community Broadcast Center" in up4.message.reply_text_calls[0]["text"]

def test_challenge_manual_duration_configuration(monkeypatch):
    """Tests manual setting of duration during creation wizard and subsequent timer edits."""
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import get_challenge

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    ctx = FakeContext()

    # 1. Start wizard
    q1 = FakeCallbackQuery(user_id=99999, data="adm_create_ch")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    asyncio.run(handle_admin_callback(up1, ctx))

    # 2. Enter details with manual 25 minute duration
    up2 = FakeUpdate(user_id=99999, text="AWS Specialty Security | Security | Deep dive security sprint | 25")
    asyncio.run(bot.handle_message(up2, ctx))

    assert len(up2.message.reply_text_calls) == 1
    resp = up2.message.reply_text_calls[0]["text"]
    assert "25 Minutes" in resp
    kb = up2.message.reply_text_calls[0]["reply_markup"]
    # Get callback data from first button (e.g. adm_cr_sched:3:now:7d)
    cb_data = kb.inline_keyboard[0][0].callback_data
    ch_id = int(cb_data.split(":")[1])

    # 3. Schedule it
    q_sched = FakeCallbackQuery(user_id=99999, data=f"adm_cr_sched:{ch_id}:now:7d")
    up_sched = FakeUpdate(user_id=99999, callback_query=q_sched)
    asyncio.run(handle_admin_callback(up_sched, ctx))
    assert "25 minutes total" in q_sched.edited_text

    # 4. Verify in DB
    ch = asyncio.run(get_challenge(ch_id))
    assert ch is not None
    assert ch["duration_seconds"] == 25 * 60

    # 5. Change duration via timer custom option to 45 mins
    q_timer = FakeCallbackQuery(user_id=99999, data=f"adm_timer_custom:{ch_id}")
    up_t = FakeUpdate(user_id=99999, callback_query=q_timer)
    asyncio.run(handle_admin_callback(up_t, ctx))

    up_t_msg = FakeUpdate(user_id=99999, text="45")
    asyncio.run(bot.handle_message(up_t_msg, ctx))

    ch_updated = asyncio.run(get_challenge(ch_id))
    assert ch_updated["duration_seconds"] == 45 * 60


def test_modern_step_by_step_creation_wizard(monkeypatch):
    """Verifies the modern 4-step challenge creation flow: Title -> Description -> Schedule/Duration -> Add Questions."""
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import get_challenge, get_challenge_questions

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    ctx = FakeContext()

    # Step 1: Open Wizard & Enter Title
    q1 = FakeCallbackQuery(user_id=99999, data="adm_create_ch")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    asyncio.run(handle_admin_callback(up1, ctx))
    assert "Step 1/4: Title" in q1.edited_text

    up_title = FakeUpdate(user_id=99999, text="AWS Developer Associate Sprint")
    asyncio.run(bot.handle_message(up_title, ctx))

    assert len(up_title.message.reply_text_calls) == 1
    resp1 = up_title.message.reply_text_calls[0]["text"]
    assert "Step 2/4: Description" in resp1
    assert "AWS Developer Associate Sprint" in resp1

    state = asyncio.run(db.get_user_state(99999))
    assert state.startswith("WAITING_FOR_CHALLENGE_DESC:")
    ch_id = int(state.split(":")[1])

    # Test category picker & updating category
    q_cat = FakeCallbackQuery(user_id=99999, data=f"adm_wiz_cat_menu:{ch_id}")
    up_cat = FakeUpdate(user_id=99999, callback_query=q_cat)
    asyncio.run(handle_admin_callback(up_cat, ctx))
    assert "Choose Category" in q_cat.edited_text

    q_set_cat = FakeCallbackQuery(user_id=99999, data=f"adm_wiz_set_cat:{ch_id}:DevOps")
    up_set_cat = FakeUpdate(user_id=99999, callback_query=q_set_cat)
    asyncio.run(handle_admin_callback(up_set_cat, ctx))
    assert "DevOps" in q_set_cat.edited_text

    # Step 2: Enter Description
    up_desc = FakeUpdate(user_id=99999, text="Hands-on practice quiz covering DynamoDB, Lambda, CI/CD, and ECS architectures.")
    asyncio.run(bot.handle_message(up_desc, ctx))

    assert len(up_desc.message.reply_text_calls) == 1
    resp2 = up_desc.message.reply_text_calls[0]["text"]
    assert "Step 3/4: Exam Time Limit" in resp2
    assert "DynamoDB, Lambda, CI/CD" in resp2

    # Step 3: Select Exam Time Limit (15 Mins)
    q_timer = FakeCallbackQuery(user_id=99999, data=f"adm_wiz_timer:{ch_id}:15")
    up_t = FakeUpdate(user_id=99999, callback_query=q_timer)
    asyncio.run(handle_admin_callback(up_t, ctx))
    assert "Step 4/4: Schedule & Start/End Time" in q_timer.edited_text
    assert "15 Minutes" in q_timer.edited_text

    # Step 4: Select Schedule preset
    q_sched = FakeCallbackQuery(user_id=99999, data=f"adm_cr_sched:{ch_id}:now:7d")
    up_s = FakeUpdate(user_id=99999, callback_query=q_sched)
    asyncio.run(handle_admin_callback(up_s, ctx))

    assert "Add Questions" in q_sched.edited_text

    # Step 4: Add single question
    q_single = FakeCallbackQuery(user_id=99999, data=f"adm_add_q_to_ch:{ch_id}")
    up_sq = FakeUpdate(user_id=99999, callback_query=q_single)
    asyncio.run(handle_admin_callback(up_sq, ctx))

    q_text = (
        "What is AWS CodePipeline?\n"
        "A: A continuous delivery service\n"
        "B: A relational database engine\n"
        "C: An object storage repository\n"
        "D: A DNS management service\n"
        "Answer: A\n"
        "Category: DevOps\n"
        "Difficulty: EASY\n"
        "Explanation: CodePipeline is a managed continuous delivery service."
    )
    up_q = FakeUpdate(user_id=99999, text=q_text)
    asyncio.run(bot.handle_message(up_q, ctx))

    assert len(up_q.message.reply_text_calls) == 1
    resp_q = up_q.message.reply_text_calls[0]["text"]
    assert f"Added to Challenge #{ch_id}!" in resp_q

    # Step 5: Publish LIVE
    q_pub = FakeCallbackQuery(user_id=99999, data=f"adm_pub:{ch_id}")
    up_pub = FakeUpdate(user_id=99999, callback_query=q_pub)
    asyncio.run(handle_admin_callback(up_pub, ctx))
    assert "is now LIVE" in q_pub.edited_text

    # Verify final challenge state
    final_ch = asyncio.run(get_challenge(ch_id))
    assert final_ch["title"] == "AWS Developer Associate Sprint"
    assert "Hands-on practice quiz" in final_ch["description"]
    assert final_ch["status"] == "LIVE"

    questions = asyncio.run(get_challenge_questions(ch_id))
    assert len(questions) == 1


def test_power_user_challenge_creation_title_description_duration(monkeypatch):
    """Tests power user single-line creation with format: Title | Description | Duration."""
    import app.bot as bot
    from app.challenge.service import get_challenge

    asyncio.run(db.reset_db())
    monkeypatch.setenv("ADMIN_USER_IDS", "88888")

    ctx = FakeContext()

    # Admin initiates create challenge
    up_start = FakeUpdate(user_id=88888, text="Create Challenge")
    asyncio.run(bot.handle_message(up_start, ctx))

    state = asyncio.run(db.get_user_state(88888))
    assert state == "WAITING_FOR_CHALLENGE_TITLE"

    # Enter power-user multi-part format: Test | this   is test challeng | 20
    up_power = FakeUpdate(user_id=88888, text="Test | this   is test challeng | 20")
    asyncio.run(bot.handle_message(up_power, ctx))

    assert len(up_power.message.reply_text_calls) == 1
    resp = up_power.message.reply_text_calls[0]["text"]

    # Must be Step 4/4
    assert "Step 4/4: Schedule & Start/End Time" in resp
    assert "Test" in resp
    assert "this   is test challeng" in resp
    assert "20 Minutes" in resp

    # State allows typing custom dates immediately on Step 4 screen
    state_after = asyncio.run(db.get_user_state(88888))
    assert state_after is not None and state_after.startswith("WAITING_FOR_EDIT_CHALLENGE_SCHEDULE")

    # Verify challenge in database
    from app.challenge.service import list_challenges
    all_ch = asyncio.run(list_challenges(limit=1))
    assert len(all_ch) == 1
    ch_full = asyncio.run(get_challenge(all_ch[0]["id"]))
    assert ch_full is not None
    assert ch_full["title"] == "Test"
    assert ch_full["description"] == "this   is test challeng"
    assert ch_full["duration_seconds"] == 20 * 60


def test_zero_question_challenge_remains_draft_and_independent_publishing(monkeypatch):
    """Verifies that selecting Go LIVE with 0 questions leaves status as DRAFT,

    rejects going LIVE on the next screen with an alert, and allows independent
    publishing for Go LIVE and Schedule once questions are attached.
    """
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import get_challenge, add_question_to_challenge

    asyncio.run(db.reset_db())
    monkeypatch.setenv("ADMIN_USER_IDS", "77777")
    ctx = FakeContext()

    # 1. Admin creates a challenge and selects 'Go LIVE' in Step 4
    q_sched = FakeCallbackQuery(user_id=77777, data="adm_cr_sched:now:7d")
    ctx.user_data["wiz_title"] = "Zero Question Challenge"
    ctx.user_data["wiz_category"] = "Networking"
    ctx.user_data["wiz_description"] = "Networking test quiz."
    ctx.user_data["wiz_duration_mins"] = 15

    up_s = FakeUpdate(user_id=77777, callback_query=q_sched)
    asyncio.run(handle_admin_callback(up_s, ctx))

    # Next screen shows Add Questions prompt
    assert "Add Questions" in q_sched.edited_text

    # Find created challenge
    from app.challenge.service import list_challenges
    all_ch = asyncio.run(list_challenges(limit=1))
    assert len(all_ch) == 1
    ch_id = all_ch[0]["id"]
    ch = asyncio.run(get_challenge(ch_id))

    # CRITICAL: Must be DRAFT, NEVER prematurely LIVE with 0 questions!
    assert ch["status"] == "DRAFT"

    # 2. Admin taps 'Go LIVE' on the next screen with 0 questions
    q_pub_fail = FakeCallbackQuery(user_id=77777, data=f"adm_pub:{ch_id}:live")
    up_pub_fail = FakeUpdate(user_id=77777, callback_query=q_pub_fail)
    asyncio.run(handle_admin_callback(up_pub_fail, ctx))

    # Must alert requiring at least 1 question, and remain DRAFT
    assert q_pub_fail.answered is True
    assert "attach at least 1 question" in q_pub_fail.answered_text
    assert asyncio.run(get_challenge(ch_id))["status"] == "DRAFT"

    # 3. Admin taps 'Publish (Schedule)' on the next screen with 0 questions
    q_sched_fail = FakeCallbackQuery(user_id=77777, data=f"adm_pub:{ch_id}:sched")
    up_sched_fail = FakeUpdate(user_id=77777, callback_query=q_sched_fail)
    asyncio.run(handle_admin_callback(up_sched_fail, ctx))

    # Must also alert requiring at least 1 question
    assert q_sched_fail.answered is True
    assert "attach at least 1 question" in q_sched_fail.answered_text
    assert asyncio.run(get_challenge(ch_id))["status"] == "DRAFT"

    # 4. Attach a question
    asyncio.run(add_question_to_challenge(ch_id, {
        "question_text": "What is Amazon VPC?",
        "option_a": "Isolated virtual network",
        "option_b": "Database",
        "option_c": "Storage",
        "option_d": "Monitoring",
        "correct_option": "A",
        "category": "Networking",
        "explanation": "VPC provides isolated virtual cloud networking.",
    }))

    # 5. Now publish for Future (Schedule)
    q_sched_ok = FakeCallbackQuery(user_id=77777, data=f"adm_pub:{ch_id}:sched")
    up_sched_ok = FakeUpdate(user_id=77777, callback_query=q_sched_ok)
    asyncio.run(handle_admin_callback(up_sched_ok, ctx))

    ch_sched = asyncio.run(get_challenge(ch_id))
    assert ch_sched["status"] == "SCHEDULED"

    # 6. Now publish LIVE directly from manage
    q_live_ok = FakeCallbackQuery(user_id=77777, data=f"adm_pub:{ch_id}:live")
    up_live_ok = FakeUpdate(user_id=77777, callback_query=q_live_ok)
    asyncio.run(handle_admin_callback(up_live_ok, ctx))

    ch_live = asyncio.run(get_challenge(ch_id))
    assert ch_live["status"] == "LIVE"


def test_setup_bot_commands_and_notifications_command():
    ctx = FakeContext()
    asyncio.run(bot.setup_bot_commands(ctx.bot))
    assert any(c.command == "education" for c in ctx.bot.commands)
    assert any(c.command == "events" for c in ctx.bot.commands)
    assert any(c.command == "about" for c in ctx.bot.commands)
    assert any(c.command == "admin" for c in ctx.bot.commands)
    assert ctx.bot.menu_button is not None

    up = FakeUpdate(user_id=12345, text="/notifications")
    asyncio.run(bot.notifications_command(up, ctx))
    assert len(up.message.reply_text_calls) == 1
    assert "Community Notifications" in up.message.reply_text_calls[0]["text"]
    assert up.message.reply_text_calls[0]["reply_markup"] is not None


def test_step_by_step_title_and_category_input(monkeypatch):
    """Tests entering 'Title | Category' in Step 1 proceeds to Step 2 with the specified category."""
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import get_challenge

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    ctx = FakeContext()

    q1 = FakeCallbackQuery(user_id=99999, data="adm_create_ch")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    asyncio.run(handle_admin_callback(up1, ctx))

    up_title = FakeUpdate(user_id=99999, text="AWS Security Specialty | Security")
    asyncio.run(bot.handle_message(up_title, ctx))

    assert len(up_title.message.reply_text_calls) == 1
    resp = up_title.message.reply_text_calls[0]["text"]
    assert "Step 2/4: Description" in resp
    assert "AWS Security Specialty" in resp
    assert "Security" in resp

    state = asyncio.run(db.get_user_state(99999))
    assert state.startswith("WAITING_FOR_CHALLENGE_DESC:")
    ch_id = int(state.split(":")[1])

    ch = asyncio.run(get_challenge(ch_id))
    assert ch["title"] == "AWS Security Specialty"
    assert ch["category"] == "Security"


def test_wizard_custom_category_selection(monkeypatch):
    """Tests choosing Custom Category in Step 2 and typing a custom category."""
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import get_challenge

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    ctx = FakeContext()

    q1 = FakeCallbackQuery(user_id=99999, data="adm_create_ch")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    asyncio.run(handle_admin_callback(up1, ctx))

    up_title = FakeUpdate(user_id=99999, text="AWS Bedrock & Titan Mastery")
    asyncio.run(bot.handle_message(up_title, ctx))

    state = asyncio.run(db.get_user_state(99999))
    ch_id = int(state.split(":")[1])

    # Click Custom Category
    q_custom = FakeCallbackQuery(user_id=99999, data=f"adm_wiz_custom_cat:{ch_id}")
    up_custom = FakeUpdate(user_id=99999, callback_query=q_custom)
    asyncio.run(handle_admin_callback(up_custom, ctx))
    assert "Custom Category" in q_custom.edited_text

    # Type custom category
    up_cat_input = FakeUpdate(user_id=99999, text="Generative AI")
    asyncio.run(bot.handle_message(up_cat_input, ctx))

    assert len(up_cat_input.message.reply_text_calls) == 1
    resp = up_cat_input.message.reply_text_calls[0]["text"]
    assert "Step 2/4: Description" in resp
    assert "Generative AI" in resp

    ch = asyncio.run(get_challenge(ch_id))
    assert ch["category"] == "Generative AI"


def test_edit_schedule_with_copied_chat_prefix_and_direct_input(monkeypatch):
    """Tests entering dates directly on edit schedule screen even with copied chat prefixes."""
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import create_challenge, get_challenge

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    ctx = FakeContext()

    ch_id = asyncio.run(create_challenge(
        title="Copied Schedule Challenge",
        description="Testing date parsing",
        category="DevOps",
        created_by=99999,
    ))

    # Admin opens Edit Schedule
    q_edit = FakeCallbackQuery(user_id=99999, data=f"adm_edit_sched:{ch_id}")
    up_edit = FakeUpdate(user_id=99999, callback_query=q_edit)
    asyncio.run(handle_admin_callback(up_edit, ctx))

    # Verify state is set so admin can directly send dates
    state = asyncio.run(db.get_user_state(99999))
    assert state == f"WAITING_FOR_EDIT_CHALLENGE_SCHEDULE:{ch_id}"

    # Admin sends date with chat copied prefix
    copied_text = "[9/2/2026 3:23 PM] אַבְרָהָם: 2026-09-02 15:25 to 2026-09-02 15:50"
    up_date = FakeUpdate(user_id=99999, text=copied_text)
    asyncio.run(bot.handle_message(up_date, ctx))

    assert len(up_date.message.reply_text_calls) == 1
    resp = up_date.message.reply_text_calls[0]["text"]
    assert f"Schedule Updated for Challenge #{ch_id}" in resp
    assert "Sep 2, 2026 · 3:25 PM EAT" in resp
    assert "Sep 2, 2026 · 3:50 PM EAT" in resp

    ch = asyncio.run(get_challenge(ch_id))
    assert "2026-09-02T12:25:00" in ch["starts_at"]
    assert "2026-09-02T12:50:00" in ch["ends_at"]


def test_education_track_command_and_menu_button():
    """Verifies that /education and the '📚 Education Track' button return the curriculum and schedule."""
    from app.community import education_command
    up1 = FakeUpdate(user_id=123)
    ctx1 = FakeContext()
    asyncio.run(education_command(up1, ctx1))
    assert len(up1.message.reply_text_calls) == 1
    text1 = up1.message.reply_text_calls[0]["text"]
    assert "AWS SBG Education Track" in text1
    assert "Machine Learning" in text1
    assert "Wednesday" in text1
    assert up1.message.reply_text_calls[0]["reply_markup"] is not None

    # Via bottom menu text
    up2 = FakeUpdate(user_id=123, text="📚 Education Track")
    ctx2 = FakeContext()
    asyncio.run(bot.handle_message(up2, ctx2))
    assert len(up2.message.reply_text_calls) == 1
    assert "AWS SBG Education Track" in up2.message.reply_text_calls[0]["text"]


def test_events_command_and_menu_button():
    """Verifies that /events and the '📅 Next Event' button return upcoming program info."""
    from app.community import events_command
    up1 = FakeUpdate(user_id=123)
    ctx1 = FakeContext()
    asyncio.run(events_command(up1, ctx1))
    assert len(up1.message.reply_text_calls) == 1
    text1 = up1.message.reply_text_calls[0]["text"]
    assert "Upcoming Event & Community Programs" in text1
    assert "AWS Community Day 2026" in text1
    assert up1.message.reply_text_calls[0]["reply_markup"] is not None

    # Via bottom menu text
    up2 = FakeUpdate(user_id=123, text="📅 Next Event")
    ctx2 = FakeContext()
    asyncio.run(bot.handle_message(up2, ctx2))
    assert len(up2.message.reply_text_calls) == 1
    assert "Upcoming Event & Community Programs" in up2.message.reply_text_calls[0]["text"]


def test_about_command_and_menu_button():
    """Verifies that /about and the 'ℹ️ About Us' button return team & community details."""
    from app.community import about_command
    up1 = FakeUpdate(user_id=123)
    ctx1 = FakeContext()
    asyncio.run(about_command(up1, ctx1))
    assert len(up1.message.reply_text_calls) == 1
    text1 = up1.message.reply_text_calls[0]["text"]
    assert "About AWS Student Builder Group (AASTU)" in text1
    assert "The Team" in text1
    assert "@AWSAASTU" in text1
    assert up1.message.reply_text_calls[0]["reply_markup"] is not None

    # Via bottom menu text
    up2 = FakeUpdate(user_id=123, text="ℹ️ About Us")
    ctx2 = FakeContext()
    asyncio.run(bot.handle_message(up2, ctx2))
    assert len(up2.message.reply_text_calls) == 1
    assert "About AWS Student Builder Group (AASTU)" in up2.message.reply_text_calls[0]["text"]


def test_community_inline_callback_navigation():
    """Verifies inline buttons switch between education, events, and about smoothly."""
    from app.community import handle_community_callback

    # 1. Click comm_education
    q_edu = FakeCallbackQuery(user_id=123, data="comm_education")
    up_edu = FakeUpdate(user_id=123, callback_query=q_edu)
    ctx = FakeContext()
    asyncio.run(handle_community_callback(up_edu, ctx))
    assert "AWS SBG Education Track" in q_edu.edited_text

    # 2. Click comm_events
    q_ev = FakeCallbackQuery(user_id=123, data="comm_events")
    up_ev = FakeUpdate(user_id=123, callback_query=q_ev)
    asyncio.run(handle_community_callback(up_ev, ctx))
    assert "Upcoming Event & Community Programs" in q_ev.edited_text

    # 3. Click comm_about
    q_ab = FakeCallbackQuery(user_id=123, data="comm_about")
    up_ab = FakeUpdate(user_id=123, callback_query=q_ab)
    asyncio.run(handle_community_callback(up_ab, ctx))
    assert "About AWS Student Builder Group (AASTU)" in q_ab.edited_text


def test_paused_challenge_commands_gracefully_fallback():
    """Verifies that all paused challenge commands return the friendly pause notice."""
    from app.community import challenge_paused_command
    up = FakeUpdate(user_id=123)
    ctx = FakeContext()
    asyncio.run(challenge_paused_command(up, ctx))
    assert len(up.message.reply_text_calls) == 1
    text = up.message.reply_text_calls[0]["text"]
    assert "Challenge Center Update" in text
    assert "Education Track" in text
    assert up.message.reply_text_calls[0]["reply_markup"] is not None


def test_admin_broadcast_command_direct_prompt(monkeypatch):
    """Verifies that /broadcast sets the WAITING_FOR_ADMIN_BROADCAST state and prompts for text."""
    monkeypatch.setenv("ADMIN_USER_IDS", "88888")
    up = FakeUpdate(user_id=88888)
    ctx = FakeContext()

    asyncio.run(bot.broadcast_command(up, ctx))
    assert len(up.message.reply_text_calls) == 1
    assert "Community Broadcast Center" in up.message.reply_text_calls[0]["text"]
    state = asyncio.run(db.get_user_state(88888))
    assert state == "WAITING_FOR_ADMIN_BROADCAST"


def test_admin_stats_and_support_info_menu_buttons(monkeypatch):
    """Verifies admin bottom menu buttons for Community Stats and Support Info."""
    monkeypatch.setenv("ADMIN_USER_IDS", "88888")
    ctx = FakeContext()

    # Community Stats
    up_stats = FakeUpdate(user_id=88888, text="📊 Community Stats")
    asyncio.run(bot.handle_message(up_stats, ctx))
    assert "AWS SBG Community Statistics" in up_stats.message.reply_text_calls[0]["text"]

    # Support Info
    up_sup = FakeUpdate(user_id=88888, text="💬 Support Info")
    asyncio.run(bot.handle_message(up_sup, ctx))
    assert "AWS SBG Support & Helpdesk" in up_sup.message.reply_text_calls[0]["text"]


def test_parse_education_track_input_multiline_and_custom_columns():
    from app.challenge.admin import parse_education_track_input
    raw = (
        "Day: Every Sunday\n"
        "Time: 3:00 PM - 5:00 PM EAT\n"
        "Location: Block 54 Hall 3\n"
        "Students: 200+ Enrolled\n"
        "Leads: Lead Mentor John\n"
        "Notes: Advanced Cloud Architecture & DynamoDB\n"
        "Prerequisites: Linux Basics\n"
        "Cohort: Cohort 2\n"
    )
    parsed = parse_education_track_input(raw)
    assert parsed["edu_days"] == "Every Sunday"
    assert parsed["edu_time"] == "3:00 PM - 5:00 PM EAT"
    assert parsed["edu_location"] == "Block 54 Hall 3"
    assert parsed["edu_students"] == "200+ Enrolled"
    assert parsed["edu_leads"] == "Lead Mentor John"
    assert parsed["edu_notes"] == "Advanced Cloud Architecture & DynamoDB"
    assert "Prerequisites: Linux Basics" in parsed["edu_custom_fields"]
    assert "Cohort: Cohort 2" in parsed["edu_custom_fields"]


def test_parse_education_track_input_single_line():
    from app.challenge.admin import parse_education_track_input
    raw = "Saturday | 2:00 PM | Campus Hall 1 | 180 Students | Ambassador Jane | Serverless API"
    parsed = parse_education_track_input(raw)
    assert parsed["edu_days"] == "Saturday"
    assert parsed["edu_time"] == "2:00 PM"
    assert parsed["edu_location"] == "Campus Hall 1"
    assert parsed["edu_students"] == "180 Students"
    assert parsed["edu_leads"] == "Ambassador Jane"
    assert parsed["edu_notes"] == "Serverless API"


def test_parse_next_event_input_multiline_and_custom_columns():
    from app.challenge.admin import parse_next_event_input
    raw = (
        "Title: Serverless Microservices Workshop\n"
        "Date: Oct 28, 2026\n"
        "Time: 2:00 PM - 5:00 PM\n"
        "Venue: AASTU Central Lab\n"
        "Prereqs: Laptop + AWS Free Tier\n"
        "Description: Build and deploy serverless apps.\n"
        "Guest Speaker: AWS Solution Architect\n"
    )
    parsed = parse_next_event_input(raw)
    assert parsed["event_title"] == "Serverless Microservices Workshop"
    assert parsed["event_date"] == "Oct 28, 2026"
    assert parsed["event_time"] == "2:00 PM - 5:00 PM"
    assert parsed["event_venue"] == "AASTU Central Lab"
    assert parsed["event_prereqs"] == "Laptop + AWS Free Tier"
    assert parsed["event_description"] == "Build and deploy serverless apps."
    assert "Guest Speaker: AWS Solution Architect" in parsed["event_custom_fields"]


def test_admin_manage_education_track_flow():
    import os
    from app.challenge.admin import _verified_admin_cache
    from app.community import education_command
    asyncio.run(db.reset_db())
    os.environ["ADMIN_USER_IDS"] = "99999"
    _verified_admin_cache.add(99999)

    ctx = FakeContext()

    # 1. Admin clicks "🔹 Manage Education Track"
    up_btn = FakeUpdate(user_id=99999, text="🔹 Manage Education Track")
    asyncio.run(bot.handle_message(up_btn, ctx))
    assert len(up_btn.message.reply_text_calls) == 1
    assert "Manage Education Track" in up_btn.message.reply_text_calls[0]["text"]

    # 2. Trigger edit callback
    cb_up = FakeUpdate(user_id=99999)
    cb_up.callback_query = FakeCallbackQuery(user_id=99999, data="adm_update_edu")
    asyncio.run(bot.handle_admin_callback(cb_up, ctx))
    state = asyncio.run(db.get_user_state(99999))
    assert state == "WAITING_FOR_ADMIN_UPDATE_EDU"

    # 3. Admin submits update text
    update_text = (
        "Day: Every Sunday\n"
        "Time: 10:00 AM – 1:00 PM EAT\n"
        "Location: Virtual Stream (Zoom)\n"
        "Students: 250+ Cohort Members\n"
        "Leads: Senior Cloud Leads\n"
        "Notes: Cloud Practitioner & SysOps Sprint\n"
        "Certifications: CCP & SAA\n"
    )
    msg_up = FakeUpdate(user_id=99999, text=update_text)
    asyncio.run(bot.handle_message(msg_up, ctx))
    assert "Education Track Update Preview" in msg_up.message.reply_text_calls[0]["text"]
    assert "Every Sunday" in msg_up.message.reply_text_calls[0]["text"]
    assert ctx.user_data.get("staged_edu") is not None

    # 4. Admin clicks confirm save
    save_cb = FakeUpdate(user_id=99999)
    save_cb.callback_query = FakeCallbackQuery(user_id=99999, data="adm_save_edu")
    asyncio.run(bot.handle_admin_callback(save_cb, ctx))

    # 5. Verify member view reflects the saved details
    member_up = FakeUpdate(user_id=12345)
    asyncio.run(education_command(member_up, ctx))
    member_text = member_up.message.reply_text_calls[0]["text"]
    assert "Every Sunday" in member_text
    assert "10:00 AM – 1:00 PM EAT" in member_text
    assert "Virtual Stream (Zoom)" in member_text
    assert "250+ Cohort Members" in member_text
    assert "Senior Cloud Leads" in member_text
    assert "<b>Certifications:</b> CCP &amp; SAA" in member_text


def test_admin_manage_next_event_flow():
    import os
    from app.challenge.admin import _verified_admin_cache
    from app.community import events_command
    asyncio.run(db.reset_db())
    os.environ["ADMIN_USER_IDS"] = "99999"
    _verified_admin_cache.add(99999)

    ctx = FakeContext()

    # 1. Admin clicks "🔹 Manage Next Event"
    up_btn = FakeUpdate(user_id=99999, text="🔹 Manage Next Event")
    asyncio.run(bot.handle_message(up_btn, ctx))
    assert len(up_btn.message.reply_text_calls) == 1
    assert "Manage Next Event" in up_btn.message.reply_text_calls[0]["text"]

    # 2. Trigger edit callback
    cb_up = FakeUpdate(user_id=99999)
    cb_up.callback_query = FakeCallbackQuery(user_id=99999, data="adm_update_event")
    asyncio.run(bot.handle_admin_callback(cb_up, ctx))
    state = asyncio.run(db.get_user_state(99999))
    assert state == "WAITING_FOR_ADMIN_UPDATE_EVENT"

    # 3. Admin submits update text
    update_text = (
        "Title: AWS Hackathon 2026 Kickoff\n"
        "Date: Nov 15, 2026\n"
        "Time: 9:00 AM – 5:00 PM\n"
        "Venue: AASTU Main Auditorium\n"
        "Prereqs: Team of 3 builders + GitHub account\n"
        "Description: 24-hour campus cloud hackathon with mentorship and awards.\n"
        "Prize Pool: $1,000 in AWS Credits\n"
    )
    msg_up = FakeUpdate(user_id=99999, text=update_text)
    asyncio.run(bot.handle_message(msg_up, ctx))
    assert "Next Event Update Preview" in msg_up.message.reply_text_calls[0]["text"]
    assert "AWS Hackathon 2026 Kickoff" in msg_up.message.reply_text_calls[0]["text"]
    assert ctx.user_data.get("staged_event") is not None

    # 4. Admin clicks confirm save
    save_cb = FakeUpdate(user_id=99999)
    save_cb.callback_query = FakeCallbackQuery(user_id=99999, data="adm_save_event")
    asyncio.run(bot.handle_admin_callback(save_cb, ctx))

    # 5. Verify member view reflects the saved details
    member_up = FakeUpdate(user_id=12345)
    asyncio.run(events_command(member_up, ctx))
    member_text = member_up.message.reply_text_calls[0]["text"]
    assert "AWS Hackathon 2026 Kickoff" in member_text
    assert "Nov 15, 2026" in member_text
    assert "AASTU Main Auditorium" in member_text
    assert "Team of 3 builders + GitHub account" in member_text
    assert "<b>Prize Pool:</b> $1,000 in AWS Credits" in member_text


def test_default_seeded_education_tracks():
    """Verifies that the bot starts with two flexible tracks with 60 students and 3 classes each."""
    from app.db import reset_db, list_education_tracks, seed_default_education_tracks_if_empty
    asyncio.run(reset_db())
    asyncio.run(seed_default_education_tracks_if_empty())
    tracks = asyncio.run(list_education_tracks(active_only=True))
    assert len(tracks) == 2
    t1 = tracks[0]
    t2 = tracks[1]
    assert "Continues to the end of the year" in t1["duration"]
    assert "60 students (3 classes)" in t1["students"]
    assert "AWS SBG Mentors" in t1["mentors"]
    assert "Continues to the end of the year" in t2["duration"]
    assert "60 students (3 classes)" in t2["students"]
    assert "AWS SBG Mentors" in t2["mentors"]


def test_parse_track_input_flexible_omissions():
    """Verifies that every detail is optional in parse_track_input and can be skipped without errors."""
    from app.challenge.admin import parse_track_input

    # 1. Minimal input: only title and notes (duration, students, mentors, schedule, location skipped)
    raw1 = (
        "Title: Generative AI & Bedrock\n"
        "Notes: Hands-on foundation models and prompt engineering on AWS.\n"
    )
    p1 = parse_track_input(raw1)
    assert p1["title"] == "Generative AI & Bedrock"
    assert p1["notes"] == "Hands-on foundation models and prompt engineering on AWS."
    assert "duration" not in p1
    assert "students" not in p1
    assert "mentors" not in p1
    assert "schedule" not in p1
    assert "location" not in p1

    # 2. Pipe format with omitted/empty middle fields
    raw2 = "DevOps Track | Continues to December | 60 students ||||"
    p2 = parse_track_input(raw2)
    assert p2["title"] == "DevOps Track"
    assert p2["duration"] == "Continues to December"
    assert p2["students"] == "60 students"
    assert "mentors" not in p2
    assert "schedule" not in p2

    # 3. Custom extra columns preserved
    raw3 = (
        "Title: Security & IAM Track\n"
        "Duration: 6 Months\n"
        "Prerequisites: AWS Builder ID\n"
        "Lab Cloud: Free Tier Supported\n"
    )
    p3 = parse_track_input(raw3)
    assert p3["title"] == "Security & IAM Track"
    assert p3["duration"] == "6 Months"
    assert "Prerequisites: AWS Builder ID" in p3["custom_fields"]
    assert "Lab Cloud: Free Tier Supported" in p3["custom_fields"]


def test_format_track_card_skips_omitted_fields():
    """Verifies that format_track_card completely excludes omitted fields rather than showing placeholders."""
    from app.community import format_track_card

    # Track with only title, students, and notes (duration, mentors, schedule, location skipped)
    partial_track = {
        "title": "Cloud Networking Deep Dive",
        "students": "60 students (3 classes)",
        "notes": "VPC peering, Transit Gateway, and Direct Connect architectures.",
    }
    card = format_track_card(partial_track, 1, 1)

    assert "Cloud Networking Deep Dive" in card
    assert "60 students (3 classes)" in card
    assert "VPC peering" in card
    # Omitted fields should NOT appear
    assert "• <b>Duration:</b>" not in card
    assert "• <b>Schedule:</b>" not in card
    assert "• <b>Location:</b>" not in card
    assert "• <b>Mentors & Leads:</b>" not in card


def test_admin_add_third_track_and_student_switcher():
    """Verifies an admin adding a third track, and students switching between all tracks via inline buttons."""
    import os
    from app.challenge.admin import _verified_admin_cache
    from app.community import education_command, handle_community_callback
    from app.db import reset_db, list_education_tracks, seed_default_education_tracks_if_empty

    asyncio.run(reset_db())
    asyncio.run(seed_default_education_tracks_if_empty())
    os.environ["ADMIN_USER_IDS"] = "99999"
    _verified_admin_cache.add(99999)
    ctx = FakeContext()

    # 1. Admin triggers add track
    cb_add = FakeUpdate(user_id=99999)
    cb_add.callback_query = FakeCallbackQuery(user_id=99999, data="adm_add_track")
    asyncio.run(bot.handle_admin_callback(cb_add, ctx))
    state = asyncio.run(db.get_user_state(99999))
    assert state == "WAITING_FOR_ADMIN_NEW_TRACK"

    # 2. Admin submits a 3rd track (skipping schedule and location)
    new_track_text = (
        "Title: DevOps & CI/CD Pipelines\n"
        "Duration: Continues to the end of the year\n"
        "Students: 60 students (3 classes)\n"
        "Mentors: 1 mentor per class (3 mentors total)\n"
        "Notes: GitHub Actions, CodePipeline, Docker, and ECS deployments.\n"
    )
    msg_up = FakeUpdate(user_id=99999, text=new_track_text)
    asyncio.run(bot.handle_message(msg_up, ctx))
    assert len(msg_up.message.reply_text_calls) == 1
    assert "New Track Preview" in msg_up.message.reply_text_calls[0]["text"]
    assert "DevOps &amp; CI/CD Pipelines" in msg_up.message.reply_text_calls[0]["text"]
    assert "• <b>Location:</b>" not in msg_up.message.reply_text_calls[0]["text"]

    # 3. Admin clicks confirm save
    save_cb = FakeUpdate(user_id=99999)
    save_cb.callback_query = FakeCallbackQuery(user_id=99999, data="adm_save_new_track")
    asyncio.run(bot.handle_admin_callback(save_cb, ctx))

    # Verify database now contains 3 active tracks
    tracks = asyncio.run(list_education_tracks(active_only=True))
    assert len(tracks) == 3
    t3 = tracks[2]
    assert t3["title"] == "DevOps & CI/CD Pipelines"

    # 4. Student views education page
    student_up = FakeUpdate(user_id=777)
    asyncio.run(education_command(student_up, ctx))
    call = student_up.message.reply_text_calls[0]
    markup = call["reply_markup"]

    # Verify track switcher inline buttons exist for all 3 tracks
    callback_datas = [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]
    assert f"comm_track:{tracks[0]['id']}" in callback_datas
    assert f"comm_track:{tracks[1]['id']}" in callback_datas
    assert f"comm_track:{tracks[2]['id']}" in callback_datas

    # 5. Student clicks on track 3 button
    toggle_up = FakeUpdate(user_id=777)
    toggle_up.callback_query = FakeCallbackQuery(user_id=777, data=f"comm_track:{tracks[2]['id']}")
    asyncio.run(handle_community_callback(toggle_up, ctx))
    assert "DevOps &amp; CI/CD Pipelines" in toggle_up.callback_query.edited_text
    assert "GitHub Actions, CodePipeline" in toggle_up.callback_query.edited_text


def test_admin_edit_and_delete_track_flow():
    """Verifies editing specific track fields and deleting a track via admin console."""
    import os
    from app.challenge.admin import _verified_admin_cache
    from app.db import reset_db, list_education_tracks, seed_default_education_tracks_if_empty

    asyncio.run(reset_db())
    asyncio.run(seed_default_education_tracks_if_empty())
    os.environ["ADMIN_USER_IDS"] = "99999"
    _verified_admin_cache.add(99999)
    ctx = FakeContext()

    tracks_before = asyncio.run(list_education_tracks(active_only=True))
    target_track_id = tracks_before[0]["id"]

    # 1. Admin triggers edit for track 1
    cb_edit = FakeUpdate(user_id=99999)
    cb_edit.callback_query = FakeCallbackQuery(user_id=99999, data=f"adm_edit_track:{target_track_id}")
    asyncio.run(bot.handle_admin_callback(cb_edit, ctx))
    state = asyncio.run(db.get_user_state(99999))
    assert state == f"WAITING_FOR_ADMIN_EDIT_TRACK:{target_track_id}"

    # 2. Admin submits updated student and note fields (skipping unchanged fields)
    msg_edit = FakeUpdate(user_id=99999, text="Students: 80 students (4 classes)\nNotes: Expanded cohort with advanced serverless.")
    asyncio.run(bot.handle_message(msg_edit, ctx))
    assert "Updated Track Preview" in msg_edit.message.reply_text_calls[0]["text"]

    # 3. Admin confirms edit save
    save_cb = FakeUpdate(user_id=99999)
    save_cb.callback_query = FakeCallbackQuery(user_id=99999, data=f"adm_save_edit_track:{target_track_id}")
    asyncio.run(bot.handle_admin_callback(save_cb, ctx))

    # Verify track 1 updated in DB
    updated_track = asyncio.run(db.get_education_track(target_track_id))
    assert updated_track["students"] == "80 students (4 classes)"
    assert "Expanded cohort with advanced serverless" in updated_track["notes"]

    # 4. Admin deletes track 2
    del_track_id = tracks_before[1]["id"]
    del_cb = FakeUpdate(user_id=99999)
    del_cb.callback_query = FakeCallbackQuery(user_id=99999, data=f"adm_del_track:{del_track_id}")
    asyncio.run(bot.handle_admin_callback(del_cb, ctx))

    # Verify remaining track count is 1
    tracks_after = asyncio.run(list_education_tracks(active_only=True))
    assert len(tracks_after) == 1
    assert tracks_after[0]["id"] == target_track_id


def test_broadcast_large_length_with_pipes_does_not_create_challenge():
    """Verifies that large broadcast messages containing pipe characters '|' do not accidentally trigger challenge creation."""
    import os
    from app.challenge.admin import _verified_admin_cache
    from app.challenge.service import list_challenges
    from app.db import reset_db, register_or_update_bot_user

    asyncio.run(reset_db())
    os.environ["ADMIN_USER_IDS"] = "99999"
    _verified_admin_cache.add(99999)
    asyncio.run(register_or_update_bot_user(1001, "Alice"))
    asyncio.run(register_or_update_bot_user(1002, "Bob"))

    ctx = FakeContext()

    # 1. Admin triggers broadcast
    cb_bcast = FakeUpdate(user_id=99999)
    cb_bcast.callback_query = FakeCallbackQuery(user_id=99999, data="adm_broadcast")
    asyncio.run(bot.handle_admin_callback(cb_bcast, ctx))
    state = asyncio.run(db.get_user_state(99999))
    assert state == "WAITING_FOR_ADMIN_BROADCAST"

    # 2. Admin submits a large announcement text with pipe characters and multiple sections
    large_broadcast_text = (
        "🚀 <b>AWS Student Builder Special Cohort Announcement!</b>\n\n"
        "We are excited to kick off our multi-track cloud program for this semester!\n\n"
        "<b>Track Details:</b>\n"
        "• Track 1: Cloud Practitioner & Core Services | Saturday 2:00 PM | Campus Hall 54\n"
        "• Track 2: Solutions Architect & Serverless | Saturday 2:00 PM | Campus Hall 55\n"
        "• Track 3: DevOps & Kubernetes CI/CD | Sunday 10:00 AM | Virtual Lab Stream\n\n"
        "<b>What To Bring:</b>\n"
        "Laptop | AWS Free Tier Account | GitHub Profile\n\n"
        "Please ensure you join our community group and review the prerequisites before attending. "
        "Mentors will be present in every class to provide 1-on-1 assistance with console setups and labs!\n\n"
        + ("Additional study resources and documentation will be shared weekly in the official channel. " * 10)
    )
    assert len(large_broadcast_text) > 800
    assert large_broadcast_text.count("|") >= 4

    msg_up = FakeUpdate(user_id=99999, text=large_broadcast_text)
    asyncio.run(bot.handle_message(msg_up, ctx))

    # CRITICAL: Verify NO challenge was created!
    challenges = asyncio.run(list_challenges(limit=10))
    assert len(challenges) == 0, f"Expected 0 challenges, found {len(challenges)}! Challenge was mistakenly created."

    # Verify that the message was treated as a Broadcast Preview
    assert len(msg_up.message.reply_text_calls) == 1
    reply_text = msg_up.message.reply_text_calls[0]["text"]
    assert "BROADCAST PREVIEW" in reply_text
    assert "Target Audience:" in reply_text
    assert ctx.user_data.get("bcast_text") == large_broadcast_text

    # 3. Confirm and send broadcast
    send_cb = FakeUpdate(user_id=99999)
    send_cb.callback_query = FakeCallbackQuery(user_id=99999, data="adm_bcast_send:custom")
    asyncio.run(bot.handle_admin_callback(send_cb, ctx))
    assert "Broadcast Complete" in send_cb.callback_query.edited_text
    assert "Delivered Successfully:" in send_cb.callback_query.edited_text


def test_long_message_without_state_does_not_create_accidental_challenge():
    """Verifies that an admin sending a multi-line long message with pipes when state is None never triggers challenge creation."""
    import os
    from app.challenge.admin import _verified_admin_cache
    from app.challenge.service import list_challenges
    from app.db import reset_db

    asyncio.run(reset_db())
    os.environ["ADMIN_USER_IDS"] = "99999"
    _verified_admin_cache.add(99999)
    ctx = FakeContext()

    state = asyncio.run(db.get_user_state(99999))
    assert state is None

    long_message_with_pipes = (
        "Hello everyone,\n"
        "Here is the proposed schedule for this month:\n"
        "Week 1: IAM | EC2 | S3\n"
        "Week 2: VPC | Subnets | Route Tables\n"
        "Week 3: DynamoDB | Lambda | API Gateway\n"
        "Let me know your thoughts!"
    )
    msg_up = FakeUpdate(user_id=99999, text=long_message_with_pipes)
    asyncio.run(bot.handle_message(msg_up, ctx))

    # Should NOT create a challenge
    challenges = asyncio.run(list_challenges(limit=10))
    assert len(challenges) == 0


def test_admin_broadcast_with_photo_and_caption(monkeypatch):
    from app.challenge.admin import handle_admin_callback, _verified_admin_cache

    asyncio.run(db.reset_db())
    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    _verified_admin_cache.add(99999)

    # 1. Setup audience
    asyncio.run(db.set_user_state(601, "ACTIVE"))
    asyncio.run(db.set_user_state(602, "ACTIVE"))

    # 2. Trigger broadcast
    q1 = FakeCallbackQuery(user_id=99999, data="adm_broadcast")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    ctx = FakeContext()

    asyncio.run(handle_admin_callback(up1, ctx))
    state = asyncio.run(db.get_user_state(99999))
    assert state == "WAITING_FOR_ADMIN_BROADCAST"

    # 3. Admin sends photo with caption (e.g. Zinabu Kelemework panelist poster)
    photo_obj = [FakePhotoSize(file_id="zinabu_poster_file_id")]
    caption_text = (
        "🎙️ <b>MEET OUR FIRST COMMUNITY DAY PANELIST!</b>\n\n"
        "We're excited to introduce <b>Zinabu Kelemework</b> as our first panelist for AWS Community Day 2026!"
    )
    up_photo = FakeUpdate(
        user_id=99999,
        text="",
        photo=photo_obj,
        caption=caption_text,
    )
    asyncio.run(bot.handle_message(up_photo, ctx))

    assert "BROADCAST PREVIEW" in up_photo.message.reply_text_calls[0]["text"]
    assert "Photo included" in up_photo.message.reply_text_calls[0]["text"]
    assert "Zinabu Kelemework" in up_photo.message.reply_text_calls[0]["text"]
    assert ctx.user_data.get("bcast_photo") == "zinabu_poster_file_id"
    assert ctx.user_data.get("bcast_text") == caption_text

    # 4. Confirm broadcast delivery
    users = asyncio.run(db.get_all_broadcast_user_ids())
    q_send = FakeCallbackQuery(user_id=99999, data="adm_bcast_send:custom")
    up_send = FakeUpdate(user_id=99999, callback_query=q_send)

    asyncio.run(handle_admin_callback(up_send, ctx))
    assert "Broadcast Complete" in q_send.edited_text
    assert len(ctx.bot.send_photo_calls) == len(users)
    assert any(c["photo"] == "zinabu_poster_file_id" for c in ctx.bot.send_photo_calls)
    assert any("Zinabu Kelemework" in (c["caption"] or "") for c in ctx.bot.send_photo_calls)
    assert ctx.user_data.get("bcast_photo") is None
    assert ctx.user_data.get("bcast_text") is None


def test_admin_broadcast_with_photo_only(monkeypatch):
    from app.challenge.admin import handle_admin_callback, _verified_admin_cache

    asyncio.run(db.reset_db())
    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    _verified_admin_cache.add(99999)

    asyncio.run(db.set_user_state(701, "ACTIVE"))

    q1 = FakeCallbackQuery(user_id=99999, data="adm_broadcast")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    ctx = FakeContext()
    asyncio.run(handle_admin_callback(up1, ctx))

    # Send photo without text caption
    photo_obj = [FakePhotoSize(file_id="raw_photo_id_456")]
    up_photo = FakeUpdate(user_id=99999, text="", photo=photo_obj, caption=None)
    asyncio.run(bot.handle_message(up_photo, ctx))

    assert "BROADCAST PREVIEW" in up_photo.message.reply_text_calls[0]["text"]
    assert "Photo included" in up_photo.message.reply_text_calls[0]["text"]
    assert "(Photo announcement without text caption)" in up_photo.message.reply_text_calls[0]["text"]

    users = asyncio.run(db.get_all_broadcast_user_ids())
    q_send = FakeCallbackQuery(user_id=99999, data="adm_bcast_send:custom")
    up_send = FakeUpdate(user_id=99999, callback_query=q_send)
    asyncio.run(handle_admin_callback(up_send, ctx))

    assert "Broadcast Complete" in q_send.edited_text
    assert len(ctx.bot.send_photo_calls) == len(users)
    assert all(c["photo"] == "raw_photo_id_456" for c in ctx.bot.send_photo_calls)
    assert all(c["caption"] is None for c in ctx.bot.send_photo_calls)


def test_admin_broadcast_with_photo_and_long_caption(monkeypatch):
    from app.challenge.admin import handle_admin_callback, _verified_admin_cache

    asyncio.run(db.reset_db())
    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    _verified_admin_cache.add(99999)

    asyncio.run(db.set_user_state(801, "ACTIVE"))

    q1 = FakeCallbackQuery(user_id=99999, data="adm_broadcast")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    ctx = FakeContext()
    asyncio.run(handle_admin_callback(up1, ctx))

    # Caption longer than 1024 characters
    long_caption = "A" * 1100 + "\nOverflow announcement section."
    photo_obj = [FakePhotoSize(file_id="long_caption_photo")]
    up_photo = FakeUpdate(user_id=99999, text="", photo=photo_obj, caption=long_caption)
    asyncio.run(bot.handle_message(up_photo, ctx))

    users = asyncio.run(db.get_all_broadcast_user_ids())
    q_send = FakeCallbackQuery(user_id=99999, data="adm_bcast_send:custom")
    up_send = FakeUpdate(user_id=99999, callback_query=q_send)
    asyncio.run(handle_admin_callback(up_send, ctx))

    assert "Broadcast Complete" in q_send.edited_text
    # Photo sent with caption <= 1024 chars
    assert len(ctx.bot.send_photo_calls) == len(users)
    assert all(len(c["caption"]) <= 1024 for c in ctx.bot.send_photo_calls)
    # Overflow sent via send_message
    assert len(ctx.bot.send_message_calls) >= len(users)
    assert any("Overflow announcement section." in c["text"] for c in ctx.bot.send_message_calls)


def test_admin_broadcast_cancel_cleans_staged_photo(monkeypatch):
    from app.challenge.admin import handle_admin_callback, _verified_admin_cache

    asyncio.run(db.reset_db())
    monkeypatch.setenv("ADMIN_USER_IDS", "99999")
    _verified_admin_cache.add(99999)

    q1 = FakeCallbackQuery(user_id=99999, data="adm_broadcast")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    ctx = FakeContext()
    asyncio.run(handle_admin_callback(up1, ctx))

    photo_obj = [FakePhotoSize(file_id="cancel_photo_id")]
    up_photo = FakeUpdate(user_id=99999, text="", photo=photo_obj, caption="Test cancel caption")
    asyncio.run(bot.handle_message(up_photo, ctx))
    assert ctx.user_data.get("bcast_photo") == "cancel_photo_id"

    # Cancel via callback
    q_cancel = FakeCallbackQuery(user_id=99999, data="adm_bcast_cancel")
    up_cancel = FakeUpdate(user_id=99999, callback_query=q_cancel)
    asyncio.run(handle_admin_callback(up_cancel, ctx))

    assert "Broadcast Cancelled" in q_cancel.edited_text
    assert ctx.user_data.get("bcast_photo") is None
    assert ctx.user_data.get("bcast_text") is None


























