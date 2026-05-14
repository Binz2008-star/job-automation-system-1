import json
import os
from datetime import datetime
from typing import List, Dict, Any

JOB_HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_history.json")


def load_job_history() -> List[Dict[str, Any]]:
    """Load job history from JSON file."""
    try:
        with open(JOB_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_job_history(jobs: List[Dict[str, Any]]) -> None:
    """Save job history to JSON file."""
    with open(JOB_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)


def add_jobs_to_history(scored_jobs: List[tuple]) -> None:
    """Add scored jobs to history, avoiding duplicates."""
    history = load_job_history()
    current_date = datetime.now().isoformat()

    # Create set of existing job IDs for deduplication
    existing_ids = set()
    for job in history:
        job_id = f"{job.get('title', '')}_{job.get('company', '')}_{job.get('location', '')}"
        existing_ids.add(job_id.lower())

    new_jobs_added = 0
    for job, score in scored_jobs:
        # Create unique job ID
        job_id = f"{job.get('title', '')}_{job.get('company', '')}_{job.get('location', '')}"

        # Skip if already exists
        if job_id.lower() in existing_ids:
            continue

        # Add to history
        job_entry = {
            "title": job.get('title', ''),
            "company": job.get('company', ''),
            "location": job.get('location', ''),
            "score": score,
            "link": job.get('link', ''),
            "date_found": current_date,
            "source": "jobspy",
            "description": str(job.get('description', ''))[:500]  # Truncate description
        }

        history.append(job_entry)
        existing_ids.add(job_id.lower())
        new_jobs_added += 1

    if new_jobs_added > 0:
        save_job_history(history)
        print(f"Added {new_jobs_added} new jobs to history")
    else:
        print("No new jobs to add to history")


def get_job_stats() -> Dict[str, Any]:
    """Get basic statistics about job history."""
    history = load_job_history()

    if not history:
        return {
            "total_jobs": 0,
            "average_score": 0,
            "top_companies": [],
            "top_titles": [],
            "highest_scored": []
        }

    # Calculate statistics
    total_jobs = len(history)
    scores = [job.get('score', 0) for job in history]
    average_score = sum(scores) / len(scores) if scores else 0

    # Count companies
    companies = {}
    for job in history:
        company = job.get('company', '')
        if company:
            companies[company] = companies.get(company, 0) + 1

    # Count titles
    titles = {}
    for job in history:
        title = job.get('title', '')
        if title:
            titles[title] = titles.get(title, 0) + 1

    # Get top 10 highest scored jobs
    highest_scored = sorted(history, key=lambda x: x.get('score', 0), reverse=True)[:10]

    return {
        "total_jobs": total_jobs,
        "average_score": round(average_score, 1),
        "top_companies": sorted(companies.items(), key=lambda x: x[1], reverse=True)[:10],
        "top_titles": sorted(titles.items(), key=lambda x: x[1], reverse=True)[:10],
        "highest_scored": highest_scored
    }
