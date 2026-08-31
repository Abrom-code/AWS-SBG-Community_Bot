import csv
import io
import json
import logging
import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import app.db as db
from app.challenge.scoring import calculate_score

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database Helper
# ---------------------------------------------------------------------------
async def _execute(query: str, params: tuple = (), fetch: str = "none") -> Any:
    """Executes a query against SQLite or PostgreSQL based on configuration."""
    await db.ensure_db()

    if db.is_postgres():
        import psycopg

        url = (
            db.DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if db.DATABASE_URL.startswith("postgres://")
            else db.DATABASE_URL
        )
        # Convert ? placeholders to %s for PostgreSQL
        pg_query = query.replace("?", "%s")
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(pg_query, params)
                    if fetch == "one":
                        return await cur.fetchone()
                    elif fetch == "all":
                        return await cur.fetchall()
                    elif fetch == "id":
                        return cur.lastrowid
                    await conn.commit()
        except Exception as e:
            logger.error(f"Postgres execution error on query [{pg_query}]: {e}")
            raise
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(db.SQLITE_DB_PATH) as conn:
                async with conn.execute(query, params) as cur:
                    if fetch == "one":
                        return await cur.fetchone()
                    elif fetch == "all":
                        return await cur.fetchall()
                    elif fetch == "id":
                        await conn.commit()
                        return cur.lastrowid
                    await conn.commit()
        except Exception as e:
            logger.error(f"SQLite execution error on query [{query}]: {e}")
            raise


# ---------------------------------------------------------------------------
# Seasons
# ---------------------------------------------------------------------------
async def create_season(name: str, start_date: str = None, end_date: str = None) -> int:
    """Creates a challenge season."""
    now = datetime.now(timezone.utc).isoformat()
    return await _execute(
        "INSERT INTO challenge_seasons (name, start_date, end_date, status, created_at) VALUES (?, ?, ?, 'ACTIVE', ?)",
        (name, start_date or now, end_date, now),
        fetch="id",
    )


async def get_or_create_current_season() -> int:
    """Retrieves the active season ID or creates a default monthly season."""
    row = await _execute("SELECT id FROM challenge_seasons WHERE status = 'ACTIVE' ORDER BY id DESC LIMIT 1", fetch="one")
    if row:
        return row[0]
    season_name = datetime.now(timezone.utc).strftime("%B %Y Season")
    return await create_season(season_name)


# ---------------------------------------------------------------------------
# Challenges
# ---------------------------------------------------------------------------
async def create_challenge(
    title: str,
    description: str = "",
    category: str = "General",
    question_time_limit_seconds: int = 60,
    duration_seconds: int = 3600,
    accuracy_weight: float = 0.70,
    speed_weight: float = 0.30,
    starts_at: str = None,
    ends_at: str = None,
    season_id: int = None,
    created_by: int = None,
) -> int:
    """Creates a new challenge in DRAFT status."""
    now = datetime.now(timezone.utc).isoformat()
    s_id = season_id or await get_or_create_current_season()
    return await _execute(
        """
        INSERT INTO challenges (
            season_id, title, description, category, starts_at, ends_at,
            duration_seconds, question_time_limit_seconds, accuracy_weight, speed_weight,
            status, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?)
        """,
        (
            s_id,
            title,
            description,
            category,
            starts_at or now,
            ends_at,
            duration_seconds,
            question_time_limit_seconds,
            accuracy_weight,
            speed_weight,
            created_by,
            now,
        ),
        fetch="id",
    )


async def get_challenge(challenge_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single challenge by ID."""
    row = await _execute(
        """
        SELECT id, season_id, title, description, category, starts_at, ends_at,
               duration_seconds, question_time_limit_seconds, accuracy_weight, speed_weight,
               status, created_by, created_at
        FROM challenges WHERE id = ?
        """,
        (challenge_id,),
        fetch="one",
    )
    if not row:
        return None
    return {
        "id": row[0],
        "season_id": row[1],
        "title": row[2],
        "description": row[3],
        "category": row[4],
        "starts_at": row[5],
        "ends_at": row[6],
        "duration_seconds": row[7],
        "question_time_limit_seconds": row[8],
        "accuracy_weight": float(row[9]),
        "speed_weight": float(row[10]),
        "status": row[11],
        "created_by": row[12],
        "created_at": row[13],
    }


async def get_active_challenge() -> Optional[Dict[str, Any]]:
    """Retrieves the latest LIVE challenge, or next SCHEDULED challenge, with time-based transitions."""
    now_dt = datetime.now(timezone.utc)

    # 1. Transition SCHEDULED challenges to LIVE if start time has arrived
    scheduled = await _execute(
        "SELECT id, starts_at FROM challenges WHERE status = 'SCHEDULED'",
        fetch="all",
    )
    for ch in scheduled:
        if ch[1]:
            try:
                s_dt = datetime.fromisoformat(str(ch[1]).replace("Z", "+00:00"))
                if now_dt >= s_dt:
                    await _execute("UPDATE challenges SET status = 'LIVE' WHERE id = ?", (ch[0],))
            except Exception:
                pass

    # 2. Transition LIVE challenges to ENDED if end time has passed
    live = await _execute(
        "SELECT id, ends_at FROM challenges WHERE status = 'LIVE'",
        fetch="all",
    )
    for ch in live:
        if ch[1]:
            try:
                e_dt = datetime.fromisoformat(str(ch[1]).replace("Z", "+00:00"))
                if now_dt >= e_dt:
                    await _execute("UPDATE challenges SET status = 'ENDED' WHERE id = ?", (ch[0],))
            except Exception:
                pass

    row = await _execute(
        """
        SELECT id, season_id, title, description, category, starts_at, ends_at,
               duration_seconds, question_time_limit_seconds, accuracy_weight, speed_weight,
               status, created_by, created_at
        FROM challenges WHERE status IN ('LIVE', 'SCHEDULED')
        ORDER BY CASE WHEN status = 'LIVE' THEN 1 ELSE 2 END, id DESC LIMIT 1
        """,
        fetch="one",
    )
    if not row:
        return None
    return {
        "id": row[0],
        "season_id": row[1],
        "title": row[2],
        "description": row[3],
        "category": row[4],
        "starts_at": row[5],
        "ends_at": row[6],
        "duration_seconds": row[7],
        "question_time_limit_seconds": row[8],
        "accuracy_weight": float(row[9]),
        "speed_weight": float(row[10]),
        "status": row[11],
        "created_by": row[12],
        "created_at": row[13],
    }


async def list_past_challenges(limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves all past or available challenges for leaderboard review and practice questions."""
    rows = await _execute(
        """
        SELECT id, season_id, title, description, category, starts_at, ends_at,
               question_time_limit_seconds, status
        FROM challenges
        WHERE status IN ('ENDED', 'LIVE')
        ORDER BY id DESC LIMIT ?
        """,
        (limit,),
        fetch="all",
    )
    results = []
    for r in rows:
        results.append({
            "id": r[0],
            "season_id": r[1],
            "title": r[2],
            "description": r[3],
            "category": r[4],
            "starts_at": r[5],
            "ends_at": r[6],
            "question_time_limit_seconds": r[7],
            "status": r[8],
        })
    return results


async def list_challenges(status: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Lists challenges optionally filtered by status."""
    if status:
        rows = await _execute(
            """
            SELECT id, season_id, title, category, status, starts_at, ends_at, question_time_limit_seconds
            FROM challenges WHERE status = ? ORDER BY id DESC LIMIT ?
            """,
            (status, limit),
            fetch="all",
        )
    else:
        rows = await _execute(
            """
            SELECT id, season_id, title, category, status, starts_at, ends_at, question_time_limit_seconds
            FROM challenges ORDER BY id DESC LIMIT ?
            """,
            (limit,),
            fetch="all",
        )

    return [
        {
            "id": r[0],
            "season_id": r[1],
            "title": r[2],
            "category": r[3],
            "status": r[4],
            "starts_at": r[5],
            "ends_at": r[6],
            "question_time_limit_seconds": r[7],
        }
        for r in rows
    ]


async def update_challenge_status(challenge_id: int, new_status: str) -> None:
    """Updates challenge lifecycle state."""
    await _execute("UPDATE challenges SET status = ? WHERE id = ?", (new_status, challenge_id))


async def delete_challenge(challenge_id: int) -> bool:
    """Permanently deletes a challenge and its associated answers, participants, and linked questions."""
    await _execute("DELETE FROM challenge_answers WHERE challenge_id = ?", (challenge_id,))
    await _execute("DELETE FROM challenge_participants WHERE challenge_id = ?", (challenge_id,))
    await _execute("DELETE FROM challenge_questions WHERE challenge_id = ?", (challenge_id,))
    await _execute("DELETE FROM challenges WHERE id = ?", (challenge_id,))
    return True


async def update_challenge_details(
    challenge_id: int,
    title: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    question_time_limit_seconds: Optional[int] = None,
    starts_at: Optional[str] = None,
    ends_at: Optional[str] = None,
) -> bool:
    """Updates editable fields of a challenge."""
    fields = []
    values = []
    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if category is not None:
        fields.append("category = ?")
        values.append(category)
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if question_time_limit_seconds is not None:
        fields.append("question_time_limit_seconds = ?")
        values.append(question_time_limit_seconds)
    if starts_at is not None:
        fields.append("starts_at = ?")
        values.append(starts_at)
    if ends_at is not None:
        fields.append("ends_at = ?")
        values.append(ends_at)

    if not fields:
        return False

    values.append(challenge_id)
    query = f"UPDATE challenges SET {', '.join(fields)} WHERE id = ?"
    await _execute(query, tuple(values))
    return True


# ---------------------------------------------------------------------------
# Questions & Question Bank
# ---------------------------------------------------------------------------
async def create_question(
    question_text: str,
    option_a: str,
    option_b: str,
    option_c: str,
    option_d: str,
    correct_option: str,
    category: str = "General",
    difficulty: str = "MEDIUM",
    base_points: float = 10.0,
    explanation: str = "",
) -> int:
    """Creates a question in the question bank."""
    now = datetime.now(timezone.utc).isoformat()
    return await _execute(
        """
        INSERT INTO questions (
            question_text, category, difficulty, option_a, option_b, option_c, option_d,
            correct_option, base_points, explanation, is_active, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            question_text.strip(),
            category.strip(),
            difficulty.upper().strip(),
            option_a.strip(),
            option_b.strip(),
            option_c.strip(),
            option_d.strip(),
            correct_option.upper().strip(),
            base_points,
            explanation.strip() if explanation else "",
            now,
        ),
        fetch="id",
    )


async def import_questions_from_csv(csv_text: str) -> Dict[str, Any]:
    """Parses a CSV string and inserts questions into the question bank.

    Expected CSV columns:
    question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation
    """
    imported = 0
    errors = []
    f = io.StringIO(csv_text.strip())
    reader = csv.DictReader(f)

    for line_num, row in enumerate(reader, start=2):
        try:
            # Normalize column keys
            normalized = {k.strip().lower(): v for k, v in row.items() if k}
            q_text = normalized.get("question") or normalized.get("question_text")
            opt_a = normalized.get("option_a") or normalized.get("a")
            opt_b = normalized.get("option_b") or normalized.get("b")
            opt_c = normalized.get("option_c") or normalized.get("c")
            opt_d = normalized.get("option_d") or normalized.get("d")
            correct = normalized.get("correct") or normalized.get("correct_option") or normalized.get("answer")

            if not all([q_text, opt_a, opt_b, opt_c, opt_d, correct]):
                errors.append(f"Row {line_num}: Missing required question or option fields")
                continue

            correct_clean = correct.strip().upper()
            if correct_clean not in ("A", "B", "C", "D"):
                errors.append(f"Row {line_num}: Invalid correct option '{correct}' (must be A, B, C, or D)")
                continue

            diff = (normalized.get("difficulty") or "MEDIUM").strip().upper()
            cat = (normalized.get("category") or "General").strip()
            pts = float(normalized.get("points") or normalized.get("base_points") or 10.0)
            exp = (normalized.get("explanation") or "").strip()

            await create_question(
                question_text=q_text,
                option_a=opt_a,
                option_b=opt_b,
                option_c=opt_c,
                option_d=opt_d,
                correct_option=correct_clean,
                category=cat,
                difficulty=diff,
                base_points=pts,
                explanation=exp,
            )
            imported += 1
        except Exception as e:
            errors.append(f"Row {line_num}: {str(e)}")

    return {"imported": imported, "errors": errors}


async def list_questions(category: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves questions from the question bank."""
    if category:
        rows = await _execute(
            """
            SELECT id, question_text, category, difficulty, option_a, option_b, option_c, option_d,
                   correct_option, base_points, explanation
            FROM questions WHERE is_active = 1 AND category = ? ORDER BY id DESC LIMIT ?
            """,
            (category, limit),
            fetch="all",
        )
    else:
        rows = await _execute(
            """
            SELECT id, question_text, category, difficulty, option_a, option_b, option_c, option_d,
                   correct_option, base_points, explanation
            FROM questions WHERE is_active = 1 ORDER BY id DESC LIMIT ?
            """,
            (limit,),
            fetch="all",
        )

    return [
        {
            "id": r[0],
            "question_text": r[1],
            "category": r[2],
            "difficulty": r[3],
            "option_a": r[4],
            "option_b": r[5],
            "option_c": r[6],
            "option_d": r[7],
            "correct_option": r[8],
            "base_points": float(r[9]),
            "explanation": r[10],
        }
        for r in rows
    ]


async def link_questions_to_challenge(
    challenge_id: int, question_ids: Optional[List[int]] = None, count: Optional[int] = None
) -> int:
    """Links questions to a challenge and creates an immutable snapshot."""
    if not question_ids:
        all_q = await list_questions(limit=count or 50)
        q_ids = [q["id"] for q in all_q]
    else:
        q_ids = question_ids

    linked = 0
    for idx, q_id in enumerate(q_ids):
        # Fetch question details for immutable snapshot
        q_row = await _execute(
            """
            SELECT id, question_text, category, difficulty, option_a, option_b, option_c, option_d,
                   correct_option, base_points, explanation
            FROM questions WHERE id = ?
            """,
            (q_id,),
            fetch="one",
        )
        if q_row:
            snapshot = {
                "id": q_row[0],
                "question_text": q_row[1],
                "category": q_row[2],
                "difficulty": q_row[3],
                "option_a": q_row[4],
                "option_b": q_row[5],
                "option_c": q_row[6],
                "option_d": q_row[7],
                "correct_option": q_row[8],
                "base_points": float(q_row[9]),
                "explanation": q_row[10],
            }
            await _execute(
                """
                INSERT INTO challenge_questions (challenge_id, question_id, question_order, snapshot_json)
                VALUES (?, ?, ?, ?)
                """,
                (challenge_id, q_id, idx, json.dumps(snapshot)),
            )
            linked += 1

    return linked


async def get_challenge_questions(challenge_id: int) -> List[Dict[str, Any]]:
    """Retrieves all snapshot questions for a challenge."""
    rows = await _execute(
        "SELECT question_id, snapshot_json FROM challenge_questions WHERE challenge_id = ? ORDER BY question_order ASC",
        (challenge_id,),
        fetch="all",
    )
    questions = []
    for r in rows:
        if r[1]:
            questions.append(json.loads(r[1]))
        else:
            # Fallback to live question
            q = await _execute("SELECT * FROM questions WHERE id = ?", (r[0],), fetch="one")
            if q:
                questions.append({
                    "id": q[0], "question_text": q[1], "category": q[2], "difficulty": q[3],
                    "option_a": q[4], "option_b": q[5], "option_c": q[6], "option_d": q[7],
                    "correct_option": q[8], "base_points": float(q[9]), "explanation": q[10]
                })
    return questions


import math


# ---------------------------------------------------------------------------
# Participant Lifecycle & Quiz Progression
# ---------------------------------------------------------------------------
async def register_or_get_participant(
    challenge_id: int, telegram_user_id: int, user_name: str = "", username: str = ""
) -> Dict[str, Any]:
    """Registers a participant or retrieves existing registration with username tracking."""
    row = await _execute(
        """
        SELECT id, challenge_id, telegram_user_id, user_name, started_at, completed_at,
               current_question_index, question_order_json, current_option_order_json,
               score, correct_count, answered_count, status, is_locked, current_question_sent_at, username
        FROM challenge_participants
        WHERE challenge_id = ? AND telegram_user_id = ?
        """,
        (challenge_id, telegram_user_id),
        fetch="one",
    )
    if row:
        current_un = row[15] if len(row) > 15 and row[15] else ""
        current_name = row[3] or ""
        # Keep username / name updated if provided
        if (username and username != current_un) or (user_name and user_name != current_name):
            await _execute(
                "UPDATE challenge_participants SET user_name = ?, username = ? WHERE id = ?",
                (user_name or current_name, username or current_un, row[0]),
            )

        return {
            "id": row[0],
            "challenge_id": row[1],
            "telegram_user_id": row[2],
            "user_name": user_name or current_name,
            "username": username or current_un,
            "started_at": row[4],
            "completed_at": row[5],
            "current_question_index": row[6],
            "question_order": json.loads(row[7]) if row[7] else [],
            "current_option_order": json.loads(row[8]) if row[8] else {},
            "score": float(row[9]),
            "correct_count": row[10],
            "answered_count": row[11],
            "status": row[12],
            "is_locked": row[13],
            "current_question_sent_at": row[14],
        }

    # Fetch challenge questions and randomize order for this participant
    questions = await get_challenge_questions(challenge_id)
    q_ids = [q["id"] for q in questions]
    random.shuffle(q_ids)

    now = datetime.now(timezone.utc).isoformat()
    part_id = await _execute(
        """
        INSERT INTO challenge_participants (
            challenge_id, telegram_user_id, user_name, username, current_question_index,
            question_order_json, score, correct_count, answered_count, status, is_locked
        ) VALUES (?, ?, ?, ?, 0, ?, 0.0, 0, 0, 'REGISTERED', 0)
        """,
        (challenge_id, telegram_user_id, user_name, username or "", json.dumps(q_ids)),
        fetch="id",
    )

    return {
        "id": part_id,
        "challenge_id": challenge_id,
        "telegram_user_id": telegram_user_id,
        "user_name": user_name,
        "username": username or "",
        "started_at": None,
        "completed_at": None,
        "current_question_index": 0,
        "question_order": q_ids,
        "current_option_order": {},
        "score": 0.0,
        "correct_count": 0,
        "answered_count": 0,
        "status": "REGISTERED",
        "is_locked": 0,
        "current_question_sent_at": None,
    }


async def start_participant_quiz(challenge_id: int, telegram_user_id: int) -> None:
    """Marks a participant as IN_PROGRESS and records started_at timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    await _execute(
        "UPDATE challenge_participants SET status = 'IN_PROGRESS', started_at = ? WHERE challenge_id = ? AND telegram_user_id = ?",
        (now, challenge_id, telegram_user_id),
    )


async def get_next_question_for_participant(
    challenge_id: int, telegram_user_id: int
) -> Optional[Dict[str, Any]]:
    """Prepares the next question for a participant with randomized option mapping."""
    part = await register_or_get_participant(challenge_id, telegram_user_id)
    if part["status"] not in ("REGISTERED", "IN_PROGRESS"):
        return None

    q_order = part["question_order"]
    idx = part["current_question_index"]
    if idx >= len(q_order):
        return None

    target_q_id = q_order[idx]
    all_questions = await get_challenge_questions(challenge_id)
    question = next((q for q in all_questions if q["id"] == target_q_id), None)
    if not question:
        return None

    # Map raw options to randomized display keys A, B, C, D
    raw_options = [
        ("A", question["option_a"]),
        ("B", question["option_b"]),
        ("C", question["option_c"]),
        ("D", question["option_d"]),
    ]
    correct_canonical = question["correct_option"]

    # Shuffle the options
    shuffled_options = list(raw_options)
    random.shuffle(shuffled_options)

    # Assign to display keys A, B, C, D
    display_keys = ["A", "B", "C", "D"]
    mapping = {}
    display_correct = "A"

    for d_key, (orig_key, text) in zip(display_keys, shuffled_options):
        mapping[d_key] = text
        if orig_key == correct_canonical:
            display_correct = d_key

    mapping["_canonical_correct"] = correct_canonical
    mapping["_display_correct"] = display_correct
    mapping["_question_id"] = target_q_id
    mapping["_base_points"] = question["base_points"]

    now = datetime.now(timezone.utc).isoformat()
    # Save option order & sent_at timestamp, unlock participant
    await _execute(
        """
        UPDATE challenge_participants
        SET current_option_order_json = ?, current_question_sent_at = ?, is_locked = 0
        WHERE id = ?
        """,
        (json.dumps(mapping), now, part["id"]),
    )

    return {
        "question_number": idx + 1,
        "total_questions": len(q_order),
        "question_id": target_q_id,
        "question_text": question["question_text"],
        "category": question["category"],
        "difficulty": question["difficulty"],
        "options": {k: mapping[k] for k in ["A", "B", "C", "D"]},
        "base_points": question["base_points"],
        "display_keys": display_keys,
    }


async def record_answer_and_advance(
    challenge_id: int,
    telegram_user_id: int,
    selected_option_key: str,
    question_index: int,
) -> Dict[str, Any]:
    """Validates and scores an answer, preventing double-clicks and recording detailed audit logs."""
    part = await register_or_get_participant(challenge_id, telegram_user_id)
    if part["status"] != "IN_PROGRESS":
        return {"error": "Challenge is not active or already completed."}

    # Anti-cheat & out-of-order check
    if part["current_question_index"] != question_index:
        return {"error": "Question has already been answered or is out of order."}

    # Double-click lock check
    if part["is_locked"]:
        return {"error": "Answer is already being processed."}

    # Immediately engage atomic lock
    await _execute("UPDATE challenge_participants SET is_locked = 1 WHERE id = ?", (part["id"],))

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Calculate server-measured response time
    sent_at_str = part["current_question_sent_at"]
    if sent_at_str:
        sent_at = datetime.fromisoformat(sent_at_str.replace("Z", "+00:00"))
        # Ensure timezone compatibility
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        response_time_seconds = max(0.0, (now - sent_at).total_seconds())
    else:
        response_time_seconds = 0.0

    response_time_ms = int(response_time_seconds * 1000)

    # Fetch challenge config
    challenge = await get_challenge(challenge_id)
    time_limit = challenge["question_time_limit_seconds"] if challenge else 60
    acc_weight = challenge["accuracy_weight"] if challenge else 0.70
    spd_weight = challenge["speed_weight"] if challenge else 0.30

    # Retrieve randomized options mapping
    mapping = part["current_option_order"]
    display_correct = mapping.get("_display_correct", "A")
    canonical_correct = mapping.get("_canonical_correct", "A")
    question_id = mapping.get("_question_id", 0)
    base_points = float(mapping.get("_base_points", 10.0))

    is_correct = (selected_option_key.upper() == display_correct.upper())

    points_awarded = calculate_score(
        is_correct=is_correct,
        response_time_seconds=response_time_seconds,
        time_limit_seconds=time_limit,
        base_points=base_points,
        accuracy_weight=acc_weight,
        speed_weight=spd_weight,
    )

    speed_fraction = max(0.0, min(1.0, 1.0 - (response_time_seconds / time_limit))) if time_limit > 0 else 0.0
    speed_multiplier = round(acc_weight + (spd_weight * speed_fraction), 3) if is_correct else 0.0

    # Insert detailed answer audit log
    await _execute(
        """
        INSERT INTO challenge_answers (
            participant_id, challenge_id, question_id, question_position,
            selected_option, correct_option, is_correct, question_sent_at,
            answered_at, response_time_ms, base_points, speed_multiplier,
            points_awarded, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            part["id"],
            challenge_id,
            question_id,
            question_index + 1,
            selected_option_key.upper(),
            canonical_correct,
            1 if is_correct else 0,
            sent_at_str,
            now_iso,
            response_time_ms,
            base_points,
            speed_multiplier,
            points_awarded,
            now_iso,
        ),
    )

    # Advance participant state
    new_index = question_index + 1
    new_score = round(part["score"] + points_awarded, 2)
    new_correct = part["correct_count"] + (1 if is_correct else 0)
    new_answered = part["answered_count"] + 1
    total_q = len(part["question_order"])
    is_completed = new_index >= total_q

    if is_completed:
        await _execute(
            """
            UPDATE challenge_participants
            SET current_question_index = ?, score = ?, correct_count = ?,
                answered_count = ?, status = 'COMPLETED', completed_at = ?, is_locked = 0
            WHERE id = ?
            """,
            (new_index, new_score, new_correct, new_answered, now_iso, part["id"]),
        )
    else:
        await _execute(
            """
            UPDATE challenge_participants
            SET current_question_index = ?, score = ?, correct_count = ?,
                answered_count = ?, is_locked = 0
            WHERE id = ?
            """,
            (new_index, new_score, new_correct, new_answered, part["id"]),
        )

    return {
        "is_correct": is_correct,
        "points_awarded": points_awarded,
        "response_time_seconds": round(response_time_seconds, 1),
        "response_time_ms": response_time_ms,
        "current_score": new_score,
        "correct_count": new_correct,
        "answered_count": new_answered,
        "total_questions": total_q,
        "is_completed": is_completed,
    }


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------
async def get_weekly_leaderboard(
    challenge_id: int, limit: int = 10, page: int = 1
) -> Dict[str, Any]:
    """Computes the paginated leaderboard for a specific challenge."""
    page = max(1, page)
    offset = (page - 1) * limit

    cnt_row = await _execute(
        "SELECT COUNT(*) FROM challenge_participants WHERE challenge_id = ? AND status = 'COMPLETED'",
        (challenge_id,),
        fetch="one",
    )
    total_count = cnt_row[0] if cnt_row else 0
    total_pages = max(1, math.ceil(total_count / limit)) if total_count > 0 else 1

    rows = await _execute(
        """
        SELECT telegram_user_id, user_name, username, score, correct_count, answered_count, started_at, completed_at
        FROM challenge_participants
        WHERE challenge_id = ? AND status = 'COMPLETED'
        ORDER BY score DESC, completed_at ASC
        LIMIT ? OFFSET ?
        """,
        (challenge_id, limit, offset),
        fetch="all",
    )
    leaderboard = []
    for idx, r in enumerate(rows):
        rank = offset + idx + 1
        leaderboard.append({
            "rank": rank,
            "telegram_user_id": r[0],
            "user_name": r[1] or f"Builder #{rank}",
            "username": r[2] or "",
            "score": float(r[3]),
            "correct_count": r[4],
            "answered_count": r[5],
        })
    return {
        "entries": leaderboard,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


async def get_monthly_leaderboard(
    season_id: Optional[int] = None, limit: int = 10, page: int = 1
) -> Dict[str, Any]:
    """Aggregates paginated cumulative scores across all completed challenges in the season."""
    s_id = season_id or await get_or_create_current_season()
    page = max(1, page)
    offset = (page - 1) * limit

    cnt_row = await _execute(
        """
        SELECT COUNT(DISTINCT cp.telegram_user_id)
        FROM challenge_participants cp
        JOIN challenges c ON cp.challenge_id = c.id
        WHERE c.season_id = ? AND cp.status = 'COMPLETED'
        """,
        (s_id,),
        fetch="one",
    )
    total_count = cnt_row[0] if cnt_row else 0
    total_pages = max(1, math.ceil(total_count / limit)) if total_count > 0 else 1

    rows = await _execute(
        """
        SELECT cp.telegram_user_id, cp.user_name, MAX(cp.username) as username, SUM(cp.score) as total_score,
               SUM(cp.correct_count) as total_correct, COUNT(cp.id) as challenges_completed
        FROM challenge_participants cp
        JOIN challenges c ON cp.challenge_id = c.id
        WHERE c.season_id = ? AND cp.status = 'COMPLETED'
        GROUP BY cp.telegram_user_id, cp.user_name
        ORDER BY total_score DESC
        LIMIT ? OFFSET ?
        """,
        (s_id, limit, offset),
        fetch="all",
    )
    leaderboard = []
    for idx, r in enumerate(rows):
        rank = offset + idx + 1
        leaderboard.append({
            "rank": rank,
            "telegram_user_id": r[0],
            "user_name": r[1] or f"Champion #{rank}",
            "username": r[2] or "",
            "total_score": round(float(r[3]), 2),
            "total_correct": int(r[4]),
            "challenges_completed": int(r[5]),
        })
    return {
        "entries": leaderboard,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


async def get_monthly_analytics_report(season_id: Optional[int] = None) -> Dict[str, Any]:
    """Compiles an executive monthly report covering engagement, challenges, accuracy, and champions."""
    now = datetime.now(timezone.utc)
    month_name = now.strftime("%B %Y")

    # 1. User engagement
    users_row = await _execute("SELECT COUNT(*) FROM bot_users", fetch="one")
    total_users = users_row[0] if users_row else 0

    # 2. Challenge statistics
    ch_row = await _execute("SELECT COUNT(*) FROM challenges", fetch="one")
    total_challenges = ch_row[0] if ch_row else 0

    part_row = await _execute(
        """
        SELECT COUNT(*), COALESCE(SUM(score), 0), COALESCE(AVG(score), 0),
               COALESCE(SUM(correct_count), 0), COALESCE(SUM(answered_count), 0)
        FROM challenge_participants
        WHERE status = 'COMPLETED'
        """,
        fetch="one",
    )
    total_attempts = part_row[0] if part_row else 0
    total_score = round(float(part_row[1]), 1) if part_row else 0.0
    avg_score = round(float(part_row[2]), 1) if part_row else 0.0
    total_correct = part_row[3] if part_row else 0
    total_answered = part_row[4] if part_row else 0
    accuracy_pct = round((total_correct / total_answered * 100), 1) if total_answered > 0 else 0.0

    # 3. Community Feedback & Support
    fb_row = await _execute("SELECT COUNT(*) FROM feedback_submissions", fetch="one")
    feedback_count = fb_row[0] if fb_row else 0

    reply_row = await _execute("SELECT COUNT(*) FROM admin_reply_mappings", fetch="one")
    reply_count = reply_row[0] if reply_row else 0

    # 4. Question Bank
    q_row = await _execute("SELECT COUNT(*) FROM questions WHERE is_active = 1 OR is_active = TRUE", fetch="one")
    question_count = q_row[0] if q_row else 0

    # 5. Top Champions
    monthly_lb = await get_monthly_leaderboard(season_id=season_id, limit=3)
    champions = monthly_lb.get("entries", [])

    return {
        "month_name": month_name,
        "total_users": total_users,
        "total_challenges": total_challenges,
        "total_attempts": total_attempts,
        "total_score": total_score,
        "avg_score": avg_score,
        "total_correct": total_correct,
        "total_answered": total_answered,
        "accuracy_pct": accuracy_pct,
        "feedback_count": feedback_count,
        "reply_count": reply_count,
        "question_count": question_count,
        "champions": champions,
    }
