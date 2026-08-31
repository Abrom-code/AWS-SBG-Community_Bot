import html
import io
import logging
import os
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.challenge.service import (
    create_challenge,
    get_challenge,
    list_challenges,
    update_challenge_status,
    link_questions_to_challenge,
    list_questions,
    import_questions_from_csv,
    get_challenge_questions,
)
from app.challenge.keyboards import (
    get_admin_panel_keyboard,
    get_challenge_manage_keyboard,
)

logger = logging.getLogger(__name__)

ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_CHAT_ID", "0"))


def get_configured_admin_ids() -> set:
    """Returns the set of explicitly configured admin Telegram user IDs."""
    admin_ids = set()
    raw_ids = os.getenv("ADMIN_USER_IDS", "") or os.getenv("ADMIN_IDS", "")
    for part in raw_ids.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
            admin_ids.add(int(part))
    return admin_ids


async def is_admin_user(user_id: int, chat_id: Optional[int] = None, bot=None) -> bool:
    """Verifies whether a user has administrative permissions."""
    # 1. Check explicitly configured admin user IDs
    if user_id in get_configured_admin_ids():
        return True

    # 2. Check if executed directly inside the admin staff group
    if chat_id and ADMIN_GROUP_ID != 0 and chat_id == ADMIN_GROUP_ID:
        return True

    # 3. Check if user is a creator, administrator, or member of the staff group
    if ADMIN_GROUP_ID != 0 and bot:
        try:
            member = await bot.get_chat_member(chat_id=ADMIN_GROUP_ID, user_id=user_id)
            if member.status in ("creator", "administrator", "member"):
                return True
        except Exception as e:
            logger.debug(f"Admin verification check failed for user {user_id}: {e}")

    return False


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entrypoint for the Challenge Administration Panel (restricted to administrators)."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not await is_admin_user(user.id, chat.id if chat else None, context.bot):
        await update.message.reply_text(
            "⛔ <b>Access Denied:</b> This command is restricted to AWS SBG administrators.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Render admin dashboard
    text = (
        "👑 <b>AWS SBG Challenge Admin Panel</b>\n\n"
        "Welcome to the challenge operations center. You can schedule weekly competitions, "
        "manage the question bank, and publish live quizzes."
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard(),
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes admin dashboard button actions with permission checks."""
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id if query.message else None

    if not await is_admin_user(user.id, chat_id, context.bot):
        await query.answer("⛔ Access Denied: Admin privileges required.", show_alert=True)
        return

    await query.answer()

    data = query.data

    if data == "adm_panel":
        await query.edit_message_text(
            "👑 <b>AWS SBG Challenge Admin Panel</b>\n\n"
            "Select an action below to manage challenges and questions:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard(),
        )

    elif data == "adm_list_ch":
        challenges = await list_challenges(limit=10)
        if not challenges:
            await query.edit_message_text(
                "📋 <b>Challenges</b>\n\nNo challenges found. Click <b>Create Challenge</b> to start!",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_panel_keyboard(),
            )
            return

        lines = ["📋 <b>Recent Challenges:</b>\n"]
        for ch in challenges:
            status_icon = "🟢" if ch["status"] == "LIVE" else "🟡" if ch["status"] == "SCHEDULED" else "⚪"
            title = html.escape(ch["title"])
            lines.append(f"{status_icon} <b>#{ch['id']} {title}</b> — <i>{ch['status']}</i>")
            lines.append(f"   /manage_{ch['id']}\n")

        lines.append("<i>Type /manage_&lt;id&gt; or click below to return.</i>")
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard(),
        )

    elif data == "adm_qbank":
        questions = await list_questions(limit=100)
        count = len(questions)
        await query.edit_message_text(
            f"❓ <b>Question Bank Status</b>\n\n"
            f"📊 <b>Total Active Questions:</b> <code>{count}</code>\n\n"
            f"To add more questions, upload a CSV file with columns:\n"
            f"<code>question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard(),
        )

    elif data == "adm_import_csv":
        await query.edit_message_text(
            "📥 <b>Import Question Bank via CSV</b>\n\n"
            "Please send a <b>.csv file</b> as a Telegram document, or reply with raw CSV text.\n\n"
            "<b>Required Columns:</b>\n"
            "<code>question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation</code>\n\n"
            "<i>Example:</i>\n"
            "<code>What is S3?,Object Storage,Block Storage,Compute,Database,A,EASY,Storage,10,S3 is scalable object storage</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard(),
        )

    elif data == "adm_create_ch":
        # Create a new challenge and link available questions
        ch_id = await create_challenge(
            title="AWS Cloud Architecture Challenge",
            description="Weekly test on AWS core compute, storage, security, and networking services.",
            category="Architecture",
            question_time_limit_seconds=60,
            duration_seconds=3600,
            accuracy_weight=0.70,
            speed_weight=0.30,
        )
        # Link questions and create snapshot
        linked = await link_questions_to_challenge(ch_id)

        await query.edit_message_text(
            f"✅ <b>Challenge Created (DRAFT)!</b>\n\n"
            f"🆔 <b>ID:</b> <code>{ch_id}</code>\n"
            f"⚡ <b>Title:</b> AWS Cloud Architecture Challenge\n"
            f"📊 <b>Linked Questions:</b> {linked}\n\n"
            f"When ready, click <b>Publish Challenge</b> to make it LIVE for participants!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, "DRAFT"),
        )

    elif data.startswith("adm_pub:"):
        ch_id = int(data.split(":")[1])
        await update_challenge_status(ch_id, "LIVE")
        await query.edit_message_text(
            f"🚀 <b>Challenge #{ch_id} is now LIVE!</b>\n\n"
            f"Community members can now participate using /challenge.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, "LIVE"),
        )

    elif data.startswith("adm_end:"):
        ch_id = int(data.split(":")[1])
        await update_challenge_status(ch_id, "ENDED")
        await query.edit_message_text(
            f"🏁 <b>Challenge #{ch_id} has been ENDED.</b>\n\n"
            f"Final leaderboard standings are now locked.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, "ENDED"),
        )

    elif data.startswith("adm_can:"):
        ch_id = int(data.split(":")[1])
        await update_challenge_status(ch_id, "CANCELLED")
        await query.edit_message_text(
            f"❌ <b>Challenge #{ch_id} has been CANCELLED.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, "CANCELLED"),
        )


async def handle_admin_csv_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes uploaded CSV document files to bulk-import questions into the question bank."""
    if not update.message or not update.message.document:
        return

    user = update.effective_user
    chat = update.effective_chat
    if not user or not await is_admin_user(user.id, chat.id if chat else None, context.bot):
        return

    doc = update.message.document
    if not doc.file_name.endswith(".csv"):
        return

    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()
    csv_text = file_bytes.decode("utf-8", errors="ignore")

    result = await import_questions_from_csv(csv_text)
    imported = result["imported"]
    errors = result["errors"]

    err_text = ""
    if errors:
        err_list = "\n".join(errors[:5])
        err_text = f"\n\n⚠️ <b>Errors Encountered ({len(errors)}):</b>\n{html.escape(err_list)}"

    await update.message.reply_text(
        f"📥 <b>CSV Import Complete!</b>\n\n"
        f"✅ <b>Successfully Imported:</b> <code>{imported}</code> questions{err_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard(),
    )
