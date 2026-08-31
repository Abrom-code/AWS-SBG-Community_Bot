# AWS SBG Community & Challenge Bot

A Telegram bot for the AWS Student Builder Group community featuring an interactive **Weekly Challenge Engine**, **Leaderboards**, and direct **Feedback & Support Routing**.

---

## Key Features

### 1. ⚡ AWS Builder Challenge Engine (Phase 1)
* **Multiple-Choice Questions (MCQ)**: 4 options with randomized display order and anti-cheat question shuffling per participant.
* **Server-Side Timing Model**: Server measures exact elapsed response time ($t$) up to the configured question time limit ($T$).
* **Continuous Decay Scoring Formula**:
  $$Score = B \times \left(0.70 + 0.30 \times \left(1 - \frac{t}{T}\right)\right)$$
  * $70\%$ of points awarded for knowledge accuracy, and up to $30\%$ for response speed.
  * Overtime ($t > T$) or incorrect answers award $0$ points.
  * Configurable accuracy & speed weights per challenge.
* **Single Attempt Enforcement**: Exactly 1 attempt per user per challenge.
* **Anti-Double-Click Lock**: Prevents duplicate answer submissions or rapid tapping glitches.
* **Challenge Question Snapshotting**: Questions are snapshotted at publication time for immutability.
* **Leaderboards**:
  * 🏆 **Weekly Challenge Leaderboard**: Real-time ranks and accuracy for the active challenge.
  * 📅 **Monthly Cumulative Leaderboard**: Aggregated season scores across all weekly challenges.

### 2. 👑 Admin Challenge Panel & CSV Importer
* Accessible via `/admin`.
* **CSV Bulk Question Importer**: Upload a `.csv` file via Telegram to import hundreds of questions instantly.
  * Columns: `question,option_a,option_b,option_c,option_d,correct,difficulty,category,points,explanation`
* **Challenge Lifecycle State Machine**: `DRAFT` $\rightarrow$ `SCHEDULED` $\rightarrow$ `LIVE` $\rightarrow$ `ENDED` (or `CANCELLED`).

### 3. 💬 Feedback & Community Support System
* Direct forwarding of feedback tickets to the configured admin group with clean HTML formatting.
* **Multi-Reply & Thread Support**: Admins can send multiple replies and discussion thread replies that automatically route back to the member.
* **Real-Time Edit Synchronization**: Editing an admin reply or user feedback dynamically updates the corresponding message in real time.

---

## Member Experience

### Available Commands
- `/start` — Opens the welcome screen and main menu
- `/challenge` — Starts or resumes the active weekly challenge
- `/leaderboard` — Displays weekly and monthly cumulative rankings
- `/feedback` — Starts the feedback submission flow
- `/help` — Displays command list and shortcuts
- `/about` — Community info and links
- `/cancel` — Cancels an active feedback draft
- `/admin` — Admin operations dashboard

### Main Menu Shortcuts
- `⚡ Challenges`
- `🏆 Leaderboard`
- `📝 Submit Feedback`
- `ℹ️ About`
- `❓ Help`
- `❌ Cancel`

---

## Project Structure

```
AWS-SBG-Community_Bot/
├── main.py                     # Local development launcher with auto-reconnect
├── requirements.txt            # Python dependencies
├── vercel.json                 # Vercel serverless routing configuration
├── .env.example                # Environment variables template
├── api/
│   └── webhook.py              # Vercel serverless Telegram webhook entrypoint
├── app/
│   ├── bot.py                  # Bot application factory & route aggregator
│   ├── db.py                   # SQLite & PostgreSQL dual-persistence layer
│   └── challenge/
│       ├── models.py           # Enums & data structures
│       ├── scoring.py          # Decoupled accuracy + speed scoring engine
│       ├── keyboards.py        # Inline keyboards (quiz options, menus, admin)
│       ├── service.py          # Database operations, session tracking, CSV parser, leaderboards
│       ├── handlers.py         # Student quiz flow & leaderboard views
│       └── admin.py            # Admin operations & CSV document upload
└── tests/
    ├── test_bot.py             # Feedback & bot core unit tests (12 tests)
    ├── test_scoring.py         # Scoring engine math unit tests (6 tests)
    └── test_challenge.py       # Challenge engine & leaderboard tests (5 tests)
```

---

## Setup & Local Development

1. Create and activate a Python virtual environment.
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Configure `.env`:
```env
TELEGRAM_BOT_TOKEN=your_bot_token
ADMIN_GROUP_CHAT_ID=your_admin_group_chat_id
# Optional: PostgreSQL Database URL (if omitted, automatically uses local SQLite bot.db)
# DATABASE_URL=postgresql://user:password@host:port/database
```
4. Start the bot locally:
```bash
python main.py
```
5. Run the test suite:
```bash
python -m pytest tests/
```

---

## Deployment to Vercel (Serverless)

1. Import this repository into Vercel.
2. Configure Environment Variables in Vercel project settings:
   - `TELEGRAM_BOT_TOKEN`
   - `ADMIN_GROUP_CHAT_ID`
   - `DATABASE_URL` (from Supabase or Neon PostgreSQL)
3. Set your Telegram webhook:
```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<VERCEL_APP>.vercel.app/api/webhook
```
