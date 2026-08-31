from typing import Dict, Optional, List
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


def get_challenge_start_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Button to initiate an active challenge with info and leaderboard shortcuts."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Start Challenge Now", callback_data=f"ch_start:{challenge_id}")],
            [
                InlineKeyboardButton("🏆 Leaderboard", callback_data=f"lb_weekly:{challenge_id}"),
                InlineKeyboardButton("📖 How Scoring Works", callback_data="ch_rules"),
            ],
            [InlineKeyboardButton("🔙 Back to Challenge Center", callback_data="ch_hub")],
        ]
    )


def get_question_options_keyboard(
    challenge_id: int,
    question_index: int,
    options_keys: Optional[List[str]] = None,
) -> InlineKeyboardMarkup:
    """Randomized 4-option question response keyboard."""
    keys = options_keys or ["A", "B", "C", "D"]
    # Group in 2x2 grid
    row1 = [
        InlineKeyboardButton(f"{keys[0]}", callback_data=f"ch_ans:{challenge_id}:{question_index}:{keys[0]}"),
        InlineKeyboardButton(f"{keys[1]}", callback_data=f"ch_ans:{challenge_id}:{question_index}:{keys[1]}"),
    ]
    row2 = [
        InlineKeyboardButton(f"{keys[2]}", callback_data=f"ch_ans:{challenge_id}:{question_index}:{keys[2]}"),
        InlineKeyboardButton(f"{keys[3]}", callback_data=f"ch_ans:{challenge_id}:{question_index}:{keys[3]}"),
    ]
    return InlineKeyboardMarkup([row1, row2])


def get_leaderboard_keyboard(
    challenge_id: Optional[int] = None,
    mode: str = "weekly",
    page: int = 1,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """Navigation for Weekly vs Monthly leaderboards with pagination (omits the active view's button)."""
    ch_id = challenge_id or 0
    buttons = []

    # 1. Pagination Row (when there are multiple pages)
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"lb_{mode}:{ch_id}:{page - 1}"))

        nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))

        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"lb_{mode}:{ch_id}:{page + 1}"))

        buttons.append(nav_row)

    # 2. Switch to alternate leaderboard view (omit current view)
    if mode == "weekly":
        buttons.append([InlineKeyboardButton("📅 Switch to Monthly Cumulative", callback_data="lb_monthly:0:1")])
    else:
        buttons.append([InlineKeyboardButton("🏆 Switch to Weekly Leaderboard", callback_data=f"lb_weekly:{ch_id}:1")])

    # 3. Action and info shortcuts
    action_row = []
    if ch_id > 0:
        action_row.append(InlineKeyboardButton("🚀 Take Challenge", callback_data=f"ch_start:{ch_id}"))
    action_row.append(InlineKeyboardButton("📖 How Scoring Works", callback_data="ch_rules"))
    buttons.append(action_row)

    # 4. Context-aware Back navigation
    if ch_id > 0:
        buttons.append([
            InlineKeyboardButton("🔙 Back to Challenge", callback_data=f"ch_past:{ch_id}"),
            InlineKeyboardButton("🔙 Challenge Center", callback_data="ch_hub"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("📚 Past Challenges", callback_data="ch_past_list"),
            InlineKeyboardButton("🔙 Challenge Center", callback_data="ch_hub"),
        ])

    return InlineKeyboardMarkup(buttons)


def get_scoring_rules_keyboard(challenge_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Navigation keyboard displayed on the Scoring Rules guide (omits the rules button itself)."""
    ch_id = challenge_id or 0
    buttons = []
    if ch_id > 0:
        buttons.append([InlineKeyboardButton("🚀 Start Challenge Now", callback_data=f"ch_start:{ch_id}")])
        buttons.append([InlineKeyboardButton("🏆 View Leaderboard", callback_data=f"lb_weekly:{ch_id}:1")])
    else:
        buttons.append([InlineKeyboardButton("📅 Monthly Cumulative Leaderboard", callback_data="lb_monthly:0:1")])
    buttons.append([InlineKeyboardButton("🔙 Back to Challenge Center", callback_data="ch_hub")])
    return InlineKeyboardMarkup(buttons)


def get_past_challenges_keyboard(challenges: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Inline keyboard listing previous challenges for review/practice."""
    buttons = []
    for ch in challenges:
        ch_id = ch["id"]
        title = ch["title"]
        status_icon = "🟢" if ch["status"] == "LIVE" else "🏁"
        buttons.append([InlineKeyboardButton(f"{status_icon} #{ch_id} {title}", callback_data=f"ch_past:{ch_id}")])

    buttons.append([InlineKeyboardButton("🔙 Back to Challenge Center", callback_data="ch_hub")])
    return InlineKeyboardMarkup(buttons)


def get_past_challenge_detail_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Options for an inspected past challenge: View Leaderboard or Practice Questions."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🏆 View Final Leaderboard", callback_data=f"lb_weekly:{challenge_id}:1")],
            [InlineKeyboardButton("🧩 Practice Questions", callback_data=f"ch_start:{challenge_id}")],
            [
                InlineKeyboardButton("📚 Back to Archive", callback_data="ch_past_list"),
                InlineKeyboardButton("🔙 Challenge Center", callback_data="ch_hub"),
            ],
        ]
    )


def get_challenge_hub_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline shortcuts for Challenge Center hub."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🚀 Take Active Challenge", callback_data="ch_active_view"),
                InlineKeyboardButton("🏆 Leaderboards", callback_data="lb_weekly:0:1"),
            ],
            [
                InlineKeyboardButton("📚 Past Challenges", callback_data="ch_past_list"),
                InlineKeyboardButton("📖 Scoring Rules", callback_data="ch_rules"),
            ],
        ]
    )


def get_admin_schedule_presets_keyboard() -> InlineKeyboardMarkup:
    """Preset scheduling intervals for challenge creation."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🟢 Go LIVE Now (Ends in 7 Days)", callback_data="adm_cr_sched:now:7d")],
            [InlineKeyboardButton("⏳ Start in 1 Hour (Ends in 7 Days)", callback_data="adm_cr_sched:1h:7d")],
            [InlineKeyboardButton("📅 Start Tomorrow (Ends in 7 Days)", callback_data="adm_cr_sched:24h:7d")],
            [InlineKeyboardButton("🛠️ Save as Draft (No Schedule)", callback_data="adm_cr_sched:draft:0")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")],
        ]
    )


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Admin dashboard navigation."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Create Challenge", callback_data="adm_create_ch"),
                InlineKeyboardButton("📋 View Challenges", callback_data="adm_list_ch"),
            ],
            [
                InlineKeyboardButton("📥 Import Questions (CSV)", callback_data="adm_import_csv"),
                InlineKeyboardButton("❓ Question Bank", callback_data="adm_qbank"),
            ],
            [
                InlineKeyboardButton("📊 Monthly Report", callback_data="adm_report"),
                InlineKeyboardButton("📢 Broadcast Notification", callback_data="adm_broadcast"),
            ],
        ]
    )


def get_admin_report_keyboard() -> InlineKeyboardMarkup:
    """Action buttons for the Monthly Report view."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📢 Broadcast Summary to Community", callback_data="adm_bcast_preset:report")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")],
        ]
    )


def get_admin_broadcast_presets_keyboard() -> InlineKeyboardMarkup:
    """Options for broadcasting to community members."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Announce Live Challenge", callback_data="adm_bcast_preset:challenge")],
            [InlineKeyboardButton("🏆 Announce Leaderboard Standings", callback_data="adm_bcast_preset:leaderboard")],
            [InlineKeyboardButton("📊 Announce Monthly Season Wrap-Up", callback_data="adm_bcast_preset:report")],
            [InlineKeyboardButton("✍️ Custom Announcement Message", callback_data="adm_bcast_custom")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")],
        ]
    )


def get_admin_broadcast_confirm_keyboard(target_action: str = "custom") -> InlineKeyboardMarkup:
    """Confirmation button before sending broadcast."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Confirm & Send to All", callback_data=f"adm_bcast_send:{target_action}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="adm_panel")],
        ]
    )


def get_challenge_manage_keyboard(challenge_id: int, status: str) -> InlineKeyboardMarkup:
    """Status transition buttons for admins."""
    buttons = []
    if status == "DRAFT":
        buttons.append([InlineKeyboardButton("🚀 Publish Challenge (Go LIVE)", callback_data=f"adm_pub:{challenge_id}")])
    elif status == "LIVE":
        buttons.append([InlineKeyboardButton("🏁 End Challenge Now", callback_data=f"adm_end:{challenge_id}")])
    
    if status not in ("ENDED", "CANCELLED"):
        buttons.append([InlineKeyboardButton("❌ Cancel Challenge", callback_data=f"adm_can:{challenge_id}")])
        
    buttons.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")])
    return InlineKeyboardMarkup(buttons)
