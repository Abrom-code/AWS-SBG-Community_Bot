def calculate_exam_score(
    raw_points_earned: float,
    total_time_taken_seconds: float,
    total_time_limit_seconds: float,
    accuracy_weight: float = 0.70,
    speed_weight: float = 0.30,
) -> float:
    """Calculates overall test score combining accuracy and total test completion speed.

    Formula:
      Speed Fraction = max(0.0, min(1.0, 1.0 - (total_time / total_limit)))
      Speed Multiplier = accuracy_weight + (speed_weight * Speed Fraction)
      Final Score = raw_points_earned * Speed Multiplier
    """
    if raw_points_earned <= 0:
        return 0.0

    if total_time_limit_seconds <= 0:
        return round(raw_points_earned, 2)

    t = max(0.0, float(total_time_taken_seconds))
    time_limit = float(total_time_limit_seconds)

    speed_fraction = max(0.0, min(1.0, 1.0 - (t / time_limit)))
    speed_multiplier = float(accuracy_weight) + (float(speed_weight) * speed_fraction)

    max_multiplier = accuracy_weight + speed_weight
    speed_multiplier = min(max_multiplier, speed_multiplier)

    return round(raw_points_earned * speed_multiplier, 2)


def calculate_score(
    is_correct: bool,
    response_time_seconds: float,
    time_limit_seconds: float,
    base_points: float = 10.0,
    accuracy_weight: float = 0.70,
    speed_weight: float = 0.30,
) -> float:
    """Calculates points awarded based on accuracy and speed."""
    if not is_correct:
        return 0.0

    if time_limit_seconds <= 0 or response_time_seconds > time_limit_seconds:
        return 0.0

    t = max(0.0, float(response_time_seconds))
    time_limit = float(time_limit_seconds)

    speed_fraction = max(0.0, min(1.0, 1.0 - (t / time_limit)))
    speed_multiplier = float(accuracy_weight) + (float(speed_weight) * speed_fraction)

    max_multiplier = accuracy_weight + speed_weight
    speed_multiplier = min(max_multiplier, speed_multiplier)

    score = base_points * speed_multiplier
    return round(score, 2)

