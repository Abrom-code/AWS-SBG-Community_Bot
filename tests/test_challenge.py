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

    # Second rapid click on same question index 0 fails
    res2 = asyncio.run(service.record_answer_and_advance(ch_id, user_id, "B", 0))
    assert "error" in res2


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




