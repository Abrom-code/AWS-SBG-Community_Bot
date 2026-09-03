# ⚡ AWS SBG Community & Challenge Bot

[![CI](https://github.com/Abrom-code/AWS-SBG-Community_Bot/actions/workflows/bot_app.yml/badge.svg)](https://github.com/Abrom-code/AWS-SBG-Community_Bot/actions/workflows/bot_app.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An advanced, production-grade Telegram bot built for the **AWS Student Builder Group (AASTU)**. Features an interactive **Cloud Challenge & Exam Engine**, **Competitive Leaderboards**, **Community Guidelines & Anti-Cheat System**, **2-Way Support Ticket Routing**, **East Africa Time (EAT) Native Scheduling**, and a **Modern Emoji-Free Admin Operations Command Center**.

---

## 🌟 Key Features

### 1. ⚡ AWS Builder Challenge & Exam Engine
* **Unified Exam Timer & Self-Pacing**: Configurable overall test duration (e.g. 10 minutes total). Live countdown display on each question card.
* **Intelligent Deadline Capping**: If a challenge closes before the standard exam duration finishes, the timer dynamically caps to the closing deadline with real-time warnings.
* **Real-Time "Refresh Status" Button**: Emoji-free on-demand refresh button on challenge cards. Immediately re-checks the live clock against the database, seamlessly unlocking scheduled challenges to `Live Now` without Telegram API rate limits or screen flickering.
* **East Africa Time (EAT, UTC+3) Native**: All challenge schedules and user-facing timecards are displayed in a clean 12-hour format with timezone identification (e.g. `Sep 2, 2026 · 3:40 PM EAT`).
* **Continuous Decay Scoring Formula**:
  $$\text{Final Score} = \text{Raw Points} \times \left(0.70 + 0.30 \times \left(1 - \frac{\text{Total Time Taken}}{\text{Allotted Exam Time}}\right)\right)$$
  * $70\%$ baseline awarded for correct answers (accuracy).
  * Up to $30\%$ efficiency bonus awarded for rapid completion speed.
  * Overtime or incorrect submissions yield $0$ points.
* **Anti-Cheat & Shuffling**:
  * Randomized 4-option keyboard layout ($A, B, C, D$) per participant.
  * Anti-double-click atomic locking prevents duplicate score submissions.
  * Content protection / anti-forwarding enabled on questions.
  * Strict single-attempt policy per participant.
* **Post-Exam Explanation**: Detailed explanations and correct answers revealed immediately after submission with question-by-question review navigation.

### 2. 📱 Telegram Menu Button & Quick Commands
* **Interactive Menu Button**: Native Telegram `MenuButtonCommands` popup listing all available actions right in the chat bar.
* **Dual Interface**: Full Telegram command menu alongside the intuitive, persistent custom reply keyboard (`ReplyKeyboardMarkup`).

### 3. 🛡️ Universal Community Guidelines & Code of Conduct
* Accessible anytime via `/guidelines` or the dedicated button on any challenge start card.
* **Rules Enforced**: Strictly 1 account per builder, no AI/automation assistance, continuous exam timer, anti-leak integrity, and screenshot restriction.

### 4. 🏆 Championship Leaderboards
* ⚡ **Weekly Challenge Leaderboard**: Real-time rank, points, and accuracy for active challenges with next/prev pagination.
* 📅 **Monthly Season Championship**: Aggregated monthly scores across all weekly challenges.
* **Tie-Breaker Logic**: Fastest total exam completion time ranks higher.

### 5. 📚 Past Challenges & Practice Archive
* Accessible via `/archive` or `/past`.
* Browse past competitions to review final leaderboards or practice all questions indefinitely in self-paced archive mode.

### 6. 💬 2-Way Feedback & Support Routing
* Direct forwarding of feedback tickets to the configured admin group formatted in clean blockquotes.
* **Multi-Reply & Staff Routing**: Admin replies sent to feedback messages automatically route directly to the original member's private chat.
* **Real-Time Edit Sync**: Editing an admin reply or user feedback dynamically updates the corresponding message in real time.

### 7. 👑 Admin Operations Command Center (`/admin`)
* **Modern, Emoji-Free Interface**: Clean, professional management dashboard designed for effortless community moderation.
* **4-Step Interactive Creation Wizard**:
  * **Step 1: Title & Category**: Choose from modern tech categories (`AI`, `DevOps`, `Web3`, `Cloud`, `Architecture`, `Serverless`, `Security`, `Database`, `Networking`), enter a **Custom Category** on demand, or use the single-line shortcut (`Title | Category` or `Title | Category | Description | Duration`).
  * **Step 2: Description**: Enter custom challenge description or use the community default.
  * **Step 3: Exam Time Limit**: Set exam duration (5, 10, 15, 20, 30, 45, 60 minutes or custom).
  * **Step 4: Schedule & Launch**: Choose presets (*Go Live Now*, *1 Week*, *This Weekend*, *Draft*) or enter custom dates in East Africa Time.
* **Robust Schedule Date Input**:
  * Paste dates directly onto the **Edit Schedule** screen without needing extra button taps.
  * Resilient regex parsing extracts start and end times even from copy-pasted chat messages (e.g. `[9/2/2026 3:23 PM] User: 2026-09-02 15:25 to 2026-09-02 15:50`).
* **Full Question Inspector**: View complete question cards (options, answer, difficulty, points, explanation) with 4-card pagination and individual remove buttons.
* **Bulk CSV Importer**: Upload `.csv` files or paste CSV text directly in chat.
  ```csv
  question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation
  What is Amazon S3?,Object Storage,Block Storage,Compute,Database,A,EASY,Storage,10,S3 is scalable object storage
  ```
* **Flexible Single-Question Parser**: Supports natural multiline format with `A:`, `1.`, `Ans:`, `Difficulty:`, `Explanation:`.
* **Monthly Analytics Report**: Summary of registered members, challenge attempts, average score, accuracy %, and Top 3 builders of the month.
* **Community Broadcast Announcements**: Deliver formatted announcements to all registered bot members with 1 click.

---

## 🤖 Member Commands Reference

| Command | Description |
| :--- | :--- |
| `/start` | Open the main welcome menu & persistent keyboard |
| `/challenge` | Open Challenge Center or start the live weekly challenge |
| `/leaderboard` | View weekly & monthly championship standings |
| `/notifications` | Check broadcast notification subscriptions & alerts |
| `/archive` / `/past` | Browse archived challenges to practice questions |
| `/rules` | View how the two-factor scoring formula works |
| `/guidelines` | Read universal community rules & code of conduct |
| `/feedback` / `/support` | Submit a ticket/suggestion to the core admin team |
| `/about` | Learn about AWS Student Builder Group AASTU |
| `/help` | Display shortcuts and full command reference |
| `/cancel` | Cancel current text input state and return to main menu |
| `/admin` | Open Admin Operations Command Center *(restricted)* |

---

## 🛠️ Tech Stack

| Layer | Technology |
| :--- | :--- |
| Language | Python 3.11+ |
| Bot Framework | [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) ≥ 21.0 |
| Database (Dev) | SQLite via [aiosqlite](https://github.com/omnilib/aiosqlite) |
| Database (Prod) | PostgreSQL via [psycopg 3](https://www.psycopg.org/psycopg3/) + async connection pool |
| Hosting | [Vercel](https://vercel.com) serverless functions + [Supabase](https://supabase.com) PostgreSQL |
| CI/CD | GitHub Actions (lint + test on every push/PR) |

---

## 📂 Project Architecture

```
AWS-SBG-Community_Bot/
├── main.py                         # Local development: polling & self-hosted webhook launcher
├── requirements.txt                # Python dependencies (psycopg, telegram, etc.)
├── vercel.json                     # Vercel serverless routing configuration
├── .env.example                    # Environment variables template
├── .github/
│   └── workflows/
│       └── bot_app.yml             # GitHub Actions CI: lint (flake8) + test (pytest)
├── api/
│   └── webhook.py                  # Vercel serverless Telegram webhook handler & health endpoint
├── app/
│   ├── bot.py                      # Bot factory, menu buttons, command router & text handlers
│   ├── db.py                       # SQLite (dev) & Supabase PostgreSQL (prod) async database layer
│   └── challenge/
│       ├── __init__.py             # Package marker
│       ├── models.py              # Enums & challenge data structures
│       ├── scoring.py             # Decoupled accuracy & speed scoring math
│       ├── keyboards.py           # Inline keyboards (quiz options, menus, admin)
│       ├── service.py             # Business logic, timer capping, EAT timezone, leaderboards & CSV parser
│       ├── handlers.py            # Quiz lifecycle, Refresh button, guidelines & student views
│       └── admin.py               # Emoji-free admin operations, wizard, report cards & broadcast
├── scripts/
│   ├── init_db.py                  # Create all PostgreSQL tables on Supabase (one-time setup)
│   └── reset_db.py                 # Drop & reset all database tables (dev/staging utility)
├── assets/
│   └── logo.jpg                    # Bot welcome card logo displayed on /start
└── tests/
    ├── conftest.py                 # Isolated SQLite sandbox database fixture
    ├── test_bot.py                 # Feedback routing, menus, shortcuts, schedule parser & admin security
    ├── test_challenge.py           # Challenge lifecycle, questions CRUD, Refresh button & archive
    └── test_scoring.py             # Mathematical scoring formulas & speed multipliers
```

---

## ⚡ Performance & Architecture

* **Async Connection Pooling**: Production PostgreSQL queries go through a shared `psycopg_pool.AsyncConnectionPool` (min 2 / max 10 connections) with `prepare_threshold=None` for full compatibility with Supabase Transaction Pooler (PgBouncer).
* **In-Memory Challenge Caching**: Active challenge metadata and question snapshots are cached in-memory with a 30-second TTL, eliminating redundant database round-trips during high-throughput quiz sessions.
* **Per-User Concurrency Locks**: Each `(challenge_id, user_id)` pair gets an in-memory `asyncio.Lock`, preventing race conditions and double-scoring without any remote database lock overhead.
* **Zero-Downtime Schema Migration**: All tables, constraints, and indexes are created automatically via `CREATE TABLE IF NOT EXISTS` on first boot — no manual migration scripts required.
* **Serverless Cold-Start Optimization**: The Vercel webhook handler reuses a persistent event loop and pre-initialized Telegram application instance across invocations.

---

## 💻 Local Setup & Development

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/Abrom-code/AWS-SBG-Community_Bot.git
cd AWS-SBG-Community_Bot

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate   # On Windows
source .venv/bin/activate # On Linux/macOS

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_GROUP_CHAT_ID=-1001234567890
ADMIN_USER_IDS=123456789,987654321

# Optional: Timezone configuration (Default: East Africa Time / EAT, UTC+3)
BOT_TIMEZONE_OFFSET_HOURS=3
BOT_TIMEZONE_NAME=EAT

# Optional: Supabase PostgreSQL (if omitted, automatically defaults to local SQLite bot.db)
# DATABASE_URL=postgresql://postgres.xxx:password@aws-0-region.pooler.supabase.com:6543/postgres

# Optional: Self-hosted webhook mode (if omitted, defaults to long-polling)
# WEBHOOK_URL=https://your-domain.com/api/webhook
# WEBHOOK_SECRET=your_secret_token
# PORT=8443
```

### 3. Run Locally (Long-Polling Mode)
```bash
python main.py
```

### 4. Run Automated Test Suite
```bash
python -m pytest tests/ -v
```
*(All 71 automated tests run against an isolated sandbox database, preserving development data.)*

---

## 🗄️ Database Utility Scripts

### Initialize Supabase Tables
Create all 10 tables, constraints, and indexes on a fresh Supabase project:
```bash
python scripts/init_db.py
```

### Reset Database
Drop all tables and start clean (works for both PostgreSQL and local SQLite):
```bash
python scripts/reset_db.py
```

---

## 🚀 Cloud Deployment (Vercel + Supabase)

### Step 1: Set Up Supabase PostgreSQL
1. Create a free project at [supabase.com](https://supabase.com).
2. In **Project Settings** ➔ **Database** ➔ **Connection String**, copy the **URI (Transaction Pooler - Port 6543)**:
   ```env
   DATABASE_URL=postgresql://postgres.[project-ref]:[PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
3. *All database tables, constraints, and indexes are automatically created on first boot!*

### Step 2: Deploy to Vercel
1. Push your repository to your GitHub account.
2. Import the repository in [vercel.com](https://vercel.com).
3. Set the following **Environment Variables**:
   * `TELEGRAM_BOT_TOKEN`
   * `ADMIN_GROUP_CHAT_ID`
   * `ADMIN_USER_IDS`
   * `DATABASE_URL`
   * `BOT_TIMEZONE_OFFSET_HOURS` *(optional, default: `3`)*
   * `BOT_TIMEZONE_NAME` *(optional, default: `EAT`)*
4. Click **Deploy**.

### Step 3: Register Telegram Webhook
Tell Telegram to deliver incoming updates to your Vercel endpoint:
```bash
curl -F "url=https://<your-project>.vercel.app/api/webhook" https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook
```

To verify your webhook status anytime:
```bash
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo
```

### Webhook Health & Diagnostics

Once deployed, the following GET endpoints are available:

| Endpoint | Description |
| :--- | :--- |
| `GET /api/webhook` | Health check — confirms the bot is active, shows DB type and admin count |
| `GET /api/webhook?logs` | Live ring-buffer log viewer — displays the last 100 log entries for debugging |

---

## 🧪 Continuous Integration

Every push to `main` or `feature/**` branches and every pull request automatically triggers the GitHub Actions CI pipeline:

1. **Lint** — `flake8` checks for syntax errors and undefined names
2. **Test** — `pytest tests/ -v` runs the full 71-test suite against an isolated SQLite sandbox

---

## 👥 Contributing & Community

* **Organization:** AWS Student Builder Group — Addis Ababa Science and Technology University (AASTU)
* **Telegram Channel:** [@AWSAASTU](https://t.me/AWSAASTU)
* **License:** MIT
