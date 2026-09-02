import math
from typing import Dict, Optional, List, Any
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup


def get_challenge_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns persistent sub-menu keyboard for the Challenge Center."""
    return ReplyKeyboardMarkup(
        [
            ["Leaderboards", "Past Challenges"],
            ["Scoring Rules", "Guidelines"],
            ["Main Menu"],
        ],
        resize_keyboard=True,
    )


def get_challenge_start_keyboard(challenge_id: int, has_multiple: bool = False) -> InlineKeyboardMarkup:
    """Button to initiate an active challenge, with optional back button if multiple challenges active."""
    buttons = [
        [InlineKeyboardButton("Start Challenge", callback_data=f"ch_start:{challenge_id}")],
    ]
    if has_multiple:
        buttons.append([InlineKeyboardButton("« All Active Challenges", callback_data="ch_active_view")])
    return InlineKeyboardMarkup(buttons)


def get_active_challenges_nav_keyboard(
    challenge_id: int,
    current_index: int,
    total_challenges: int,
    is_completed: bool = False,
    is_scheduled: bool = False,
    challenge_statuses: Optional[List[str]] = None,
    scheduled_countdown: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """
    Renders the active challenge keyboard in questions format:
    - Primary action button(s) for the current challenge
    - Smart navigation bar (Prev / Next & jump numbers) if total_challenges > 1
    - No repeated footer buttons
    """
    buttons = []

    # 1. Action Buttons for the current challenge
    if is_completed:
        buttons.append([
            InlineKeyboardButton("Leaderboard", callback_data=f"lb_weekly:{challenge_id}:1"),
            InlineKeyboardButton("Review Answers", callback_data=f"ch_review:{challenge_id}:0"),
        ])
        buttons.append([InlineKeyboardButton("Refresh Status", callback_data=f"ch_refresh:{challenge_id}:{current_index}")])
    elif is_scheduled:
        btn_label = f"Opens {scheduled_countdown}" if scheduled_countdown else "Scheduled Challenge"
        if len(btn_label) > 38:
            btn_label = btn_label[:35] + "..."
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"ch_sched_info:{challenge_id}")])
        buttons.append([InlineKeyboardButton("Refresh Status", callback_data=f"ch_refresh:{challenge_id}:{current_index}")])
    else:
        buttons.append([InlineKeyboardButton("🚀 Start Challenge", callback_data=f"ch_start:{challenge_id}")])
        buttons.append([InlineKeyboardButton("Refresh Status", callback_data=f"ch_refresh:{challenge_id}:{current_index}")])

    # 2. Smart Navigation Bar (if there are multiple challenges)
    if total_challenges > 1:
        # Prev / Next Row
        nav_row = []
        if current_index > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"ch_nav_act:{current_index - 1}"))
        nav_row.append(InlineKeyboardButton(f"{current_index + 1}/{total_challenges}", callback_data="noop"))
        if current_index < total_challenges - 1:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ch_nav_act:{current_index + 1}"))
        buttons.append(nav_row)

        # Direct number jump row (chunks of 5, matching questions navigation!)
        chunk_size = 5
        chunk_page = current_index // chunk_size
        start_num = chunk_page * chunk_size
        end_num = min(total_challenges, start_num + chunk_size)

        num_row = []
        for i in range(start_num, end_num):
            q_num = i + 1
            status_tag = challenge_statuses[i] if challenge_statuses and i < len(challenge_statuses) else ""
            if i == current_index:
                label = f"• {q_num}{status_tag} •"
            else:
                label = f"{q_num}{status_tag}"
            num_row.append(InlineKeyboardButton(label, callback_data=f"ch_nav_act:{i}"))
        buttons.append(num_row)

        # Chunk pagination if > 5 challenges
        if total_challenges > chunk_size:
            chunk_nav = []
            if start_num > 0:
                prev_start = start_num - chunk_size
                chunk_nav.append(InlineKeyboardButton(f"◀️ C{prev_start + 1}-{start_num}", callback_data=f"ch_nav_act:{prev_start}"))
            if end_num < total_challenges:
                next_start = end_num
                next_end = min(total_challenges, next_start + chunk_size)
                chunk_nav.append(InlineKeyboardButton(f"C{next_start + 1}-{next_end} ▶️", callback_data=f"ch_nav_act:{next_start}"))
            if chunk_nav:
                buttons.append(chunk_nav)

    return InlineKeyboardMarkup(buttons)


def get_active_challenges_keyboard(
    challenges: List[Dict[str, Any]],
    user_participations: Optional[Dict[int, Dict[str, Any]]] = None,
) -> InlineKeyboardMarkup:
    """Renders a single-column list of active challenges with status badges."""
    user_participations = user_participations or {}
    buttons = []

    for ch in challenges:
        ch_id = ch["id"]
        title = ch.get("title", f"Challenge #{ch_id}")
        part = user_participations.get(ch_id)

        # Determine badge & status
        if part and part.get("status") == "COMPLETED":
            badge = "✔️"
            label = f"{badge} {title} (Completed)"
        elif ch.get("status") == "SCHEDULED":
            badge = "🕒"
            label = f"{badge} {title} (Upcoming)"
        else:
            badge = "🟢"
            label = f"{badge} {title}"

        if len(label) > 38:
            label = label[:35] + "..."

        buttons.append([InlineKeyboardButton(label, callback_data=f"ch_select:{ch_id}")])

    return InlineKeyboardMarkup(buttons)


def get_question_options_keyboard(
    challenge_id: int,
    question_index: int,
    options_keys: Optional[List[str]] = None,
    total_questions: int = 1,
    answered_indices: Optional[List[int]] = None,
) -> InlineKeyboardMarkup:
    """Randomized 4-option question response keyboard with 5-question chunked bottom navigation."""
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

    # 2. Bottom Chunked Question Navigation Bar (Chunks of 5 questions: 1-5, 6-10, 11-15, etc.)
    if total_questions > 1:
        chunk_size = 5
        chunk_page = question_index // chunk_size
        start_num = chunk_page * chunk_size
        end_num = min(total_questions, start_num + chunk_size)

        num_row = []
        for i in range(start_num, end_num):
            q_num = i + 1
            if i == question_index:
                label = f"• {q_num}✅ •" if i in answered_set else f"• {q_num} •"
            elif i in answered_set:
                label = f"{q_num}✅"
            else:
                label = f"{q_num}"
            num_row.append(InlineKeyboardButton(label, callback_data=f"ch_nav:{challenge_id}:{i}"))
        buttons.append(num_row)

        # 3. Chunk Paging Row (e.g. [ ◀️ Q1-5 ] [ Q6-10 ▶️ ])
        nav_row = []
        if start_num > 0:
            prev_start = start_num - chunk_size
            prev_end = start_num
            nav_row.append(InlineKeyboardButton(f"◀️ Q{prev_start + 1}-{prev_end}", callback_data=f"ch_nav:{challenge_id}:{prev_start}"))
        if end_num < total_questions:
            next_start = end_num
            next_end = min(total_questions, next_start + chunk_size)
            nav_row.append(InlineKeyboardButton(f"Q{next_start + 1}-{next_end} ▶️", callback_data=f"ch_nav:{challenge_id}:{next_start}"))

        if nav_row:
            buttons.append(nav_row)

    return InlineKeyboardMarkup(buttons)


def get_leaderboard_keyboard(
    challenge_id: Optional[int] = None,
    mode: str = "weekly",
    page: int = 1,
    total_pages: int = 1,
    can_review: bool = False,
    is_active: bool = False,
) -> InlineKeyboardMarkup:
    """Navigation for Weekly vs Monthly leaderboards with interactive tab switcher."""
    ch_id = challenge_id or 0
    buttons = []

    # 1. Mode Tab Switcher: [ • 🏆 Weekly • ] [ 📅 Monthly ]  OR  [ 🏆 Weekly ] [ • 📅 Monthly • ]
    if mode == "weekly":
        buttons.append([
            InlineKeyboardButton("• 🏆 Weekly •", callback_data="noop"),
            InlineKeyboardButton("📅 Monthly", callback_data=f"lb_monthly:{ch_id}:1"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("🏆 Weekly", callback_data=f"lb_weekly:{ch_id}:1"),
            InlineKeyboardButton("• 📅 Monthly •", callback_data="noop"),
        ])

    # 2. Pagination Row (when there are multiple pages)
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"lb_{mode}:{ch_id}:{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"lb_{mode}:{ch_id}:{page + 1}"))
        buttons.append(nav_row)

    # 3. Contextual action shortcuts
    if mode == "weekly" and can_review and ch_id > 0:
        buttons.append([InlineKeyboardButton("Review Questions & Answers", callback_data=f"ch_review:{ch_id}:0")])

    if ch_id > 0:
        back_cb = f"ch_select:{ch_id}" if is_active else f"ch_past:{ch_id}"
        buttons.append([InlineKeyboardButton("« Back to Challenge", callback_data=back_cb)])
    else:
        buttons.append([InlineKeyboardButton("« Back to Challenges", callback_data="ch_active_view")])

    return InlineKeyboardMarkup(buttons)


def get_challenge_completion_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Action buttons displayed on the challenge completion screen in clean rows without emojis."""
    ch_id = challenge_id or 0
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Weekly Board", callback_data=f"lb_weekly:{ch_id}:1"),
            InlineKeyboardButton("Monthly Board", callback_data=f"lb_monthly:{ch_id}:1"),
        ],
        [
            InlineKeyboardButton("Review Answers", callback_data=f"ch_review:{ch_id}:0"),
            InlineKeyboardButton("Back to Challenges", callback_data="ch_active_view"),
        ],
    ])



def get_review_navigation_keyboard(
    challenge_id: int,
    question_index: int,
    total_questions: int,
    answered_status: Optional[Dict[int, bool]] = None,
) -> InlineKeyboardMarkup:
    """Bottom navigation keyboard for reviewing questions and explanations."""
    answered_status = answered_status or {}
    buttons = []

    # 1. Previous / Next Navigation Row
    nav_row = []
    if question_index > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"ch_review:{challenge_id}:{question_index - 1}"))
    nav_row.append(InlineKeyboardButton(f"{question_index + 1}/{total_questions}", callback_data="noop"))
    if question_index < total_questions - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ch_review:{challenge_id}:{question_index + 1}"))
    buttons.append(nav_row)

    # 2. Chunked Question Number Buttons (chunks of 5: 1-5, 6-10, etc.)
    if total_questions > 1:
        chunk_size = 5
        chunk_page = question_index // chunk_size
        start_num = chunk_page * chunk_size
        end_num = min(total_questions, start_num + chunk_size)

        num_row = []
        for i in range(start_num, end_num):
            q_num = i + 1
            if i in answered_status:
                icon = "✅" if answered_status[i] else "❌"
                label = f"• {q_num}{icon} •" if i == question_index else f"{q_num}{icon}"
            else:
                label = f"• {q_num} •" if i == question_index else f"{q_num}"
            num_row.append(InlineKeyboardButton(label, callback_data=f"ch_review:{challenge_id}:{i}"))
        buttons.append(num_row)

        # Chunk Paging Row if needed
        chunk_nav = []
        if start_num > 0:
            prev_start = start_num - chunk_size
            chunk_nav.append(InlineKeyboardButton(f"◀️ Q{prev_start + 1}-{start_num}", callback_data=f"ch_review:{challenge_id}:{prev_start}"))
        if end_num < total_questions:
            next_start = end_num
            next_end = min(total_questions, next_start + chunk_size)
            chunk_nav.append(InlineKeyboardButton(f"Q{next_start + 1}-{next_end} ▶️", callback_data=f"ch_review:{challenge_id}:{next_start}"))
        if chunk_nav:
            buttons.append(chunk_nav)



    return InlineKeyboardMarkup(buttons)


def get_scoring_rules_keyboard(challenge_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Navigation keyboard displayed on the Scoring Rules guide."""
    ch_id = challenge_id or 0
    buttons = []
    if ch_id > 0:
        buttons.append([InlineKeyboardButton("Start Challenge", callback_data=f"ch_start:{ch_id}")])
    return InlineKeyboardMarkup(buttons)


def get_guidelines_keyboard(challenge_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Navigation keyboard displayed on the Community Guidelines page."""
    ch_id = challenge_id or 0
    buttons = []
    if ch_id > 0:
        buttons.append([InlineKeyboardButton("Start Challenge", callback_data=f"ch_start:{ch_id}")])
    return InlineKeyboardMarkup(buttons)


def get_past_challenges_keyboard(challenges: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Inline keyboard listing previous challenges for review/practice."""
    buttons = []
    for ch in challenges:
        if ch.get("status") == "DRAFT":
            continue
        ch_id = ch["id"]
        title = ch["title"]
        buttons.append([InlineKeyboardButton(f"#{ch_id} {title[:32]}", callback_data=f"ch_past:{ch_id}")])
    return InlineKeyboardMarkup(buttons)


def get_past_challenge_detail_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Options for an inspected past challenge."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Review Questions & Explanations", callback_data=f"ch_review:{challenge_id}:0")],
            [InlineKeyboardButton("« All Past Challenges", callback_data="ch_past_list")],
        ]
    )


def get_challenge_hub_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline shortcut for Challenge Center hub."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Take Active Challenge", callback_data="ch_active_view")],
        ]
    )


def get_admin_schedule_presets_keyboard(challenge_id: int = 0, duration_mins: int = 10) -> InlineKeyboardMarkup:
    """Independent Go LIVE vs Publish for Future (Start Tomorrow) vs Custom scheduling options."""
    if challenge_id > 0:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Go Live", callback_data=f"adm_cr_sched:{challenge_id}:now:7d")],
                [InlineKeyboardButton("Publish for Future (Start Tomorrow)", callback_data=f"adm_cr_sched:{challenge_id}:24h:7d")],
                [
                    InlineKeyboardButton("Custom Schedule", callback_data=f"adm_sched_custom:{challenge_id}"),
                    InlineKeyboardButton("Save as Draft", callback_data=f"adm_cr_sched:{challenge_id}:draft:0"),
                ],
                [InlineKeyboardButton("« Back to Admin", callback_data="adm_panel")],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Go Live", callback_data="adm_cr_sched:now:7d")],
            [InlineKeyboardButton("Publish for Future (Start Tomorrow)", callback_data="adm_cr_sched:24h:7d")],
            [
                InlineKeyboardButton("Custom Schedule", callback_data="adm_cr_custom_date"),
                InlineKeyboardButton("Save as Draft", callback_data="adm_cr_sched:draft:0"),
            ],
            [InlineKeyboardButton("« Back to Admin", callback_data="adm_panel")],
        ]
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns persistent bottom keyboard buttons for Admin operations."""
    return ReplyKeyboardMarkup(
        [
            ["Create Challenge", "Manage Challenges"],
            ["Leaderboards", "Monthly Report"],
            ["Broadcast", "Exit Admin"],
            ["Main Menu"],
        ],
        resize_keyboard=True,
    )


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Admin dashboard inline shortcut."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Create Challenge", callback_data="adm_create_ch")],
            [InlineKeyboardButton("Manage Challenges", callback_data="adm_list_ch")],
        ]
    )


def get_admin_leaderboard_keyboard(active_ch_id: int = 0) -> InlineKeyboardMarkup:
    """Action buttons for Admin Leaderboard view."""
    buttons = []
    if active_ch_id > 0:
        buttons.append([InlineKeyboardButton("Active Standings", callback_data=f"adm_lb_view:weekly:{active_ch_id}")])
    buttons.append([InlineKeyboardButton("Monthly Championship", callback_data="adm_lb_view:monthly:0")])
    return InlineKeyboardMarkup(buttons)


def get_admin_report_keyboard() -> InlineKeyboardMarkup:
    """Action buttons for the Monthly Report view."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Broadcast Report", callback_data="adm_bcast_preset:report")],
        ]
    )


def get_admin_broadcast_presets_keyboard() -> InlineKeyboardMarkup:
    """Options for broadcasting to community members."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Announce Live Challenge", callback_data="adm_bcast_preset:challenge")],
            [InlineKeyboardButton("Announce Leaderboard", callback_data="adm_bcast_preset:leaderboard")],
            [InlineKeyboardButton("Announce Monthly Wrap-Up", callback_data="adm_bcast_preset:report")],
            [InlineKeyboardButton("Custom Broadcast", callback_data="adm_bcast_custom")],
        ]
    )


def get_admin_broadcast_confirm_keyboard(target_action: str = "custom") -> InlineKeyboardMarkup:
    """Confirmation button before sending broadcast."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Send Broadcast", callback_data=f"adm_bcast_send:{target_action}")],
            [InlineKeyboardButton("Cancel", callback_data="adm_panel")],
        ]
    )


def get_question_bank_actions_keyboard() -> InlineKeyboardMarkup:
    """Action buttons for Question Bank inspection."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("« All Challenges", callback_data="adm_list_ch")],
        ]
    )


def get_challenge_schedule_edit_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Options for editing a challenge's start/end dates and schedule."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Go Live", callback_data=f"adm_sched_set:{challenge_id}:now:7d")],
            [InlineKeyboardButton("Publish for Future (Start Tomorrow)", callback_data=f"adm_sched_set:{challenge_id}:24h:7d")],
            [
                InlineKeyboardButton("Custom Schedule", callback_data=f"adm_sched_custom:{challenge_id}"),
                InlineKeyboardButton("Save as Draft", callback_data=f"adm_sched_set:{challenge_id}:draft:0"),
            ],
            [InlineKeyboardButton("« Back to Challenge", callback_data=f"adm_manage:{challenge_id}")],
        ]
    )


def get_challenge_timer_edit_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Options for editing a challenge's allowed exam time limit."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("5 Mins", callback_data=f"adm_timer_set:{challenge_id}:5"),
                InlineKeyboardButton("10 Mins", callback_data=f"adm_timer_set:{challenge_id}:10"),
                InlineKeyboardButton("15 Mins", callback_data=f"adm_timer_set:{challenge_id}:15"),
            ],
            [
                InlineKeyboardButton("20 Mins", callback_data=f"adm_timer_set:{challenge_id}:20"),
                InlineKeyboardButton("30 Mins", callback_data=f"adm_timer_set:{challenge_id}:30"),
                InlineKeyboardButton("45 Mins", callback_data=f"adm_timer_set:{challenge_id}:45"),
            ],
            [InlineKeyboardButton("Custom Duration", callback_data=f"adm_timer_custom:{challenge_id}")],
            [InlineKeyboardButton("« Back to Challenge", callback_data=f"adm_manage:{challenge_id}")],
        ]
    )


def get_wizard_skip_desc_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Provides skip description and category picker shortcuts in wizard Step 2."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Use Default Description", callback_data=f"adm_wiz_skip_desc:{challenge_id}")],
            [InlineKeyboardButton("Select Category", callback_data=f"adm_wiz_cat_menu:{challenge_id}")],
            [InlineKeyboardButton("Cancel", callback_data="adm_panel")],
        ]
    )


def get_wizard_category_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Category picker for Challenge Creation Wizard."""
    categories = [
        "AI",
        "DevOps",
        "Web3",
        "Cloud",
        "Architecture",
        "Serverless",
        "Security",
        "Database",
        "Networking",
    ]
    buttons = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(cat, callback_data=f"adm_wiz_set_cat:{challenge_id}:{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("Custom Category", callback_data=f"adm_wiz_custom_cat:{challenge_id}")])
    buttons.append([InlineKeyboardButton("« Back to Description", callback_data=f"adm_wiz_back_desc:{challenge_id}")])
    return InlineKeyboardMarkup(buttons)


def get_wizard_timer_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Step 3 Exam Time Limit selection options for Challenge Creation Wizard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("5 Mins", callback_data=f"adm_wiz_timer:{challenge_id}:5"),
                InlineKeyboardButton("10 Mins", callback_data=f"adm_wiz_timer:{challenge_id}:10"),
                InlineKeyboardButton("15 Mins", callback_data=f"adm_wiz_timer:{challenge_id}:15"),
            ],
            [
                InlineKeyboardButton("20 Mins", callback_data=f"adm_wiz_timer:{challenge_id}:20"),
                InlineKeyboardButton("30 Mins", callback_data=f"adm_wiz_timer:{challenge_id}:30"),
                InlineKeyboardButton("45 Mins", callback_data=f"adm_wiz_timer:{challenge_id}:45"),
            ],
            [
                InlineKeyboardButton("Custom Duration", callback_data=f"adm_wiz_timer_custom:{challenge_id}"),
            ],
            [
                InlineKeyboardButton("Cancel", callback_data="adm_panel")],
        ]
    )


def get_wizard_questions_keyboard(challenge_id: int = 0, is_scheduled: bool = False) -> InlineKeyboardMarkup:
    """Post-creation question attachment and publishing options."""
    if challenge_id > 0:
        pub_btn = (
            InlineKeyboardButton("Publish (Schedule)", callback_data=f"adm_pub:{challenge_id}:sched")
            if is_scheduled
            else InlineKeyboardButton("Publish (Go Live)", callback_data=f"adm_pub:{challenge_id}:live")
        )
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Add Question", callback_data=f"adm_add_q_to_ch:{challenge_id}"),
                    InlineKeyboardButton("Import CSV", callback_data=f"adm_import_csv_to_ch:{challenge_id}"),
                ],
                [
                    InlineKeyboardButton("View Questions", callback_data=f"adm_view_ch_q:{challenge_id}"),
                    pub_btn,
                ],
                [
                    InlineKeyboardButton("Manage Challenge", callback_data=f"adm_manage:{challenge_id}"),
                ],
            ]
        )
    return InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="adm_panel")]])


def get_challenge_delete_confirm_keyboard(challenge_id: int) -> InlineKeyboardMarkup:
    """Confirmation keyboard before permanently deleting a challenge."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Delete", callback_data=f"adm_del_conf:{challenge_id}")],
            [InlineKeyboardButton("Cancel", callback_data=f"adm_manage:{challenge_id}")],
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
            InlineKeyboardButton(f"Remove Q{idx+1}: {q_text_short}...", callback_data=f"adm_rm_ch_q:{challenge_id}:{q_id}:{page}")
        ])

    # Navigation buttons if multiple pages
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("« Prev", callback_data=f"adm_view_ch_q:{challenge_id}:{page-1}"))
        nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("Next »", callback_data=f"adm_view_ch_q:{challenge_id}:{page+1}"))
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton("Add Question", callback_data=f"adm_add_q_to_ch:{challenge_id}"),
        InlineKeyboardButton("Import CSV", callback_data=f"adm_import_csv_to_ch:{challenge_id}"),
    ])
    buttons.append([InlineKeyboardButton("« Back to Challenge", callback_data=f"adm_manage:{challenge_id}")])
    return InlineKeyboardMarkup(buttons)


def get_challenge_manage_keyboard(challenge_id: int, status: str) -> InlineKeyboardMarkup:
    """Action buttons for challenge management."""
    buttons = []
    if status == "DRAFT":
        buttons.append([
            InlineKeyboardButton("Go Live", callback_data=f"adm_pub:{challenge_id}:live"),
            InlineKeyboardButton("Publish (Schedule)", callback_data=f"adm_pub:{challenge_id}:sched"),
        ])
    elif status == "SCHEDULED":
        buttons.append([InlineKeyboardButton("Go Live Now", callback_data=f"adm_pub:{challenge_id}:live")])
    elif status == "LIVE":
        buttons.append([InlineKeyboardButton("End Challenge", callback_data=f"adm_end:{challenge_id}")])

    if status not in ("ENDED", "CANCELLED"):
        buttons.append([
            InlineKeyboardButton("Add Question", callback_data=f"adm_add_q_to_ch:{challenge_id}"),
            InlineKeyboardButton("Import CSV", callback_data=f"adm_import_csv_to_ch:{challenge_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("View Questions", callback_data=f"adm_view_ch_q:{challenge_id}"),
            InlineKeyboardButton("Edit Title", callback_data=f"adm_edit_title:{challenge_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("Edit Schedule", callback_data=f"adm_edit_sched:{challenge_id}"),
            InlineKeyboardButton("Edit Time Limit", callback_data=f"adm_edit_timer:{challenge_id}"),
        ])
        buttons.append([
            InlineKeyboardButton("Cancel Challenge", callback_data=f"adm_can:{challenge_id}"),
            InlineKeyboardButton("Delete Challenge", callback_data=f"adm_del_prompt:{challenge_id}"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("View Questions", callback_data=f"adm_view_ch_q:{challenge_id}"),
            InlineKeyboardButton("Delete Challenge", callback_data=f"adm_del_prompt:{challenge_id}"),
        ])

    buttons.append([InlineKeyboardButton("« All Challenges", callback_data="adm_list_ch")])
    return InlineKeyboardMarkup(buttons)
