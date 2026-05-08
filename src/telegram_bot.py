"""
src/telegram_bot.py
Telegram notification helper.
  - All user-supplied fields are HTML-escaped (including link).
  - Messages are clamped to Telegram's 4 096-char hard limit.
"""

import html
import requests
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

_TELEGRAM_MAX_CHARS = 4096
_MAX_JOBS_PER_MESSAGE = 8  # conservative ceiling; adjust if needed


def _safe_html(value: object) -> str:
    """Convert any value to an HTML-escaped string."""
    return html.escape(str(value) if value is not None else "")


def _safe_link(value: object) -> str:
    """
    Sanitise a URL for use inside an HTML href attribute.
    Accepts only http/https schemes; anything else becomes '#'.
    """
    raw = str(value or "").strip()
    try:
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https"):
            return "#"
    except Exception:
        return "#"
    # Escape for HTML attribute context (handles quotes, angle brackets)
    return html.escape(raw, quote=True)


def send_telegram_message(message: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not all([bot_token, chat_id]):
        print("Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env file")
        return False

    # Hard-clamp to Telegram limit before every send
    if len(message) > _TELEGRAM_MAX_CHARS:
        truncation_note = "\n\n<b>... (message truncated)</b>"
        message = message[: _TELEGRAM_MAX_CHARS - len(truncation_note)] + truncation_note

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("Telegram message sent successfully")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending Telegram message: {e}")
        return False


def format_telegram_jobs(jobs_with_scores) -> str:
    """
    Format jobs for Telegram with HTML.
    All fields are escaped; links are scheme-validated.
    Message is clamped to 4 096 chars.
    """
    if not jobs_with_scores:
        return "<b>No new jobs found today.</b>"

    lines = [
        "<b>🔔 Job Hunting Daily Report</b>",
        f"Found {len(jobs_with_scores)} high-quality job matches",
        "",
    ]

    for job, score in list(jobs_with_scores)[:_MAX_JOBS_PER_MESSAGE]:
        title = _safe_html(job.get("title", "N/A"))
        company = _safe_html(job.get("company", "N/A"))
        location = _safe_html(job.get("location", "N/A"))
        link = _safe_link(job.get("link", ""))

        lines.extend([
            f"<b>📌 {title}</b>",
            f"🏢 {company}",
            f"📍 {location}",
            f"⭐ Score: {_safe_html(score)}",
            f'🔗 <a href="{link}">Apply</a>',
            "",
        ])

    message = "\n".join(lines)

    # Final hard clamp (defensive — send_telegram_message also clamps)
    if len(message) > _TELEGRAM_MAX_CHARS:
        truncation_note = "\n\n<b>... (truncated)</b>"
        message = message[: _TELEGRAM_MAX_CHARS - len(truncation_note)] + truncation_note

    return message
