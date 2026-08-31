from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


class ChallengeStatus(str, Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"


class ParticipantStatus(str, Enum):
    REGISTERED = "REGISTERED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    TIMED_OUT = "TIMED_OUT"


class Difficulty(str, Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


@dataclass
class Challenge:
    id: int
    title: str
    description: str
    category: str
    starts_at: Optional[str]
    ends_at: Optional[str]
    duration_seconds: int
    question_time_limit_seconds: int
    accuracy_weight: float
    speed_weight: float
    status: ChallengeStatus
    season_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class Question:
    id: int
    question_text: str
    category: str
    difficulty: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    base_points: float
    explanation: Optional[str] = None
    is_active: bool = True
