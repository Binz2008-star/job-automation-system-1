"""
src/models/job.py
Domain model for a job posting. Framework-agnostic.
"""
from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class Job(TypedDict, total=False):
    id: str
    title: str
    company: str
    location: str
    link: str
    score: int
    match_reason: str
    source: str
    date_found: Optional[str]
    seen: bool
