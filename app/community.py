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
        "The <b>AWS Student Builder Group at Addis Ababa Science and Technology University (AASTU)</b> "
        "is an active student cloud community dedicated to empowering future cloud architects, "
        "software engineers, and technology leaders.\n\n"
        "◆ <b>Our Mission</b>\n"
        "To bridge the gap between academic theory and real-world cloud engineering through "
        "hands-on learning, collaborative projects, peer mentorship, and industry certification.\n\n"
        "◆ <b>The Team</b>\n"
        "Our community is student-led by passionate cloud builders, AWS student ambassadors, "
        "technical leads, and peer mentors committed to fostering cloud literacy on campus.\n\n"
        "◆ <b>What We Provide to Members:</b>\n"
        "• <b>Structured Education Track:</b> Hands-on cloud curriculum from zero to advanced.\n"
        "• <b>Practical Workshops & Labs:</b> Real AWS console labs, serverless architectures, and CI/CD pipelines.\n"
        "• <b>Certification Roadmaps:</b> Study circles for AWS Certified Cloud Practitioner & Solutions Architect.\n"
        "• <b>Hackathons & Project Showcases:</b> Building scalable solutions for campus and community needs.\n"
        "• <b>Mentorship & Career Networking:</b> Connecting students with industry practitioners.\n\n"
        f"✦ <b>Official Community Channel:</b> {COMMUNITY_CHANNEL}"
    )


def format_track_card(track: Dict[str, Any], track_index: int = 1, total_tracks: int = 1) -> str:
    """Formats an individual education track card.
    Conditionally renders only provided fields. Omitted or skipped fields are completely excluded.
    Strictly uses approved minimalist emojis.
    """
    title = track.get("title") or "AWS SBG Education Track"
    duration = track.get("duration")
    students = track.get("students")
    mentors = track.get("mentors")
    schedule = track.get("schedule")
    location = track.get("location")
    notes = track.get("notes")
    custom_rows = track.get("custom_fields") or ""

    if total_tracks > 1:
        header = f"✦ <b>Track {track_index} of {total_tracks}: {html.escape(title)}</b>"
    else:
        header = f"✦ <b>{html.escape(title)}</b>"

    lines = [header]

    if duration:
        lines.append(f"• <b>Duration:</b> {html.escape(duration)}")

    # Cohort & Leadership details
    cohort_details = []
    if students:
        cohort_details.append(f"• <b>Active Builders:</b> {html.escape(students)}")
    if mentors:
        cohort_details.append(f"• <b>Mentors & Leads:</b> {html.escape(mentors)}")
    if cohort_details:
        lines.append("\n◆ <b>Cohort & Leadership:</b>")
        lines.extend(cohort_details)

    # Schedule & Logistics
    logistics = []
    if schedule:
        logistics.append(f"• <b>Schedule:</b> {html.escape(schedule)}")
    if location:
        logistics.append(f"• <b>Location:</b> {html.escape(location)}")
    if logistics:
        lines.append("\n◆ <b>Schedule & Logistics:</b>")
        lines.extend(logistics)
        lines.append(f"• <b>Materials & Updates:</b> Shared directly in {COMMUNITY_CHANNEL}")

    # Curriculum & Focus
    if notes:
        lines.append("\n◆ <b>Curriculum & Focus:</b>")
        lines.append(f"<blockquote>{html.escape(notes)}</blockquote>")

    # Extra custom rows
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
            lines.append("\n◆ <b>Additional Track Information:</b>")
            lines.extend(extra)

    lines.append("\n<i>Open to all university students! No prior cloud experience required.</i>")
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


def get_next_event_text(settings: Optional[dict] = None) -> str:
    """Returns information about the upcoming event and community programs."""
    s = settings or {}
    title = s.get("event_title") or NEXT_EVENT_TITLE
    date_str = s.get("event_date") or NEXT_EVENT_DATE
    time_str = s.get("event_time") or NEXT_EVENT_TIME
    venue = s.get("event_venue") or NEXT_EVENT_VENUE
    prereqs = s.get("event_prereqs") or "Laptop & a free AWS Builder ID / Free-Tier account"
    description = s.get("event_description") or "Hands-on exploration of AWS compute, storage, networking, and serverless fundamentals."
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
            extra_section = "\n◆ <b>Additional Session Info:</b>\n" + "\n".join(lines) + "\n"

    return (
        "✦ <b>Upcoming Event & Community Programs</b>\n\n"
        "Join fellow student builders in our next live hands-on session:\n\n"
        "🔹 <b>Featured Session:</b>\n"
        f"<b>{html.escape(title)}</b>\n\n"
        f"• <b>Date & Day:</b> {html.escape(date_str)}\n"
        f"• <b>Time:</b> {html.escape(time_str)}\n"
        f"• <b>Venue:</b> {html.escape(venue)}\n"
        f"• <b>Prerequisites:</b> {html.escape(prereqs)}\n\n"
        "◆ <b>Session Overview:</b>\n"
        f"<blockquote>{html.escape(description)}</blockquote>\n"
        f"{extra_section}\n"
        "◆ <b>Upcoming Programs in this Cohort:</b>\n"
        "🔹 <b>AWS Certification Study Circles:</b> Guided group prep for AWS certs.\n"
        "🔹 <b>Hands-On Cloud Labs:</b> Building serverless web apps from scratch.\n"
        "🔹 <b>Campus Cloud Hackathon:</b> Team architecture challenge with mentorship.\n"
        "🔹 <b>Industry Guest Talks:</b> Insights from practicing cloud architects.\n\n"
        f"<i>Stay tuned to {COMMUNITY_CHANNEL} for room details, meeting links, and slide decks!</i>"
    )


async def get_next_event_text_async() -> str:
    from app.db import get_all_community_settings
    settings = await get_all_community_settings()
    return get_next_event_text(settings)


def get_support_info_text() -> str:
    """Returns information about the feedback and support desk."""
    return (
        "✦ <b>AWS SBG Support & Helpdesk</b>\n\n"
        "Have questions about the Education Track, workshop schedules, technical roadblocks, "
        "or ideas for the community? The AWS SBG core team is here to assist you.\n\n"
        "◆ <b>Two Channels to Connect:</b>\n"
        "• <b>Ask a Question (/ask):</b> Ask technical questions, get help with labs, or inquire about events.\n"
        "• <b>Submit Feedback (/feedback):</b> Share ideas, suggestions, and topic requests for our community.\n\n"
        "◆ <b>How It Works:</b>\n"
        "1. Tap <b>Ask Question</b> or <b>Submit Feedback</b> in the menu below.\n"
        "2. Type your message directly into this chat.\n"
        "3. Your message is forwarded directly to the student leadership team.\n"
        "4. A team member replies directly back to your Telegram chat!\n\n"
        "<i>We typically reply within a few hours.</i>"
    )


def get_challenge_paused_text() -> str:
    """Polite notice informing members that weekly quizzes are paused in favor of the Education Track."""
    return (
        "✦ <b>Challenge Center Update</b>\n\n"
        "Weekly quiz competitions are currently paused while our community focuses on our newly launched "
        "<b>Education Track</b> and hands-on workshops!\n\n"
        "◆ <b>Get Involved:</b>\n"
        "• Check out <b>Education Track</b> for weekly curriculum & schedules.\n"
        "• View <b>Next Event</b> to see our upcoming live sessions.\n"
        "• Tap <b>Ask Question</b> or <b>Submit Feedback</b> to connect with the core team."
    )


def get_about_inline_keyboard() -> InlineKeyboardMarkup:
    """Interactive navigation buttons for the About page."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔹 Education Track", callback_data="comm_education"),
                InlineKeyboardButton("🔹 Next Event", callback_data="comm_events"),
            ],
            [
                InlineKeyboardButton("🔹 Feedback", callback_data="comm_feedback"),
                InlineKeyboardButton("🔹 Ask Question", callback_data="comm_question"),
            ],
            [
                InlineKeyboardButton("› Channel @AWSAASTU", url=COMMUNITY_CHANNEL_URL),
            ],
        ]
    )


def get_education_inline_keyboard(
    tracks: Optional[List[Dict[str, Any]]] = None,
    current_track_id: Optional[int] = None,
) -> InlineKeyboardMarkup:
    """Interactive navigation buttons for Education Track, with track switcher if multiple tracks exist."""
    rows = []
    if tracks and len(tracks) > 1:
        switcher_row = []
        for t in tracks:
            tid = t.get("id")
            title = t.get("title") or "Track"
            short_title = title if len(title) <= 20 else title[:18] + ".."
            if tid == current_track_id:
                btn_text = f"● {short_title}"
            else:
                btn_text = f"🔹 {short_title}"
            switcher_row.append(InlineKeyboardButton(btn_text, callback_data=f"comm_track:{tid}"))
            if len(switcher_row) == 2:
                rows.append(switcher_row)
                switcher_row = []
        if switcher_row:
            rows.append(switcher_row)

    rows.append([
        InlineKeyboardButton("🔹 Next Event", callback_data="comm_events"),
        InlineKeyboardButton("🔹 Ask Question", callback_data="comm_question"),
    ])
    rows.append([
        InlineKeyboardButton("🔹 Feedback", callback_data="comm_feedback"),
        InlineKeyboardButton("› Channel @AWSAASTU", url=COMMUNITY_CHANNEL_URL),
    ])
    return InlineKeyboardMarkup(rows)


def get_events_inline_keyboard() -> InlineKeyboardMarkup:
    """Interactive navigation buttons for Next Event."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔹 Education Track", callback_data="comm_education"),
                InlineKeyboardButton("🔹 Ask Question", callback_data="comm_question"),
            ],
            [
                InlineKeyboardButton("🔹 Feedback", callback_data="comm_feedback"),
                InlineKeyboardButton("› Channel @AWSAASTU", url=COMMUNITY_CHANNEL_URL),
            ],
        ]
    )


def get_challenge_paused_keyboard() -> InlineKeyboardMarkup:
    """Navigation buttons when a paused challenge command is triggered."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔹 Education Track", callback_data="comm_education"),
                InlineKeyboardButton("🔹 Next Event", callback_data="comm_events"),
            ],
            [
                InlineKeyboardButton("🔹 Feedback", callback_data="comm_feedback"),
                InlineKeyboardButton("🔹 Ask Question", callback_data="comm_question"),
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
    elif update.message:
        await update.message.reply_text(
            text,
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
    elif update.message:
        await update.message.reply_text(
            text,
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
    elif update.message:
        await update.message.reply_text(
            text,
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
    elif update.message:
        await update.message.reply_text(
            text,
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
