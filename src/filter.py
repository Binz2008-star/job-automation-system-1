import json
import os
from typing import List, Dict, Set

SEEN_JOBS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "seen_jobs.json")


def load_seen_jobs() -> Set[str]:
    """Load seen jobs from JSON file. Returns empty set if file doesn't exist or is corrupted."""
    try:
        if not os.path.exists(SEEN_JOBS_FILE):
            return set()
        
        with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(data)
            return set()
    except (json.JSONDecodeError, IOError, TypeError):
        return set()


def save_seen_jobs(seen_jobs: Set[str]) -> None:
    """Save seen jobs to JSON file. Creates file if it doesn't exist."""
    try:
        os.makedirs(os.path.dirname(SEEN_JOBS_FILE), exist_ok=True)
        with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen_jobs), f, indent=2)
    except IOError:
        pass


def _generate_job_id(job: Dict) -> str:
    """Generate unique ID for a job based on title, company, and location."""
    title = job.get("title", "").strip()
    company = job.get("company", "").strip()
    location = job.get("location", "").strip()
    return f"{title}_{company}_{location}"


def filter_new_jobs(jobs: List[Dict]) -> List[Dict]:
    """Filter out jobs that have been seen before. Returns only new jobs."""
    seen_jobs = load_seen_jobs()
    new_jobs = []
    new_job_ids = set()
    
    for job in jobs:
        job_id = _generate_job_id(job)
        if job_id and job_id not in seen_jobs:
            new_jobs.append(job)
            new_job_ids.add(job_id)
    
    # Update seen jobs with new job IDs
    if new_job_ids:
        seen_jobs.update(new_job_ids)
        save_seen_jobs(seen_jobs)
    
    return new_jobs
