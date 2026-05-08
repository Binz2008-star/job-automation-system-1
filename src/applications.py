"""
src/applications.py
Application tracking with:
  - Cross-process file locking (filelock) to prevent race conditions
  - Atomic writes (tempfile + os.replace) to prevent corruption
  - Collision-resistant SHA-256 job IDs with backward-compat fallback
  - Status validation before write
  - Batch is_applied() to avoid N+1 file reads
"""

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

from filelock import FileLock, Timeout as FileLockTimeout

APPLIED_JOBS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "applied_jobs.json"
)
_LOCK_FILE = APPLIED_JOBS_FILE + ".lock"

# In-process lock (belt-and-suspenders alongside the file lock)
_THREAD_LOCK = threading.RLock()

# Valid application statuses — enforced on every write
VALID_STATUSES: Set[str] = {
    "saved", "opened", "applied", "interview",
    "rejected", "offer", "decision_made",
}

_LOCK_TIMEOUT_S = 10  # max wait for file lock before raising


# ─── Low-level I/O ────────────────────────────────────────────────────────────

def _atomic_write(path: str, data: List[Dict[str, Any]]) -> None:
    """Write JSON atomically: write to temp file, then os.replace()."""
    dir_ = os.path.dirname(path) or "."
    os.makedirs(dir_, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)  # atomic on POSIX and Windows
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_applied_jobs() -> List[Dict[str, Any]]:
    """Load applied jobs. Returns [] on missing or corrupt file."""
    try:
        with open(APPLIED_JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_applied_jobs(jobs: List[Dict[str, Any]]) -> None:
    """Atomically save applied jobs (no lock — callers must hold it)."""
    _atomic_write(APPLIED_JOBS_FILE, jobs)


# ─── Job ID ───────────────────────────────────────────────────────────────────

def get_job_id(job: Dict[str, Any]) -> str:
    """
    Collision-resistant job ID.
    Primary key: SHA-256[:16] of the canonical link URL.
    Fallback (no link): SHA-256[:16] of normalised title|company|location.
    """
    if not isinstance(job, dict):
        return ""
    link = (job.get("link") or "").strip()
    if link:
        return hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
    raw = (
        (job.get("title") or "").strip().lower()
        + "|"
        + (job.get("company") or "").strip().lower()
        + "|"
        + (job.get("location") or "").strip().lower()
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _legacy_job_id(job: Dict[str, Any]) -> str:
    """Old ID format — kept only for backward-compat matching in is_applied()."""
    title = job.get("title", "").strip()
    company = job.get("company", "").strip()
    location = job.get("location", "").strip()
    return f"{title}_{company}_{location}".lower().replace(" ", "_")


def _normalize(s: str) -> str:
    return " ".join(s.lower().strip().split())


def _extract_indeed_jk(link: str) -> Optional[str]:
    if "jk=" in link:
        return link.split("jk=")[1].split("&")[0]
    return None


# ─── Core operations ──────────────────────────────────────────────────────────

def mark_applied(
    job: Dict[str, Any],
    status: str = "applied",
    notes: str = "",
) -> bool:
    """
    Mark a job as applied.
    Thread-safe and cross-process-safe via FileLock + atomic write.
    Returns True if newly added, False if already present.
    """
    if not isinstance(job, dict):
        return False
    if status not in VALID_STATUSES:
        status = "applied"

    job_id = get_job_id(job)
    if not job_id:
        return False

    try:
        with FileLock(_LOCK_FILE, timeout=_LOCK_TIMEOUT_S):
            with _THREAD_LOCK:
                applied_jobs = load_applied_jobs()
                if _is_in_list(job, applied_jobs):
                    print(f"Job already marked as applied: {job.get('title', '')}")
                    return False

                entry: Dict[str, Any] = {
                    "job_id": job_id,
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "location": job.get("location", ""),
                    "link": job.get("link", ""),
                    "score": job.get("score", 0),
                    "status": status,
                    "date_applied": datetime.now().isoformat(),
                    "date_updated": datetime.now().isoformat(),
                    "notes": notes or "",
                    "interview_date": None,
                    "rejection_reason": None,
                }
                applied_jobs.append(entry)
                save_applied_jobs(applied_jobs)

        print(f"✅ Marked as applied: {job.get('title', '')} - {job.get('company', '')}")
        return True

    except FileLockTimeout:
        print(f"⚠️ Could not acquire lock for mark_applied (timeout={_LOCK_TIMEOUT_S}s)")
        return False


def is_applied(job: Dict[str, Any]) -> bool:
    """
    Check if a job has been applied to.
    Checks: new hash ID, legacy string ID, exact link, Indeed jk= key,
    and normalised title+company match.
    """
    if not isinstance(job, dict):
        return False
    applied_jobs = load_applied_jobs()
    return _is_in_list(job, applied_jobs)


def is_applied_batch(jobs: List[Dict[str, Any]]) -> Dict[str, bool]:
    """
    Batch version of is_applied() — reads the file ONCE for all jobs.
    Returns {job_id: bool} mapping.
    """
    applied_jobs = load_applied_jobs()
    return {get_job_id(j): _is_in_list(j, applied_jobs) for j in jobs}


def _is_in_list(job: Dict[str, Any], applied_jobs: List[Dict[str, Any]]) -> bool:
    """Check if job matches any record in applied_jobs (already loaded)."""
    if not isinstance(job, dict):
        return False

    job_id = get_job_id(job)
    legacy_id = _legacy_job_id(job)
    job_link = (job.get("link") or "").strip()
    job_jk = _extract_indeed_jk(job_link)
    job_title_n = _normalize(job.get("title") or "")
    job_company_n = _normalize(job.get("company") or "")

    for rec in applied_jobs:
        if not isinstance(rec, dict):
            continue
        # 1. New hash ID
        if job_id and rec.get("job_id") == job_id:
            return True
        # 2. Legacy string ID (backward compat)
        if legacy_id and rec.get("job_id") == legacy_id:
            return True
        # 3. Exact link match
        rec_link = (rec.get("link") or "").strip()
        if job_link and rec_link and job_link == rec_link:
            return True
        # 4. Indeed jk= key
        if job_jk:
            rec_jk = _extract_indeed_jk(rec_link)
            if rec_jk and rec_jk == job_jk:
                return True
        # 5. Normalised title + company
        rec_title_n = _normalize(rec.get("title") or "")
        rec_company_n = _normalize(rec.get("company") or "")
        if (rec_title_n and rec_company_n
                and rec_title_n == job_title_n
                and rec_company_n == job_company_n):
            return True

    return False


def update_application_status(
    job: Dict[str, Any],
    status: str,
    notes: str = "",
) -> bool:
    """
    Update application status. Thread/process-safe. Status is validated.
    Returns True if record was found and updated.
    """
    if not isinstance(job, dict):
        return False
    if status not in VALID_STATUSES:
        print(f"❌ Invalid status '{status}'. Must be one of: {VALID_STATUSES}")
        return False

    try:
        with FileLock(_LOCK_FILE, timeout=_LOCK_TIMEOUT_S):
            with _THREAD_LOCK:
                applied_jobs = load_applied_jobs()
                job_id = get_job_id(job)
                legacy_id = _legacy_job_id(job)

                for rec in applied_jobs:
                    if not isinstance(rec, dict):
                        continue
                    if rec.get("job_id") in (job_id, legacy_id):
                        rec["status"] = status
                        rec["date_updated"] = datetime.now().isoformat()
                        if notes:
                            rec["notes"] = notes
                        if status == "interview" and not rec.get("interview_date"):
                            rec["interview_date"] = datetime.now().isoformat()
                        if status == "rejected" and notes:
                            rec["rejection_reason"] = notes
                        save_applied_jobs(applied_jobs)
                        print(f"✅ Updated status to {status}: {job.get('title', '')}")
                        return True

        print(f"❌ Applied job not found: {job.get('title', '')}")
        return False

    except FileLockTimeout:
        print("⚠️ Could not acquire lock for update_application_status")
        return False


def get_applied_jobs() -> List[Dict[str, Any]]:
    """Get all applied jobs (read-only, no lock needed)."""
    return load_applied_jobs()


def get_application_stats() -> Dict[str, Any]:
    """Compute application statistics from the persisted list."""
    applied_jobs = load_applied_jobs()

    if not applied_jobs:
        return {
            "total_applied": 0,
            "status_breakdown": {},
            "interviews_scheduled": 0,
            "rejections": 0,
            "pending": 0,
            "success_rate": 0.0,
        }

    status_counts: Dict[str, int] = {}
    interviews = rejections = pending = 0

    for job in applied_jobs:
        if not isinstance(job, dict):
            continue
        status = job.get("status", "applied")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "interview":
            interviews += 1
        elif status == "rejected":
            rejections += 1
        elif status == "applied":
            pending += 1

    total = len(applied_jobs)
    success_rate = (interviews / total * 100) if total else 0.0

    return {
        "total_applied": total,
        "status_breakdown": status_counts,
        "interviews_scheduled": interviews,
        "rejections": rejections,
        "pending": pending,
        "success_rate": round(success_rate, 1),
    }


def filter_unapplied_jobs(
    jobs_with_scores: List[tuple],
) -> List[tuple]:
    """
    Filter out already-applied jobs.
    Uses batch check to read applied_jobs.json exactly once.
    """
    if not jobs_with_scores:
        return []
    jobs = [j for j, _ in jobs_with_scores]
    applied_map = is_applied_batch(jobs)
    return [
        (job, score)
        for (job, score) in jobs_with_scores
        if not applied_map.get(get_job_id(job), False)
    ]


def mark_job_interactive(job: Dict[str, Any]) -> None:
    """Interactive helper to mark a job as applied (CLI use only)."""
    title = job.get("title", "N/A")
    company = job.get("company", "N/A")

    print("\n📝 Mark Job as Applied")
    print(f"Title: {title}")
    print(f"Company: {company}")
    print(f"Status options: {', '.join(sorted(VALID_STATUSES))}")

    status = input("Enter status (default: applied): ").strip().lower() or "applied"
    if status not in VALID_STATUSES:
        print("❌ Invalid status. Using 'applied'.")
        status = "applied"

    notes = input("Add notes (optional): ").strip()

    if mark_applied(job, status, notes):
        print(f"✅ Job marked as {status}")
    else:
        print("❌ Failed to mark job as applied")


def main() -> None:
    """Smoke-test application tracking."""
    print("🧪 Testing Application Tracking")

    sample_job = {
        "title": "HSE Manager",
        "company": "Test Company",
        "location": "Dubai, UAE",
        "link": "https://example.com/job1",
        "score": 75,
    }

    print("\n1. mark_applied:")
    mark_applied(sample_job)

    print("\n2. is_applied:")
    print(f"  Is applied: {is_applied(sample_job)}")

    print("\n3. stats:")
    print(f"  Stats: {get_application_stats()}")

    print("\n4. filter_unapplied_jobs:")
    pairs = [
        (sample_job, 75),
        ({"title": "QHSE Manager", "company": "Tech Co", "location": "Abu Dhabi",
          "link": "https://example.com/job2", "score": 68}, 68),
    ]
    unapplied = filter_unapplied_jobs(pairs)
    print(f"  Unapplied: {len(unapplied)}")


if __name__ == "__main__":
    main()
