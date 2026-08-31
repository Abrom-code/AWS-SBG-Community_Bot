import asyncio
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "bot.db")

_is_initialized = False
_db_lock = asyncio.Lock()


def is_postgres() -> bool:
    """Checks if a PostgreSQL connection string is configured."""
    return bool(
        DATABASE_URL
        and (
            DATABASE_URL.startswith("postgres://")
            or DATABASE_URL.startswith("postgresql://")
        )
    )


async def init_db(db_path: str = None) -> None:
    """Initializes tables for SQLite or PostgreSQL if not already created."""
    global _is_initialized
    path = db_path or SQLITE_DB_PATH

    if is_postgres():
        import psycopg

        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_states (
                            user_id BIGINT PRIMARY KEY,
                            state TEXT,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS feedback_submissions (
                            message_id BIGINT PRIMARY KEY,
                            sender_chat_id BIGINT NOT NULL,
                            sender_name TEXT,
                            user_message_id BIGINT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    try:
                        await cur.execute("ALTER TABLE feedback_submissions ADD COLUMN IF NOT EXISTS user_message_id BIGINT;")
                    except Exception:
                        pass

                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS admin_reply_mappings (
                            admin_message_id BIGINT PRIMARY KEY,
                            user_chat_id BIGINT NOT NULL,
                            delivered_message_id BIGINT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS challenge_seasons (
                            id BIGSERIAL PRIMARY KEY,
                            name TEXT NOT NULL,
                            start_date TIMESTAMP,
                            end_date TIMESTAMP,
                            status TEXT DEFAULT 'ACTIVE',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS challenges (
                            id BIGSERIAL PRIMARY KEY,
                            season_id BIGINT,
                            title TEXT NOT NULL,
                            description TEXT,
                            category TEXT DEFAULT 'General',
                            starts_at TIMESTAMP,
                            ends_at TIMESTAMP,
                            duration_seconds INT DEFAULT 3600,
                            question_time_limit_seconds INT DEFAULT 60,
                            accuracy_weight REAL DEFAULT 0.70,
                            speed_weight REAL DEFAULT 0.30,
                            status TEXT DEFAULT 'DRAFT',
                            created_by BIGINT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS questions (
                            id BIGSERIAL PRIMARY KEY,
                            question_text TEXT NOT NULL,
                            category TEXT DEFAULT 'General',
                            difficulty TEXT DEFAULT 'MEDIUM',
                            option_a TEXT NOT NULL,
                            option_b TEXT NOT NULL,
                            option_c TEXT NOT NULL,
                            option_d TEXT NOT NULL,
                            correct_option TEXT NOT NULL,
                            base_points REAL DEFAULT 10.0,
                            explanation TEXT,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS challenge_questions (
                            id BIGSERIAL PRIMARY KEY,
                            challenge_id BIGINT NOT NULL,
                            question_id BIGINT NOT NULL,
                            question_order INT DEFAULT 0,
                            snapshot_json TEXT
                        );
                    """)
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS challenge_participants (
                            id BIGSERIAL PRIMARY KEY,
                            challenge_id BIGINT NOT NULL,
                            telegram_user_id BIGINT NOT NULL,
                            user_name TEXT,
                            username TEXT,
                            started_at TIMESTAMP,
                            completed_at TIMESTAMP,
                            current_question_index INT DEFAULT 0,
                            question_order_json TEXT,
                            current_option_order_json TEXT,
                            current_question_sent_at TIMESTAMP,
                            score REAL DEFAULT 0.0,
                            correct_count INT DEFAULT 0,
                            answered_count INT DEFAULT 0,
                            is_locked INT DEFAULT 0,
                            status TEXT DEFAULT 'REGISTERED',
                            UNIQUE(challenge_id, telegram_user_id)
                        );
                    """)
                    try:
                        await cur.execute("ALTER TABLE challenge_participants ADD COLUMN IF NOT EXISTS username TEXT;")
                    except Exception:
                        pass
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS challenge_answers (
                            id BIGSERIAL PRIMARY KEY,
                            participant_id BIGINT NOT NULL,
                            challenge_id BIGINT NOT NULL,
                            question_id BIGINT NOT NULL,
                            question_position INT,
                            selected_option TEXT,
                            correct_option TEXT,
                            is_correct BOOLEAN,
                            question_sent_at TIMESTAMP,
                            answered_at TIMESTAMP,
                            response_time_ms INT,
                            base_points REAL,
                            speed_multiplier REAL,
                            points_awarded REAL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    await conn.commit()
            _is_initialized = True
            logger.info("Initialized PostgreSQL database tables.")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS user_states (
                        user_id INTEGER PRIMARY KEY,
                        state TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS feedback_submissions (
                        message_id INTEGER PRIMARY KEY,
                        sender_chat_id INTEGER NOT NULL,
                        sender_name TEXT,
                        user_message_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                try:
                    await db.execute("ALTER TABLE feedback_submissions ADD COLUMN user_message_id INTEGER;")
                except Exception:
                    pass

                await db.execute("""
                    CREATE TABLE IF NOT EXISTS admin_reply_mappings (
                        admin_message_id INTEGER PRIMARY KEY,
                        user_chat_id INTEGER NOT NULL,
                        delivered_message_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_seasons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        start_date TIMESTAMP,
                        end_date TIMESTAMP,
                        status TEXT DEFAULT 'ACTIVE',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS challenges (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        season_id INTEGER,
                        title TEXT NOT NULL,
                        description TEXT,
                        category TEXT DEFAULT 'General',
                        starts_at TIMESTAMP,
                        ends_at TIMESTAMP,
                        duration_seconds INTEGER DEFAULT 3600,
                        question_time_limit_seconds INTEGER DEFAULT 60,
                        accuracy_weight REAL DEFAULT 0.70,
                        speed_weight REAL DEFAULT 0.30,
                        status TEXT DEFAULT 'DRAFT',
                        created_by INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS questions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question_text TEXT NOT NULL,
                        category TEXT DEFAULT 'General',
                        difficulty TEXT DEFAULT 'MEDIUM',
                        option_a TEXT NOT NULL,
                        option_b TEXT NOT NULL,
                        option_c TEXT NOT NULL,
                        option_d TEXT NOT NULL,
                        correct_option TEXT NOT NULL,
                        base_points REAL DEFAULT 10.0,
                        explanation TEXT,
                        is_active INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_questions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        challenge_id INTEGER NOT NULL,
                        question_id INTEGER NOT NULL,
                        question_order INTEGER DEFAULT 0,
                        snapshot_json TEXT
                    );
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_participants (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        challenge_id INTEGER NOT NULL,
                        telegram_user_id INTEGER NOT NULL,
                        user_name TEXT,
                        username TEXT,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        current_question_index INTEGER DEFAULT 0,
                        question_order_json TEXT,
                        current_option_order_json TEXT,
                        current_question_sent_at TIMESTAMP,
                        score REAL DEFAULT 0.0,
                        correct_count INTEGER DEFAULT 0,
                        answered_count INTEGER DEFAULT 0,
                        is_locked INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'REGISTERED',
                        UNIQUE(challenge_id, telegram_user_id)
                    );
                """)
                try:
                    await db.execute("ALTER TABLE challenge_participants ADD COLUMN username TEXT;")
                except Exception:
                    pass
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_answers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        participant_id INTEGER NOT NULL,
                        challenge_id INTEGER NOT NULL,
                        question_id INTEGER NOT NULL,
                        question_position INTEGER,
                        selected_option TEXT,
                        correct_option TEXT,
                        is_correct INTEGER,
                        question_sent_at TIMESTAMP,
                        answered_at TIMESTAMP,
                        response_time_ms INTEGER,
                        base_points REAL,
                        speed_multiplier REAL,
                        points_awarded REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await db.commit()
            _is_initialized = True
            logger.info(f"Initialized SQLite database tables at {path}.")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")


async def ensure_db(db_path: str = None) -> None:
    """Ensures database tables are initialized before executing operations."""
    global _is_initialized
    if not _is_initialized:
        async with _db_lock:
            if not _is_initialized:
                await init_db(db_path)


async def get_user_state(user_id: int, db_path: str = None) -> Optional[str]:
    """Retrieves the active conversation state for a given user."""
    await ensure_db(db_path)
    path = db_path or SQLITE_DB_PATH

    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT state FROM user_states WHERE user_id = %s", (user_id,)
                    )
                    row = await cur.fetchone()
                    return row[0] if row else None
        except Exception as e:
            logger.error(f"Error in get_user_state (Postgres): {e}")
            return None
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                async with db.execute(
                    "SELECT state FROM user_states WHERE user_id = ?", (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else None
        except Exception as e:
            logger.error(f"Error in get_user_state (SQLite): {e}")
            return None


async def set_user_state(
    user_id: int, state: Optional[str], db_path: str = None
) -> None:
    """Sets or clears the conversation state for a given user."""
    await ensure_db(db_path)
    path = db_path or SQLITE_DB_PATH

    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    if state is None:
                        await cur.execute(
                            "DELETE FROM user_states WHERE user_id = %s", (user_id,)
                        )
                    else:
                        await cur.execute(
                            """
                            INSERT INTO user_states (user_id, state)
                            VALUES (%s, %s)
                            ON CONFLICT (user_id) DO UPDATE SET state = EXCLUDED.state, updated_at = CURRENT_TIMESTAMP
                        """,
                            (user_id, state),
                        )
                    await conn.commit()
        except Exception as e:
            logger.error(f"Error in set_user_state (Postgres): {e}")
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                if state is None:
                    await db.execute(
                        "DELETE FROM user_states WHERE user_id = ?", (user_id,)
                    )
                else:
                    await db.execute(
                        """
                        INSERT INTO user_states (user_id, state)
                        VALUES (?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET state = excluded.state, updated_at = CURRENT_TIMESTAMP
                    """,
                        (user_id, state),
                    )
                await db.commit()
        except Exception as e:
            logger.error(f"Error in set_user_state (SQLite): {e}")


async def save_feedback_submission(
    message_id: int,
    sender_chat_id: int,
    sender_name: str,
    user_message_id: int = None,
    db_path: str = None,
) -> None:
    """Saves a forwarded admin-group message mapping to the original user."""
    await ensure_db(db_path)
    path = db_path or SQLITE_DB_PATH

    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO feedback_submissions (message_id, sender_chat_id, sender_name, user_message_id)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (message_id) DO UPDATE SET
                            sender_chat_id = EXCLUDED.sender_chat_id,
                            sender_name = EXCLUDED.sender_name,
                            user_message_id = EXCLUDED.user_message_id
                    """,
                        (message_id, sender_chat_id, sender_name, user_message_id),
                    )
                    await conn.commit()
        except Exception as e:
            logger.error(f"Error in save_feedback_submission (Postgres): {e}")
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                await db.execute(
                    """
                    INSERT INTO feedback_submissions (message_id, sender_chat_id, sender_name, user_message_id)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(message_id) DO UPDATE SET
                        sender_chat_id = excluded.sender_chat_id,
                        sender_name = excluded.sender_name,
                        user_message_id = excluded.user_message_id
                """,
                    (message_id, sender_chat_id, sender_name, user_message_id),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error in save_feedback_submission (SQLite): {e}")


async def get_feedback_submission(
    message_id: int, db_path: str = None
) -> Optional[Dict[str, Any]]:
    """Retrieves the original sender data for a forwarded admin-group message."""
    await ensure_db(db_path)
    path = db_path or SQLITE_DB_PATH

    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT sender_chat_id, sender_name, user_message_id FROM feedback_submissions WHERE message_id = %s",
                        (message_id,),
                    )
                    row = await cur.fetchone()
                    if row:
                        return {
                            "sender_chat_id": row[0],
                            "sender_name": row[1],
                            "user_message_id": row[2],
                        }
        except Exception as e:
            logger.error(f"Error in get_feedback_submission (Postgres): {e}")
            return None
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                async with db.execute(
                    "SELECT sender_chat_id, sender_name, user_message_id FROM feedback_submissions WHERE message_id = ?",
                    (message_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "sender_chat_id": row[0],
                            "sender_name": row[1],
                            "user_message_id": row[2],
                        }
        except Exception as e:
            logger.error(f"Error in get_feedback_submission (SQLite): {e}")
            return None

    return None


async def get_feedback_submission_by_user_message(
    user_message_id: int, db_path: str = None
) -> Optional[Dict[str, Any]]:
    """Finds the forwarded admin-group message ID corresponding to a user message."""
    await ensure_db(db_path)
    path = db_path or SQLITE_DB_PATH

    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT message_id, sender_chat_id, sender_name FROM feedback_submissions WHERE user_message_id = %s",
                        (user_message_id,),
                    )
                    row = await cur.fetchone()
                    if row:
                        return {
                            "message_id": row[0],
                            "sender_chat_id": row[1],
                            "sender_name": row[2],
                        }
        except Exception as e:
            logger.error(f"Error in get_feedback_submission_by_user_message (Postgres): {e}")
            return None
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                async with db.execute(
                    "SELECT message_id, sender_chat_id, sender_name FROM feedback_submissions WHERE user_message_id = ?",
                    (user_message_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "message_id": row[0],
                            "sender_chat_id": row[1],
                            "sender_name": row[2],
                        }
        except Exception as e:
            logger.error(f"Error in get_feedback_submission_by_user_message (SQLite): {e}")
            return None

    return None


async def delete_feedback_submission(message_id: int, db_path: str = None) -> None:
    """Deletes a feedback submission mapping after the reply is processed."""
    await ensure_db(db_path)
    path = db_path or SQLITE_DB_PATH

    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM feedback_submissions WHERE message_id = %s",
                        (message_id,),
                    )
                    await conn.commit()
        except Exception as e:
            logger.error(f"Error in delete_feedback_submission (Postgres): {e}")
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                await db.execute(
                    "DELETE FROM feedback_submissions WHERE message_id = ?",
                    (message_id,),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error in delete_feedback_submission (SQLite): {e}")


async def save_admin_reply_mapping(
    admin_message_id: int,
    user_chat_id: int,
    delivered_message_id: int,
    db_path: str = None,
) -> None:
    """Saves mapping between an admin reply and the delivered message in user chat."""
    await ensure_db(db_path)
    path = db_path or SQLITE_DB_PATH

    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO admin_reply_mappings (admin_message_id, user_chat_id, delivered_message_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (admin_message_id) DO UPDATE SET
                            user_chat_id = EXCLUDED.user_chat_id,
                            delivered_message_id = EXCLUDED.delivered_message_id
                    """,
                        (admin_message_id, user_chat_id, delivered_message_id),
                    )
                    await conn.commit()
        except Exception as e:
            logger.error(f"Error in save_admin_reply_mapping (Postgres): {e}")
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                await db.execute(
                    """
                    INSERT INTO admin_reply_mappings (admin_message_id, user_chat_id, delivered_message_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(admin_message_id) DO UPDATE SET
                        user_chat_id = excluded.user_chat_id,
                        delivered_message_id = excluded.delivered_message_id
                """,
                    (admin_message_id, user_chat_id, delivered_message_id),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error in save_admin_reply_mapping (SQLite): {e}")


async def get_admin_reply_mapping(
    admin_message_id: int, db_path: str = None
) -> Optional[Dict[str, Any]]:
    """Retrieves the user chat ID and delivered message ID for an admin reply."""
    await ensure_db(db_path)
    path = db_path or SQLITE_DB_PATH

    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT user_chat_id, delivered_message_id FROM admin_reply_mappings WHERE admin_message_id = %s",
                        (admin_message_id,),
                    )
                    row = await cur.fetchone()
                    if row:
                        return {
                            "user_chat_id": row[0],
                            "delivered_message_id": row[1],
                        }
        except Exception as e:
            logger.error(f"Error in get_admin_reply_mapping (Postgres): {e}")
            return None
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                async with db.execute(
                    "SELECT user_chat_id, delivered_message_id FROM admin_reply_mappings WHERE admin_message_id = ?",
                    (admin_message_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "user_chat_id": row[0],
                            "delivered_message_id": row[1],
                        }
        except Exception as e:
            logger.error(f"Error in get_admin_reply_mapping (SQLite): {e}")
            return None

    return None


async def get_all_broadcast_user_ids() -> list[int]:
    """Retrieves all distinct user Telegram IDs who have interacted with the bot."""
    query = """
        SELECT DISTINCT user_id FROM (
            SELECT user_id FROM user_states
            UNION
            SELECT sender_chat_id AS user_id FROM feedback_submissions
            UNION
            SELECT telegram_user_id AS user_id FROM challenge_participants
            UNION
            SELECT user_chat_id AS user_id FROM admin_reply_mappings
        ) WHERE user_id IS NOT NULL AND user_id > 0
    """
    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query)
                    rows = await cur.fetchall()
                    return [r[0] for r in rows]
        except Exception as e:
            logger.error(f"Error fetching broadcast user IDs (Postgres): {e}")
            return []
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(SQLITE_DB_PATH) as db:
                async with db.execute(query) as cur:
                    rows = await cur.fetchall()
                    return [r[0] for r in rows]
        except Exception as e:
            logger.error(f"Error fetching broadcast user IDs (SQLite): {e}")
            return []


async def reset_db(db_path: str = None) -> None:
    """Helper to clear tables during automated testing."""
    path = db_path or SQLITE_DB_PATH
    await ensure_db(path)

    if is_postgres():
        import psycopg

        url = (
            DATABASE_URL.replace("postgres://", "postgresql://", 1)
            if DATABASE_URL.startswith("postgres://")
            else DATABASE_URL
        )
        try:
            async with await psycopg.AsyncConnection.connect(url) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM user_states;")
                    await cur.execute("DELETE FROM feedback_submissions;")
                    await cur.execute("DELETE FROM admin_reply_mappings;")
                    await cur.execute("DELETE FROM challenge_answers;")
                    await cur.execute("DELETE FROM challenge_participants;")
                    await cur.execute("DELETE FROM challenge_questions;")
                    await cur.execute("DELETE FROM challenges;")
                    await cur.execute("DELETE FROM questions;")
                    await cur.execute("DELETE FROM challenge_seasons;")
                    await conn.commit()
        except Exception as e:
            logger.error(f"Error resetting Postgres: {e}")
    else:
        import aiosqlite

        try:
            async with aiosqlite.connect(path) as db:
                await db.execute("DELETE FROM user_states;")
                await db.execute("DELETE FROM feedback_submissions;")
                await db.execute("DELETE FROM admin_reply_mappings;")
                await db.execute("DELETE FROM challenge_answers;")
                await db.execute("DELETE FROM challenge_participants;")
                await db.execute("DELETE FROM challenge_questions;")
                await db.execute("DELETE FROM challenges;")
                await db.execute("DELETE FROM questions;")
                await db.execute("DELETE FROM challenge_seasons;")
                await db.commit()
        except Exception as e:
            logger.error(f"Error resetting SQLite: {e}")
