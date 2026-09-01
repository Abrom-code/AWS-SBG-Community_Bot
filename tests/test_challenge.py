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
    assert "📄 1/2" in kb1_texts
    assert "⬅️ Prev" not in kb1_texts

    kb2 = get_leaderboard_keyboard(ch_id, mode="weekly", page=2, total_pages=2)
    kb2_texts = [btn.text for row in kb2.inline_keyboard for btn in row]
    assert "⬅️ Prev" in kb2_texts
    assert "📄 2/2" in kb2_texts
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







