"""
Script to create/recreate all PostgreSQL tables on Supabase using synchronous psycopg.
"""
import os
import sys
from dotenv import load_dotenv
import psycopg

sys.path.insert(0, ".")
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in environment or .env file.")
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bot_users (
    user_id BIGINT PRIMARY KEY,
    first_name TEXT,
    username TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_states (
    user_id BIGINT PRIMARY KEY,
    state TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback_submissions (
    message_id BIGINT PRIMARY KEY,
    sender_chat_id BIGINT NOT NULL,
    sender_name TEXT,
    user_message_id BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_reply_mappings (
    admin_message_id BIGINT PRIMARY KEY,
    user_chat_id BIGINT NOT NULL,
    delivered_message_id BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS challenge_seasons (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    status TEXT DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS challenge_questions (
    id BIGSERIAL PRIMARY KEY,
    challenge_id BIGINT NOT NULL,
    question_id BIGINT NOT NULL,
    question_order INT DEFAULT 0,
    snapshot_json TEXT
);

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

CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges(status);
CREATE INDEX IF NOT EXISTS idx_challenge_questions_challenge ON challenge_questions(challenge_id);
CREATE INDEX IF NOT EXISTS idx_challenge_answers_participant ON challenge_answers(participant_id, challenge_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user_message ON feedback_submissions(user_message_id);
"""

def main():
    print("Connecting to Supabase PostgreSQL...")
    conn = psycopg.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()
    conn.close()
    print("SUCCESS: All 10 tables and indexes created on Supabase!")

if __name__ == "__main__":
    main()
