"""
src/linkedin_importer.py
Import job applications from LinkedIn data export CSV.

LinkedIn exports job applications in a file called "Job Applications.csv"
inside the data archive ZIP. This tool:
  1. Reads the CSV
  2. Maps columns to application format
  3. Matches to existing job history where possible
  4. Saves to applied_jobs.json and Postgres (if available)
  5. Triggers a feedback loop learning cycle

Usage:
    python -m src.linkedin_importer --file "Job Applications.csv"
    python -m src.linkedin_importer --zip linkedin_export.zip
    python -m src.linkedin_importer --file "Job Applications.csv" --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR  = BASE_DIR / "data"

# LinkedIn CSV column names (may vary slightly between exports)
_POSSIBLE_COLUMNS = {
    "title":    ["Job Title", "Position", "Title", "Role"],
    "company":  ["Company Name", "Company", "Employer", "Organization"],
    "date":     ["Application Date", "Date Applied", "Applied On", "Date", "Applied At"],
    "status":   ["Status", "Application Status", "State"],
    "link":     ["Job URL", "URL", "Link", "Job Link", "Apply URL"],
    "location": ["Location", "Job Location", "City"],
}

# LinkedIn status → ResponseType mapping
_STATUS_MAP: Dict[str, str] = {
    "applied":              "applied",
    "submitted":            "applied",
    "in review":            "screening",
    "under review":         "screening",
    "screening":            "screening",
    "interviewing":         "interview_scheduled",
    "interview":            "interview_scheduled",
    "interview scheduled":  "interview_scheduled",
    "assessment":           "technical_assessment",
    "offer":                "offer_extended",
    "offer extended":       "offer_extended",
    "hired":                "offer_accepted",
    "rejected":             "rejected",
    "declined":             "rejected",
    "not selected":         "rejected",
    "withdrawn":            "rejected",
    "closed":               "no_response",
    "expired":              "no_response",
    "viewed":               "applied",
}


@dataclass
class ImportedApplication:
    title:      str
    company:    str
    link:       str
    status:     str
    date_applied: str
    location:   str = ""
    notes:      str = "Imported from LinkedIn export"
    score:      float = 0.0
    source:     str = "linkedin_import"


@dataclass
class ImportReport:
    total_rows:     int = 0
    imported:       int = 0
    skipped:        int = 0
    matched_jobs:   int = 0
    errors:         int = 0
    dry_run:        bool = False
    applications:   List[ImportedApplication] = field(default_factory=list)


def _find_column(headers: List[str], candidates: List[str]) -> Optional[str]:
    """Find matching column name case-insensitively."""
    headers_lower = {h.lower(): h for h in headers}
    for candidate in candidates:
        if candidate.lower() in headers_lower:
            return headers_lower[candidate.lower()]
    return None


def _parse_date(raw: str) -> str:
    """Parse various LinkedIn date formats to ISO."""
    if not raw or not raw.strip():
        return datetime.now().isoformat()

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw.strip(), fmt).isoformat()
        except ValueError:
            continue

    logger.debug(f"date_parse_failed raw={raw!r}")
    return datetime.now().isoformat()


def _normalize_status(raw: str) -> str:
    """Map LinkedIn status string to ResponseType value."""
    if not raw:
        return "applied"
    normalized = _STATUS_MAP.get(raw.lower().strip(), "applied")
    return normalized


def _build_link(row: Dict[str, str], link_col: Optional[str],
                company: str, title: str) -> str:
    """Build job link — use CSV value or generate a stable synthetic key."""
    if link_col and row.get(link_col, "").strip():
        return row[link_col].strip()
    # Synthetic but stable key for matching
    safe_company = company.lower().replace(" ", "-")[:30]
    safe_title   = title.lower().replace(" ", "-")[:30]
    return f"linkedin://imported/{safe_company}/{safe_title}"


def _load_job_index() -> Dict[str, Dict[str, Any]]:
    """Build index of existing job history for link matching."""
    try:
        from src.job_history import load_job_history
        jobs = load_job_history()
        return {j["link"]: j for j in jobs if j.get("link")}
    except Exception:
        logger.warning("job_history_load_failed — no link matching available")
        return {}


def parse_csv(
    csv_path: Path,
    job_index: Dict[str, Dict[str, Any]],
) -> Tuple[List[ImportedApplication], int, int]:
    """
    Parse LinkedIn Job Applications CSV.
    Returns (applications, skipped, errors).
    """
    applications: List[ImportedApplication] = []
    skipped = 0
    errors  = 0

    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Detect columns
        title_col    = _find_column(headers, _POSSIBLE_COLUMNS["title"])
        company_col  = _find_column(headers, _POSSIBLE_COLUMNS["company"])
        date_col     = _find_column(headers, _POSSIBLE_COLUMNS["date"])
        status_col   = _find_column(headers, _POSSIBLE_COLUMNS["status"])
        link_col     = _find_column(headers, _POSSIBLE_COLUMNS["link"])
        location_col = _find_column(headers, _POSSIBLE_COLUMNS["location"])

        logger.info(
            f"csv_columns_detected "
            f"title={title_col} company={company_col} "
            f"date={date_col} status={status_col} link={link_col}"
        )

        if not title_col and not company_col:
            logger.error("csv_unrecognized — no title or company column found")
            logger.error(f"available_columns: {headers}")
            return [], 0, 1

        for i, row in enumerate(reader, start=2):  # row 1 = header
            try:
                title   = (row.get(title_col,   "") if title_col   else "").strip()
                company = (row.get(company_col, "") if company_col else "").strip()

                if not title and not company:
                    skipped += 1
                    continue

                title   = title   or "Unknown Position"
                company = company or "Unknown Company"

                date_raw = row.get(date_col, "") if date_col else ""
                status_raw = row.get(status_col, "applied") if status_col else "applied"
                location = (row.get(location_col, "") if location_col else "").strip()

                link = _build_link(row, link_col, company, title)
                date_iso = _parse_date(date_raw)
                status   = _normalize_status(status_raw)

                # Score boost if matched to job history
                score = 0.0
                if link in job_index:
                    score = float(job_index[link].get("score", 0))

                app = ImportedApplication(
                    title=title,
                    company=company,
                    link=link,
                    status=status,
                    date_applied=date_iso,
                    location=location,
                    score=score,
                )
                applications.append(app)

            except Exception as exc:
                logger.warning(f"row_parse_error row={i} error={exc}")
                errors += 1

    return applications, skipped, errors


def extract_csv_from_zip(zip_path: Path, extract_to: Path) -> Optional[Path]:
    """Extract Job Applications CSV from LinkedIn ZIP archive."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        logger.info(f"zip_contents: {names}")

        # Look for job applications file
        candidates = [
            n for n in names
            if "job" in n.lower() and (
                "application" in n.lower() or "apply" in n.lower()
            )
        ]

        if not candidates:
            # Show all CSVs so user can identify manually
            csvs = [n for n in names if n.endswith(".csv")]
            logger.warning(f"no_job_applications_csv_found available_csvs={csvs}")
            return None

        target = candidates[0]
        logger.info(f"extracting: {target}")
        zf.extract(target, extract_to)
        return extract_to / target


def save_applications(
    applications: List[ImportedApplication],
    dry_run: bool,
) -> Tuple[int, int]:
    """
    Save applications to JSON and Postgres.
    Returns (saved_json, saved_db).
    """
    if dry_run:
        return len(applications), 0

    # Load existing to avoid duplicates
    from src.applications import get_applied_jobs, save_applied_jobs

    existing = get_applied_jobs()
    existing_links = {a.get("link", "") for a in existing}

    new_apps = []
    for app in applications:
        if app.link not in existing_links:
            new_apps.append({
                "title":        app.title,
                "company":      app.company,
                "link":         app.link,
                "location":     app.location,
                "status":       app.status,
                "score":        app.score,
                "date_applied": app.date_applied,
                "date_updated": app.date_applied,
                "notes":        app.notes,
                "source":       app.source,
            })

    if new_apps:
        save_applied_jobs(existing + new_apps)
        logger.info(f"json_saved count={len(new_apps)}")

    # Save to Postgres
    saved_db = 0
    try:
        from src.db import save_application, is_db_available
        if is_db_available():
            for app_dict in new_apps:
                if save_application(app_dict):
                    saved_db += 1
            logger.info(f"db_saved count={saved_db}")
    except Exception:
        logger.warning("db_save_failed — JSON only", exc_info=True)

    return len(new_apps), saved_db


def run_import(
    csv_path: Optional[Path] = None,
    zip_path: Optional[Path] = None,
    dry_run: bool = False,
) -> ImportReport:
    """Main import flow."""
    report = ImportReport(dry_run=dry_run)

    # Resolve CSV path
    if zip_path:
        tmp = DATA_DIR / "linkedin_tmp"
        tmp.mkdir(exist_ok=True)
        csv_path = extract_csv_from_zip(zip_path, tmp)
        if not csv_path:
            logger.error("job_applications_csv_not_found_in_zip")
            return report

    if not csv_path or not csv_path.exists():
        logger.error(f"csv_not_found path={csv_path}")
        return report

    logger.info(f"linkedin_import_start csv={csv_path} dry_run={dry_run}")

    job_index = _load_job_index()
    applications, skipped, errors = parse_csv(csv_path, job_index)

    report.total_rows  = len(applications) + skipped + errors
    report.skipped     = skipped
    report.errors      = errors
    report.applications = applications
    report.matched_jobs = sum(1 for a in applications if a.score > 0)

    saved_json, saved_db = save_applications(applications, dry_run)
    report.imported = saved_json

    logger.info(
        f"linkedin_import_complete "
        f"total={report.total_rows} "
        f"imported={report.imported} "
        f"matched_jobs={report.matched_jobs} "
        f"skipped={report.skipped} "
        f"errors={report.errors} "
        f"db_saved={saved_db}"
    )

    return report


def _print_report(report: ImportReport) -> None:
    mode = "DRY RUN" if report.dry_run else "IMPORTED"
    print(f"\nLinkedIn Import Report [{mode}]")
    print(f"{'─' * 55}")
    print(f"  Total rows processed:  {report.total_rows}")
    print(f"  Applications imported: {report.imported}")
    print(f"  Matched to job history:{report.matched_jobs}")
    print(f"  Skipped (empty rows):  {report.skipped}")
    print(f"  Errors:                {report.errors}")
    print(f"{'─' * 55}")

    if report.dry_run and report.applications:
        print(f"\nPreview (first 10):")
        for app in report.applications[:10]:
            print(f"  {app.status:<22} {app.company:<25} {app.title[:35]}")
        if len(report.applications) > 10:
            print(f"  ... and {len(report.applications) - 10} more")

    if not report.dry_run and report.imported > 0:
        print(f"\n✓ {report.imported} applications saved.")
        print("  Run feedback loop:")
        print("  python -m src.run_daily")
    print()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    parser = argparse.ArgumentParser(
        description="Import LinkedIn job applications into the tracking system."
    )
    parser.add_argument("--file", help="Path to Job Applications.csv")
    parser.add_argument("--zip",  help="Path to LinkedIn export ZIP file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only — no writes")
    args = parser.parse_args()

    if not args.file and not args.zip:
        parser.print_help()
        return 1

    csv_path = Path(args.file) if args.file else None
    zip_path = Path(args.zip)  if args.zip  else None

    report = run_import(csv_path=csv_path, zip_path=zip_path, dry_run=args.dry_run)
    _print_report(report)
    return 0 if report.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
