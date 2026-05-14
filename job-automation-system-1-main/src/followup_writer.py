"""14-day follow-up message writer for submitted applications."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List


def generate_followup(job: Dict[str, Any]) -> str:
    title = job.get("title", "the role")
    company = job.get("company", "your team")
    return f"""Dear Hiring Manager,

I hope you are well. I wanted to follow up on my application for the {title} position at {company}.

I remain very interested in the opportunity and believe my UAE experience in environmental compliance, HSE leadership, ISO 14001 systems, and multi-site operations would allow me to contribute effectively.

Please let me know if any additional information would be helpful.

Kind regards,
Roben Edwan
"""


def due_for_followup(applied_job: Dict[str, Any], days: int = 14) -> bool:
    status = str(applied_job.get("status", "applied")).lower()
    if status not in {"applied", "saved", "opened"}:
        return False
    raw = applied_job.get("date_applied") or applied_job.get("applied_at")
    if not raw:
        return False
    try:
        applied_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return False
    return datetime.now() >= applied_at + timedelta(days=days)


def build_due_followups(applied_jobs: List[Dict[str, Any]], days: int = 14) -> List[Dict[str, str]]:
    return [
        {"title": str(job.get("title", "")), "company": str(job.get("company", "")), "message": generate_followup(job)}
        for job in applied_jobs
        if due_for_followup(job, days=days)
    ]
