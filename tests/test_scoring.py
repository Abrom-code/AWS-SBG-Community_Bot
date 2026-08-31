import pytest
from app.challenge.scoring import calculate_score


def test_scoring_correct_immediate_answer():
    # 0 seconds response time at base_points=10 -> full points (10.0)
    score = calculate_score(
        is_correct=True,
        response_time_seconds=0.0,
        time_limit_seconds=60.0,
        base_points=10.0,
        accuracy_weight=0.70,
        speed_weight=0.30,
    )
    assert score == 10.0


def test_scoring_correct_half_time():
    # 30 seconds out of 60 -> speed fraction = 0.5 -> multiplier = 0.70 + 0.30*0.5 = 0.85 -> 8.5 points
    score = calculate_score(
        is_correct=True,
        response_time_seconds=30.0,
        time_limit_seconds=60.0,
        base_points=10.0,
        accuracy_weight=0.70,
        speed_weight=0.30,
    )
    assert score == 8.5


def test_scoring_correct_full_time():
    # 60 seconds out of 60 -> speed fraction = 0.0 -> multiplier = 0.70 -> 7.0 points
    score = calculate_score(
        is_correct=True,
        response_time_seconds=60.0,
        time_limit_seconds=60.0,
        base_points=10.0,
        accuracy_weight=0.70,
        speed_weight=0.30,
    )
    assert score == 7.0


def test_scoring_correct_overtime_gives_zero():
    # 60.1 seconds out of 60 -> 0.0 points
    score = calculate_score(
        is_correct=True,
        response_time_seconds=60.1,
        time_limit_seconds=60.0,
        base_points=10.0,
    )
    assert score == 0.0


def test_scoring_wrong_answer_gives_zero():
    # Wrong answer fast -> 0.0 points
    score = calculate_score(
        is_correct=False,
        response_time_seconds=2.0,
        time_limit_seconds=60.0,
        base_points=10.0,
    )
    assert score == 0.0


def test_scoring_custom_weights_and_base_points():
    # Base points 20, 80% accuracy / 20% speed, 15s out of 60s (75% speed fraction)
    # multiplier = 0.80 + 0.20 * 0.75 = 0.95 -> 20 * 0.95 = 19.0
    score = calculate_score(
        is_correct=True,
        response_time_seconds=15.0,
        time_limit_seconds=60.0,
        base_points=20.0,
        accuracy_weight=0.80,
        speed_weight=0.20,
    )
    assert score == 19.0
