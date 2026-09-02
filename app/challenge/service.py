import asyncio
import csv
import io
import json
import logging
import math
import random
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import app.db as db
from app.challenge.scoring import calculate_score, calculate_exam_score

logger = logging.getLogger(__name__)

BOT_TIMEZONE_OFFSET_HOURS = int(os.getenv("BOT_TIMEZONE_OFFSET_HOURS", "3"))
BOT_TIMEZONE_NAME = os.getenv("BOT_TIMEZONE_NAME", "EAT")
LOCAL_TZ = timezone(timedelta(hours=BOT_TIMEZONE_OFFSET_HOURS))

# In-memory caching for challenge metadata and questions during active quizzes
_challenge_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
_challenge_questions_cache: Dict[int, Tuple[float, List[Dict[str, Any]]]] = {}
CACHE_TTL_SECONDS = 30.0

# In-memory concurrency locks per (challenge_id, user_id) to eliminate remote DB lock roundtrips
_user_quiz_locks: Dict[Tuple[int, int], asyncio.Lock] = {}


def _get_user_quiz_lock(challenge_id: int, user_id: int) -> asyncio.Lock:
    key = (challenge_id, user_id)
    lock = _user_quiz_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _user_quiz_locks[key] = lock
    return lock


def invalidate_challenge_cache(challenge_id: int) -> None:
    """Invalidates the in-memory cache for a challenge and its questions."""
    _challenge_cache.pop(challenge_id, None)
    _challenge_questions_cache.pop(challenge_id, None)



def parse_single_question_text(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Flexible parser that converts human-formatted question text or CSV into structured question data.

    Supports:
    - Standard multiline (Question, A/B/C/D, Answer, Category, Difficulty, Explanation)
    - Option prefixes: A:, A., A), Option A:, 1., 1), - A:, * A:, • A., etc.
    - Markdown codeblock wrapping (``` ... ```)
    - Answer prefixes: Answer: B, Correct: B, Ans: B, Answer: 2, etc.
    - Positional single-line and multiline CSV
    """
    text = raw_text.strip()
    if not text:
        return None

    # Remove markdown code block fences if present
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if text.lower().startswith("csv") or text.lower().startswith("text"):
            text = text.split("\n", 1)[1].strip()

    # 1. Try single-line CSV parse if commas are present and text is short
    if "," in text and text.count("\n") < 2:
        try:
            reader = csv.reader(io.StringIO(text))
            row = next(reader, None)
            if row and len(row) >= 5:
                correct = row[5].strip().upper() if len(row) > 5 else "A"
                if correct not in ("A", "B", "C", "D"):
                    num_map = {"1": "A", "2": "B", "3": "C", "4": "D"}
                    correct = num_map.get(correct, "A")
                return {
                    "question_text": row[0].strip(),
                    "option_a": row[1].strip(),
                    "option_b": row[2].strip(),
                    "option_c": row[3].strip() if len(row) > 3 else "N/A",
                    "option_d": row[4].strip() if len(row) > 4 else "N/A",
                    "correct_option": correct,
                    "difficulty": row[6].strip().upper() if len(row) > 6 and row[6].strip().upper() in ("EASY", "MEDIUM", "HARD") else "MEDIUM",
                    "category": row[7].strip() if len(row) > 7 and row[7].strip() else "General",
                    "base_points": float(row[8].strip()) if len(row) > 8 and row[8].strip().replace(".", "", 1).isdigit() else 10.0,
                    "explanation": row[9].strip() if len(row) > 9 else "",
                }
        except Exception:
            pass

    # 2. Parse multiline format
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    q_text = ""
    opt_a, opt_b, opt_c, opt_d = "", "", "", ""
    answer = ""
    category = "General"
    difficulty = "MEDIUM"
    explanation = ""

    for line in lines:
        # Strip leading bullet points, markdown quotes, or hashtags
        clean_line = re.sub(r"^[\*\-\•\>\#\s]+", "", line).strip()
        if not clean_line or clean_line.startswith("```"):
            continue

        # Check Option A / 1
        m_a = re.match(r"^(?:option\s+)?(?:a|1)[\.\:\)\-\s]\s*(.*)$", clean_line, re.IGNORECASE)
        # Check Option B / 2
        m_b = re.match(r"^(?:option\s+)?(?:b|2)[\.\:\)\-\s]\s*(.*)$", clean_line, re.IGNORECASE)
        # Check Option C / 3
        m_c = re.match(r"^(?:option\s+)?(?:c|3)[\.\:\)\-\s]\s*(.*)$", clean_line, re.IGNORECASE)
        # Check Option D / 4
        m_d = re.match(r"^(?:option\s+)?(?:d|4)[\.\:\)\-\s]\s*(.*)$", clean_line, re.IGNORECASE)

        m_ans = re.match(r"^(?:answer|correct(?:\s*option)?|ans)[\.\:\-\s]?\s*(.*)$", clean_line, re.IGNORECASE)
        m_cat = re.match(r"^(?:category|cat)[\.\:\-\s]?\s*(.*)$", clean_line, re.IGNORECASE)
        m_diff = re.match(r"^(?:difficulty|diff)[\.\:\-\s]?\s*(.*)$", clean_line, re.IGNORECASE)
        m_exp = re.match(r"^(?:explanation|exp|reason)[\.\:\-\s]?\s*(.*)$", clean_line, re.IGNORECASE)
        m_q = re.match(r"^(?:question|q)[\.\:\-\s]?\s*(.*)$", clean_line, re.IGNORECASE)

        if m_a and not opt_a:
            opt_a = m_a.group(1).strip()
        elif m_b and not opt_b:
            opt_b = m_b.group(1).strip()
        elif m_c and not opt_c:
            opt_c = m_c.group(1).strip()
        elif m_d and not opt_d:
            opt_d = m_d.group(1).strip()
        elif m_ans:
            val = m_ans.group(1).strip().upper()
            if val:
                num_map = {"1": "A", "2": "B", "3": "C", "4": "D"}
                for k, v in num_map.items():
                    if val.startswith(k):
                        answer = v
                        break
                if not answer:
                    found = re.search(r"[ABCD]", val)
                    if found:
                        answer = found.group(0)
        elif m_cat:
            category = m_cat.group(1).strip() or "General"
        elif m_diff:
            d_val = m_diff.group(1).strip().upper()
            if d_val in ("EASY", "MEDIUM", "HARD"):
                difficulty = d_val
        elif m_exp:
            explanation = m_exp.group(1).strip()
        elif m_q:
            if not q_text:
                q_text = m_q.group(1).strip()
        else:
            if not q_text:
                q_text = clean_line

    if q_text and opt_a and opt_b:
        if not opt_c:
            opt_c = "N/A"
        if not opt_d:
            opt_d = "None of the above"
        if not answer:
            answer = "A"

        return {
            "question_text": q_text,
            "option_a": opt_a,
            "option_b": opt_b,
            "option_c": opt_c,
            "option_d": opt_d,
            "correct_option": answer if answer in ("A", "B", "C", "D") else "A",
            "category": category,
            "difficulty": difficulty,
            "base_points": 10.0,
            "explanation": explanation,
        }

    return None


# ---------------------------------------------------------------------------
# Database Helper
# ---------------------------------------------------------------------------
async def _execute(query: str, params: tuple = (), fetch: str = "none") -> Any:
    """Executes a query against SQLite or PostgreSQL based on configuration."""
    await db.ensure_db()

    if db.is_postgres():
        try:
            pool = await db.get_pg_pool()
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    pg_query = query.replace("?", "%s")
                    # PostgreSQL requires RETURNING id to get the inserted row's ID
                    if fetch == "id" and "RETURNING" not in pg_query.upper():
                        pg_query = pg_query.rstrip().rstrip(";") + " RETURNING id"
                    await cur.execute(pg_query, params, prepare=False)
                    if fetch == "one":
                        return await cur.fetchone()
                    elif fetch == "all":
                        return await cur.fetchall()
                    elif fetch == "id":
                        res = await cur.fetchone()
                        last_id = res[0] if res else None
                        await conn.commit()
                        return last_id
                    await conn.commit()
        except Exception as e:
            logger.error(f"Postgres execution error on query '{query}': {e}")
            raise e
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
                        last_id = cur.lastrowid
                        await conn.commit()
                        return last_id
                    await conn.commit()
        except Exception as e:
            logger.error(f"SQLite execution error on query '{query}': {e}")
            raise e


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


def to_utc_datetime(val: Any) -> Optional[datetime]:
    """Converts a string, timestamp, or datetime to an offset-aware UTC datetime safely."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    try:
        s = str(val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def format_datetime_12h(val: Any, fallback: str = "Unscheduled") -> str:
    """Formats an ISO string, timestamp, or datetime into a clean 12-hour East Africa Time (EAT) format.
    Example: 'Sep 2, 2026 · 3:10 PM EAT'.

    If val is None or invalid, returns fallback.
    """
    if not val:
        return fallback
    dt = to_utc_datetime(val)
    if not dt:
        return str(val)
    local_dt = dt.astimezone(LOCAL_TZ)
    month_name = local_dt.strftime("%b")
    day = local_dt.day
    year = local_dt.year
    hour_12 = local_dt.strftime("%I").lstrip("0") or "12"
    minute = local_dt.strftime("%M")
    ampm = local_dt.strftime("%p")
    return f"{month_name} {day}, {year} · {hour_12}:{minute} {ampm} {BOT_TIMEZONE_NAME}"


async def get_challenge(challenge_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single challenge by ID with automatic time-based status transitions and caching."""
    now_time = time.time()
    cached = _challenge_cache.get(challenge_id)
    if cached and (now_time - cached[0] < CACHE_TTL_SECONDS):
        return dict(cached[1])

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

    status = row[11]
    starts_at_val = row[5]
    ends_at_val = row[6]

    now_dt = datetime.now(timezone.utc)
    # Auto-transition SCHEDULED to LIVE if start time has arrived
    if status == "SCHEDULED" and starts_at_val:
        s_dt = to_utc_datetime(starts_at_val)
        if s_dt and now_dt >= s_dt:
            await _execute("UPDATE challenges SET status = 'LIVE' WHERE id = ?", (challenge_id,))
            status = "LIVE"

    data = {
        "id": row[0],
        "season_id": row[1],
        "title": row[2],
        "description": row[3],
        "category": row[4],
        "starts_at": str(row[5]) if row[5] is not None else None,
        "ends_at": str(row[6]) if row[6] is not None else None,
        "duration_seconds": row[7],
        "question_time_limit_seconds": row[8],
        "accuracy_weight": float(row[9]),
        "speed_weight": float(row[10]),
        "status": status,
        "created_by": row[12],
        "created_at": str(row[13]) if row[13] is not None else None,
    }
    _challenge_cache[challenge_id] = (now_time, data)
    return dict(data)


async def get_active_challenges(limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves all LIVE and SCHEDULED challenges, sorted by live time (starts_at) and status priority."""
    now_dt = datetime.now(timezone.utc)

    # 1. Batch transition SCHEDULED→LIVE and LIVE→ENDED using server-side timestamps
    now_iso = now_dt.isoformat()
    await _execute(
        "UPDATE challenges SET status = 'LIVE' WHERE status = 'SCHEDULED' AND starts_at <= ?",
        (now_iso,),
    )
    await _execute(
        "UPDATE challenges SET status = 'ENDED' WHERE status = 'LIVE' AND ends_at IS NOT NULL AND ends_at <= ?",
        (now_iso,),
    )

    rows = await _execute(
        """
        SELECT id, season_id, title, description, category, starts_at, ends_at,
               duration_seconds, question_time_limit_seconds, accuracy_weight, speed_weight,
               status, created_by, created_at
        FROM challenges WHERE status IN ('LIVE', 'SCHEDULED')
        ORDER BY 
            CASE WHEN status = 'LIVE' THEN 1 ELSE 2 END,
            COALESCE(starts_at, created_at) DESC,
            id DESC
        LIMIT ?
        """,
        (limit,),
        fetch="all",
    )
    return [
        {
            "id": row[0],
            "season_id": row[1],
            "title": row[2],
            "description": row[3],
            "category": row[4],
            "starts_at": str(row[5]) if row[5] is not None else None,
            "ends_at": str(row[6]) if row[6] is not None else None,
            "duration_seconds": row[7],
            "question_time_limit_seconds": row[8],
            "accuracy_weight": float(row[9]),
            "speed_weight": float(row[10]),
            "status": row[11],
            "created_by": row[12],
            "created_at": str(row[13]) if row[13] is not None else None,
        }
        for row in rows
    ]


async def get_active_challenge() -> Optional[Dict[str, Any]]:
    """Retrieves the top active challenge (for single-challenge operations)."""
    challenges = await get_active_challenges(limit=1)
    return challenges[0] if challenges else None


async def list_past_challenges(limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves all past or available challenges for leaderboard review and practice questions."""
    rows = await _execute(
        """
        SELECT id, season_id, title, description, category, starts_at, ends_at,
               question_time_limit_seconds, status
        FROM challenges
        WHERE status = 'ENDED'
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
    invalidate_challenge_cache(challenge_id)
    await _execute("UPDATE challenges SET status = ? WHERE id = ?", (new_status, challenge_id))


async def delete_challenge(challenge_id: int) -> bool:
    """Permanently deletes a challenge and its associated answers, participants, and linked questions."""
    invalidate_challenge_cache(challenge_id)
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
    duration_seconds: Optional[int] = None,
    starts_at: Optional[str] = None,
    ends_at: Optional[str] = None,
) -> bool:
    """Updates editable fields of a challenge."""
    invalidate_challenge_cache(challenge_id)
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
    if duration_seconds is not None:
        fields.append("duration_seconds = ?")
        values.append(duration_seconds)
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, ?)
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


def _normalize_header_key(key: str) -> str:
    """Strips non-alphanumeric characters and converts to lowercase for fuzzy header matching."""
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _sniff_delimiter(text: str) -> str:
    """Detects whether CSV is separated by comma, semicolon, tab, or pipe."""
    first_lines = [l for l in text.split("\n")[:5] if l.strip()]
    if not first_lines:
        return ","
    sample = "\n".join(first_lines)
    counts = {
        ",": sample.count(","),
        ";": sample.count(";"),
        "\t": sample.count("\t"),
        "|": sample.count("|"),
    }
    best_delim = max(counts, key=counts.get)
    return best_delim if counts[best_delim] > 0 else ","


def _clean_correct_option(correct_val: Any, opt_a: str, opt_b: str, opt_c: str, opt_d: str) -> Optional[str]:
    """Intelligently cleans and maps correct option text/keys (e.g. 'Option A', '1', 'Amazon S3') to 'A'|'B'|'C'|'D'."""
    if not correct_val:
        return None
    raw = str(correct_val).strip()

    # 1. Clean common wrappers like "Option A", "Ans: A", "(A)", "A."
    cleaned = re.sub(r"^(option|ans|answer|choice|key)\s*[:\-]?\s*", "", raw, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"[\(\)\[\]\.\:]", "", cleaned).strip().upper()

    if cleaned in ("A", "B", "C", "D"):
        return cleaned

    # 2. Numbered options 1..4 -> A..D
    num_map = {"1": "A", "2": "B", "3": "C", "4": "D"}
    if cleaned in num_map:
        return num_map[cleaned]

    # 3. Text match against option strings
    raw_lower = raw.lower()
    if opt_a and raw_lower == opt_a.strip().lower():
        return "A"
    if opt_b and raw_lower == opt_b.strip().lower():
        return "B"
    if opt_c and raw_lower == opt_c.strip().lower():
        return "C"
    if opt_d and raw_lower == opt_d.strip().lower():
        return "D"

    return None


def _parse_csv_question_rows(csv_text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Robust universal parser for CSV, TSV, semicolon-delimited, and human-formatted question data.
    Returns (parsed_questions_list, errors_list).
    """
    text = csv_text.strip()
    # Strip UTF-8 BOM if present
    if text.startswith("\ufeff") or text.startswith("\ufffe"):
        text = text[1:].strip()

    # Remove Markdown codeblock wrappers
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if text.lower().startswith("csv") or text.lower().startswith("text") or text.lower().startswith("tsv"):
            text = text.split("\n", 1)[1].strip()

    if not text:
        return [], ["Empty input provided."]

    # Delimiter detection
    delim = _sniff_delimiter(text)

    parsed_questions: List[Dict[str, Any]] = []
    errors: List[str] = []

    lines = [l for l in text.split("\n") if l.strip()]
    first_line = lines[0]
    first_norm = _normalize_header_key(first_line)

    has_header = any(
        kw in first_norm
        for kw in ("question", "optiona", "opta", "prompt", "choicea", "correct", "answer", "difficulty")
    )

    if has_header:
        f = io.StringIO(text)
        reader = csv.DictReader(f, delimiter=delim)
        for line_num, row in enumerate(reader, start=2):
            if not row or not any(v for v in row.values() if v and str(v).strip()):
                continue

            # Normalize row keys
            norm_row = {_normalize_header_key(k): (v.strip() if isinstance(v, str) else "") for k, v in row.items() if k}

            # 1. Question prompt
            q_text = ""
            for k in ("question", "questiontext", "prompt", "q", "title", "questionprompt"):
                if k in norm_row and norm_row[k]:
                    q_text = norm_row[k]
                    break
            if not q_text:
                for k, v in norm_row.items():
                    if "question" in k or "prompt" in k:
                        q_text = v
                        break

            # 2. Option A
            opt_a = ""
            for k in ("optiona", "opta", "choicea", "a", "option1", "opt1", "choice1", "1"):
                if k in norm_row and norm_row[k]:
                    opt_a = norm_row[k]
                    break

            # 3. Option B
            opt_b = ""
            for k in ("optionb", "optb", "choiceb", "b", "option2", "opt2", "choice2", "2"):
                if k in norm_row and norm_row[k]:
                    opt_b = norm_row[k]
                    break

            # 4. Option C
            opt_c = ""
            for k in ("optionc", "optc", "choicec", "c", "option3", "opt3", "choice3", "3"):
                if k in norm_row and norm_row[k]:
                    opt_c = norm_row[k]
                    break

            # 5. Option D
            opt_d = ""
            for k in ("optiond", "optd", "choiced", "d", "option4", "opt4", "choice4", "4"):
                if k in norm_row and norm_row[k]:
                    opt_d = norm_row[k]
                    break

            # 6. Correct Option / Answer
            correct_raw = ""
            for k in ("correct", "correctoption", "correctanswer", "answer", "ans", "solution", "key", "correctans"):
                if k in norm_row and norm_row[k]:
                    correct_raw = norm_row[k]
                    break
            if not correct_raw:
                for k, v in norm_row.items():
                    if "correct" in k or "answer" in k:
                        correct_raw = v
                        break

            # 7. Category
            cat = "General"
            for k in ("category", "cat", "topic", "domain", "section"):
                if k in norm_row and norm_row[k]:
                    cat = norm_row[k]
                    break

            # 8. Difficulty
            diff = "MEDIUM"
            for k in ("difficulty", "diff", "level"):
                if k in norm_row and norm_row[k]:
                    val = norm_row[k].upper()
                    if val in ("EASY", "MEDIUM", "HARD"):
                        diff = val
                    break

            # 9. Points
            pts = 10.0
            for k in ("points", "basepoints", "pts", "score", "weight"):
                if k in norm_row and norm_row[k]:
                    try:
                        pts = float(norm_row[k])
                    except Exception:
                        pts = 10.0
                    break

            # 10. Explanation
            exp = ""
            for k in ("explanation", "exp", "reason", "why", "description", "notes", "rationale", "desc"):
                if k in norm_row and norm_row[k]:
                    exp = norm_row[k]
                    break

            if not q_text or not opt_a or not opt_b:
                errors.append(f"Row {line_num}: Missing question prompt or required options")
                continue

            if not opt_c:
                opt_c = "N/A"
            if not opt_d:
                opt_d = "N/A"

            correct_clean = _clean_correct_option(correct_raw, opt_a, opt_b, opt_c, opt_d)
            if not correct_clean:
                errors.append(f"Row {line_num}: Invalid correct option '{correct_raw}' (must be A, B, C, or D)")
                continue

            parsed_questions.append({
                "question_text": q_text,
                "option_a": opt_a,
                "option_b": opt_b,
                "option_c": opt_c,
                "option_d": opt_d,
                "correct_option": correct_clean,
                "category": cat,
                "difficulty": diff,
                "base_points": pts,
                "explanation": exp,
            })
    else:
        # Positional CSV / TSV fallback
        f = io.StringIO(text)
        reader = csv.reader(f, delimiter=delim)
        for line_num, row in enumerate(reader, start=1):
            if not row or not any(field.strip() for field in row):
                continue
            if len(row) < 3:
                continue
            if len(row) < 6:
                single = parse_single_question_text("\n".join(row))
                if single:
                    parsed_questions.append(single)
                    continue
                errors.append(f"Row {line_num}: Expected at least 6 columns, got {len(row)}")
                continue

            q_text = row[0].strip()
            opt_a = row[1].strip()
            opt_b = row[2].strip()
            opt_c = row[3].strip() if len(row) > 3 else "N/A"
            opt_d = row[4].strip() if len(row) > 4 else "N/A"
            correct_raw = row[5].strip() if len(row) > 5 else "A"

            diff = row[6].strip().upper() if len(row) > 6 and row[6].strip().upper() in ("EASY", "MEDIUM", "HARD") else "MEDIUM"
            cat = row[7].strip() if len(row) > 7 and row[7].strip() else "General"
            try:
                pts = float(row[8].strip()) if len(row) > 8 and row[8].strip().replace(".", "", 1).isdigit() else 10.0
            except Exception:
                pts = 10.0
            exp = row[9].strip() if len(row) > 9 else ""

            if not q_text or not opt_a or not opt_b:
                errors.append(f"Row {line_num}: Missing question prompt or options")
                continue

            correct_clean = _clean_correct_option(correct_raw, opt_a, opt_b, opt_c, opt_d)
            if not correct_clean:
                errors.append(f"Row {line_num}: Invalid correct option '{correct_raw}'")
                continue

            parsed_questions.append({
                "question_text": q_text,
                "option_a": opt_a,
                "option_b": opt_b,
                "option_c": opt_c,
                "option_d": opt_d,
                "correct_option": correct_clean,
                "category": cat,
                "difficulty": diff,
                "base_points": pts,
                "explanation": exp,
            })

    if not parsed_questions:
        single = parse_single_question_text(text)
        if single:
            parsed_questions.append(single)
            errors.clear()

    return parsed_questions, errors


async def import_questions_from_csv(csv_text: str) -> Dict[str, Any]:
    """Parses a CSV/TSV string and inserts questions into the general question bank."""
    questions, errors = _parse_csv_question_rows(csv_text)
    if not questions:
        return {"imported": 0, "errors": errors or ["No valid questions found."]}

    imported = 0
    for q in questions:
        try:
            await create_question(
                question_text=q["question_text"],
                option_a=q["option_a"],
                option_b=q["option_b"],
                option_c=q["option_c"],
                option_d=q["option_d"],
                correct_option=q["correct_option"],
                category=q.get("category", "General"),
                difficulty=q.get("difficulty", "MEDIUM"),
                base_points=q.get("base_points", 10.0),
                explanation=q.get("explanation", ""),
            )
            imported += 1
        except Exception as e:
            errors.append(f"DB Error: {str(e)}")

    return {"imported": imported, "errors": errors}


async def list_questions(category: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves questions from the question bank."""
    if category:
        rows = await _execute(
            """
            SELECT id, question_text, category, difficulty, option_a, option_b, option_c, option_d,
                   correct_option, base_points, explanation
            FROM questions WHERE is_active = TRUE AND category = ? ORDER BY id DESC LIMIT ?
            """,
            (category, limit),
            fetch="all",
        )
    else:
        rows = await _execute(
            """
            SELECT id, question_text, category, difficulty, option_a, option_b, option_c, option_d,
                   correct_option, base_points, explanation
            FROM questions WHERE is_active = TRUE ORDER BY id DESC LIMIT ?
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

    invalidate_challenge_cache(challenge_id)
    return linked


async def get_challenge_questions(challenge_id: int) -> List[Dict[str, Any]]:
    """Retrieves all snapshot questions for a challenge with caching."""
    now_time = time.time()
    cached = _challenge_questions_cache.get(challenge_id)
    if cached and (now_time - cached[0] < CACHE_TTL_SECONDS):
        return [dict(q) for q in cached[1]]

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
    _challenge_questions_cache[challenge_id] = (now_time, questions)
    return [dict(q) for q in questions]


async def add_question_to_challenge(challenge_id: int, question_data: Dict[str, Any]) -> int:
    """Creates a question and directly links it to a specific challenge."""
    q_id = await create_question(
        question_text=question_data["question_text"],
        option_a=question_data["option_a"],
        option_b=question_data["option_b"],
        option_c=question_data["option_c"],
        option_d=question_data["option_d"],
        correct_option=question_data["correct_option"],
        category=question_data.get("category", "General"),
        difficulty=question_data.get("difficulty", "MEDIUM"),
        base_points=question_data.get("base_points", 10.0),
        explanation=question_data.get("explanation", ""),
    )
    await link_questions_to_challenge(challenge_id, [q_id])
    return q_id


async def get_challenge_review_data(challenge_id: int, user_id: int, question_index: int = 0) -> Dict[str, Any]:
    """Retrieves question details, correct options, user responses, and explanations for completed or archived challenges."""
    challenge = await get_challenge(challenge_id)
    if not challenge:
        return {"error": "Challenge not found."}

    if challenge.get("status") == "DRAFT":
        return {"error": "🛠️ This challenge is in draft mode and not yet published."}

    # 1. Verify access permissions: participant completed OR challenge ended/cancelled/past deadline
    part_row = await _execute(
        "SELECT id, status FROM challenge_participants WHERE challenge_id = ? AND telegram_user_id = ?",
        (challenge_id, user_id),
        fetch="one",
    )
    part_id = part_row[0] if part_row else None
    part_status = part_row[1] if part_row else None

    remaining_sec, is_capped, ends_at_str = calculate_remaining_exam_seconds(challenge, None)
    is_ended = (challenge["status"] in ("ENDED", "CANCELLED") or (ends_at_str is not None and remaining_sec <= 0))
    is_completed = (part_status == "COMPLETED")

    if not is_completed and not is_ended:
        return {
            "error": "locked",
            "message": "🔒 Questions, answers, and explanations are unlocked only after you complete your challenge attempt!",
        }

    # 2. Retrieve questions for this challenge
    questions = await get_challenge_questions(challenge_id)
    if not questions:
        return {"error": "No questions attached to this challenge."}

    total_q = len(questions)
    q_idx = max(0, min(question_index, total_q - 1))
    target_q = questions[q_idx]

    # 3. Retrieve user's answer history for this participant
    answers_by_qid = {}
    if part_id:
        ans_rows = await _execute(
            "SELECT question_id, selected_option, is_correct FROM challenge_answers WHERE participant_id = ? AND challenge_id = ?",
            (part_id, challenge_id),
            fetch="all",
        )
        for r in ans_rows or []:
            answers_by_qid[r[0]] = {
                "selected_option": r[1],
                "is_correct": bool(r[2]),
            }

    # Build status mapping for navigation buttons
    answered_status = {}
    for i, q in enumerate(questions):
        q_id = q.get("id")
        if q_id in answers_by_qid:
            answered_status[i] = answers_by_qid[q_id]["is_correct"]

    target_qid = target_q.get("id")
    target_ans = answers_by_qid.get(target_qid, {})

    return {
        "challenge_id": challenge_id,
        "challenge_title": challenge["title"],
        "question_index": q_idx,
        "question_number": q_idx + 1,
        "total_questions": total_q,
        "question_text": target_q.get("question_text", ""),
        "category": target_q.get("category", "General"),
        "difficulty": target_q.get("difficulty", "MEDIUM"),
        "option_a": target_q.get("option_a", ""),
        "option_b": target_q.get("option_b", ""),
        "option_c": target_q.get("option_c", ""),
        "option_d": target_q.get("option_d", ""),
        "correct_option": target_q.get("correct_option", "A"),
        "explanation": target_q.get("explanation") or "AWS Cloud best practices and architectural patterns.",
        "user_selected_option": target_ans.get("selected_option"),
        "is_correct": target_ans.get("is_correct"),
        "answered_status": answered_status,
    }


async def import_questions_for_challenge(challenge_id: int, csv_text: str) -> Dict[str, Any]:
    """Bulk imports questions from CSV or multiline text and links them directly to the specified challenge."""
    questions, errors = _parse_csv_question_rows(csv_text)
    if not questions:
        return {"imported": 0, "errors": errors or ["No valid questions found."]}

    imported = 0
    for q_data in questions:
        try:
            await add_question_to_challenge(challenge_id, q_data)
            imported += 1
        except Exception as e:
            errors.append(f"DB Error: {str(e)}")

    return {"imported": imported, "errors": errors}


async def remove_question_from_challenge(challenge_id: int, question_id: int) -> bool:
    """Removes a question link from a challenge."""
    invalidate_challenge_cache(challenge_id)
    await _execute(
        "DELETE FROM challenge_questions WHERE challenge_id = ? AND question_id = ?",
        (challenge_id, question_id),
    )
    return True


import math


# ---------------------------------------------------------------------------
# Participant Lifecycle & Quiz Progression
# ---------------------------------------------------------------------------
async def register_or_get_participant(
    challenge_id: int, telegram_user_id: int, user_name: str = "", username: str = ""
) -> Dict[str, Any]:
    """Registers a participant or retrieves existing registration with username tracking."""
    # Ensure user is registered in global bot users directory
    try:
        await db.register_or_update_bot_user(telegram_user_id, user_name, username)
    except Exception as e:
        logger.debug(f"Failed to update bot user in register_or_get_participant: {e}")

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

        q_order = json.loads(row[7]) if row[7] else []
        if not q_order:
            questions = await get_challenge_questions(challenge_id)
            q_order = [q["id"] for q in questions]
            random.shuffle(q_order)
            if q_order:
                await _execute(
                    "UPDATE challenge_participants SET question_order_json = ? WHERE id = ?",
                    (json.dumps(q_order), row[0]),
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
            "question_order": q_order,
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


def calculate_remaining_exam_seconds(
    challenge: Dict[str, Any], started_at_str: Optional[str] = None
) -> Tuple[float, bool, Optional[str]]:
    """
    Computes accurate time remaining for an exam session, accounting for:
    1. Standard exam duration limit (e.g. 20 minutes)
    2. Challenge closing deadline (e.g. ends_at timestamp)

    Returns:
        (remaining_seconds, is_deadline_capped, closing_time_iso)
    """
    now_dt = datetime.now(timezone.utc)
    configured_seconds = float(challenge.get("duration_seconds") or 600)
    if configured_seconds > 7200:
        configured_seconds = 7200.0

    ends_at_val = challenge.get("ends_at")
    seconds_until_close = None
    if ends_at_val:
        ends_dt = to_utc_datetime(ends_at_val)
        if ends_dt:
            seconds_until_close = (ends_dt - now_dt).total_seconds()

    ends_at_str = str(ends_at_val) if ends_at_val is not None else None

    # If the challenge is already marked ENDED, run in practice mode on the exam timer
    if challenge.get("status") == "ENDED":
        if not started_at_str:
            return (configured_seconds, False, None)
        started_dt = to_utc_datetime(started_at_str) or now_dt
        elapsed = max(0.0, (now_dt - started_dt).total_seconds())
        time_from_exam_timer = max(0.0, configured_seconds - elapsed)
        return (time_from_exam_timer, False, None)

    # 1. Participant hasn't started yet
    if not started_at_str:
        if seconds_until_close is not None:
            if seconds_until_close <= 0.0:
                return (0.0, True, ends_at_str)
            if seconds_until_close < configured_seconds:
                return (max(0.0, seconds_until_close), True, ends_at_str)
        return (configured_seconds, False, ends_at_str)

    # 2. Participant has already started
    started_dt = to_utc_datetime(started_at_str) or now_dt
    elapsed = max(0.0, (now_dt - started_dt).total_seconds())
    time_from_exam_timer = max(0.0, configured_seconds - elapsed)

    if seconds_until_close is not None:
        effective_remaining = min(time_from_exam_timer, max(0.0, seconds_until_close))
        is_capped = (seconds_until_close < time_from_exam_timer)
        return (effective_remaining, is_capped, ends_at_str)

    return (time_from_exam_timer, False, None)


async def start_participant_quiz(challenge_id: int, telegram_user_id: int) -> None:
    """Marks a participant as IN_PROGRESS and records started_at timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    await _execute(
        "UPDATE challenge_participants SET status = 'IN_PROGRESS', started_at = ? WHERE challenge_id = ? AND telegram_user_id = ?",
        (now, challenge_id, telegram_user_id),
    )


async def get_answered_positions_for_participant(participant_id: int) -> List[int]:
    """Returns list of 0-based question indices that have been answered by the participant."""
    rows = await _execute(
        "SELECT DISTINCT question_position FROM challenge_answers WHERE participant_id = ?",
        (participant_id,),
        fetch="all",
    )
    if not rows:
        return []
    return [int(r[0]) - 1 for r in rows if r and r[0] is not None]


async def get_next_question_for_participant(
    challenge_id: int,
    telegram_user_id: int,
    question_index: Optional[int] = None,
    prefetched_part: Optional[Dict[str, Any]] = None,
    prefetched_challenge: Optional[Dict[str, Any]] = None,
    prefetched_answered_indices: Optional[List[int]] = None,
) -> Optional[Dict[str, Any]]:
    """Prepares a question for a participant with randomized option mapping, bottom navigation state, and timer."""
    part = prefetched_part or await register_or_get_participant(challenge_id, telegram_user_id)
    if part["status"] not in ("REGISTERED", "IN_PROGRESS"):
        return None

    q_order = part["question_order"]
    total_q = len(q_order)
    if total_q == 0:
        return None

    if question_index is not None and 0 <= question_index < total_q:
        idx = question_index
        # Update current index in DB if different and not prefetched
        if part.get("current_question_index") != idx and not prefetched_part:
            await _execute(
                "UPDATE challenge_participants SET current_question_index = ? WHERE id = ?",
                (idx, part["id"]),
            )
    else:
        idx = part.get("current_question_index", 0)

    if idx < 0:
        idx = 0
    if idx >= total_q:
        answered_pos = (
            prefetched_answered_indices
            if prefetched_answered_indices is not None
            else await get_answered_positions_for_participant(part["id"])
        )
        unanswered = [i for i in range(total_q) if i not in answered_pos]
        if unanswered:
            idx = unanswered[0]
            await _execute(
                "UPDATE challenge_participants SET current_question_index = ? WHERE id = ?",
                (idx, part["id"]),
            )
        else:
            return None

    challenge = prefetched_challenge or await get_challenge(challenge_id)
    if not challenge:
        return None

    now_dt = datetime.now(timezone.utc)
    time_remaining_seconds, is_capped, ends_at_str = calculate_remaining_exam_seconds(
        challenge, part.get("started_at")
    )

    if time_remaining_seconds <= 0 and part["status"] == "IN_PROGRESS":
        # Exam timed out or challenge window closed
        await _execute(
            "UPDATE challenge_participants SET status = 'COMPLETED', completed_at = ?, is_locked = 0 WHERE id = ?",
            (now_dt.isoformat(), part["id"]),
        )
        return None

    mins = int(time_remaining_seconds // 60)
    secs = int(time_remaining_seconds % 60)
    time_remaining_str = f"{mins:02d}:{secs:02d}"

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

    answered_indices = (
        prefetched_answered_indices
        if prefetched_answered_indices is not None
        else await get_answered_positions_for_participant(part["id"])
    )

    return {
        "question_number": idx + 1,
        "question_index": idx,
        "total_questions": total_q,
        "question_id": target_q_id,
        "question_text": question["question_text"],
        "category": question["category"],
        "difficulty": question["difficulty"],
        "options": {k: mapping[k] for k in ["A", "B", "C", "D"]},
        "base_points": question["base_points"],
        "display_keys": display_keys,
        "time_remaining_seconds": time_remaining_seconds,
        "time_remaining_str": time_remaining_str,
        "is_deadline_capped": is_capped,
        "answered_indices": answered_indices,
    }


async def record_answer_and_advance(
    challenge_id: int,
    telegram_user_id: int,
    selected_option_key: str,
    question_index: int,
) -> Dict[str, Any]:
    """Validates and scores an answer, preventing double-clicks and recording detailed audit logs."""
    lock = _get_user_quiz_lock(challenge_id, telegram_user_id)
    if lock.locked():
        # Fast in-memory guard against double-clicks while previous query is in flight
        part = await register_or_get_participant(challenge_id, telegram_user_id)
        answered_positions = await get_answered_positions_for_participant(part["id"])
        total_q = len(part["question_order"])
        is_completed = (len(answered_positions) >= total_q)
        next_idx = question_index + 1 if question_index + 1 < total_q else 0
        return {
            "already_answered": True,
            "is_completed": is_completed,
            "current_score": part["score"],
            "correct_count": part["correct_count"],
            "answered_count": part["answered_count"],
            "total_questions": total_q,
            "next_question_index": next_idx,
        }

    async with lock:
        part = await register_or_get_participant(challenge_id, telegram_user_id)
        if part["status"] == "COMPLETED":
            s_dt = to_utc_datetime(part.get("started_at"))
            c_dt = to_utc_datetime(part.get("completed_at"))
            dur = max(0.0, (c_dt - s_dt).total_seconds()) if (s_dt and c_dt) else None
            return {
                "is_completed": True,
                "already_completed": True,
                "current_score": part["score"],
                "correct_count": part["correct_count"],
                "answered_count": part["answered_count"],
                "total_questions": len(part["question_order"]),
                "time_taken_seconds": round(dur, 1) if dur is not None else None,
            }
        if part["status"] != "IN_PROGRESS":
            return {"error": "Challenge is not active or already completed."}

        answered_positions = await get_answered_positions_for_participant(part["id"])
        total_q = len(part["question_order"])

        # If this specific question has already been answered, gracefully advance to next question
        if question_index in answered_positions:
            is_completed = (len(answered_positions) >= total_q)
            next_idx = question_index + 1
            if next_idx >= total_q and not is_completed:
                unanswered = [i for i in range(total_q) if i not in answered_positions]
                next_idx = unanswered[0] if unanswered else total_q
            return {
                "already_answered": True,
                "is_completed": is_completed,
                "current_score": part["score"],
                "correct_count": part["correct_count"],
                "answered_count": part["answered_count"],
                "total_questions": total_q,
                "next_question_index": next_idx,
            }

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        challenge = await get_challenge(challenge_id)
        if not challenge:
            return {"error": "Challenge not found."}

        started_at_str = part.get("started_at")
        time_remaining_seconds, is_capped, ends_at_str = calculate_remaining_exam_seconds(
            challenge, started_at_str
        )

        total_time_taken = 0.0
        started_dt = to_utc_datetime(started_at_str)
        if started_dt:
            total_time_taken = max(0.0, (now - started_dt).total_seconds())

        test_limit = float(challenge.get("duration_seconds") or 600)
        if test_limit > 7200:
            logger.warning(f"Challenge {challenge_id} has duration_seconds={test_limit} (>2h), capping to 7200s.")
            test_limit = 7200.0

        if time_remaining_seconds <= 0:
            # Overtime or challenge window closed
            await _execute(
                "UPDATE challenge_participants SET status = 'COMPLETED', completed_at = ?, is_locked = 0 WHERE id = ?",
                (now_iso, part["id"]),
            )
            return {
                "error": "Time's up! The allowed exam window or challenge closing deadline has been reached. Your completed answers have been submitted.",
                "is_completed": True,
                "current_score": part["score"],
                "correct_count": part["correct_count"],
                "answered_count": part["answered_count"],
                "total_questions": len(part["question_order"]),
            }

        # Calculate per-question response time for telemetry
        sent_at_val = part.get("current_question_sent_at")
        sent_at = to_utc_datetime(sent_at_val)
        sent_at_iso = sent_at.isoformat() if sent_at else None
        if sent_at:
            response_time_seconds = max(0.0, (now - sent_at).total_seconds())
        else:
            response_time_seconds = 0.0

        response_time_ms = int(response_time_seconds * 1000)

        # Retrieve randomized options mapping
        mapping = part.get("current_option_order") or {}
        display_correct = mapping.get("_display_correct", "A")
        canonical_correct = mapping.get("_canonical_correct", "A")
        question_id = mapping.get("_question_id", 0)
        base_points = float(mapping.get("_base_points", 10.0))

        is_correct = (selected_option_key.upper() == display_correct.upper())

        # Use the scoring engine so speed actually affects points
        question_time_limit = float(challenge.get("question_time_limit_seconds") or 60)
        points_awarded = calculate_score(
            is_correct=is_correct,
            response_time_seconds=response_time_seconds,
            time_limit_seconds=question_time_limit,
            base_points=base_points,
            accuracy_weight=float(challenge.get("accuracy_weight", 0.70)),
            speed_weight=float(challenge.get("speed_weight", 0.30)),
        )
        speed_multiplier = (points_awarded / base_points) if (is_correct and base_points > 0) else 0.0

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
                bool(is_correct),
                sent_at_iso,
                now_iso,
                response_time_ms,
                base_points,
                round(speed_multiplier, 4),
                points_awarded,
                now_iso,
            ),
        )

        # Advance participant state to the next question (e.g. Q1 -> Q2, Q2 -> Q3)
        new_index = question_index + 1
        raw_accumulated_score = round(part["score"] + points_awarded, 2)
        new_correct = part["correct_count"] + (1 if is_correct else 0)
        new_answered = part["answered_count"] + 1
        total_q = len(part["question_order"])

        new_answered_set = set(answered_positions)
        new_answered_set.add(question_index)
        is_completed = (len(new_answered_set) >= total_q)

        if not is_completed and new_index >= total_q:
            # Wrap around to first unanswered question if user answered out-of-order
            unanswered = [i for i in range(total_q) if i not in new_answered_set]
            new_index = unanswered[0] if unanswered else total_q

        now_iso_completed = datetime.now(timezone.utc).isoformat() if is_completed else None

        # Apply exam-level speed bonus when all questions are answered
        if is_completed:
            raw_accumulated_score = calculate_exam_score(
                raw_points_earned=raw_accumulated_score,
                total_time_taken_seconds=total_time_taken,
                total_time_limit_seconds=test_limit,
                accuracy_weight=float(challenge.get("accuracy_weight", 0.70)),
                speed_weight=float(challenge.get("speed_weight", 0.30)),
            )

        # Update database record
        await _execute(
            """
            UPDATE challenge_participants
            SET current_question_index = ?,
                score = ?,
                correct_count = ?,
                answered_count = ?,
                completed_at = COALESCE(?, completed_at),
                status = CASE WHEN ? THEN 'COMPLETED' ELSE 'IN_PROGRESS' END,
                current_question_sent_at = NULL,
                is_locked = 0
            WHERE id = ?
            """,
            (
                new_index,
                raw_accumulated_score,
                new_correct,
                new_answered,
                now_iso_completed,
                is_completed,
                part["id"],
            ),
        )

        # Build updated participant dict for instant in-memory handoff
        updated_part = dict(part)
        updated_part["current_question_index"] = new_index
        updated_part["score"] = raw_accumulated_score
        updated_part["correct_count"] = new_correct
        updated_part["answered_count"] = new_answered
        updated_part["status"] = "COMPLETED" if is_completed else "IN_PROGRESS"

        return {
            "is_completed": is_completed,
            "current_score": raw_accumulated_score,
            "correct_count": new_correct,
            "total_questions": total_q,
            "next_question_index": new_index,
            "points_awarded": points_awarded,
            "is_correct": is_correct,
            "time_taken_seconds": round(total_time_taken, 1) if is_completed else None,
            "time_limit_seconds": test_limit if is_completed else None,
            "accuracy_weight": float(challenge.get("accuracy_weight", 0.70)),
            "speed_weight": float(challenge.get("speed_weight", 0.30)),
            "_participant": updated_part,
            "_challenge": challenge,
            "_answered_indices": sorted(new_answered_set),
        }


# ---------------------------------------------------------------------------
# Leaderboards & Analytics
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

    # 1. Consolidated counts in 1 single fast query (engagement, challenges, feedback, questions)
    counts_row = await _execute(
        """
        SELECT
            (SELECT COUNT(*) FROM bot_users),
            (SELECT COUNT(*) FROM challenges),
            (SELECT COUNT(*) FROM feedback_submissions),
            (SELECT COUNT(*) FROM admin_reply_mappings),
            (SELECT COUNT(*) FROM questions WHERE is_active = TRUE)
        """,
        fetch="one",
    )
    total_users = counts_row[0] if counts_row else 0
    total_challenges = counts_row[1] if counts_row else 0
    feedback_count = counts_row[2] if counts_row else 0
    reply_count = counts_row[3] if counts_row else 0
    question_count = counts_row[4] if counts_row else 0

    # 2. Aggregated participant quiz performance
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

    # 3. Top Champions
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
