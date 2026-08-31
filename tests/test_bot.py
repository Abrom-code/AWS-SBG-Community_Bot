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
    def __init__(self, user_id=42, text="", chat_id=1, reply_to_message_id=None, is_edited=False, chat_type="private", callback_query=None):
        self.effective_user = FakeUser(user_id=user_id)
        self.effective_chat = FakeChat(chat_id=chat_id, chat_type=chat_type)
        self.callback_query = callback_query
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
        self.send_message_calls = []
        self.edited_messages = []

    async def send_message(self, chat_id, text, parse_mode=None):
        message_id = len(self.sent_messages) + 1
        self.sent_messages.append((chat_id, text, message_id, parse_mode))
        self.send_message_calls.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return type("SentMessage", (), {"message_id": message_id})()

    async def edit_message_text(self, chat_id, message_id, text, parse_mode=None):
        self.edited_messages.append((chat_id, message_id, text, parse_mode))
        return type("SentMessage", (), {"message_id": message_id})()


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
        ["⚡ Challenge Center", "💬 Feedback & Support"],
        ["ℹ️ About Us", "❓ Help"],
    ]

    ch_keyboard = bot.get_challenge_menu_keyboard()
    ch_labels = [[button.text for button in row] for row in ch_keyboard.keyboard]
    assert ch_labels == [
        ["🚀 Take Active Challenge", "🏆 Leaderboards"],
        ["📚 Past Challenges", "📖 Scoring & Rules"],
        ["🔙 Main Menu"],
    ]

    fb_keyboard = bot.get_feedback_menu_keyboard()
    fb_labels = [[button.text for button in row] for row in fb_keyboard.keyboard]
    assert fb_labels == [
        ["📝 Submit Feedback", "ℹ️ About Support"],
        ["🔙 Main Menu"],
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
    assert "/start" in update.message.reply_text_calls[0]["text"]
    assert "/challenge" in update.message.reply_text_calls[0]["text"]
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
        ["⚡ Challenge Center", "💬 Feedback & Support"],
        ["ℹ️ About Us", "❓ Help"],
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
    assert "AWS SBG AASTU Community & Challenge Bot!" in update.message.reply_photo_calls[0]["caption"]
    assert "<b>Join our community:</b> @AWSAASTU" in update.message.reply_photo_calls[0]["caption"]
    assert update.message.reply_photo_calls[0]["parse_mode"] == ParseMode.HTML


def test_start_command_falls_back_to_text_when_logo_missing(monkeypatch):
    update = FakeUpdate(user_id=123)
    context = FakeContext()
    
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    
    asyncio.run(bot.start_command(update, context))
    
    assert len(update.message.reply_photo_calls) == 0
    assert len(update.message.reply_text_calls) == 1
    assert "AWS SBG AASTU Community & Challenge Bot!" in update.message.reply_text_calls[0]["text"]
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
def test_challenge_hub_and_feedback_hub_commands():
    update = FakeUpdate(user_id=123)
    context = FakeContext()

    asyncio.run(bot.challenge_hub_command(update, context))
    assert len(update.message.reply_text_calls) == 1
    assert "AWS Builder Challenge Center" in update.message.reply_text_calls[0]["text"]
    assert "🚀 Take Active Challenge" in [b.text for row in update.message.reply_text_calls[0]["reply_markup"].keyboard for b in row]

    asyncio.run(bot.feedback_hub_command(update, context))
    assert len(update.message.reply_text_calls) == 2
    assert "Feedback & Community Support Hub" in update.message.reply_text_calls[1]["text"]
    assert "📝 Submit Feedback" in [b.text for row in update.message.reply_text_calls[1]["reply_markup"].keyboard for b in row]


def test_scoring_rules_command_renders_guide():
    update = FakeUpdate(user_id=123)
    context = FakeContext()

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
    assert "AWS SBG Challenge Admin Panel" in admin_update.message.reply_text_calls[0]["text"]
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
    from app.challenge.service import create_challenge, update_challenge_status

    monkeypatch.setenv("ADMIN_USER_IDS", "99999")

    # 1. Populate community audience
    asyncio.run(db.set_user_state(501, "ACTIVE"))
    asyncio.run(db.set_user_state(502, "ACTIVE"))

    # 2. Open broadcast menu
    q1 = FakeCallbackQuery(user_id=99999, data="adm_broadcast")
    up1 = FakeUpdate(user_id=99999, callback_query=q1)
    ctx1 = FakeContext()

    asyncio.run(handle_admin_callback(up1, ctx1))
    assert "Community Broadcast System" in q1.edited_text
    assert q1.reply_markup is not None

    # 3. Choose leaderboard preset
    q2 = FakeCallbackQuery(user_id=99999, data="adm_bcast_preset:leaderboard")
    up2 = FakeUpdate(user_id=99999, callback_query=q2)
    ctx2 = FakeContext()

    asyncio.run(handle_admin_callback(up2, ctx2))
    assert "BROADCAST PREVIEW" in q2.edited_text
    assert "bcast_text" in ctx2.user_data

    # 4. Confirm & Send to all
    q3 = FakeCallbackQuery(user_id=99999, data="adm_bcast_send:preset_leaderboard")
    up3 = FakeUpdate(user_id=99999, callback_query=q3)
    ctx3 = FakeContext()
    ctx3.user_data["bcast_text"] = "🏆 AWS Builder Standings Updated!"

    asyncio.run(handle_admin_callback(up3, ctx3))
    assert "Broadcast Complete" in q3.edited_text
    assert len(ctx3.bot.send_message_calls) >= 2


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

    assert len(up_msg.message.reply_text_calls) == 1
    resp = up_msg.message.reply_text_calls[0]["text"]
    assert "Created with Custom Schedule" in resp
    assert "2026-09-10" in resp
    assert up_msg.message.reply_text_calls[0]["reply_markup"] is not None


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

    # 3. Add Single Question Interactively
    q_single = FakeCallbackQuery(user_id=99999, data="adm_add_single_q")
    up_s = FakeUpdate(user_id=99999, callback_query=q_single)
    ctx_s = FakeContext()
    asyncio.run(handle_admin_callback(up_s, ctx_s))

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
    ctx_q = FakeContext()
    asyncio.run(bot.handle_message(up_q, ctx_q))

    assert len(up_q.message.reply_text_calls) == 1
    assert "Added to Question Bank" in up_q.message.reply_text_calls[0]["text"]


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














