# ☁️ AWS SBG Community Bot

[![CI](https://github.com/Abrom-code/AWS-SBG-Community_Bot/actions/workflows/bot_app.yml/badge.svg)](https://github.com/Abrom-code/AWS-SBG-Community_Bot/actions/workflows/bot_app.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An advanced, production-grade Telegram bot built for the **AWS Student Builder Group (AASTU)**. Features a dedicated **Education Track Portal & Curriculum Guide**, **Upcoming Event & Programs Hub**, **In-Depth Team & Community About Page**, **2-Way Support Ticket Routing with Real-Time Edit Sync**, and a **Streamlined Community Announcement Broadcast Engine**.

---

## 🌟 Key Features

### 1. 📚 AWS SBG Education Track
* **Structured Cloud Learning**: Complete curriculum taking student builders from zero cloud knowledge to production-ready AWS architectures.
* **Curriculum Coverage**:
  * **Foundations**: Cloud computing principles, virtualization, AWS Global Infrastructure.
  * **Core Services**: IAM security, EC2 compute, S3 storage, VPC networking, RDS & DynamoDB databases.
  * **Serverless Architecture**: Event-driven computing with AWS Lambda, API Gateway, and EventBridge.
  * **DevOps & CI/CD**: CloudWatch monitoring, Infrastructure as Code, automated deployments.
  * **Certification Roadmaps**: Preparation for AWS Certified Cloud Practitioner & Solutions Architect Associate.
  * **Capstone Projects**: Deploying practical, portfolio-ready cloud applications.
* **Schedules & Logistics**:
  * **Day**: Every Saturday
  * **Time**: 2:00 PM – 4:30 PM East Africa Time (EAT) / 8:00 – 10:30 Local Time
  * **Location**: AASTU Campus + Hybrid Virtual Stream & recordings shared in [@AWSAASTU](https://t.me/AWSAASTU).

### 2. 📅 Next Event & Upcoming Programs
* **Featured Sessions**: Real-time display of the next scheduled session, date, time, venue, and required prerequisites.
* **Upcoming Community Programs**:
  * AWS Certification Study Circles
  * Hands-On Serverless & Cloud Labs
  * Campus Cloud Architecture Hackathons
  * Industry Guest Speaker series with practicing cloud architects.
* **Smooth Inline Navigation**: Instant interactive buttons allowing members to jump between Education Track details, Event schedules, Support, and the official Telegram channel.

### 3. ℹ️ In-Depth Community & Team About Page
* **Mission & Vision**: Empowering students through hands-on cloud computing, certifications, and industry mentorship.
* **The Leadership Team**: Student cloud ambassadors, technical leads, and certified mentors.
* **What Membership Provides**: Practical labs, peer study circles, hackathons, and career networking.

### 4. 💬 Divided Feedback & Member Question Support System
* **Separated Channels**: Dedicated workflows distinguishing community suggestions from technical/event inquiries:
  * **Feedback & Suggestions (`/feedback`)**: Community ideas, workshop topic suggestions, and general feedback. Forwarded to the admin group with distinct header `✦ Feedback`.
  * **Member Questions & Support (`/ask` or `/support`)**: Inquiries regarding the Education Track, hands-on lab roadblocks, certification, or logistics. Forwarded with header `✦ Question`.
* **Multi-Reply & Staff Routing**: Admin replies sent directly to either ticket type in the staff group automatically route back to the member's private chat with tailored confirmation headers.
* **Real-Time Edit Sync**: Editing an admin reply or user submission dynamically updates the corresponding message in real time with preserved ticket categorization.

### 5. 📢 Streamlined Community Message Broadcasting
* **One-Click Input**: No unnecessary category menus or presets. Clicking **Broadcast** or typing `/broadcast` immediately opens the text composition prompt with audience reach count.
* **Rich Text Support**: Supports full HTML formatting (bold, italics, code blocks, links).
* **Interactive Broadcast Preview**: Admins see a live preview of the announcement and audience count before confirming delivery.
* **Error Boundary & Summary Report**: Instant reporting of delivered count and delivery issues (e.g. blocked/deleted users) upon completion.

### 6. ⚙️ Dynamic Education Tracks & Event Management
* **Multi-Track Cloud Curriculum**: Supports multiple simultaneous tracks (defaults to two tracks: *Cloud Foundations & Core Services* and *Solutions Architect & Serverless*, each with 60 students across 3 classes and 1 dedicated mentor per class).
* **Effortless Admin Track Creation & Editing**: Admins can tap `[➕ Add New Track]` or `[🔹 Edit Track]` anytime from `/admin` or the admin menu.
* **Complete Field Flexibility (Skip Anything)**: Every single detail (duration, cohort size, mentors, schedule, location, focus) is optional. Any omitted or skipped fields are seamlessly excluded from the card without placeholder clutter.
* **Interactive Member Track Switcher**: Members browsing the Education Track can seamlessly toggle between tracks using clean inline buttons (`● Track 1` vs `🔹 Track 2`).
* **Live Database Persistence**: Tracks and event details persist in the `education_tracks` and `community_settings` tables across both PostgreSQL and SQLite, instantly reflecting live updates for all members.

---

## 🤖 Member Commands Reference

| Command | Description |
| :--- | :--- |
| `/start` | Open the main welcome menu & persistent keyboard |
| `/education` / `/track` | Explore the AWS Education Track curriculum & schedule |
| `/events` / `/nextevent` | Check the next scheduled workshop & upcoming programs |
| `/about` | Learn about AWS Student Builder Group AASTU & the team |
| `/feedback` | Share ideas, suggestions, or community feedback |
| `/ask` / `/question` | Ask a question directly to the core team & mentors |
| `/support` | Helpdesk desk information & support guidelines |
| `/help` | Full shortcuts list & command reference |
| `/broadcast` | Direct broadcast announcement prompt *(authorized admins)* |
| `/admin` | Open Admin Operations Command Center *(restricted)* |
| `/cancel` | Cancel active text input and return to the main dashboard |

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
