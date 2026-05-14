"""
src/filter.py
Job de-duplication filter.
  - load_seen_jobs() is called ONCE per filter_new_jobs() call (no N+1).
  - save_seen_jobs() uses atomic write.
  - Handles corrupt seen_jobs.json gracefully (returns empty set).
"""

import json
import os
import tempfile
from typing import Dict, List, Set

from src.db import get_seen_links, is_db_available

SEEN_JOBS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "seen_jobs.json"
)


def load_seen_jobs() -> Set[str]:
    """Load seen job IDs from DB (primary) or JSON fallback."""
    if is_db_available():
        try:
            db_links = get_seen_links()
            if db_links:
                return set(db_links)
        except Exception as e:
            print(f"⚠️ Database seen links failed, using JSON fallback: {e}")

    try:
        if not os.path.exists(SEEN_JOBS_FILE):
            return set()
        with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(str(x) for x in data if x)
            return set()
    except (json.JSONDecodeError, IOError, TypeError, ValueError):
        return set()


def save_seen_jobs(seen_jobs: Set[str]) -> None:
    """Atomically write seen jobs to JSON backup."""
    dir_ = os.path.dirname(SEEN_JOBS_FILE) or "."
    try:
        os.makedirs(dir_, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(sorted(seen_jobs), f, indent=2)
            os.replace(tmp_path, SEEN_JOBS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except IOError:
        pass


def _generate_job_id(job: Dict) -> str:
    """Stable job ID: link (preferred) or title_company_location composite."""
    link = (job.get("link") or "").strip()
    if link:
        return link
    title = job.get("title", "").strip()
    company = job.get("company", "").strip()
    location = job.get("location", "").strip()
    return f"{title}_{company}_{location}"


def filter_new_jobs(jobs: List[Dict]) -> List[Dict]:
    """
    Filter out jobs that have been seen before.
    Loads seen_jobs ONCE regardless of list size (no N+1).
    Returns only new (unseen) jobs.
    """
    if not jobs:
        return []

    seen_jobs = load_seen_jobs()  # single read
    new_jobs: List[Dict] = []
    new_job_ids: Set[str] = set()

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = _generate_job_id(job)
        if job_id and job_id not in seen_jobs and job_id not in new_job_ids:
            new_jobs.append(job)
            new_job_ids.add(job_id)

    if new_job_ids:
        seen_jobs.update(new_job_ids)
        save_seen_jobs(seen_jobs)

    return new_jobs
