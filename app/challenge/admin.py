import html
import io
import logging
import os
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.db import get_all_broadcast_user_ids, set_user_state
from app.challenge.service import (
    create_challenge,
    get_challenge,
    get_active_challenge,
    list_challenges,
    update_challenge_status,
    link_questions_to_challenge,
    list_questions,
    create_question,
    import_questions_from_csv,
    get_challenge_questions,
    get_monthly_analytics_report,
    delete_challenge,
    update_challenge_details,
    get_weekly_leaderboard,
    get_monthly_leaderboard,
)
from app.challenge.keyboards import (
    get_admin_panel_keyboard,
    get_challenge_manage_keyboard,
    get_admin_schedule_presets_keyboard,
    get_admin_broadcast_presets_keyboard,
    get_admin_broadcast_confirm_keyboard,
    get_admin_report_keyboard,
    get_question_bank_actions_keyboard,
    get_wizard_questions_keyboard,
    get_challenge_delete_confirm_keyboard,
    get_admin_leaderboard_keyboard,
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
        from telegram import InlineKeyboardMarkup
        challenges = await list_challenges(limit=10)
        if not challenges:
            await query.edit_message_text(
                "📋 <b>Challenges</b>\n\nNo challenges found. Click <b>Create Challenge</b> to start!",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_panel_keyboard(),
            )
            return

        lines = ["📋 <b>Active & Recent Challenges:</b>\n"]
        buttons = []
        for ch in challenges:
            status_icon = "🟢" if ch["status"] == "LIVE" else "⏳" if ch["status"] == "SCHEDULED" else "🏁" if ch["status"] == "ENDED" else "🛠️"
            title = html.escape(ch["title"])
            lines.append(f"{status_icon} <b>#{ch['id']} {title}</b> — <i>{ch['status']}</i>")
            buttons.append([InlineKeyboardButton(f"{status_icon} Manage #{ch['id']} {title[:20]}", callback_data=f"adm_manage:{ch['id']}")])

        buttons.append([InlineKeyboardButton("➕ Create New Challenge", callback_data="adm_create_ch")])
        buttons.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")])
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data.startswith("adm_manage:"):
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        if not ch:
            await query.answer("⚠️ Challenge not found.", show_alert=True)
            return

        questions = await get_challenge_questions(ch_id)
        status = ch["status"]
        title = html.escape(ch["title"])
        category = html.escape(ch["category"])
        starts = ch.get("starts_at") or "Unscheduled (Draft)"
        ends = ch.get("ends_at") or "None"
        time_l = ch["question_time_limit_seconds"]

        manage_text = (
            f"⚙️ <b>Manage Challenge #{ch_id}</b>\n\n"
            f"⚡ <b>Title:</b> {title}\n"
            f"🏗️ <b>Category:</b> {category}\n"
            f"🚦 <b>Current Status:</b> <code>{status}</code>\n"
            f"⏳ <b>Starts At:</b> <code>{starts}</code>\n"
            f"🏁 <b>Ends At:</b> <code>{ends}</code>\n"
            f"⏱️ <b>Time Limit:</b> {time_l}s per question\n"
            f"📊 <b>Attached Questions:</b> <code>{len(questions)}</code>\n\n"
            f"<i>Select an action below to update or change status:</i>"
        )
        await query.edit_message_text(
            manage_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
        )

    elif data.startswith("adm_link_q:"):
        ch_id = int(data.split(":")[1])
        linked = await link_questions_to_challenge(ch_id)
        ch = await get_challenge(ch_id)
        status = ch["status"] if ch else "LIVE"
        await query.answer(f"✅ Linked questions! Total: {linked}", show_alert=True)
        questions = await get_challenge_questions(ch_id)
        await query.edit_message_text(
            f"✅ <b>Question Bank Linked to Challenge #{ch_id}!</b>\n\n"
            f"📊 <b>Total Questions Now Attached:</b> <code>{len(questions)}</code>\n\n"
            f"Participants will be tested on these randomized questions.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
        )

    elif data == "adm_cr_custom_date":
        await set_user_state(user.id, "WAITING_FOR_ADMIN_SCHEDULE")
        await query.edit_message_text(
            "📅 <b>Set Custom Challenge Schedule</b>\n\n"
            "Please type and send the start and end date/time in one of these formats:\n\n"
            "• <code>2026-09-05 14:00 to 2026-09-12 18:00</code>\n"
            "• <code>2026-09-05 to 2026-09-12</code>\n"
            "• <code>2026-09-05T14:00:00 to 2026-09-12T18:00:00</code>\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data == "adm_qbank":
        questions = await list_questions(limit=100)
        count = len(questions)
        await query.edit_message_text(
            f"❓ <b>AWS Question Bank Operations</b>\n\n"
            f"📊 <b>Active Questions Available:</b> <code>{count}</code>\n\n"
            f"You can add questions interactively one-by-one, or bulk import via CSV.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_question_bank_actions_keyboard(),
        )

    elif data == "adm_add_single_q":
        await set_user_state(user.id, "WAITING_FOR_ADMIN_SINGLE_QUESTION")
        await query.edit_message_text(
            "✍️ <b>Add Question to Question Bank</b>\n\n"
            "Please send the question details in the following format:\n\n"
            "<code>What is Amazon DynamoDB?\n"
            "A: Relational database\n"
            "B: Key-value NoSQL database\n"
            "C: In-memory cache\n"
            "D: Object storage\n"
            "Answer: B\n"
            "Category: Database\n"
            "Difficulty: EASY\n"
            "Explanation: DynamoDB is a managed NoSQL key-value store</code>\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
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
        await set_user_state(user.id, "WAITING_FOR_CHALLENGE_TITLE")
        await query.edit_message_text(
            "✍️ <b>Create Challenge Wizard (Step 1/2)</b>\n\n"
            "Please enter the <b>Challenge Title</b> and optional <b>Category</b>:\n\n"
            "<i>Example:</i> <code>AWS Serverless Microservices | Compute</code>\n"
            "<i>(Or just send the title: <code>AWS Serverless Microservices</code>)</i>\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_del_prompt:"):
        ch_id = int(data.split(":")[1])
        ch = await get_challenge(ch_id)
        title = html.escape(ch["title"]) if ch else f"#{ch_id}"
        await query.edit_message_text(
            f"⚠️ <b>Delete Challenge #{ch_id}?</b>\n\n"
            f"⚡ <b>Title:</b> {title}\n\n"
            f"Are you sure you want to permanently delete this challenge and all its participant submissions?",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_delete_confirm_keyboard(ch_id),
        )

    elif data.startswith("adm_del_conf:"):
        ch_id = int(data.split(":")[1])
        await delete_challenge(ch_id)
        await query.edit_message_text(
            f"🗑️ <b>Challenge #{ch_id} has been permanently deleted.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard(),
        )

    elif data.startswith("adm_edit_title:"):
        ch_id = int(data.split(":")[1])
        context.user_data["edit_ch_id"] = ch_id
        await set_user_state(user.id, "WAITING_FOR_EDIT_CHALLENGE_TITLE")
        await query.edit_message_text(
            f"✏️ <b>Edit Challenge #{ch_id}</b>\n\n"
            f"Please send the new title and category (e.g. <code>AWS Cloud Essentials | General</code>):\n\n"
            f"<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data.startswith("adm_cr_sched:"):
        parts = data.split(":")
        start_opt = parts[1]
        from datetime import datetime, timezone, timedelta
        now_dt = datetime.now(timezone.utc)

        if start_opt == "now":
            starts_at = now_dt.isoformat()
            ends_at = (now_dt + timedelta(days=7)).isoformat()
            status = "LIVE"
            schedule_note = "🟢 <b>Status:</b> LIVE immediately (Ends in 7 days)"
        elif start_opt == "1h":
            s_dt = now_dt + timedelta(hours=1)
            starts_at = s_dt.isoformat()
            ends_at = (s_dt + timedelta(days=7)).isoformat()
            status = "SCHEDULED"
            schedule_note = "⏳ <b>Status:</b> SCHEDULED (Starts in 1 hour)"
        elif start_opt == "24h":
            s_dt = now_dt + timedelta(days=1)
            starts_at = s_dt.isoformat()
            ends_at = (s_dt + timedelta(days=7)).isoformat()
            status = "SCHEDULED"
            schedule_note = "📅 <b>Status:</b> SCHEDULED (Starts in 24 hours)"
        else:
            starts_at = None
            ends_at = None
            status = "DRAFT"
            schedule_note = "🛠️ <b>Status:</b> DRAFT (Unscheduled)"

        title = context.user_data.get("wiz_title", "AWS Cloud Architecture Challenge")
        category = context.user_data.get("wiz_category", "Architecture")

        ch_id = await create_challenge(
            title=title,
            description="Weekly test on AWS core compute, storage, security, and networking services.",
            category=category,
            starts_at=starts_at,
            ends_at=ends_at,
            question_time_limit_seconds=60,
            duration_seconds=604800 if ends_at else 3600,
            accuracy_weight=0.70,
            speed_weight=0.30,
        )
        linked = await link_questions_to_challenge(ch_id)
        if status != "DRAFT":
            await update_challenge_status(ch_id, status)

        context.user_data.pop("wiz_title", None)
        context.user_data.pop("wiz_category", None)

        await query.edit_message_text(
            f"✅ <b>Challenge #{ch_id} Created!</b>\n\n"
            f"⚡ <b>Title:</b> {html.escape(title)}\n"
            f"🏗️ <b>Category:</b> {html.escape(category)}\n"
            f"{schedule_note}\n"
            f"📊 <b>Linked Questions:</b> {linked}\n\n"
            f"Participants can now view/access it according to the schedule!",
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_manage_keyboard(ch_id, status),
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

    elif data == "adm_report":
        rep = await get_monthly_analytics_report()
        month = rep["month_name"]
        users = rep["total_users"]
        challenges = rep["total_challenges"]
        attempts = rep["total_attempts"]
        total_score = rep["total_score"]
        avg_score = rep["avg_score"]
        accuracy = rep["accuracy_pct"]
        correct = rep["total_correct"]
        answered = rep["total_answered"]
        feedbacks = rep["feedback_count"]
        replies = rep["reply_count"]
        questions = rep["question_count"]
        champions = rep["champions"]

        champs_text = ""
        if champions:
            medals = ["🥇", "🥈", "🥉"]
            for idx, c in enumerate(champions[:3]):
                name = html.escape(c["user_name"])
                uname = f" (@{html.escape(c['username'])})" if c.get("username") else ""
                champs_text += f"• {medals[idx]} <b>{name}</b>{uname} — <code>{c['total_score']} pts</code> ({c['challenges_completed']} quizzes)\n"
        else:
            champs_text = "• <i>No completed challenge attempts recorded yet this month.</i>\n"

        report_card = (
            f"📊 <b>AWS Student Builder Monthly Activity Report</b>\n"
            f"📅 <b>Period:</b> {month}\n\n"
            f"👥 <b>Community Engagement:</b>\n"
            f"• Registered Bot Members: <code>{users}</code>\n"
            f"• Feedback Tickets Received: <code>{feedbacks}</code>\n"
            f"• Staff Replies Delivered: <code>{replies}</code>\n\n"
            f"⚡ <b>Challenges & Competitions:</b>\n"
            f"• Total Challenges: <code>{challenges}</code>\n"
            f"• Total Submissions: <code>{attempts}</code>\n"
            f"• Community Accuracy: <code>{accuracy}%</code> ({correct}/{answered})\n"
            f"• Average Score: <code>{avg_score} pts</code>\n"
            f"• Total Points Earned: <code>{total_score} pts</code>\n"
            f"• Active Questions in Bank: <code>{questions}</code>\n\n"
            f"🏆 <b>Top 3 Builders of the Month:</b>\n"
            f"{champs_text}\n"
            f"<i>AWS Student Builder Group • AASTU</i>"
        )
        await query.edit_message_text(
            report_card,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_report_keyboard(),
        )

    elif data == "adm_leaderboards":
        active_ch = await get_active_challenge()
        active_ch_id = active_ch["id"] if active_ch else 0
        await query.edit_message_text(
            "🏆 <b>Admin Leaderboard & Builder Standings</b>\n\n"
            "View live participant scores, ranks, and monthly cumulative standings:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_leaderboard_keyboard(active_ch_id),
        )

    elif data.startswith("adm_lb_view:"):
        parts = data.split(":")
        mode = parts[1]
        target_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

        if mode == "weekly" and target_id > 0:
            ch = await get_challenge(target_id)
            title = html.escape(ch["title"]) if ch else f"#{target_id}"
            lb_data = await get_weekly_leaderboard(target_id, limit=20)
            entries = lb_data["entries"]

            if not entries:
                text = (
                    f"🏆 <b>Active Challenge Leaderboard</b>\n"
                    f"⚡ <b>{title}</b>\n\n"
                    f"<i>No completed submissions yet.</i>"
                )
            else:
                lines = [
                    f"🏆 <b>Active Challenge Leaderboard</b>",
                    f"⚡ <b>{title}</b>\n",
                    f"👥 <b>Total Completed Participants:</b> <code>{lb_data['total_count']}</code>\n",
                ]
                medals = {1: "🥇", 2: "🥈", 3: "🥉"}
                for row in entries:
                    rank_icon = medals.get(row["rank"], f"<b>{row['rank']}.</b>")
                    name = html.escape(row["user_name"])
                    uname = f" (@{html.escape(row['username'])})" if row.get("username") else ""
                    uid = row["telegram_user_id"]
                    score = row["score"]
                    correct = row["correct_count"]
                    total = row["answered_count"]
                    lines.append(f"{rank_icon} <b>{name}</b>{uname} [<code>{uid}</code>] — <b>{score} pts</b> ({correct}/{total} ✅)")
                text = "\n".join(lines)
        else:
            lb_data = await get_monthly_leaderboard(limit=20)
            entries = lb_data["entries"]

            if not entries:
                text = (
                    f"📅 <b>Monthly Season Championship Standings</b>\n\n"
                    f"<i>No completed challenge data recorded yet this season.</i>"
                )
            else:
                lines = [
                    f"📅 <b>Monthly Season Championship Standings</b>",
                    f"🏆 <b>Top Builders of the Month</b>\n",
                    f"👥 <b>Total Ranked Builders:</b> <code>{lb_data['total_count']}</code>\n",
                ]
                medals = {1: "🥇", 2: "🥈", 3: "🥉"}
                for row in entries:
                    rank_icon = medals.get(row["rank"], f"<b>{row['rank']}.</b>")
                    name = html.escape(row["user_name"])
                    uname = f" (@{html.escape(row['username'])})" if row.get("username") else ""
                    uid = row["telegram_user_id"]
                    total_pts = row["total_score"]
                    completed = row["challenges_completed"]
                    lines.append(f"{rank_icon} <b>{name}</b>{uname} [<code>{uid}</code>] — <b>{total_pts} pts</b> ({completed} quizzes)")
                text = "\n".join(lines)

        from telegram import InlineKeyboardMarkup
        back_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Leaderboards", callback_data="adm_leaderboards")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")],
        ])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb)

    elif data == "adm_broadcast":
        users = await get_all_broadcast_user_ids()
        count = len(users)
        await query.edit_message_text(
            f"📢 <b>Community Broadcast System</b>\n\n"
            f"Deliver an announcement notification to all registered bot participants.\n\n"
            f"👥 <b>Active Members in Reach:</b> <code>{count}</code>\n\n"
            f"<i>Select a preset below or compose a custom message:</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_broadcast_presets_keyboard(),
        )

    elif data == "adm_bcast_custom":
        await set_user_state(user.id, "WAITING_FOR_ADMIN_BROADCAST")
        await query.edit_message_text(
            "✍️ <b>Custom Announcement Broadcast</b>\n\n"
            "Please type and send the announcement text now.\n\n"
            "• Supports HTML formatting (<b>bold</b>, <i>italic</i>, <code>code</code>)\n"
            "• Supports URLs and emojis\n\n"
            "<i>(Type /cancel to abort)</i>",
            parse_mode=ParseMode.HTML,
        )

    elif data == "adm_bcast_preset:challenge":
        active_ch = await get_active_challenge()
        users = await get_all_broadcast_user_ids()
        count = len(users)
        if not active_ch:
            await query.answer("⚠️ No live or scheduled challenge found.", show_alert=True)
            return

        title = active_ch["title"]
        cat = active_ch["category"]
        time_l = active_ch["question_time_limit_seconds"]
        bcast_text = (
            f"🚀 <b>AWS Builder Challenge Announcement!</b>\n\n"
            f"A cloud competition is active:\n"
            f"⚡ <b>{html.escape(title)}</b>\n"
            f"🏗️ <b>Category:</b> {html.escape(cat)}\n"
            f"⏱️ <b>Time Limit:</b> {time_l}s per question\n\n"
            f"👉 Open /challenge in the bot now to take the quiz and climb the leaderboard!\n\n"
            f"📢 @AWSAASTU"
        )
        context.user_data["bcast_text"] = bcast_text

        preview_text = (
            f"📢 <b>BROADCAST PREVIEW</b>\n"
            f"👥 <b>Target Audience:</b> <code>{count}</code> members\n\n"
            f"<blockquote>{bcast_text}</blockquote>\n\n"
            f"Ready to deliver this notification?"
        )
        await query.edit_message_text(
            preview_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_broadcast_confirm_keyboard("preset_challenge"),
        )

    elif data == "adm_bcast_preset:leaderboard":
        users = await get_all_broadcast_user_ids()
        count = len(users)
        bcast_text = (
            "🏆 <b>AWS Builder Championship Standings Updated!</b>\n\n"
            "The Weekly & Monthly championship leaderboards are refreshed with latest scores!\n\n"
            "Check where you rank among student cloud builders.\n\n"
            "👉 Send /leaderboard to view the rankings!\n\n"
            "📢 @AWSAASTU"
        )
        context.user_data["bcast_text"] = bcast_text

        preview_text = (
            f"📢 <b>BROADCAST PREVIEW</b>\n"
            f"👥 <b>Target Audience:</b> <code>{count}</code> members\n\n"
            f"<blockquote>{bcast_text}</blockquote>\n\n"
            f"Ready to deliver this notification?"
        )
        await query.edit_message_text(
            preview_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_broadcast_confirm_keyboard("preset_leaderboard"),
        )

    elif data == "adm_bcast_preset:report":
        rep = await get_monthly_analytics_report()
        month = rep["month_name"]
        champions = rep["champions"]
        champs_text = ""
        if champions:
            medals = ["🥇", "🥈", "🥉"]
            for idx, c in enumerate(champions[:3]):
                name = html.escape(c["user_name"])
                uname = f" (@{html.escape(c['username'])})" if c.get("username") else ""
                champs_text += f"{medals[idx]} <b>{name}</b>{uname} — <code>{c['total_score']} pts</code>\n"
        else:
            champs_text = "• <i>Check /leaderboard for latest championship rankings!</i>\n"

        bcast_text = (
            f"📊 <b>AWS SBG Monthly Season Wrap-Up ({month})</b>\n\n"
            f"Awesome work builders! Here is what our community achieved this month:\n\n"
            f"👥 <b>Active Members:</b> <code>{rep['total_users']}</code>\n"
            f"⚡ <b>Challenges Completed:</b> <code>{rep['total_attempts']}</code>\n"
            f"🎯 <b>Community Accuracy:</b> <code>{rep['accuracy_pct']}%</code>\n"
            f"🏆 <b>Total Points Earned:</b> <code>{rep['total_score']} pts</code>\n\n"
            f"🌟 <b>Top 3 Builders of the Month:</b>\n"
            f"{champs_text}\n"
            f"👉 Tap <b>/challenge</b> and <b>/leaderboard</b> to participate in upcoming events!\n\n"
            f"📢 @AWSAASTU"
        )
        context.user_data["bcast_text"] = bcast_text
        users = await get_all_broadcast_user_ids()
        preview_text = (
            f"📢 <b>BROADCAST PREVIEW (Monthly Report)</b>\n"
            f"👥 <b>Target Audience:</b> <code>{len(users)}</code> members\n\n"
            f"<blockquote>{bcast_text}</blockquote>\n\n"
            f"Ready to deliver this report announcement to the community?"
        )
        await query.edit_message_text(
            preview_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_broadcast_confirm_keyboard("preset_report"),
        )

    elif data.startswith("adm_bcast_send:"):
        bcast_text = context.user_data.get("bcast_text")
        if not bcast_text:
            await query.answer("⚠️ No broadcast message prepared.", show_alert=True)
            return

        users = await get_all_broadcast_user_ids()
        logger.info(f"📢 Initiating broadcast to {len(users)} registered users: {users}")
        sent = 0
        failed = 0

        for uid in users:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=bcast_text,
                    parse_mode=ParseMode.HTML,
                )
                sent += 1
                logger.info(f"✅ Broadcast delivered to user_id={uid}")
            except Exception as e:
                logger.warning(f"⚠️ Broadcast send failed for user {uid}: {e}")
                failed += 1

        context.user_data.pop("bcast_text", None)

        await query.edit_message_text(
            f"📢 <b>Broadcast Complete!</b>\n\n"
            f"✅ <b>Delivered Successfully:</b> <code>{sent}</code>\n"
            f"⚠️ <b>Failed / Blocked:</b> <code>{failed}</code>\n\n"
            f"<i>The announcement has been broadcast to all community members.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_panel_keyboard(),
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
