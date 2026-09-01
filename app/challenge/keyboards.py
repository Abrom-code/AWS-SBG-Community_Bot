import math
from typing import Dict, Optional, List, Any
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup


def get_challenge_start_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Button to initiate an active challenge with info and leaderboard shortcuts."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Start Challenge Now", callback_data=f"ch_start:{challenge_id}")],
            [
                InlineKeyboardButton("🏆 Leaderboard", callback_data=f"lb_weekly:{challenge_id}"),
                InlineKeyboardButton("📖 How Scoring Works", callback_data="ch_rules"),
            ],
            [
                InlineKeyboardButton("🛡️ Community Guidelines", callback_data="ch_guidelines"),
            ],
            [InlineKeyboardButton("🔙 Back to Challenge Center", callback_data="ch_hub")],
        ]
    )


def get_question_options_keyboard(
    challenge_id: int,
    question_index: int,
    options_keys: Optional[List[str]] = None,
    total_questions: int = 1,
    answered_indices: Optional[List[int]] = None,
) -> InlineKeyboardMarkup:
    """Randomized 4-option question response keyboard with bottom question navigation bar."""
    keys = options_keys or ["A", "B", "C", "D"]
    answered_set = set(answered_indices or [])

    # 1. Option Answer Buttons (2x2 Grid)
    row1 = [
        InlineKeyboardButton(f"{keys[0]}", callback_data=f"ch_ans:{challenge_id}:{question_index}:{keys[0]}"),
        InlineKeyboardButton(f"{keys[1]}", callback_data=f"ch_ans:{challenge_id}:{question_index}:{keys[1]}"),
    ]
    row2 = [
        InlineKeyboardButton(f"{keys[2]}", callback_data=f"ch_ans:{challenge_id}:{question_index}:{keys[2]}"),
        InlineKeyboardButton(f"{keys[3]}", callback_data=f"ch_ans:{challenge_id}:{question_index}:{keys[3]}"),
    ]

    buttons = [row1, row2]

    # 2. Bottom Question Navigation Bar (when multiple questions exist)
    if total_questions > 1:
        # Numbered Question buttons (sliding window up to 5 buttons)
        max_visible = 5
        if total_questions <= max_visible:
            start_num = 0
            end_num = total_questions
        else:
            start_num = max(0, min(question_index - 2, total_questions - max_visible))
            end_num = min(total_questions, start_num + max_visible)

        num_row = []
        for i in range(start_num, end_num):
            q_num = i + 1
            if i == question_index:
                label = f"• {q_num} •"
            elif i in answered_set:
                label = f"{q_num}✅"
            else:
                label = f"{q_num}"
            num_row.append(InlineKeyboardButton(label, callback_data=f"ch_nav:{challenge_id}:{i}"))
        buttons.append(num_row)

        # Prev / Next navigation row
        nav_row = []
        if question_index > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev Q", callback_data=f"ch_nav:{challenge_id}:{question_index - 1}"))
        if question_index < total_questions - 1:
            nav_row.append(InlineKeyboardButton("Next Q ➡️", callback_data=f"ch_nav:{challenge_id}:{question_index + 1}"))

        if nav_row:
            buttons.append(nav_row)

    return InlineKeyboardMarkup(buttons)


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
    buttons.append([InlineKeyboardButton("🛡️ Community Guidelines", callback_data="ch_guidelines")])
    buttons.append([InlineKeyboardButton("🔙 Back to Challenge Center", callback_data="ch_hub")])
    return InlineKeyboardMarkup(buttons)


def get_guidelines_keyboard(challenge_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Navigation keyboard displayed on the Community Guidelines page."""
    ch_id = challenge_id or 0
    buttons = []
    if ch_id > 0:
        buttons.append([InlineKeyboardButton("🚀 Start Challenge Now", callback_data=f"ch_start:{ch_id}")])
    buttons.append([InlineKeyboardButton("📖 How Scoring Works", callback_data="ch_rules")])
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
                InlineKeyboardButton("📖 How Scoring Works", callback_data="ch_rules"),
            ],
            [
                InlineKeyboardButton("🛡️ Community Guidelines", callback_data="ch_guidelines"),
            ],
        ]
    )


def get_admin_schedule_presets_keyboard(challenge_id: int = 0, duration_mins: int = 10) -> InlineKeyboardMarkup:
    """Preset scheduling intervals for challenge creation with explicit duration editor."""
    if challenge_id > 0:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🟢 Go LIVE Now (Ends in 7 Days)", callback_data=f"adm_cr_sched:{challenge_id}:now:7d")],
                [InlineKeyboardButton("⏳ Start in 1 Hour (Ends in 7 Days)", callback_data=f"adm_cr_sched:{challenge_id}:1h:7d")],
                [InlineKeyboardButton("📅 Start Tomorrow (Ends in 7 Days)", callback_data=f"adm_cr_sched:{challenge_id}:24h:7d")],
                [InlineKeyboardButton("✍️ Custom Start & End Date/Time", callback_data=f"adm_sched_custom:{challenge_id}")],
                [InlineKeyboardButton(f"⏱️ Exam Duration: {duration_mins}m (Tap to Change)", callback_data=f"adm_edit_timer:{challenge_id}")],
                [InlineKeyboardButton("🛠️ Save as Draft (No Schedule)", callback_data=f"adm_cr_sched:{challenge_id}:draft:0")],
                [InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🟢 Go LIVE Now (Ends in 7 Days)", callback_data="adm_cr_sched:now:7d")],
            [InlineKeyboardButton("⏳ Start in 1 Hour (Ends in 7 Days)", callback_data="adm_cr_sched:1h:7d")],
            [InlineKeyboardButton("📅 Start Tomorrow (Ends in 7 Days)", callback_data="adm_cr_sched:24h:7d")],
            [InlineKeyboardButton("✍️ Custom Start & End Date/Time", callback_data="adm_cr_custom_date")],
            [InlineKeyboardButton("🛠️ Save as Draft (No Schedule)", callback_data="adm_cr_sched:draft:0")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")],
        ]
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns persistent bottom keyboard buttons for Admin operations."""
    return ReplyKeyboardMarkup(
        [
            ["➕ Create Challenge", "📋 Manage Challenges"],
            ["🏆 Leaderboards", "📊 Monthly Report"],
            ["📢 Broadcast Notification", "🚪 Exit Admin"],
        ],
        resize_keyboard=True,
    )


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Admin dashboard navigation in formal sequence: Create, Manage, Leaderboards, Report, Broadcast."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Create Challenge", callback_data="adm_create_ch")],
            [InlineKeyboardButton("📋 Manage Challenges", callback_data="adm_list_ch")],
            [InlineKeyboardButton("🏆 Leaderboards", callback_data="adm_leaderboards")],
            [InlineKeyboardButton("📊 Monthly Report", callback_data="adm_report")],
            [InlineKeyboardButton("📢 Broadcast Notification", callback_data="adm_broadcast")],
        ]
    )


def get_admin_leaderboard_keyboard(active_ch_id: int = 0) -> InlineKeyboardMarkup:
    """Action buttons for Admin Leaderboard view."""
    buttons = []
    if active_ch_id > 0:
        buttons.append([InlineKeyboardButton("⚡ Active Challenge Standings", callback_data=f"adm_lb_view:weekly:{active_ch_id}")])
    buttons.append([InlineKeyboardButton("📅 Monthly Cumulative Championship", callback_data="adm_lb_view:monthly:0")])
    buttons.append([InlineKeyboardButton("📚 Browse Past Challenge Boards", callback_data="ch_past_list")])
    buttons.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")])
    return InlineKeyboardMarkup(buttons)


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


def get_question_bank_actions_keyboard() -> InlineKeyboardMarkup:
    """Action buttons for Question Bank inspection."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 Manage Challenges", callback_data="adm_list_ch")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")],
        ]
    )


def get_challenge_schedule_edit_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Options for editing a challenge's start/end dates and schedule."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🟢 Start Now (Live for 7 Days)", callback_data=f"adm_sched_set:{challenge_id}:now:7d")],
            [InlineKeyboardButton("⏳ Start in 1 Hour (Ends in 7 Days)", callback_data=f"adm_sched_set:{challenge_id}:1h:7d")],
            [InlineKeyboardButton("📅 Start Tomorrow (Ends in 7 Days)", callback_data=f"adm_sched_set:{challenge_id}:24h:7d")],
            [InlineKeyboardButton("✍️ Custom Start & End Date/Time", callback_data=f"adm_sched_custom:{challenge_id}")],
            [InlineKeyboardButton("🛠️ Save as Draft (Unscheduled)", callback_data=f"adm_sched_set:{challenge_id}:draft:0")],
            [InlineKeyboardButton("🔙 Back to Manage Challenge", callback_data=f"adm_manage:{challenge_id}")],
        ]
    )


def get_challenge_timer_edit_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Options for editing a challenge's allowed exam time limit."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚡ 5 Minutes", callback_data=f"adm_timer_set:{challenge_id}:5"),
                InlineKeyboardButton("⚡ 10 Minutes", callback_data=f"adm_timer_set:{challenge_id}:10"),
            ],
            [
                InlineKeyboardButton("⚡ 15 Minutes", callback_data=f"adm_timer_set:{challenge_id}:15"),
                InlineKeyboardButton("⚡ 20 Minutes", callback_data=f"adm_timer_set:{challenge_id}:20"),
            ],
            [
                InlineKeyboardButton("⚡ 30 Minutes", callback_data=f"adm_timer_set:{challenge_id}:30"),
                InlineKeyboardButton("⚡ 45 Minutes", callback_data=f"adm_timer_set:{challenge_id}:45"),
            ],
            [InlineKeyboardButton("✍️ Custom Exam Minutes", callback_data=f"adm_timer_custom:{challenge_id}")],
            [InlineKeyboardButton("🔙 Back to Challenge", callback_data=f"adm_manage:{challenge_id}")],
        ]
    )


def get_wizard_skip_desc_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Provides a skip/default shortcut button for Challenge Description in wizard."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⏭️ Use Default Description", callback_data=f"adm_wiz_skip_desc:{challenge_id}")],
            [InlineKeyboardButton("❌ Cancel Creation", callback_data="adm_panel")],
        ]
    )


def get_wizard_questions_keyboard(challenge_id: int = 0) -> InlineKeyboardMarkup:
    """Step 2 question selection options for Challenge Creation Wizard."""
    buttons = []
    if challenge_id > 0:
        buttons.append([
            InlineKeyboardButton("➕ Add Question to Challenge", callback_data=f"adm_add_q_to_ch:{challenge_id}"),
            InlineKeyboardButton("📥 Import CSV to Challenge", callback_data=f"adm_import_csv_to_ch:{challenge_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("⏱️ Set Exam Time Limit", callback_data=f"adm_edit_timer:{challenge_id}"),
            InlineKeyboardButton("📋 View Questions", callback_data=f"adm_view_ch_q:{challenge_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("🚀 Publish (Go LIVE)", callback_data=f"adm_pub:{challenge_id}"),
            InlineKeyboardButton("⚙️ Manage Challenge", callback_data=f"adm_manage:{challenge_id}"),
        ])
        buttons.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel")])
    else:
        buttons.append([InlineKeyboardButton("❌ Cancel Creation", callback_data="adm_panel")])
    return InlineKeyboardMarkup(buttons)


def get_challenge_delete_confirm_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Confirmation keyboard before permanently deleting a challenge."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🗑️ Yes, Permanently Delete Challenge", callback_data=f"adm_del_conf:{challenge_id}")],
            [InlineKeyboardButton("❌ Cancel / Keep Challenge", callback_data=f"adm_manage:{challenge_id}")],
        ]
    )


def get_challenge_questions_view_keyboard(challenge_id: int, questions: list, page: int = 1, page_size: int = 4) -> InlineKeyboardMarkup:
    """Action buttons for inspecting and removing individual questions from a challenge."""
    buttons = []
    total = len(questions)
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_questions = questions[start_idx:end_idx]

    # Row of remove buttons for each question on the page
    for offset, q in enumerate(page_questions):
        idx = start_idx + offset
        q_id = q.get("id", 0)
        q_text_short = q.get("question_text", "")[:24]
        buttons.append([
            InlineKeyboardButton(f"🗑️ Remove Q{idx+1}: {q_text_short}...", callback_data=f"adm_rm_ch_q:{challenge_id}:{q_id}:{page}")
        ])

    # Navigation buttons if multiple pages
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm_view_ch_q:{challenge_id}:{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data=f"adm_view_ch_q:{challenge_id}:{page}"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_view_ch_q:{challenge_id}:{page+1}"))
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton("➕ Add Question", callback_data=f"adm_add_q_to_ch:{challenge_id}"),
        InlineKeyboardButton("📥 Import CSV", callback_data=f"adm_import_csv_to_ch:{challenge_id}"),
    ])
    buttons.append([InlineKeyboardButton("🔙 Back to Manage Challenge", callback_data=f"adm_manage:{challenge_id}")])
    return InlineKeyboardMarkup(buttons)


def get_challenge_manage_keyboard(challenge_id: int, status: str) -> InlineKeyboardMarkup:
    """Action buttons for challenge management."""
    buttons = []
    if status in ("DRAFT", "SCHEDULED"):
        buttons.append([InlineKeyboardButton("🚀 Publish Challenge (Go LIVE)", callback_data=f"adm_pub:{challenge_id}")])
    elif status == "LIVE":
        buttons.append([InlineKeyboardButton("🏁 End Challenge Now", callback_data=f"adm_end:{challenge_id}")])

    if status not in ("ENDED", "CANCELLED"):
        buttons.append([
            InlineKeyboardButton("➕ Add Question", callback_data=f"adm_add_q_to_ch:{challenge_id}"),
            InlineKeyboardButton("📥 Import CSV", callback_data=f"adm_import_csv_to_ch:{challenge_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("📋 View Questions", callback_data=f"adm_view_ch_q:{challenge_id}"),
            InlineKeyboardButton("✏️ Edit Title", callback_data=f"adm_edit_title:{challenge_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("⏰ Edit Schedule", callback_data=f"adm_edit_sched:{challenge_id}"),
            InlineKeyboardButton("⏱️ Edit Time Limit", callback_data=f"adm_edit_timer:{challenge_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("❌ Cancel Challenge", callback_data=f"adm_can:{challenge_id}"),
            InlineKeyboardButton("🗑️ Delete Challenge", callback_data=f"adm_del_prompt:{challenge_id}"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("📋 View Questions", callback_data=f"adm_view_ch_q:{challenge_id}"),
            InlineKeyboardButton("🗑️ Delete Challenge", callback_data=f"adm_del_prompt:{challenge_id}"),
        ])

    buttons.append([
        InlineKeyboardButton("📋 Manage Challenges", callback_data="adm_list_ch"),
        InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_panel"),
    ])
    return InlineKeyboardMarkup(buttons)
