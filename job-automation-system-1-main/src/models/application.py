"""
src/models/application.py
Domain model for a tracked job application.
"""
from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class Application(TypedDict, total=False):
    job_id: str
    title: str
    company: str
    location: str
    link: str
    score: int
    status: str          # see VALID_STATUSES in src/applications.py
    date_applied: str
    date_updated: str
    notes: str
    interview_date: Optional[str]
    rejection_reason: Optional[str]
