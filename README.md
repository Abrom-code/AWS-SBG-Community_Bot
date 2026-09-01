# ⚡ AWS SBG Community & Challenge Bot

An advanced, production-grade Telegram bot built for the **AWS Student Builder Group (AASTU)**. Features an interactive **Cloud Challenge & Exam Engine**, **Competitive Leaderboards**, **Community Guidelines & Anti-Cheat System**, **2-Way Support Ticket Routing**, and an **Admin Operations Command Center**.

---

## 🌟 Key Features

### 1. ⚡ AWS Builder Challenge & Exam Engine
* **Unified Exam Timer & Self-Pacing**: Configurable overall test duration (e.g. 10 minutes total). Live countdown display on each question card.
* **Intelligent Deadline Capping**: If a challenge closes before the standard exam duration finishes, the timer dynamically caps to the closing deadline with real-time warnings.
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
* **Post-Exam Explanation**: Detailed explanations and correct answers revealed immediately after submission.

### 2. 🛡️ Universal Community Guidelines & Code of Conduct
* Accessible anytime via `/guidelines` or the dedicated button on any challenge start card.
* **Rules Enforced**: Strictly 1 account per builder, no AI/automation assistance, continuous exam timer, anti-leak integrity, and screenshot restriction.

### 3. 🏆 Championship Leaderboards
* ⚡ **Weekly Challenge Leaderboard**: Real-time rank, points, and accuracy for active challenges with next/prev pagination.
* 📅 **Monthly Season Championship**: Aggregated monthly scores across all weekly challenges.
* **Tie-Breaker Logic**: Fastest total exam completion time ranks higher.

### 4. 📚 Past Challenges & Practice Archive
* Accessible via `/archive` or `/past`.
* Browse past competitions to review final leaderboards or practice all questions indefinitely in self-paced archive mode.

### 5. 💬 2-Way Feedback & Support Routing
* Direct forwarding of feedback tickets to the configured admin group formatted in clean blockquotes.
* **Multi-Reply & Staff Routing**: Admin replies sent to feedback messages automatically route directly to the original member's private chat.
* **Real-Time Edit Sync**: Editing an admin reply or user feedback dynamically updates the corresponding message in real time.

### 6. 👑 Admin Operations Command Center (`/admin`)
* **Interactive Creation Wizard**: Step-by-step title, category, and schedule setup.
* **Schedule & Exam Timer Editors**: Update start/end timestamps and exam time limits anytime.
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
| `/archive` / `/past` | Browse archived challenges to practice questions |
| `/leaderboard` | View weekly & monthly championship standings |
| `/rules` | View how the two-factor scoring formula works |
| `/guidelines` | Read universal community rules & code of conduct |
| `/feedback` / `/support` | Submit a ticket/suggestion to the core admin team |
| `/about` | Learn about AWS Student Builder Group AASTU |
| `/help` | Display shortcuts and command list |
| `/cancel` | Cancel current text input state and return to main menu |
| `/admin` | Open Admin Operations Command Center *(restricted)* |

---

## 📂 Project Architecture

```
AWS-SBG-Community_Bot/
├── main.py                     # Local development polling launcher
├── requirements.txt            # Python dependencies (psycopg, telegram, etc.)
├── vercel.json                 # Vercel serverless routing configuration
├── .env.example                # Environment variables template
├── api/
│   └── webhook.py              # Vercel serverless Telegram webhook handler
├── app/
│   ├── bot.py                  # Bot application factory, router & text handlers
│   ├── db.py                   # SQLite (dev) & Supabase PostgreSQL (prod) layer
│   └── challenge/
│       ├── models.py           # Enums & challenge data structures
│       ├── scoring.py          # Decoupled accuracy & speed scoring math
│       ├── keyboards.py        # Inline keyboards (quiz options, menus, admin)
│       ├── service.py          # Business logic, timer capping, leaderboards & CSV parser
│       ├── handlers.py         # Quiz lifecycle, guidelines & student views
│       └── admin.py            # Admin operations, report cards & broadcast
└── tests/
    ├── test_bot.py             # Feedback routing, menus, shortcuts & admin security
    ├── test_challenge.py       # Challenge lifecycle, questions CRUD, time capping & archive
    └── test_scoring.py         # Mathematical scoring formulas & speed multipliers
```

---

## 💻 Local Setup & Development

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/<YOUR_USERNAME>/AWS-SBG-Community_Bot.git
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

# Optional: Supabase PostgreSQL (if omitted, automatically defaults to local SQLite bot.db)
# DATABASE_URL=postgresql://postgres.xxx:password@aws-0-region.pooler.supabase.com:6543/postgres
```

### 3. Run Locally (Long-Polling Mode)
```bash
python main.py
```

### 4. Run Automated Test Suite
```bash
python -m pytest tests/ -v
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

---

## 👥 Contributing & Community

* **Organization:** AWS Student Builder Group — Addis Ababa Science and Technology University (AASTU)
* **Telegram Channel:** [@AWSAASTU](https://t.me/AWSAASTU)
* **License:** MIT
