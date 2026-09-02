import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.db as db
import app.challenge.service as service
from app.challenge.scoring import calculate_score


SAMPLE_CSV = """question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation
Which AWS service provides serverless compute?,Amazon EC2,AWS Lambda,Amazon S3,Amazon RDS,B,EASY,Compute,10,AWS Lambda is serverless
What is Amazon S3 primarily used for?,Block storage,Object storage,Relational database,Message queue,B,EASY,Storage,10,S3 is scalable object storage
Which service distributes incoming traffic?,Route 53,Elastic Load Balancing,Direct Connect,VPC,B,MEDIUM,Networking,10,ELB distributes traffic across targets
"""


def test_csv_import_and_question_listing():
    asyncio.run(db.reset_db())

    result = asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))
    assert result["imported"] == 3
    assert len(result["errors"]) == 0

    questions = asyncio.run(service.list_questions(limit=10))
    assert len(questions) == 3
    assert questions[0]["category"] in ("Compute", "Storage", "Networking")


def test_challenge_creation_and_question_snapshotting():
    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    ch_id = asyncio.run(
        service.create_challenge(
            title="AWS Cloud Architecture Quiz #01",
            category="Architecture",
            question_time_limit_seconds=45,
            accuracy_weight=0.70,
            speed_weight=0.30,
        )
    )
    assert ch_id > 0

    linked = asyncio.run(service.link_questions_to_challenge(ch_id))
    assert linked == 3

    challenge = asyncio.run(service.get_challenge(ch_id))
    assert challenge["title"] == "AWS Cloud Architecture Quiz #01"
    assert challenge["question_time_limit_seconds"] == 45
    assert challenge["accuracy_weight"] == 0.70
    assert challenge["speed_weight"] == 0.30
    assert challenge["status"] == "DRAFT"

    # Publish challenge
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))
    active = asyncio.run(service.get_active_challenge())
    assert active["id"] == ch_id
    assert active["status"] == "LIVE"


def test_participant_quiz_progression_and_scoring():
    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    ch_id = asyncio.run(
        service.create_challenge(
            title="Speed Challenge",
            question_time_limit_seconds=60,
            accuracy_weight=0.70,
            speed_weight=0.30,
        )
    )
    asyncio.run(service.link_questions_to_challenge(ch_id))
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    user_id = 98765
    user_name = "CloudBuilder"

    # 1. Register & start
    part = asyncio.run(service.register_or_get_participant(ch_id, user_id, user_name))
    assert part["status"] == "REGISTERED"
    assert len(part["question_order"]) == 3

    asyncio.run(service.start_participant_quiz(ch_id, user_id))

    # 2. Get Question 1
    q1 = asyncio.run(service.get_next_question_for_participant(ch_id, user_id))
    assert q1 is not None
    assert q1["question_number"] == 1
    assert set(q1["options"].keys()) == {"A", "B", "C", "D"}

    # Get the randomized correct display key from DB
    part_data = asyncio.run(service.register_or_get_participant(ch_id, user_id))
    correct_display_key = part_data["current_option_order"]["_display_correct"]

    # 3. Answer Question 1 correctly
    res1 = asyncio.run(
        service.record_answer_and_advance(
            challenge_id=ch_id,
            telegram_user_id=user_id,
            selected_option_key=correct_display_key,
            question_index=0,
        )
    )
    assert res1["is_correct"] is True
    assert res1["points_awarded"] > 0
    assert res1["correct_count"] == 1
    assert res1["is_completed"] is False

    # 4. Get Question 2
    q2 = asyncio.run(service.get_next_question_for_participant(ch_id, user_id))
    assert q2["question_number"] == 2

    # Answer Question 2 incorrectly
    part_data2 = asyncio.run(service.register_or_get_participant(ch_id, user_id))
    correct_key2 = part_data2["current_option_order"]["_display_correct"]
    wrong_key = "A" if correct_key2 != "A" else "B"

    res2 = asyncio.run(
        service.record_answer_and_advance(
            challenge_id=ch_id,
            telegram_user_id=user_id,
            selected_option_key=wrong_key,
            question_index=1,
        )
    )
    assert res2["is_correct"] is False
    assert res2["points_awarded"] == 0.0
    assert res2["correct_count"] == 1
    assert res2["is_completed"] is False

    # 5. Get Question 3 (Final question)
    q3 = asyncio.run(service.get_next_question_for_participant(ch_id, user_id))
    assert q3["question_number"] == 3

    part_data3 = asyncio.run(service.register_or_get_participant(ch_id, user_id))
    correct_key3 = part_data3["current_option_order"]["_display_correct"]

    res3 = asyncio.run(
        service.record_answer_and_advance(
            challenge_id=ch_id,
            telegram_user_id=user_id,
            selected_option_key=correct_key3,
            question_index=2,
        )
    )
    assert res3["is_correct"] is True
    assert res3["correct_count"] == 2
    assert res3["is_completed"] is True

    # Check participant state is COMPLETED
    final_part = asyncio.run(service.register_or_get_participant(ch_id, user_id))
    assert final_part["status"] == "COMPLETED"
    assert final_part["score"] == res3["current_score"]


def test_anti_double_click_protection():
    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    ch_id = asyncio.run(service.create_challenge(title="Double Click Test"))
    asyncio.run(service.link_questions_to_challenge(ch_id))
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    user_id = 112233
    asyncio.run(service.register_or_get_participant(ch_id, user_id, "FastClicker"))
    asyncio.run(service.start_participant_quiz(ch_id, user_id))
    asyncio.run(service.get_next_question_for_participant(ch_id, user_id))

    # First click succeeds
    res1 = asyncio.run(service.record_answer_and_advance(ch_id, user_id, "A", 0))
    assert "error" not in res1

    # Second rapid click on same question index 0 is detected as already answered and does not award double points
    res2 = asyncio.run(service.record_answer_and_advance(ch_id, user_id, "B", 0))
    assert res2.get("already_answered") is True
    assert res2["current_score"] == res1["current_score"]


def test_weekly_and_monthly_leaderboards():
    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    ch_id = asyncio.run(service.create_challenge(title="Leaderboard Championship"))
    asyncio.run(service.link_questions_to_challenge(ch_id))
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    # Simulate Student A (High score) with username
    p1 = asyncio.run(service.register_or_get_participant(ch_id, 101, "Alice", username="alice_cloud"))
    assert p1["username"] == "alice_cloud"
    asyncio.run(service.start_participant_quiz(ch_id, 101))
    asyncio.run(service.get_next_question_for_participant(ch_id, 101))
    p1_data = asyncio.run(service.register_or_get_participant(ch_id, 101))
    asyncio.run(service.record_answer_and_advance(ch_id, 101, p1_data["current_option_order"]["_display_correct"], 0))
    asyncio.run(service.get_next_question_for_participant(ch_id, 101))
    p1_data2 = asyncio.run(service.register_or_get_participant(ch_id, 101))
    asyncio.run(service.record_answer_and_advance(ch_id, 101, p1_data2["current_option_order"]["_display_correct"], 1))
    asyncio.run(service.get_next_question_for_participant(ch_id, 101))
    p1_data3 = asyncio.run(service.register_or_get_participant(ch_id, 101))
    asyncio.run(service.record_answer_and_advance(ch_id, 101, p1_data3["current_option_order"]["_display_correct"], 2))

    # Simulate Student B (Lower score) without username
    p2 = asyncio.run(service.register_or_get_participant(ch_id, 102, "Bob"))
    asyncio.run(service.start_participant_quiz(ch_id, 102))
    asyncio.run(service.get_next_question_for_participant(ch_id, 102))
    p2_data = asyncio.run(service.register_or_get_participant(ch_id, 102))
    asyncio.run(service.record_answer_and_advance(ch_id, 102, p2_data["current_option_order"]["_display_correct"], 0))
    asyncio.run(service.get_next_question_for_participant(ch_id, 102))
    asyncio.run(service.record_answer_and_advance(ch_id, 102, "INVALID", 1))
    asyncio.run(service.get_next_question_for_participant(ch_id, 102))
    asyncio.run(service.record_answer_and_advance(ch_id, 102, "INVALID", 2))

    # Test Weekly Leaderboard
    weekly_lb = asyncio.run(service.get_weekly_leaderboard(ch_id, limit=5))
    entries = weekly_lb["entries"]
    assert weekly_lb["total_count"] == 2
    assert weekly_lb["total_pages"] == 1
    assert len(entries) == 2
    assert entries[0]["user_name"] == "Alice"
    assert entries[0]["username"] == "alice_cloud"
    assert entries[0]["rank"] == 1
    assert entries[1]["user_name"] == "Bob"
    assert entries[1]["rank"] == 2
    assert entries[0]["score"] > entries[1]["score"]

    # Test Monthly Cumulative Leaderboard
    monthly_lb = asyncio.run(service.get_monthly_leaderboard(limit=5))
    m_entries = monthly_lb["entries"]
    assert monthly_lb["total_count"] == 2
    assert len(m_entries) == 2
    assert m_entries[0]["user_name"] == "Alice"
    assert m_entries[0]["username"] == "alice_cloud"
    assert m_entries[0]["total_score"] > m_entries[1]["total_score"]


def test_leaderboard_pagination_and_navigation_controls():
    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    ch_id = asyncio.run(service.create_challenge(title="Large Quiz"))
    asyncio.run(service.link_questions_to_challenge(ch_id))
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    # Register and complete for 15 participants
    for i in range(1, 16):
        uid = 1000 + i
        uname = f"Student_{i:02d}"
        asyncio.run(service.register_or_get_participant(ch_id, uid, uname, username=f"user_{i}"))
        asyncio.run(service.start_participant_quiz(ch_id, uid))
        for q_idx in range(3):
            asyncio.run(service.get_next_question_for_participant(ch_id, uid))
            p_data = asyncio.run(service.register_or_get_participant(ch_id, uid))
            correct_key = p_data["current_option_order"]["_display_correct"]
            # Alternate scores
            ans = correct_key if (i % 2 == 0 or q_idx == 0) else "INVALID"
            asyncio.run(service.record_answer_and_advance(ch_id, uid, ans, q_idx))

    # Page 1 (limit 10)
    page1 = asyncio.run(service.get_weekly_leaderboard(ch_id, limit=10, page=1))
    assert page1["total_count"] == 15
    assert page1["total_pages"] == 2
    assert page1["has_next"] is True
    assert page1["has_prev"] is False
    assert len(page1["entries"]) == 10
    assert page1["entries"][0]["rank"] == 1
    assert page1["entries"][9]["rank"] == 10

    # Page 2 (limit 10)
    page2 = asyncio.run(service.get_weekly_leaderboard(ch_id, limit=10, page=2))
    assert page2["has_next"] is False
    assert page2["has_prev"] is True
    assert len(page2["entries"]) == 5
    assert page2["entries"][0]["rank"] == 11
    assert page2["entries"][4]["rank"] == 15

    # Keyboard pagination checks
    from app.challenge.keyboards import get_leaderboard_keyboard
    kb1 = get_leaderboard_keyboard(ch_id, mode="weekly", page=1, total_pages=2)
    kb1_texts = [btn.text for row in kb1.inline_keyboard for btn in row]
    assert "Next ➡️" in kb1_texts
    assert "1/2" in kb1_texts
    assert "⬅️ Prev" not in kb1_texts

    kb2 = get_leaderboard_keyboard(ch_id, mode="weekly", page=2, total_pages=2)
    kb2_texts = [btn.text for row in kb2.inline_keyboard for btn in row]
    assert "⬅️ Prev" in kb2_texts
    assert "2/2" in kb2_texts
    assert "Next ➡️" not in kb2_texts


def test_challenge_start_end_time_transitions_and_past_challenges():
    from datetime import datetime, timezone, timedelta
    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    now = datetime.now(timezone.utc)
    past_start = (now - timedelta(days=8)).isoformat()
    past_end = (now - timedelta(days=1)).isoformat()

    future_start = (now + timedelta(hours=2)).isoformat()
    future_end = (now + timedelta(days=7)).isoformat()

    # 1. Create an ended past challenge
    ch1_id = asyncio.run(service.create_challenge(
        title="Past Cloud Quiz",
        starts_at=past_start,
        ends_at=past_end,
    ))
    asyncio.run(service.link_questions_to_challenge(ch1_id))
    asyncio.run(service.update_challenge_status(ch1_id, "LIVE"))

    # 2. Create a future scheduled challenge
    ch2_id = asyncio.run(service.create_challenge(
        title="Upcoming Cloud Sprint",
        starts_at=future_start,
        ends_at=future_end,
    ))
    asyncio.run(service.link_questions_to_challenge(ch2_id))
    asyncio.run(service.update_challenge_status(ch2_id, "SCHEDULED"))

    # 3. Trigger time transition in get_active_challenge()
    active = asyncio.run(service.get_active_challenge())
    assert active is not None
    assert active["id"] == ch2_id
    assert active["status"] == "SCHEDULED"

    # Verify ch1 was automatically transitioned from LIVE -> ENDED because past_end < now
    ch1_updated = asyncio.run(service.get_challenge(ch1_id))
    assert ch1_updated["status"] == "ENDED"

    # 4. Verify list_past_challenges returns ch1
    past_list = asyncio.run(service.list_past_challenges())
    assert len(past_list) >= 1
    assert any(c["id"] == ch1_id for c in past_list)

    # 5. User can practice questions on the ended past challenge
    asyncio.run(service.register_or_get_participant(ch1_id, 888, "Practice Student"))
    asyncio.run(service.start_participant_quiz(ch1_id, 888))
    q_data = asyncio.run(service.get_next_question_for_participant(ch1_id, 888))
    assert q_data is not None
    assert q_data["question_number"] == 1


def test_monthly_analytics_report_compilation():
    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    # 1. Register a user
    asyncio.run(db.register_or_update_bot_user(101, "Builder 1", "builder_one"))

    # 2. Create and complete a challenge
    ch_id = asyncio.run(service.create_challenge(title="Monthly Test Challenge"))
    asyncio.run(service.link_questions_to_challenge(ch_id))
    asyncio.run(service.register_or_get_participant(ch_id, 101, "Builder 1", "builder_one"))
    asyncio.run(service.start_participant_quiz(ch_id, 101))
    for q_idx in range(3):
        asyncio.run(service.get_next_question_for_participant(ch_id, 101))
        p_info = asyncio.run(service.register_or_get_participant(ch_id, 101))
        corr_key = p_info["current_option_order"]["_display_correct"]
        asyncio.run(service.record_answer_and_advance(ch_id, 101, corr_key, q_idx))

    # 3. Add feedback and admin reply
    asyncio.run(db.save_feedback_submission(message_id=999, sender_chat_id=101, sender_name="Builder 1"))
    asyncio.run(db.save_admin_reply_mapping(admin_message_id=888, user_chat_id=101, delivered_message_id=777))

    # 4. Generate report
    report = asyncio.run(service.get_monthly_analytics_report())
    assert report["total_users"] >= 1
    assert report["total_challenges"] >= 1
    assert report["total_attempts"] == 1
    assert report["total_score"] > 0
    assert report["accuracy_pct"] == 100.0
    assert report["feedback_count"] == 1
    assert report["reply_count"] == 1
    assert report["question_count"] == 3
    assert len(report["champions"]) == 1
    assert report["champions"][0]["telegram_user_id"] == 101


def test_parse_single_question_text_formats():
    sample1 = """What is Amazon DynamoDB?
A: Relational database
B: Key-value NoSQL database
C: In-memory cache
D: Object storage
Answer: B
Category: Database
Difficulty: EASY
Explanation: DynamoDB is a managed NoSQL key-value store"""

    res1 = service.parse_single_question_text(sample1)
    assert res1 is not None
    assert res1["question_text"] == "What is Amazon DynamoDB?"
    assert res1["option_a"] == "Relational database"
    assert res1["option_b"] == "Key-value NoSQL database"
    assert res1["option_c"] == "In-memory cache"
    assert res1["option_d"] == "Object storage"
    assert res1["correct_option"] == "B"
    assert res1["category"] == "Database"
    assert res1["difficulty"] == "EASY"
    assert res1["explanation"] == "DynamoDB is a managed NoSQL key-value store"

    sample2 = """Question: What service provides object storage?
Option A. AWS Lambda
Option B. Amazon EC2
Option C. Amazon S3
Option D. Amazon RDS
Correct: C"""

    res2 = service.parse_single_question_text(sample2)
    assert res2 is not None
    assert res2["correct_option"] == "C"
    assert res2["option_c"] == "Amazon S3"

    sample3 = "What is S3?,Object Storage,Block Storage,Compute,Database,A,EASY,Storage,10,S3 is scalable object storage"
    res3 = service.parse_single_question_text(sample3)
    assert res3 is not None
    assert res3["correct_option"] == "A"
    assert res3["option_a"] == "Object Storage"


def test_challenge_specific_question_crud_and_csv_import():
    asyncio.run(db.reset_db())
    ch_id = asyncio.run(service.create_challenge(title="Security Specific Challenge", category="Security"))

    # 1. Add single question directly to this challenge
    q_data = {
        "question_text": "What AWS service manages IAM policies?",
        "option_a": "AWS IAM",
        "option_b": "Amazon VPC",
        "option_c": "Amazon S3",
        "option_d": "AWS CloudTrail",
        "correct_option": "A",
        "category": "Security",
        "difficulty": "EASY",
        "base_points": 10.0,
        "explanation": "IAM provides identity and access control.",
    }
    q1_id = asyncio.run(service.add_question_to_challenge(ch_id, q_data))
    assert q1_id is not None

    ch_q1 = asyncio.run(service.get_challenge_questions(ch_id))
    assert len(ch_q1) == 1
    assert ch_q1[0]["question_text"] == "What AWS service manages IAM policies?"

    # 2. Import CSV directly to this challenge
    csv_raw = "What is KMS?,Key Management,Block Storage,Compute,Database,A,MEDIUM,Security,10,KMS manages encryption keys"
    res = asyncio.run(service.import_questions_for_challenge(ch_id, csv_raw))
    assert res["imported"] == 1

    ch_q2 = asyncio.run(service.get_challenge_questions(ch_id))
    assert len(ch_q2) == 2

    # 3. Remove a question from the challenge
    asyncio.run(service.remove_question_from_challenge(ch_id, q1_id))
    ch_q3 = asyncio.run(service.get_challenge_questions(ch_id))
    assert len(ch_q3) == 1
def test_challenge_time_capping_and_closing_deadline():
    asyncio.run(db.reset_db())
    from datetime import datetime, timezone, timedelta

    now_dt = datetime.now(timezone.utc)
    # Challenge ends in 5 minutes (300 seconds), but standard duration is 20 minutes (1200 seconds)
    ends_at_str = (now_dt + timedelta(minutes=5)).isoformat()

    ch_id = asyncio.run(
        service.create_challenge(
            title="Closing Soon Sprint",
            category="Serverless",
            duration_seconds=1200,
            starts_at=now_dt.isoformat(),
            ends_at=ends_at_str,
        )
    )
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    q_data = {
        "question_text": "What is AWS Fargate?",
        "option_a": "Serverless container compute",
        "option_b": "Virtual machine",
        "option_c": "Relational database",
        "option_d": "DNS server",
        "correct_option": "A",
    }
    asyncio.run(service.add_question_to_challenge(ch_id, q_data))

    challenge = asyncio.run(service.get_challenge(ch_id))

    # 1. Before starting: calculate_remaining_exam_seconds caps to 300 seconds (5 mins) instead of 1200s
    rem_sec, is_capped, close_iso = service.calculate_remaining_exam_seconds(challenge, None)
    assert is_capped is True
    assert 290 <= rem_sec <= 300

    # 2. Participant starts quiz
    user_id = 77777
    part = asyncio.run(service.register_or_get_participant(ch_id, user_id, "FastBuilder"))
    asyncio.run(service.start_participant_quiz(ch_id, user_id))

    # 3. Next question is marked deadline capped
    q = asyncio.run(service.get_next_question_for_participant(ch_id, user_id))
    assert q is not None
    assert q["is_deadline_capped"] is True
    assert "04:" in q["time_remaining_str"] or "05:" in q["time_remaining_str"]

    # 4. If challenge already concluded in the past (e.g. ended 1 minute ago)
    past_ends_at = (now_dt - timedelta(minutes=1)).isoformat()
    asyncio.run(service.update_challenge_details(ch_id, ends_at=past_ends_at))
    closed_ch = asyncio.run(service.get_challenge(ch_id))
    rem_sec_closed, is_capped_closed, _ = service.calculate_remaining_exam_seconds(closed_ch, None)
    assert rem_sec_closed <= 0.0

    # Attempting to fetch next question auto-completes participant due to deadline closure
    q_expired = asyncio.run(service.get_next_question_for_participant(ch_id, user_id))
    assert q_expired is None

    part_completed = asyncio.run(service.register_or_get_participant(ch_id, user_id))
    assert part_completed["status"] == "COMPLETED"


def test_question_bottom_navigation_bar_and_jumping():
    """Verifies that questions have bottom navigation buttons and direct jumping works."""
    from app.challenge.keyboards import get_question_options_keyboard

    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    ch_id = asyncio.run(service.create_challenge(title="Nav Test Sprint"))
    asyncio.run(service.link_questions_to_challenge(ch_id))
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    user_id = 998877
    asyncio.run(service.register_or_get_participant(ch_id, user_id, "NavUser"))
    asyncio.run(service.start_participant_quiz(ch_id, user_id))

    # 1. Fetch Question 1 (index 0)
    q1 = asyncio.run(service.get_next_question_for_participant(ch_id, user_id, question_index=0))
    assert q1["question_number"] == 1
    assert q1["total_questions"] == 3
    assert q1["answered_indices"] == []

    # 2. Keyboard has 2x2 options and bottom navigation
    kb1 = get_question_options_keyboard(ch_id, 0, q1["display_keys"], q1["total_questions"], q1["answered_indices"])
    all_buttons = [btn.text for row in kb1.inline_keyboard for btn in row]
    assert "• 1 •" in all_buttons
    assert "2" in all_buttons
    assert "3" in all_buttons

    # 3. Answer Question 1
    p1 = asyncio.run(service.register_or_get_participant(ch_id, user_id))
    correct_key = p1["current_option_order"]["_display_correct"]
    res = asyncio.run(service.record_answer_and_advance(ch_id, user_id, correct_key, 0))
    assert res["is_correct"] is True

    # 4. Jump directly to Question 3 (index 2) via navigation
    q3 = asyncio.run(service.get_next_question_for_participant(ch_id, user_id, question_index=2))
    assert q3["question_number"] == 3
    assert 0 in q3["answered_indices"]  # Question 1 was answered

    kb3 = get_question_options_keyboard(ch_id, 2, q3["display_keys"], q3["total_questions"], q3["answered_indices"])
    all_buttons3 = [btn.text for row in kb3.inline_keyboard for btn in row]
    assert "1✅" in all_buttons3
    assert "2" in all_buttons3
    assert "• 3 •" in all_buttons3

    # 5. Verify 10-question chunked pagination (1-5 -> 6-10)
    kb_10_p1 = get_question_options_keyboard(ch_id, 1, ["A", "B", "C", "D"], total_questions=10, answered_indices=[0, 1])
    btns_p1 = [btn.text for row in kb_10_p1.inline_keyboard for btn in row]
    assert "1✅" in btns_p1
    assert "• 2✅ •" in btns_p1
    assert "3" in btns_p1
    assert "4" in btns_p1
    assert "5" in btns_p1
    assert "Q6-10 ▶️" in btns_p1

    kb_10_p2 = get_question_options_keyboard(ch_id, 6, ["A", "B", "C", "D"], total_questions=10, answered_indices=[0, 1])
    btns_p2 = [btn.text for row in kb_10_p2.inline_keyboard for btn in row]
    assert "6" in btns_p2
    assert "• 7 •" in btns_p2
    assert "8" in btns_p2
    assert "9" in btns_p2
    assert "10" in btns_p2
    assert "◀️ Q1-5" in btns_p2


def test_answer_question_2_navigates_to_question_3():
    """Explicitly verifies: when a student answers question 2 (index 1), it navigates to question 3 (index 2)."""
    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    ch_id = asyncio.run(service.create_challenge(title="Sequential Navigation Test"))
    asyncio.run(service.link_questions_to_challenge(ch_id))
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    user_id = 554433
    asyncio.run(service.register_or_get_participant(ch_id, user_id, "Bob"))
    asyncio.run(service.start_participant_quiz(ch_id, user_id))

    # Step 1: User starts on Question 1, answers Question 1
    q1 = asyncio.run(service.get_next_question_for_participant(ch_id, user_id, question_index=0))
    assert q1["question_number"] == 1
    p1 = asyncio.run(service.register_or_get_participant(ch_id, user_id))
    res1 = asyncio.run(service.record_answer_and_advance(ch_id, user_id, p1["current_option_order"]["_display_correct"], 0))
    assert res1["next_question_index"] == 1  # Navigates to index 1 (Question 2)

    # Step 2: User is on Question 2, answers Question 2
    q2 = asyncio.run(service.get_next_question_for_participant(ch_id, user_id, question_index=res1["next_question_index"]))
    assert q2["question_number"] == 2
    p2 = asyncio.run(service.register_or_get_participant(ch_id, user_id))
    res2 = asyncio.run(service.record_answer_and_advance(ch_id, user_id, p2["current_option_order"]["_display_correct"], 1))
    assert res2["next_question_index"] == 2  # Navigates to index 2 (Question 3)

    # Step 3: Question 3 is loaded
    q3 = asyncio.run(service.get_next_question_for_participant(ch_id, user_id, question_index=res2["next_question_index"]))
    assert q3["question_number"] == 3
    assert 0 in q3["answered_indices"]
    assert 1 in q3["answered_indices"]


def test_challenge_review_questions_and_explanations():
    asyncio.run(db.reset_db())
    asyncio.run(service.import_questions_from_csv(SAMPLE_CSV))

    ch_id = asyncio.run(service.create_challenge(title="Review Test Challenge"))
    asyncio.run(service.link_questions_to_challenge(ch_id))
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    user_id = 98765
    asyncio.run(service.register_or_get_participant(ch_id, user_id, "Reviewer"))
    asyncio.run(service.start_participant_quiz(ch_id, user_id))

    # 1. While in progress, review is locked
    locked_review = asyncio.run(service.get_challenge_review_data(ch_id, user_id, question_index=0))
    assert locked_review.get("error") == "locked"

    # 2. Answer all 3 questions and complete the challenge
    for q_idx in range(3):
        asyncio.run(service.get_next_question_for_participant(ch_id, user_id, question_index=q_idx))
        part = asyncio.run(service.register_or_get_participant(ch_id, user_id))
        correct_key = part["current_option_order"]["_display_correct"]
        # Answer Q0 correct, Q1 wrong, Q2 correct
        ans = correct_key if q_idx != 1 else "INVALID"
        asyncio.run(service.record_answer_and_advance(ch_id, user_id, ans, q_idx))

    # 3. Now review is unlocked
    rev0 = asyncio.run(service.get_challenge_review_data(ch_id, user_id, question_index=0))
    assert "error" not in rev0
    assert rev0["question_number"] == 1
    assert rev0["total_questions"] == 3
    assert rev0["explanation"] != ""

    rev_all = [asyncio.run(service.get_challenge_review_data(ch_id, user_id, question_index=i)) for i in range(3)]
    assert sum(1 for r in rev_all if r["is_correct"] is True) == 2
    assert sum(1 for r in rev_all if r["is_correct"] is False) == 1

    # 4. Review card formatting
    from app.challenge.handlers import _format_review_card
    card = _format_review_card(rev_all[0])
    assert "Question Review" in card
    assert "Explanation" in card
    assert "Correct" in card


def test_flexible_csv_import_formats():
    asyncio.run(db.reset_db())
    ch_id = asyncio.run(service.create_challenge(title="CSV Test Sprint"))

    # Format 1: Human spaced headers with BOM + Full text answer
    csv_spaced = "\ufeffQuestion,Option A,Option B,Option C,Option D,Answer,Explanation\n" \
                 "What is DynamoDB?,Managed NoSQL,Relational DB,Object Storage,DNS,Managed NoSQL,DynamoDB is NoSQL\n"
    res1 = asyncio.run(service.import_questions_for_challenge(ch_id, csv_spaced))
    assert res1["imported"] == 1
    assert len(res1["errors"]) == 0

    # Format 2: Semicolon delimited
    csv_semi = "Question;Option A;Option B;Option C;Option D;Answer\n" \
               "What is CloudFront?;CDN;Compute;Storage;Queue;A\n"
    res2 = asyncio.run(service.import_questions_for_challenge(ch_id, csv_semi))
    assert res2["imported"] == 1

    # Format 3: Numbered answer (1 = A, 2 = B, 3 = C, 4 = D)
    csv_num = "Prompt,Choice 1,Choice 2,Choice 3,Choice 4,Key,Rationale\n" \
              "What is SNS?,Pub/Sub,Storage,Compute,Database,1,SNS is messaging\n"
    res3 = asyncio.run(service.import_questions_for_challenge(ch_id, csv_num))
    assert res3["imported"] == 1

    # Format 4: Markdown wrapped CSV
    csv_md = "```csv\nquestion,option_a,option_b,option_c,option_d,correct\n" \
             "What is SQS?,Queue,Storage,Compute,Database,A\n```"
    res4 = asyncio.run(service.import_questions_for_challenge(ch_id, csv_md))
    assert res4["imported"] == 1

    # Verify all 4 questions were linked to the challenge
    questions = asyncio.run(service.get_challenge_questions(ch_id))
    assert len(questions) == 4
    assert questions[0]["correct_option"] == "A"
    assert questions[1]["correct_option"] == "A"
    assert questions[2]["correct_option"] == "A"
    assert questions[3]["correct_option"] == "A"


def test_multi_active_challenges_sorting_and_selection():
    from tests.test_bot import FakeUpdate, FakeContext, FakeCallbackQuery
    from app.challenge.handlers import challenge_command, handle_challenge_select_callback

    asyncio.run(db.reset_db())

    # Create 3 challenges with different live/start times
    ch1_id = asyncio.run(
        service.create_challenge(
            title="Challenge Alpha",
            category="Compute",
            starts_at="2026-09-01T10:00:00+00:00",
        )
    )
    asyncio.run(service.update_challenge_status(ch1_id, "LIVE"))

    ch2_id = asyncio.run(
        service.create_challenge(
            title="Challenge Beta",
            category="Database",
            starts_at="2026-09-02T10:00:00+00:00",
        )
    )
    asyncio.run(service.update_challenge_status(ch2_id, "LIVE"))

    ch3_id = asyncio.run(
        service.create_challenge(
            title="Challenge Gamma",
            category="Security",
            starts_at="2099-01-01T10:00:00+00:00",
        )
    )
    asyncio.run(service.update_challenge_status(ch3_id, "SCHEDULED"))

    # Verify service sorting: Live first, newest starts_at first, then scheduled
    active = asyncio.run(service.get_active_challenges())
    assert len(active) == 3
    assert active[0]["id"] == ch2_id  # Newest LIVE
    assert active[1]["id"] == ch1_id  # Older LIVE
    assert active[2]["id"] == ch3_id  # SCHEDULED

    # Verify challenge_command presents challenge in question format with smart nav bar
    update = FakeUpdate(user_id=101)
    context = FakeContext()
    asyncio.run(challenge_command(update, context))

    assert len(update.message.reply_text_calls) == 1
    call = update.message.reply_text_calls[0]
    assert "Active Challenge" in call["text"]
    assert "Challenge Beta" in call["text"]  # Newest live is index 0
    assert "(1 of 3)" in call["text"]
    assert "🟢 <b>Status: Live Now</b>" in call["text"]

    kb = call["reply_markup"]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert f"ch_start:{ch2_id}" in callbacks
    assert "ch_nav_act:1" in callbacks
    assert "ch_nav_act:2" in callbacks

    # Verify navigating to challenge 2 (Alpha) via smart nav bar
    from app.challenge.handlers import handle_challenge_nav_active_callback
    cb = FakeCallbackQuery(data="ch_nav_act:1", user_id=101)
    cb_update = FakeUpdate(callback_query=cb)
    asyncio.run(handle_challenge_nav_active_callback(cb_update, context))

    assert cb.edited_text is not None
    assert "Challenge Alpha" in cb.edited_text
    assert "(2 of 3)" in cb.edited_text
    alpha_callbacks = [btn.callback_data for row in cb.reply_markup.inline_keyboard for btn in row]
    assert f"ch_start:{ch1_id}" in alpha_callbacks

    # Verify navigating to challenge 3 (Gamma - Scheduled) via smart nav bar
    cb3 = FakeCallbackQuery(data="ch_nav_act:2", user_id=101)
    cb3_update = FakeUpdate(callback_query=cb3)
    asyncio.run(handle_challenge_nav_active_callback(cb3_update, context))

    assert cb3.edited_text is not None
    assert "Challenge Gamma" in cb3.edited_text
    assert "(3 of 3)" in cb3.edited_text
    assert "🕒 <b>Status: Upcoming Challenge</b>" in cb3.edited_text
    assert "Scheduled Opening:" in cb3.edited_text
    assert "2099" in cb3.edited_text
    assert "Countdown:" in cb3.edited_text

    gamma_callbacks = [btn.callback_data for row in cb3.reply_markup.inline_keyboard for btn in row]
    assert f"ch_sched_info:{ch3_id}" in gamma_callbacks

    # Verify tapping scheduled button provides informational popup
    from app.challenge.handlers import handle_scheduled_challenge_info_callback
    cb_info = FakeCallbackQuery(data=f"ch_sched_info:{ch3_id}", user_id=101)
    cb_info_update = FakeUpdate(callback_query=cb_info)
    asyncio.run(handle_scheduled_challenge_info_callback(cb_info_update, context))


def test_refresh_status_button_transitions_to_live():
    """Verifies that tapping the 'Refresh Status' button without emoji unlocks a scheduled challenge in real time."""
    from tests.test_bot import FakeUpdate, FakeContext, FakeCallbackQuery
    from app.challenge.handlers import handle_challenge_refresh_callback

    asyncio.run(db.reset_db())
    ch_id = asyncio.run(
        service.create_challenge(
            title="Realtime Refresh Challenge",
            category="DevOps",
            starts_at="2099-01-01T00:00:00+00:00",
        )
    )
    asyncio.run(service.update_challenge_status(ch_id, "SCHEDULED"))

    context = FakeContext()
    cb = FakeCallbackQuery(data=f"ch_refresh:{ch_id}:0", user_id=101)
    up = FakeUpdate(callback_query=cb)

    # First refresh: challenge is still scheduled
    asyncio.run(handle_challenge_refresh_callback(up, context))
    assert cb.edited_text is not None
    assert "Status: Upcoming Challenge" in cb.edited_text
    labels = [btn.text for row in cb.reply_markup.inline_keyboard for btn in row]
    assert "Refresh Status" in labels

    # Now time arrives: update starts_at to the past
    past_iso = "2026-01-01T00:00:00+00:00"
    asyncio.run(service.update_challenge_details(ch_id, starts_at=past_iso))

    cb2 = FakeCallbackQuery(data=f"ch_refresh:{ch_id}:0", user_id=101)
    up2 = FakeUpdate(callback_query=cb2)
    asyncio.run(handle_challenge_refresh_callback(up2, context))

    assert cb2.edited_text is not None
    assert "Status: Live Now" in cb2.edited_text
    labels2 = [btn.text for row in cb2.reply_markup.inline_keyboard for btn in row]
    assert any("Start Challenge" in label for label in labels2)
    assert "Refresh Status" in labels2


def test_leaderboard_review_button_visibility_and_locking():
    from tests.test_bot import FakeUpdate, FakeContext, FakeCallbackQuery
    from app.challenge.handlers import handle_leaderboard_callback, handle_challenge_review_callback

    asyncio.run(db.reset_db())
    ch_id = asyncio.run(
        service.create_challenge(
            title="Live Quiz Challenge",
            category="Cloud",
            starts_at="2026-09-01T10:00:00+00:00",
        )
    )
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    # User 201 has not completed the challenge
    cb = FakeCallbackQuery(data=f"lb_weekly:{ch_id}:1", user_id=201)
    cb_update = FakeUpdate(callback_query=cb)
    context = FakeContext()
    asyncio.run(handle_leaderboard_callback(cb_update, context))

    assert cb.edited_text is not None
    assert "No completed submissions yet" in cb.edited_text
    btn_texts = [btn.text for row in cb.reply_markup.inline_keyboard for btn in row]
    # Review Questions & Answers should NOT be present when user has not completed
    assert "Review Questions & Answers" not in btn_texts

    # If user tries to trigger review callback while locked, it must alert them with an explanation
    cb_review = FakeCallbackQuery(data=f"ch_review:{ch_id}:0", user_id=201)
    cb_review_update = FakeUpdate(callback_query=cb_review)
    asyncio.run(handle_challenge_review_callback(cb_review_update, context))
    assert cb_review.answered is True
    assert "unlocked only after you complete" in cb_review.answered_text

    # Now mark user 201 as completed
    asyncio.run(service.register_or_get_participant(ch_id, 201, "Alice", "alice"))
    asyncio.run(service._execute("UPDATE challenge_participants SET status = 'COMPLETED' WHERE challenge_id = ? AND telegram_user_id = ?", (ch_id, 201)))

    # Leaderboard now for user 201 SHOULD include Review Questions & Answers
    cb2 = FakeCallbackQuery(data=f"lb_weekly:{ch_id}:1", user_id=201)
    cb2_update = FakeUpdate(callback_query=cb2)
    asyncio.run(handle_leaderboard_callback(cb2_update, context))
    btn2_texts = [btn.text for row in cb2.reply_markup.inline_keyboard for btn in row]
    assert "Review Questions & Answers" in btn2_texts


def test_admin_challenge_management_and_wizard_timer(monkeypatch):
    """Tests admin challenge publishing, concluding, and wizard timer customization."""
    from tests.test_bot import FakeUpdate, FakeContext, FakeCallbackQuery
    from app.challenge.admin import handle_admin_callback
    from app.challenge.service import (
        create_challenge,
        get_challenge,
        create_question,
        add_question_to_challenge,
    )

    monkeypatch.setenv("ADMIN_USER_IDS", "88888")
    asyncio.run(db.reset_db())
    ctx = FakeContext()

    # 1. Create a draft challenge with future start date
    ch_id = asyncio.run(create_challenge(title="Draft DevOps Quiz", category="DevOps", starts_at="2099-01-01T00:00:00+00:00"))

    # 2. Try to publish with 0 questions attached -> should alert and remain DRAFT
    q_pub = FakeCallbackQuery(user_id=88888, data=f"adm_pub:{ch_id}")
    up_pub = FakeUpdate(user_id=88888, callback_query=q_pub)
    asyncio.run(handle_admin_callback(up_pub, ctx))
    assert q_pub.answered is True
    assert "attach at least 1 question" in q_pub.answered_text
    ch_draft = asyncio.run(get_challenge(ch_id))
    assert ch_draft["status"] == "DRAFT"

    # 3. Attach a question
    asyncio.run(add_question_to_challenge(ch_id, {
        "question_text": "What is S3?",
        "option_a": "Storage",
        "option_b": "Database",
        "option_c": "Compute",
        "option_d": "DNS",
        "correct_option": "A",
        "category": "Storage",
        "explanation": "S3 is object storage.",
    }))

    # 4. Now publish LIVE -> starts_at should be set to now, status LIVE
    q_pub2 = FakeCallbackQuery(user_id=88888, data=f"adm_pub:{ch_id}")
    up_pub2 = FakeUpdate(user_id=88888, callback_query=q_pub2)
    asyncio.run(handle_admin_callback(up_pub2, ctx))
    ch_live = asyncio.run(get_challenge(ch_id))
    assert ch_live["status"] == "LIVE"
    assert ch_live["starts_at"] is not None
    assert ch_live["starts_at"] != "2099-01-01T00:00:00+00:00"

    # 5. End challenge -> status ENDED, ends_at updated
    q_end = FakeCallbackQuery(user_id=88888, data=f"adm_end:{ch_id}")
    up_end = FakeUpdate(user_id=88888, callback_query=q_end)
    asyncio.run(handle_admin_callback(up_end, ctx))
    ch_ended = asyncio.run(get_challenge(ch_id))
    assert ch_ended["status"] == "ENDED"

    # 6. Test wizard timer setting via callback
    q_wiz_timer = FakeCallbackQuery(user_id=88888, data=f"adm_wiz_timer:{ch_id}:25")
    up_wt = FakeUpdate(user_id=88888, callback_query=q_wiz_timer)
    asyncio.run(handle_admin_callback(up_wt, ctx))
    assert "25 Minutes" in q_wiz_timer.edited_text
    ch_updated = asyncio.run(get_challenge(ch_id))
    assert ch_updated["duration_seconds"] == 25 * 60


def test_leaderboard_weekly_monthly_tab_switching():
    """Verifies tab switching between weekly and monthly leaderboards with state preservation."""
    from tests.test_bot import FakeUpdate, FakeContext, FakeCallbackQuery
    from app.challenge.handlers import handle_leaderboard_callback

    asyncio.run(db.reset_db())
    ch_id = asyncio.run(
        service.create_challenge(
            title="Tab Switcher Challenge",
            category="Cloud",
            starts_at="2026-09-01T10:00:00+00:00",
        )
    )
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    ctx = FakeContext()

    # 1. View weekly leaderboard via callback
    cb_w = FakeCallbackQuery(data=f"lb_weekly:{ch_id}:1", user_id=301)
    up_w = FakeUpdate(callback_query=cb_w)
    asyncio.run(handle_leaderboard_callback(up_w, ctx))

    assert "Weekly Leaderboard: Tab Switcher Challenge" in cb_w.edited_text
    btn_w = [btn.text for row in cb_w.reply_markup.inline_keyboard for btn in row]
    # Active tab is Weekly (marked with bullets), Monthly is available
    assert "• 🏆 Weekly •" in btn_w
    assert "📅 Monthly" in btn_w

    # Find the Monthly button callback data
    monthly_btn = next(btn for row in cb_w.reply_markup.inline_keyboard for btn in row if btn.text == "📅 Monthly")
    assert monthly_btn.callback_data == f"lb_monthly:{ch_id}:1"

    # 2. Tap Monthly button -> switches to Monthly Championship Leaderboard
    cb_m = FakeCallbackQuery(data=monthly_btn.callback_data, user_id=301)
    up_m = FakeUpdate(callback_query=cb_m)
    asyncio.run(handle_leaderboard_callback(up_m, ctx))

    assert "Monthly Championship Leaderboard" in cb_m.edited_text
    btn_m = [btn.text for row in cb_m.reply_markup.inline_keyboard for btn in row]
    # Active tab is Monthly (marked with bullets), Weekly is available
    assert "• 📅 Monthly •" in btn_m
    assert "🏆 Weekly" in btn_m
    # Challenge context was preserved
    assert "« Back to Challenge" in btn_m

    # Find the Weekly button callback data
    weekly_btn = next(btn for row in cb_m.reply_markup.inline_keyboard for btn in row if btn.text == "🏆 Weekly")
    assert weekly_btn.callback_data == f"lb_weekly:{ch_id}:1"

    # 3. Tap Weekly button -> switches right back to Weekly Leaderboard for challenge
    cb_w2 = FakeCallbackQuery(data=weekly_btn.callback_data, user_id=301)
    up_w2 = FakeUpdate(callback_query=cb_w2)
    asyncio.run(handle_leaderboard_callback(up_w2, ctx))

    assert "Weekly Leaderboard: Tab Switcher Challenge" in cb_w2.edited_text


def test_draft_challenges_never_exposed_to_students():
    """Verifies DRAFT challenges are never shown or accessible to students in past challenges, review, or leaderboards."""
    from tests.test_bot import FakeUpdate, FakeContext, FakeCallbackQuery, FakeMessage
    from app.challenge.handlers import past_challenges_command, handle_past_challenges_callback, handle_leaderboard_callback
    from app.challenge.service import get_challenge_review_data, list_past_challenges

    asyncio.run(db.reset_db())

    # Create an ENDED challenge and a DRAFT challenge
    ended_id = asyncio.run(
        service.create_challenge(
            title="Archived Cloud Challenge",
            category="Cloud",
            starts_at="2026-08-01T10:00:00+00:00",
            ends_at="2026-08-08T10:00:00+00:00",
        )
    )
    asyncio.run(service.update_challenge_status(ended_id, "ENDED"))

    draft_id = asyncio.run(
        service.create_challenge(
            title="Secret Draft Challenge",
            category="Serverless",
            starts_at="2026-09-01T10:00:00+00:00",
        )
    )
    # Ensure draft_id is strictly DRAFT
    asyncio.run(service.update_challenge_status(draft_id, "DRAFT"))

    ctx = FakeContext()

    # 1. list_past_challenges query must NOT return the DRAFT challenge
    past_chs = asyncio.run(list_past_challenges())
    assert any(c["id"] == ended_id for c in past_chs)
    assert not any(c["id"] == draft_id for c in past_chs)

    # 2. /archive or /past command must not show DRAFT challenge
    up_cmd = FakeUpdate(user_id=401, text="/archive")
    asyncio.run(past_challenges_command(up_cmd, ctx))
    assert len(up_cmd.message.reply_text_calls) == 1
    kb = up_cmd.message.reply_text_calls[0]["reply_markup"]
    btn_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any(f"#{ended_id}" in t for t in btn_texts)
    assert not any("Secret Draft Challenge" in t for t in btn_texts)

    # 3. Direct callback inspect ch_past:{draft_id} by student must be blocked
    cb_draft = FakeCallbackQuery(data=f"ch_past:{draft_id}", user_id=401)
    up_cb = FakeUpdate(callback_query=cb_draft)
    asyncio.run(handle_past_challenges_callback(up_cb, ctx))
    assert cb_draft.answered is True
    assert "draft mode" in cb_draft.answered_text

    # 4. get_challenge_review_data must reject DRAFT challenges
    review_res = asyncio.run(get_challenge_review_data(draft_id, 401, 0))
    assert "error" in review_res
    assert "draft mode" in review_res["error"]

    # 5. Leaderboard callback requesting draft_id must not leak draft details to non-admin
    cb_lb = FakeCallbackQuery(data=f"lb_weekly:{draft_id}:1", user_id=401)
    up_lb = FakeUpdate(callback_query=cb_lb)
    asyncio.run(handle_leaderboard_callback(up_lb, ctx))
    assert "Secret Draft Challenge" not in cb_lb.edited_text


def test_pg_pool_prepared_statement_disabled_for_pooler(monkeypatch):
    """Verifies that the PostgreSQL connection pool explicitly disables prepared statements

    (prepare_threshold=None) to ensure full compatibility with transaction connection poolers
    (e.g. Supabase port 6543 / PgBouncer / Supavisor).
    """
    import app.db as db
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://user:pass@localhost:6543/postgres")
    monkeypatch.setattr(db, "_pg_pool", None)

    captured = {}

    class MockAsyncConnectionPool:
        def __init__(self, conninfo, min_size=2, max_size=10, open=False, kwargs=None):
            captured["conninfo"] = conninfo
            captured["kwargs"] = kwargs

        async def open(self):
            pass

    import sys
    from unittest.mock import MagicMock
    mock_module = MagicMock()
    mock_module.AsyncConnectionPool = MockAsyncConnectionPool
    monkeypatch.setitem(sys.modules, "psycopg_pool", mock_module)

    asyncio.run(db.get_pg_pool())
    assert captured.get("kwargs") == {"prepare_threshold": None}
    monkeypatch.setattr(db, "_pg_pool", None)


def test_quiz_navigation_latency_optimization_and_prefetched_state():
    """Verifies that record_answer_and_advance returns prefetched state and

    get_next_question_for_participant uses prefetched state to minimize roundtrips.
    """
    asyncio.run(db.reset_db())
    ch_id = asyncio.run(service.create_challenge(title="Fast Navigation Quiz", duration_seconds=600))
    q1 = asyncio.run(service.create_question("Q1 Text", "A", "B", "C", "D", "A"))
    q2 = asyncio.run(service.create_question("Q2 Text", "A", "B", "C", "D", "B"))
    asyncio.run(service.link_questions_to_challenge(ch_id, [q1, q2]))
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    user_id = 998877
    asyncio.run(service.register_or_get_participant(ch_id, user_id))
    asyncio.run(service.start_participant_quiz(ch_id, user_id))

    q1_data = asyncio.run(service.get_next_question_for_participant(ch_id, user_id, 0))
    assert q1_data is not None
    assert q1_data["question_number"] == 1

    # Record answer for Q1
    res = asyncio.run(service.record_answer_and_advance(ch_id, user_id, "A", 0))
    assert res["is_completed"] is False
    assert "_participant" in res
    assert "_challenge" in res
    assert "_answered_indices" in res
    assert res["_answered_indices"] == [0]
    assert res["_participant"]["current_question_index"] == 1

    # Load Q2 with prefetched arguments
    q2_data = asyncio.run(
        service.get_next_question_for_participant(
            ch_id,
            user_id,
            question_index=res["next_question_index"],
            prefetched_part=res["_participant"],
            prefetched_challenge=res["_challenge"],
            prefetched_answered_indices=res["_answered_indices"],
        )
    )
    assert q2_data is not None
    assert q2_data["question_number"] == 2
    assert q2_data["answered_indices"] == [0]


def test_challenge_completion_screen_quote_calculation_and_keyboard():
    """Verifies that the challenge completion screen shows score calculation

    in a blockquote and provides clickable action buttons for Weekly and Monthly leaderboards.
    """
    from tests.test_bot import FakeUpdate, FakeContext, FakeCallbackQuery
    from app.challenge.handlers import handle_challenge_answer_callback, handle_leaderboard_callback
    from app.challenge.keyboards import get_challenge_completion_keyboard

    asyncio.run(db.reset_db())
    ch_id = asyncio.run(service.create_challenge(title="Completion Test Quiz", duration_seconds=600))
    q1 = asyncio.run(service.create_question("Q1 text", "A", "B", "C", "D", "A"))
    asyncio.run(service.link_questions_to_challenge(ch_id, [q1]))
    asyncio.run(service.update_challenge_status(ch_id, "LIVE"))

    user_id = 776655
    asyncio.run(service.register_or_get_participant(ch_id, user_id))
    asyncio.run(service.start_participant_quiz(ch_id, user_id))
    q1_data = asyncio.run(service.get_next_question_for_participant(ch_id, user_id, 0))

    disp_key = q1_data["display_keys"][0]
    cb = FakeCallbackQuery(data=f"ch_ans:{ch_id}:0:{disp_key}", user_id=user_id)
    up = FakeUpdate(callback_query=cb)
    ctx = FakeContext()

    asyncio.run(handle_challenge_answer_callback(up, ctx))
    assert "Challenge Completed!" in cb.edited_text
    assert "<blockquote>💡 <b>Score Calculation:</b>" in cb.edited_text
    assert "Accuracy:" in cb.edited_text
    assert "Final Score:" in cb.edited_text or "Final Points:" in cb.edited_text

    # Verify buttons: Weekly & Monthly are clickable action buttons, NOT noop
    kb = cb.reply_markup
    flattened_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert f"lb_weekly:{ch_id}:1" in flattened_callbacks
    assert f"lb_monthly:{ch_id}:1" in flattened_callbacks
    assert f"ch_review:{ch_id}:0" in flattened_callbacks
    assert "noop" not in flattened_callbacks

    # Verify clicking Weekly Leaderboard from completion card opens the actual leaderboard
    cb_lb = FakeCallbackQuery(data=f"lb_weekly:{ch_id}:1", user_id=user_id)
    up_lb = FakeUpdate(callback_query=cb_lb)
    asyncio.run(handle_leaderboard_callback(up_lb, ctx))
    assert "Leaderboard" in cb_lb.edited_text
    # On the actual leaderboard, the tab switcher shows Weekly as active
    lb_kb_callbacks = [btn.callback_data for row in cb_lb.reply_markup.inline_keyboard for btn in row]
    assert "noop" in lb_kb_callbacks
    assert f"lb_monthly:{ch_id}:1" in lb_kb_callbacks
















