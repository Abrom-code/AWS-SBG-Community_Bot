from __future__ import annotations

import html
import os
from typing import Optional, List, Dict, Any
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

# Configurable constants with sensible defaults
COMMUNITY_CHANNEL = os.getenv("COMMUNITY_CHANNEL", "@AWSAASTU")
COMMUNITY_CHANNEL_URL = os.getenv("COMMUNITY_CHANNEL_URL", "https://t.me/AWSAASTU")
EDUCATION_TRACK_DAYS = os.getenv("EDUCATION_TRACK_DAYS", "Every Saturday")
EDUCATION_TRACK_TIME = os.getenv("EDUCATION_TRACK_TIME", "2:00 PM – 4:30 PM EAT (8:00 – 10:30 Local Time)")
EDUCATION_TRACK_LOCATION = os.getenv("EDUCATION_TRACK_LOCATION", "AASTU Campus + Hybrid Virtual Stream")

NEXT_EVENT_TITLE = os.getenv("NEXT_EVENT_TITLE", "AWS Community Day 2026")
NEXT_EVENT_DATE = os.getenv("NEXT_EVENT_DATE", "Saturday, October 31, 2026")
NEXT_EVENT_TIME = os.getenv("NEXT_EVENT_TIME", "Full-Day Event")
NEXT_EVENT_VENUE = os.getenv("NEXT_EVENT_VENUE", "AASTU Campus")


def get_about_text() -> str:
    """Returns descriptive overview of the AWS Student Builder Group at AASTU."""
    return (
        "✦ <b>About AWS Student Builder Group (AASTU)</b>\n\n"
        "We are a student-led cloud community at Addis Ababa Science and Technology University (AASTU), "
        "dedicated to empowering future cloud architects, software engineers, and technology leaders through "
        "hands-on learning and peer mentorship.\n\n"
        "<b>The Team</b>\n"
        "Our community is student-led by passionate cloud builders, AWS student ambassadors, "
        "technical leads, and peer mentors committed to fostering cloud literacy on campus.\n\n"
        "<b>What We Offer:</b>\n"
        "• Structured Education Tracks (AI/ML & Cloud/DevOps)\n"
        "• Hands-on workshops, bootcamps, and AWS console labs\n"
        "• Study circles for AWS Cloud certifications\n"
        "• Community hackathons and project showcases\n"
        "• Peer mentorship and technical support\n\n"
        f"Official Community Channel: {COMMUNITY_CHANNEL}"
    )


def format_track_card(track: Dict[str, Any], track_index: int = 1, total_tracks: int = 1) -> str:
    """Formats an individual education track card with a clean, breathable, modern layout."""
    title = track.get("title") or "AWS SBG Education Track"
    duration = track.get("duration")
    students = track.get("students")
    mentors = track.get("mentors")
    schedule = track.get("schedule")
    location = track.get("location")
    notes = track.get("notes")
    custom_rows = track.get("custom_fields") or ""

    display_title = title.split(":", 1)[1].strip() if ":" in title else title
    if total_tracks > 1:
        header = f"<b>{html.escape(display_title)}</b>  <i>(Track {track_index} of {total_tracks})</i>"
    else:
        header = f"<b>{html.escape(display_title)}</b>"

    lines = [f"✦ AWS SBG Education Track\n{header}", ""]

    if notes:
        lines.append(f"{html.escape(notes)}\n")

    details = []
    if schedule:
        details.append(f"• Schedule: {html.escape(schedule)}")
    if location:
        details.append(f"• Location: {html.escape(location)}")
    if students:
        details.append(f"• Cohort: {html.escape(students)}")
    if mentors:
        details.append(f"• Mentors: {html.escape(mentors)}")
    if duration:
        details.append(f"• Duration: {html.escape(duration)}")

    if details:
        lines.append("<b>Details:</b>")
        lines.extend(details)

    if custom_rows:
        extra = []
        for line in custom_rows.strip().split("\n"):
            line = line.strip()
            if line:
                if ":" in line:
                    k, v = line.split(":", 1)
                    extra.append(f"• <b>{html.escape(k.strip())}:</b> {html.escape(v.strip())}")
                else:
                    extra.append(f"• {html.escape(line)}")
        if extra:
            lines.append("\n<b>Additional Info:</b>")
            lines.extend(extra)

    lines.append(f"\nUpdates & materials: {COMMUNITY_CHANNEL}")
    lines.append("<i>Open to all university students · Free to join</i>")
    return "\n".join(lines)


def get_education_track_text(settings: Optional[dict] = None) -> str:
    """Returns curriculum details, benefits, and schedule for the Education Track.
    Supports either a track dictionary or community_settings legacy mapping.
    """
    s = settings or {}
    # If passed a track record directly with title/duration/mentors/etc.
    if "title" in s or "duration" in s or "mentors" in s:
        return format_track_card(s, 1, 1)

    title = s.get("edu_title") or "AWS SBG Education Track"
    days = s.get("edu_days") or EDUCATION_TRACK_DAYS
    time_str = s.get("edu_time") or EDUCATION_TRACK_TIME
    location = s.get("edu_location") or EDUCATION_TRACK_LOCATION
    students = s.get("edu_students") or "60 students (3 classes)"
    leads = s.get("edu_leads") or "1 mentor per class (3 mentors total)"
    notes = s.get("edu_notes") or (
        "We have launched a comprehensive <b>Education Track</b> designed to take students "
        "step-by-step from cloud fundamentals to production-ready AWS engineering."
    )
    custom_rows = s.get("edu_custom_fields") or ""

    extra_section = ""
    if custom_rows:
        lines = []
        for line in custom_rows.strip().split("\n"):
            line = line.strip()
            if line:
                if ":" in line:
                    k, v = line.split(":", 1)
                    lines.append(f"• <b>{html.escape(k.strip())}:</b> {html.escape(v.strip())}")
                else:
                    lines.append(f"• {html.escape(line)}")
        if lines:
            extra_section = "\n◆ <b>Additional Track Information:</b>\n" + "\n".join(lines) + "\n"

    return (
        f"✦ <b>{html.escape(title)}</b>\n\n"
        f"{notes}\n\n"
        "◆ <b>Cohort & Leadership:</b>\n"
        f"• <b>Active Builders:</b> {html.escape(students)}\n"
        f"• <b>Track Leads & Mentors:</b> {html.escape(leads)}\n\n"
        "◆ <b>Schedule & Logistics:</b>\n"
        f"• <b>Day:</b> {html.escape(days)}\n"
        f"• <b>Time:</b> {html.escape(time_str)}\n"
        f"• <b>Location:</b> {html.escape(location)}\n"
        f"• <b>Materials & Updates:</b> Shared directly in {COMMUNITY_CHANNEL}\n"
        f"{extra_section}\n"
        "<i>Open to all university students! No prior cloud experience required.</i>"
    )


async def get_education_track_text_async() -> str:
    """Returns education tracks overview text, querying active tracks from the database."""
    from app.db import list_education_tracks, seed_default_education_tracks_if_empty, get_all_community_settings
    await seed_default_education_tracks_if_empty()
    tracks = await list_education_tracks(active_only=True)
    if tracks:
        if len(tracks) == 1:
            return format_track_card(tracks[0], 1, 1)
        cards = [format_track_card(t, i, len(tracks)) for i, t in enumerate(tracks, start=1)]
        return "\n\n───────────────\n\n".join(cards)
    settings = await get_all_community_settings()
    return get_education_track_text(settings)


def get_clean_track_button_name(track_title: str) -> str:
    """Extracts a short, concise track name for inline buttons."""
    if not track_title:
        return "Track"
    if ":" in track_title:
        name = track_title.split(":", 1)[1].strip()
    else:
        name = track_title.strip()

    if "AI & Machine Learning" in name or "AI/ML" in name:
        return "AI/ML"
    if "Cloud & DevOps" in name or "Cloud/DevOps" in name or "DevOps" in name:
        return "Cloud/DevOps"
    if "Solutions Architect" in name:
        return "Solutions Architect"
    if "Cloud Foundations" in name:
        return "Cloud Foundations"
    return name[:18]


def get_next_event_text(settings: Optional[dict] = None) -> str:
    """Returns clean, readable information about upcoming community events."""
    s = settings or {}
    title = s.get("event_title") or NEXT_EVENT_TITLE
    date_str = s.get("event_date") or NEXT_EVENT_DATE
    time_str = s.get("event_time") or NEXT_EVENT_TIME
    venue = s.get("event_venue") or NEXT_EVENT_VENUE
    prereqs = s.get("event_prereqs") or "Everyone is invited! Register on Meetup"
    description = s.get("event_description") or "Full-day celebration featuring hackathons, keynote speeches, panel discussions, networking sessions, and snacks provided!"
    custom_rows = s.get("event_custom_fields") or ""

    extra_section = ""
    if custom_rows:
        lines = []
        for line in custom_rows.strip().split("\n"):
            line = line.strip()
            if line:
                if ":" in line:
                    k, v = line.split(":", 1)
                    lines.append(f"• <b>{html.escape(k.strip())}:</b> {html.escape(v.strip())}")
                else:
                    lines.append(f"• {html.escape(line)}")
        if lines:
            extra_section = "\n" + "\n".join(lines)

    return (
        f"✦ <b>Upcoming Event & Community Programs</b>\n\n"
        f"<b>{html.escape(title)}</b>\n\n"
        f"{html.escape(description)}\n\n"
        "<b>Event Details:</b>\n"
        f"• Date: {html.escape(date_str)}\n"
        f"• Time: {html.escape(time_str)}\n"
        f"• Venue: {html.escape(venue)}\n"
        f"• Registration: {html.escape(prereqs)}"
        f"{extra_section}\n\n"
        f"<i>Announcements & links are shared in {COMMUNITY_CHANNEL}.</i>"
    )


async def get_next_event_text_async() -> str:
    from app.db import get_all_community_settings
    settings = await get_all_community_settings()
    return get_next_event_text(settings)


def get_support_info_text() -> str:
    """Returns information about the feedback and support desk."""
    return (
        "<b>AWS SBG Support & Helpdesk</b>\n\n"
        "Need help with Education Track labs, AWS concepts, or event logistics?\n\n"
        "• Ask Question (/ask) — Send a technical or general question directly to our leads & mentors\n"
        "• Feedback (/feedback) — Share suggestions, ideas, or topics you want covered\n\n"
        "How it works: Type your message in the bot, and our leadership team will reply directly to your chat."
    )


def get_challenge_paused_text() -> str:
    """Polite notice informing members that weekly quizzes are paused."""
    return (
        "<b>Challenge Center Update</b>\n\n"
        "Competitions are currently paused while our community focuses on the Education Track (AI/ML & Cloud/DevOps) and hands-on workshops.\n\n"
        "• Tap Education to view weekly schedules & curriculum\n"
        "• Tap Next Event to see our upcoming live sessions\n"
        "• Tap Ask Question to reach our mentors & leads"
    )


def get_about_inline_keyboard() -> InlineKeyboardMarkup:
    """Interactive navigation buttons for the About page."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Education", callback_data="comm_education"),
                InlineKeyboardButton("Next Event", callback_data="comm_events"),
            ],
            [
                InlineKeyboardButton("Ask Question", callback_data="comm_question"),
                InlineKeyboardButton("Feedback", callback_data="comm_feedback"),
            ],
            [
                InlineKeyboardButton("Community Channel", url=COMMUNITY_CHANNEL_URL),
            ],
        ]
    )


def get_education_inline_keyboard(
    tracks: Optional[List[Dict[str, Any]]] = None,
    current_track_id: Optional[int] = None,
) -> InlineKeyboardMarkup:
    """Interactive navigation buttons for Education Track, with short track names on buttons."""
    rows = []
    if tracks and len(tracks) > 1:
        switcher_row = []
        for t in tracks:
            tid = t.get("id")
            title = t.get("title") or "Track"
            short_name = get_clean_track_button_name(title)
            if tid == current_track_id:
                btn_text = f"• {short_name} •"
            else:
                btn_text = short_name
            switcher_row.append(InlineKeyboardButton(btn_text, callback_data=f"comm_track:{tid}"))
            if len(switcher_row) == 2:
                rows.append(switcher_row)
                switcher_row = []
        if switcher_row:
            rows.append(switcher_row)

    rows.append([
        InlineKeyboardButton("Next Event", callback_data="comm_events"),
        InlineKeyboardButton("Ask Question", callback_data="comm_question"),
    ])
    rows.append([
        InlineKeyboardButton("Feedback", callback_data="comm_feedback"),
        InlineKeyboardButton("Community Channel", url=COMMUNITY_CHANNEL_URL),
    ])
    return InlineKeyboardMarkup(rows)


def get_events_inline_keyboard() -> InlineKeyboardMarkup:
    """Interactive navigation buttons for Next Event."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Education", callback_data="comm_education"),
                InlineKeyboardButton("Ask Question", callback_data="comm_question"),
            ],
            [
                InlineKeyboardButton("Feedback", callback_data="comm_feedback"),
                InlineKeyboardButton("Community Channel", url=COMMUNITY_CHANNEL_URL),
            ],
        ]
    )


def get_challenge_paused_keyboard() -> InlineKeyboardMarkup:
    """Navigation buttons when a paused challenge command is triggered."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Education", callback_data="comm_education"),
                InlineKeyboardButton("Next Event", callback_data="comm_events"),
            ],
            [
                InlineKeyboardButton("Ask Question", callback_data="comm_question"),
                InlineKeyboardButton("Feedback", callback_data="comm_feedback"),
            ],
        ]
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /about command and About menu button."""
    text = get_about_text()
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_about_inline_keyboard(),
            )
        except Exception:
            pass
    else:
        target = update.effective_message or update.message
        if target:
            await target.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_about_inline_keyboard(),
            )
        elif update.effective_chat and context.bot:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_about_inline_keyboard(),
            )


async def education_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /education command and Education Track menu button."""
    from app.db import list_education_tracks, seed_default_education_tracks_if_empty
    await seed_default_education_tracks_if_empty()
    tracks = await list_education_tracks(active_only=True)

    if tracks:
        current_track = tracks[0]
        text = format_track_card(current_track, 1, len(tracks))
        keyboard = get_education_inline_keyboard(tracks, current_track.get("id"))
    else:
        text = await get_education_track_text_async()
        keyboard = get_education_inline_keyboard()

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except Exception:
            pass
    else:
        target = update.effective_message or update.message
        if target:
            await target.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        elif update.effective_chat and context.bot:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /events and Next Event menu button."""
    text = await get_next_event_text_async()
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_events_inline_keyboard(),
            )
        except Exception:
            pass
    else:
        target = update.effective_message or update.message
        if target:
            await target.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_events_inline_keyboard(),
            )
        elif update.effective_chat and context.bot:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_events_inline_keyboard(),
            )


async def challenge_paused_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gracefully explains to users that challenges are paused and redirects to education."""
    text = get_challenge_paused_text()
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_challenge_paused_keyboard(),
        )
    else:
        target = update.effective_message or update.message
        if target:
            await target.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_challenge_paused_keyboard(),
            )
        elif update.effective_chat and context.bot:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_challenge_paused_keyboard(),
            )


async def handle_community_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles comm_ prefix callbacks for smooth inline navigation."""
    query = update.callback_query
    if not query:
        return
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    if data == "comm_about":
        await about_command(update, context)
    elif data == "comm_education":
        await education_command(update, context)
    elif data.startswith("comm_track:"):
        try:
            track_id = int(data.split(":")[1])
        except (IndexError, ValueError):
            return
        from app.db import get_education_track, list_education_tracks
        tracks = await list_education_tracks(active_only=True)
        track = await get_education_track(track_id)
        if track:
            idx = 1
            for i, t in enumerate(tracks, start=1):
                if t["id"] == track_id:
                    idx = i
                    break
            text = format_track_card(track, idx, len(tracks))
            keyboard = get_education_inline_keyboard(tracks, track_id)
            try:
                await query.edit_message_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            except Exception:
                pass
    elif data == "comm_events":
        await events_command(update, context)
    elif data == "comm_feedback":
        from app.bot import feedback_command
        await feedback_command(update, context)
    elif data == "comm_question":
        from app.bot import support_command
        await support_command(update, context)
