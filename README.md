# AWS SBG Community Bot

A Telegram bot for the AWS Student Builder Group community that lets members submit feedback, suggestions, and issues directly to the admin/core team.

## What the bot does

The bot gives community members a fast and friendly way to:

- open the bot and see a visible menu
- view help and command shortcuts
- submit feedback through `/feedback`
- learn more about the community channel through `/about`

Once a member sends feedback, the bot forwards the message to the configured admin group with clean HTML formatting and blockquotes. If an admin replies to that forwarded message in the group, the bot sends the reply directly back to the original member.

## Member experience

Members can use either Telegram commands or the visible reply keyboard buttons.

### Commands

- `/start` — opens the welcome screen and menu
- `/help` — displays the visible command list
- `/feedback` — starts the feedback submission flow
- `/about` — explains the purpose of the bot
- `/cancel` — stops the current feedback draft

### Visible keyboard options

The main menu presents these quick actions:

- `📝 Submit Feedback`
- `ℹ️ About`
- `❓ Help`
- `❌ Cancel`

## Feedback response workflow

1. A member opens the bot and starts a feedback flow.
2. The bot asks the member to send their feedback text.
3. The bot forwards the message to the configured admin group.
4. An admin replies to that forwarded message in the admin group.
5. The bot looks up the original recipient from the database and sends the admin reply back to the member.

## Project structure

- `main.py` — local polling launcher and container entrypoint
- `app/bot.py` — bot logic, command handlers, keyboard setup, and application factory
- `app/db.py` — persistence layer supporting SQLite (automatic default, zero-config) and PostgreSQL (via `DATABASE_URL` for Supabase / Neon / Railway)
- `api/webhook.py` — Vercel serverless webhook entrypoint
- `vercel.json` — Vercel serverless routing configuration
- `.env` — environment configuration (bot token, admin group ID, database URL)
- `requirements.txt` — Python dependency list

## Setup & Local Development

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your credentials:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
ADMIN_GROUP_CHAT_ID=your_admin_group_chat_id
```

4. Start the bot locally in polling mode:

```bash
python main.py
```
*(The bot will automatically create and use `bot.db` via SQLite with zero extra configuration).*

5. Run unit tests:

```bash
python -m pytest tests/
```

## Deployment to Vercel (Serverless)

Deploying to Vercel ensures instant response times with zero server sleep/cold starts:

1. **Get a Free PostgreSQL Database** (from [Supabase](https://supabase.com), [Neon](https://neon.tech), or Railway):
   - Create a free project and copy your connection string `DATABASE_URL` (e.g. `postgresql://postgres:...@...pooler.supabase.com:5432/postgres`).

2. **Deploy to Vercel**:
   - Import this repository on Vercel.
   - Configure the following Environment Variables in Vercel project settings:
     - `TELEGRAM_BOT_TOKEN`
     - `ADMIN_GROUP_CHAT_ID`
     - `DATABASE_URL`
     - `WEBHOOK_SECRET` (optional, for secure webhook verification)

3. **Register the Webhook with Telegram**:
   Set your Telegram bot webhook URL to your Vercel deployment:
   ```
   https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<YOUR_VERCEL_PROJECT>.vercel.app/api/webhook
   ```

## Contributor workflow

1. Create a feature branch (`git checkout -b feature/your-feature-name`).
2. Make your changes and test locally with `python main.py` using your personal test bot.
3. Verify test suite passes (`python -m pytest tests/`).
4. Commit and push your feature branch.
5. Open a Pull Request on GitHub.


