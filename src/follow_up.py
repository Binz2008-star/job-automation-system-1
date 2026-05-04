from datetime import datetime, timedelta
from src.applications import get_applied_jobs
from src.telegram_bot import send_telegram_message

def get_due_followups(days=14):
    cutoff = datetime.now() - timedelta(days=days)
    due = []
    for job in get_applied_jobs():
        if job.get("status") != "applied":
            continue
        try:
            applied_at = datetime.fromisoformat(str(job.get("date_applied", "")))
            if applied_at <= cutoff:
                due.append(job)
        except (ValueError, TypeError):
            continue
    return due

def send_followup_reminders():
    due = get_due_followups()
    if not due:
        return False
    lines = ["Follow-up reminders (14+ days, no response)", ""]
    for job in due[:10]:
        lines.append(f"• {job.get('title')} - {job.get('company')}")
        lines.append(f"  {job.get('link', '')}")
    return send_telegram_message("\n".join(lines))

if __name__ == "__main__":
    send_followup_reminders()
