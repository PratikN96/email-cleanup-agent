# Email Cleanup Agent

An AI-powered email cleanup agent that detects and removes promotional/spam emails using DeepSeek V4 Flash via OpenRouter. Runs on **GitHub Actions** — no laptop needed.

## How it works

```
Gmail → IMAP → Python script → OpenRouter (DeepSeek V4 Flash) → delete promos → Telegram report
```

1. Connects to Gmail via IMAP
2. Fetches unread emails
3. Sends each email to DeepSeek V4 Flash for classification (promo vs keep)
4. Deletes promotional emails
5. Sends a summary report to Telegram

## Cost

~$0.01–0.05 per run (classifying 10–20 emails with DeepSeek V4 Flash). Runs twice daily = **<$3/month**.

## Setup

### Prerequisites

- GitHub account
- Gmail account with [App Password](https://myaccount.google.com/apppasswords) enabled
- [OpenRouter](https://openrouter.ai) API key (with DeepSeek V4 Flash access)
- Telegram bot token (from [@BotFather](https://t.me/BotFather))

### 1. Fork / Clone

```bash
git clone https://github.com/PratikN96/email-cleanup-agent.git
cd email-cleanup-agent
```

### 2. Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** and add:

| Secret | Value |
|--------|-------|
| `IMAP_USER` | Your full Gmail address (e.g., `you@gmail.com`) |
| `IMAP_PASS` | Gmail App Password (16-character code) |
| `OPENROUTER_API_KEY` | Your OpenRouter API key |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather (e.g., `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID (get from [@userinfobot](https://t.me/userinfobot)) |

> **Gmail App Password:** Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → Select "Mail" → Generate. If you don't see this option, enable [2-Step Verification](https://myaccount.google.com/security) first.

### 3. Enable the Workflow

The workflow runs by default at **8:00 AM and 8:00 PM daily**. You can also trigger it manually from the Actions tab.

The first few runs will be **dry-runs** (report only, no deletion). To enable actual deletion:

1. Go to `.github/workflows/email-cleanup.yml`
2. Change `DRY_RUN: "true"` to `DRY_RUN: "false"`
3. Commit and push

## Safety

- **Dry-run mode** is enabled by default — emails are classified and reported but never deleted
- Whitelist support can be added by modifying the classification prompt
- Only processes **unread** emails (up to 20 per run to stay within budget)

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `IMAP_SERVER` | `imap.gmail.com` | IMAP server address |
| `IMAP_PORT` | `993` | IMAP SSL port |
| `MAX_EMAILS` | `20` | Max emails to process per run |
| `DRY_RUN` | `true` | Report-only mode (no deletion) |
| `OPENROUTER_MODEL` | `deepseek/deepseek-v4-flash` | LLM model for classification |

## Tech Stack

- **Python 3.12** — `imaplib`, `email`, `requests`
- **OpenRouter** — Google Gemini 2.0 Flash for email classification
- **GitHub Actions** — Scheduled CI runner
- **Telegram Bot API** — Daily reports

## Privacy

- Your email content is sent to OpenRouter for classification (DeepSeek V4 Flash)
- No data is stored — emails are classified and actioned in one pass
- API keys are stored as GitHub Secrets, never in code