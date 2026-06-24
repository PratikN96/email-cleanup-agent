#!/usr/bin/env python3
"""
Email Cleanup Agent — runs in GitHub Actions.

Uses OpenRouter (Google Gemini 2.0 Flash) to read and classify each email
as PROMOTIONAL or KEEP, then deletes promos and sends a Telegram report.
"""

import imaplib
import email
import os
import time
import html
import requests
from email.header import decode_header
import re

# ── Config from env vars (set as GitHub Secrets) ──
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASS = os.getenv("IMAP_PASS")          # App password if 2FA
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
MAX_EMAILS = int(os.getenv("MAX_EMAILS", "50"))

# ── Helpers ──

def decode_str(s):
    """Decode email subject/from headers."""
    try:
        decoded_parts = decode_header(s)
        return "".join(
            part.decode(charset or "utf-8") if isinstance(part, bytes) else part
            for part, charset in decoded_parts
        )
    except:
        return str(s)

def clean_text(text):
    """Strip HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text[:2000]  # truncate for context

def classify_with_llm(subject, sender, body_preview):
    """Send email to OpenRouter → returns 'promo' or 'keep' with reason."""
    prompt = f"""You are an email classifier. Read this email and decide:

CATEGORIES:
- PROMO: newsletters, marketing, deals, sales, offers, discounts, ads, spam, unsolicited bulk
- KEEP: transactional (receipts, confirmations, 2FA, notifications), personal, work, important

Email:
  From: {sender}
  Subject: {subject}
  Body (first 500 chars): {body_preview[:500]}

Reply with ONLY one word: "promo" or "keep". Then a short reason on the next line."""

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "You are a strict email classifier. Promotional = delete. Everything else = keep."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 50,
        "temperature": 0.1,
    }

    for attempt in range(3):
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            break
        if attempt < 2:
            print(f"⚠ API attempt {attempt + 1} failed ({resp.status_code}), retrying in 2s...")
            time.sleep(2)
    else:
        return "error", f"API failed after 3 attempts: {resp.status_code}: {resp.text[:200]}"

    result = resp.json()
    text = result["choices"][0]["message"]["content"].strip().lower()
    lines = text.split("\n")
    label = lines[0].strip()
    reason = lines[1] if len(lines) > 1 else ""
    return ("promo" if "promo" in label else "keep"), reason


def telegram_send(message):
    """Send report to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠ Telegram not configured — skipping notification.")
        return

    for parse_mode in ("Markdown", None):
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10,
        )
        result = resp.json()
        if result.get("ok"):
            print("✅ Telegram report sent.")
            return
        if parse_mode:
            print(f"⚠ Telegram Markdown send failed ({result.get('description')}) — retrying as plain text.")
        else:
            print(f"❌ Telegram send failed: {result.get('description')}")


# ── Main ──

def main():
    missing = [v for v in ("IMAP_USER", "IMAP_PASS", "OPENROUTER_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing required secrets: {', '.join(missing)}")

    print(f"📧 Connecting to {IMAP_SERVER}:{IMAP_PORT} ...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASS)
    mail.select("INBOX")

    stats = {"checked": 0, "deleted": 0, "kept": 0, "errors": 0}
    report_lines = []

    try:
        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            print("No new emails.")
            telegram_send("✅ **Email Cleanup** — No new emails today.")
            return

        ids = data[0].split()[:MAX_EMAILS]
        print(f"Found {len(ids)} unread emails. Processing ...")

        for eid in ids:
            status, data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue

            msg = email.message_from_bytes(data[0][1])
            subject = decode_str(msg.get("Subject", "")) or "(no subject)"
            sender = decode_str(msg.get("From", "")) or "(unknown)"

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
                    elif part.get_content_type() == "text/html" and not body:
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

            body_clean = clean_text(body)

            label, reason = classify_with_llm(subject, sender, body_clean)

            if label == "promo":
                if not DRY_RUN:
                    mail.store(eid, "+FLAGS", "\\Deleted")
                stats["deleted"] += 1
                report_lines.append(f"🗑 `{subject[:60]}` — {reason}")
            elif label == "keep":
                stats["kept"] += 1
            else:
                stats["errors"] += 1
                report_lines.append(f"⚠ `{subject[:60]}` — {reason}")

            stats["checked"] += 1

        if not DRY_RUN:
            mail.expunge()
    finally:
        mail.logout()

    # ── Report ──
    report = (
        f"📧 **Email Cleanup Report**\n"
        f"Checked: {stats['checked']} | "
        f"Deleted: {stats['deleted']} | "
        f"Kept: {stats['kept']} | "
        f"Errors: {stats['errors']}\n\n"
        + ("_Dry run — nothing deleted._\n" if DRY_RUN else "")
        + "\n".join(report_lines[:10])
        + ("\n... +more" if len(report_lines) > 10 else "")
    )

    print(report)
    telegram_send(report)


if __name__ == "__main__":
    main()