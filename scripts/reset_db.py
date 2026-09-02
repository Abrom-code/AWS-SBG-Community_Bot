import os
import sys
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def main():
    if DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")):
        print("Connecting directly to Supabase PostgreSQL...")
        import psycopg

        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    print("Dropping all existing Supabase tables...")
                    cur.execute("""
                        DROP TABLE IF EXISTS 
                            challenge_answers,
                            challenge_participants,
                            challenge_questions,
                            questions,
                            challenges,
                            challenge_seasons,
                            admin_reply_mappings,
                            feedback_submissions,
                            user_states,
                            bot_users
                        CASCADE;
                    """)
                    conn.commit()
            print("[SUCCESS] Successfully wiped Supabase database!")
            print("[SUCCESS] All tables dropped. When your Vercel bot receives its next webhook or message, clean tables are automatically created.")
        except Exception as e:
            print(f"[ERROR] Error connecting to Supabase: {e}")
    else:
        print("DATABASE_URL is not set to PostgreSQL in .env.")
        sqlite_path = "bot.db"
        if os.path.exists(sqlite_path):
            os.remove(sqlite_path)
            print("[SUCCESS] Removed local SQLite bot.db.")


if __name__ == "__main__":
    main()
