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
    """Navigation for Weekly vs Monthly leaderboards with pagination in column layout."""
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

    # 2. Column Mode Switchers
    buttons.append([InlineKeyboardButton("🏆 Weekly Leaderboard", callback_data=f"lb_weekly:{ch_id}:1")])
    buttons.append([InlineKeyboardButton("📅 Monthly Cumulative Leaderboard", callback_data="lb_monthly:0:1")])

    return InlineKeyboardMarkup(buttons)


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
