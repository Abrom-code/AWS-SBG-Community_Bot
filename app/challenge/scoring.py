def calculate_score(
    is_correct: bool,
    response_time_seconds: float,
    time_limit_seconds: float,
    base_points: float = 10.0,
    accuracy_weight: float = 0.70,
    speed_weight: float = 0.30,
) -> float:
    """Calculates points awarded for a question based on accuracy and server-side response time.

    Formula:
      If correct and within time limit:
        Score = base_points * (accuracy_weight + speed_weight * (1 - t / T))
      If wrong or overtime:
        Score = 0.0
    """
    if not is_correct:
        return 0.0

    if time_limit_seconds <= 0 or response_time_seconds > time_limit_seconds:
        return 0.0

    # Clamp response time to non-negative
    t = max(0.0, float(response_time_seconds))
    time_limit = float(time_limit_seconds)

    speed_fraction = max(0.0, min(1.0, 1.0 - (t / time_limit)))
    speed_multiplier = float(accuracy_weight) + (float(speed_weight) * speed_fraction)

    # Ensure speed multiplier is valid and doesn't exceed total weight
    max_multiplier = accuracy_weight + speed_weight
    speed_multiplier = min(max_multiplier, speed_multiplier)

    score = base_points * speed_multiplier
    return round(score, 2)
