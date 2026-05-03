"""
src/gmail_importer.py
Gmail job application response importer.

Reads recent Gmail, classifies job emails by keyword rules, matches to
existing tracked applications, and either updates status (high confidence)
or queues for manual review (medium confidence).

Setup (one-time):
    1. Go to https://console.cloud.google.com
    2. Create project → Enable Gmail API
    3. Credentials → OAuth 2.0 Client ID → Desktop App → Download JSON
    4. Save as credentials.json in project root
    5. First run opens browser for authorization → token.json saved automatically

Usage:
    python -m src.gmail_importer --dry-run     # preview, no writes
    python -m src.gmail_importer --apply       # write updates + queue

Environment (optional):
    GMAIL_LOOKBACK_DAYS=30   Override default lookback window
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from email import message_from_bytes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR  = BASE_DIR / "data"
CREDS_FILE  = BASE_DIR / "credentials.json"
TOKEN_FILE  = BASE_DIR / "token.json"
REVIEW_FILE = DATA_DIR / "gmail_review_queue.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Confidence thresholds
HIGH_CONFIDENCE  = 0.80   # auto-update (with --apply)
LOW_CONFIDENCE   = 0.50   # below this: skip entirely

# Lookback window
DEFAULT_LOOKBACK_DAYS = 30


# ---------------------------------------------------------------------------
# Classification rules — deterministic, no LLM
# ---------------------------------------------------------------------------

_INTERVIEW: List[str] = [
    "schedule an interview",
    "schedule a call",
    "available for a call",
    "would like to meet",
    "invite you to interview",
    "interview invitation",
    "next step",
    "shortlisted",
    "phone screen",
    "video interview",
    "technical interview",
    "hiring manager",
    "recruiter would like",
    "arrange a meeting",
    "zoom call",
    "teams call",
]

_REJECTED: List[str] = [
    "unfortunately",
    "not moving forward",
    "not selected",
    "we regret",
    "other candidates",
    "we have decided",
    "not be progressing",
    "won't be moving",
    "will not be moving",
    "position has been filled",
    "decided to pursue",
    "does not meet",
    "not a match",
    "keep your cv on file",
    "keep your resume on file",
    "no longer accepting",
]

_OFFER: List[str] = [
    "pleased to offer",
    "offer of employment",
    "job offer",
    "employment contract",
    "offer letter",
    "we would like to offer",
    "formal offer",
    "start date",
    "compensation package",
]

_JOB_SIGNAL: List[str] = [
    "application", "applying", "applied",
    "position", "role", "vacancy", "opportunity",
    "interview", "recruiter", "hiring",
    "cv", "resume", "candidate",
]

# Gmail search query — broad first pass before keyword classification
_GMAIL_QUERY = (
    'is:inbox ("application" OR "interview" OR "unfortunately" OR '
    '"recruiter" OR "offer" OR "shortlisted" OR "position")'
)

# Early filtering to block false positives
_BLOCKED_SENDER_DOMAINS = {
    "github.com", "accounts.google.com",
    "notifications@github.com", "noreply@github.com",
}

_BLOCKED_SUBJECT_PATTERNS = [
    "dispute", "regulatory escalation", "maintenance contract",
    "sewage", "oauth application", "security alert",
    "invoice", "payment", "receipt",
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ClassifiedEmail:
    message_id: str
    subject: str
    sender: str
    date: str
    snippet: str
    body_text: str
    status: str           # applied | interview_scheduled | rejected | offer_extended | no_response
    classification_confidence: float
    links_found: List[str]
    company_hint: str     # extracted from sender domain or subject


@dataclass
class MatchResult:
    email: ClassifiedEmail
    matched_application: Optional[Dict[str, Any]]
    match_confidence: float
    match_reason: str
    action: str           # update | queue | skip
    proposed_status: str


@dataclass
class ImportReport:
    run_at: str
    dry_run: bool
    emails_fetched: int = 0
    emails_classified: int = 0
    emails_skipped: int = 0
    updates_applied: int = 0
    queued_for_review: int = 0
    matches: List[MatchResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Gmail auth
# ---------------------------------------------------------------------------

def _get_gmail_service():
    """Authenticate and return Gmail API service. Opens browser on first run."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        logger.error(
            "gmail_deps_missing — install with: "
            "pip install google-auth google-auth-oauthlib google-api-python-client"
        )
        raise

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDS_FILE}. "
                    "Download from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        logger.info("gmail_token_saved")

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Email fetching
# ---------------------------------------------------------------------------

def _fetch_messages(service, lookback_days: int) -> List[Dict[str, Any]]:
    """Fetch message metadata matching the job query within the lookback window."""
    after = int((datetime.now() - timedelta(days=lookback_days)).timestamp())
    query = f"{_GMAIL_QUERY} after:{after}"

    messages = []
    page_token = None
    seen_threads = set()  # Deduplicate by thread ID

    while True:
        kwargs: Dict[str, Any] = {"userId": "me", "q": query, "maxResults": 100}
        if page_token:
            kwargs["pageToken"] = page_token

        resp = service.users().messages().list(**kwargs).execute()
        batch = resp.get("messages", [])

        # Deduplicate by thread ID
        for msg in batch:
            thread_id = msg.get("threadId")
            if thread_id and thread_id not in seen_threads:
                seen_threads.add(thread_id)
                messages.append(msg)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    logger.info(f"gmail_messages_fetched count={len(messages)} (deduped)")
    return messages


def _get_message_detail(service, msg_id: str) -> Optional[Dict[str, Any]]:
    """Fetch full message payload."""
    try:
        return service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
    except Exception:
        logger.warning(f"gmail_message_fetch_failed id={msg_id}", exc_info=True)
        return None


def _extract_body(payload: Dict[str, Any]) -> str:
    """Recursively extract plain text body from Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text

    return ""


def _extract_header(headers: List[Dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_links(text: str) -> List[str]:
    """Extract URLs from email body — used for link-based matching."""
    return re.findall(r'https?://[^\s<>"]+', text)


def _extract_company_hint(sender: str, subject: str) -> str:
    """
    Best-effort company name extraction.
    1. Sender display name before <email>
    2. Sender domain (strip common email providers)
    """
    _GENERIC_DOMAINS = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "greenhouse.io", "lever.co", "workday.com", "smartrecruiters.com",
        "successfactors.com", "taleo.net", "icims.com", "bamboohr.com",
    }

    # Try display name: "Acme Corp <hr@acme.com>"
    name_match = re.match(r'^"?([^"<]+)"?\s*<', sender)
    if name_match:
        name = name_match.group(1).strip()
        # Strip generic suffixes like "Recruiting", "Talent", "HR"
        name = re.sub(r'\b(recruiting|talent|careers|hr|noreply|no-reply)\b', '', name, flags=re.I).strip()
        if name and len(name) > 2:
            return name

    # Try sender domain
    domain_match = re.search(r'@([^>]+)', sender)
    if domain_match:
        domain = domain_match.group(1).lower().strip()
        if domain not in _GENERIC_DOMAINS:
            # "careers.acme.com" → "acme"
            parts = domain.replace(".com", "").replace(".io", "").replace(".co", "").split(".")
            return parts[-1].title()

    return ""


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify(subject: str, body: str) -> Tuple[str, float]:
    """
    Classify email into a status using keyword rules.
    Returns (status, confidence).
    """
    text = (subject + " " + body).lower()

    # Count keyword hits per category
    offer_hits     = sum(1 for kw in _OFFER      if kw in text)
    interview_hits = sum(1 for kw in _INTERVIEW  if kw in text)
    rejected_hits  = sum(1 for kw in _REJECTED   if kw in text)
    job_hits       = sum(1 for kw in _JOB_SIGNAL if kw in text)

    # Must have at least one job signal to be relevant
    if job_hits == 0:
        return "no_response", 0.0

    # Priority: offer > interview > rejected
    if offer_hits >= 1:
        confidence = min(0.70 + offer_hits * 0.08, 0.95)
        return "offer_extended", confidence

    if interview_hits >= 1:
        confidence = min(0.65 + interview_hits * 0.07, 0.95)
        return "interview_scheduled", confidence

    if rejected_hits >= 1:
        confidence = min(0.65 + rejected_hits * 0.07, 0.95)
        return "rejected", confidence

    # Has job signal but no clear classification
    return "applied", 0.40


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _build_application_index(
    applications: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build lookup structures for fast matching."""
    by_link: Dict[str, Dict[str, Any]] = {}
    by_company: Dict[str, List[Dict[str, Any]]] = {}

    for app in applications:
        link = (app.get("link") or "").strip()
        if link:
            by_link[link] = app

        company = (app.get("company") or "").lower().strip()
        if company:
            by_company.setdefault(company, []).append(app)

    return {"by_link": by_link, "by_company": by_company}


def _match_email_to_application(
    email: ClassifiedEmail,
    index: Dict[str, Any],
    applications: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], float, str]:
    """
    Try to match a classified email to an existing application.
    Returns (application, confidence, reason).
    """
    by_link    = index["by_link"]
    by_company = index["by_company"]

    # 1. Exact link match in email body (highest confidence)
    for link in email.links_found:
        # Normalize LinkedIn URLs (strip tracking params)
        clean = re.sub(r'\?.*$', '', link)
        if clean in by_link:
            return by_link[clean], 0.95, f"exact_link_match:{clean}"
        # Try prefix match for job IDs
        for stored_link, app in by_link.items():
            if _link_similarity(clean, stored_link) >= 0.90:
                return app, 0.88, f"link_similarity:{stored_link}"

    # 2. Company name match
    hint = email.company_hint.lower().strip()
    if hint and len(hint) > 2:
        # Exact company match
        if hint in by_company:
            candidates = by_company[hint]
            # If only one application at this company, high confidence
            if len(candidates) == 1:
                return candidates[0], 0.82, f"company_exact:{hint}"
            # Multiple at same company — try title disambiguation
            for c in candidates:
                title = (c.get("title") or "").lower()
                subj  = email.subject.lower()
                if any(token in subj for token in title.split() if len(token) > 3):
                    return c, 0.85, f"company+title:{hint}"
            # Return most recent if ambiguous
            recent = max(candidates, key=lambda x: x.get("date_applied", ""))
            return recent, 0.65, f"company_ambiguous:{hint}"

        # Partial company match
        for company_key, candidates in by_company.items():
            if hint in company_key or company_key in hint:
                if len(candidates) == 1:
                    return candidates[0], 0.72, f"company_partial:{company_key}"

    # 3. Subject-line token match against job titles
    subj_tokens = set(re.findall(r'\b\w{4,}\b', email.subject.lower()))
    best_app: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for app in applications:
        title_tokens = set(re.findall(r'\b\w{4,}\b', (app.get("title") or "").lower()))
        overlap = subj_tokens & title_tokens
        if overlap:
            score = len(overlap) / max(len(title_tokens), 1) * 0.60
            if score > best_score:
                best_score = score
                best_app = app

    if best_app and best_score >= LOW_CONFIDENCE:
        return best_app, best_score, f"title_token_overlap:{best_score:.2f}"

    return None, 0.0, "no_match"


def _link_similarity(a: str, b: str) -> float:
    """Simple URL similarity — ratio of shared path segments."""
    a_parts = set(a.rstrip("/").split("/"))
    b_parts = set(b.rstrip("/").split("/"))
    if not a_parts or not b_parts:
        return 0.0
    return len(a_parts & b_parts) / len(a_parts | b_parts)


# ---------------------------------------------------------------------------
# Application updater
# ---------------------------------------------------------------------------

def _update_application(
    app: Dict[str, Any],
    new_status: str,
    email: ClassifiedEmail,
    dry_run: bool,
) -> bool:
    """Update application status. No-ops in dry_run mode."""
    if dry_run:
        return True

    try:
        from src.applications import update_application_status
        update_application_status(
            link=app.get("link", ""),
            status=new_status,
            notes=f"Auto-imported from Gmail: {email.subject[:80]}",
            date_updated=datetime.now().isoformat(),
        )
        logger.info(
            f"application_updated "
            f"link={app.get('link', '')[:60]} "
            f"status={new_status}"
        )
        return True
    except Exception:
        logger.exception("application_update_failed")
        return False


def _append_review_queue(match: MatchResult) -> None:
    """Append a low-confidence match to the review queue."""
    existing = []
    if REVIEW_FILE.exists():
        try:
            existing = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    entry = {
        "queued_at":          datetime.now().isoformat(),
        "subject":            match.email.subject,
        "sender":             match.email.sender,
        "date":               match.email.date,
        "classified_status":  match.email.status,
        "classification_confidence": match.email.classification_confidence,
        "company_hint":       match.email.company_hint,
        "matched_company":    (match.matched_application or {}).get("company"),
        "matched_title":      (match.matched_application or {}).get("title"),
        "matched_link":       (match.matched_application or {}).get("link"),
        "match_confidence":   match.match_confidence,
        "match_reason":       match.match_reason,
        "proposed_status":    match.proposed_status,
        "links_found":        match.email.links_found[:5],
    }
    existing.append(entry)

    tmp = REVIEW_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(REVIEW_FILE)
    logger.info(f"review_queue_updated count={len(existing)}")


# ---------------------------------------------------------------------------
# Main import flow
# ---------------------------------------------------------------------------

def run_import(dry_run: bool, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> ImportReport:
    report = ImportReport(run_at=datetime.now().isoformat(), dry_run=dry_run)

    # Load existing applications for matching
    from src.applications import get_applied_jobs
    applications = get_applied_jobs()
    if not applications:
        logger.warning("no_applications_tracked — nothing to match against")

    index = _build_application_index(applications)

    # Authenticate + fetch
    service = _get_gmail_service()
    raw_messages = _fetch_messages(service, lookback_days)
    report.emails_fetched = len(raw_messages)

    for msg_meta in raw_messages:
        detail = _get_message_detail(service, msg_meta["id"])
        if not detail:
            report.emails_skipped += 1
            continue

        headers  = detail.get("payload", {}).get("headers", [])
        subject  = _extract_header(headers, "Subject")
        sender   = _extract_header(headers, "From")
        date     = _extract_header(headers, "Date")
        snippet  = detail.get("snippet", "")
        body     = _extract_body(detail.get("payload", {}))
        links    = _extract_links(body)
        company  = _extract_company_hint(sender, subject)

        # --- Early filters ---
        # Minimum subject length
        if len(subject.strip()) < 10:
            report.emails_skipped += 1
            continue

        # Blocked sender domains
        sender_lower = sender.lower()
        if any(domain in sender_lower for domain in _BLOCKED_SENDER_DOMAINS):
            report.emails_skipped += 1
            continue

        # Blocked subject patterns
        subject_lower = subject.lower()
        if any(pat in subject_lower for pat in _BLOCKED_SUBJECT_PATTERNS):
            report.emails_skipped += 1
            continue

        status, cls_conf = _classify(subject, body)

        # Skip emails with no job signal
        if cls_conf < 0.30:
            report.emails_skipped += 1
            continue

        email = ClassifiedEmail(
            message_id=msg_meta["id"],
            subject=subject,
            sender=sender,
            date=date,
            snippet=snippet[:200],
            body_text=body[:500],
            status=status,
            classification_confidence=cls_conf,
            links_found=links,
            company_hint=company,
        )
        report.emails_classified += 1

        # Match to application
        matched_app, match_conf, match_reason = _match_email_to_application(
            email, index, applications
        )

        # Determine action
        overall_conf = cls_conf * match_conf if matched_app else 0.0

        if overall_conf >= HIGH_CONFIDENCE and matched_app:
            action = "update"
        elif overall_conf >= LOW_CONFIDENCE and matched_app:
            action = "queue"
        elif not applications and cls_conf >= 0.60:  # No apps to match, but good classification
            action = "queue"  # Queue for manual review
        else:
            action = "skip"

        match_result = MatchResult(
            email=email,
            matched_application=matched_app,
            match_confidence=match_conf,
            match_reason=match_reason,
            action=action,
            proposed_status=status,
        )
        report.matches.append(match_result)

        # Execute action
        if action == "update":
            if _update_application(matched_app, status, email, dry_run):
                report.updates_applied += 1
            else:
                # Failed update → queue instead
                _append_review_queue(match_result)
                report.queued_for_review += 1

        elif action == "queue":
            _append_review_queue(match_result)
            report.queued_for_review += 1

        # Log every match regardless of action
        logger.info(
            f"email_processed "
            f"action={action} "
            f"status={status} "
            f"cls_conf={cls_conf:.2f} "
            f"match_conf={match_conf:.2f} "
            f"company={company!r} "
            f"subject={subject[:60]!r}"
        )

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_report(report: ImportReport) -> None:
    mode = "DRY RUN — no writes" if report.dry_run else "APPLY MODE"
    print(f"\nGmail Import Report [{mode}]")
    print(f"{'─' * 60}")
    print(f"  Emails fetched:       {report.emails_fetched}")
    print(f"  Classified:           {report.emails_classified}")
    print(f"  Skipped (no signal):  {report.emails_skipped}")
    print(f"  Updates {'(preview)' if report.dry_run else 'applied'}:   {report.updates_applied}")
    print(f"  Queued for review:    {report.queued_for_review}")
    print(f"{'─' * 60}")

    if report.matches:
        print(f"\nMatches:")
        for m in report.matches:
            app_str = (
                f"{m.matched_application.get('company')} / {m.matched_application.get('title')}"
                if m.matched_application else "NO MATCH"
            )
            print(
                f"  [{m.action.upper():6}] {m.email.status:<22} "
                f"cls={m.email.classification_confidence:.2f}  "
                f"match={m.match_confidence:.2f}  "
                f"→ {app_str}"
            )
            print(f"           Subject: {m.email.subject[:70]}")

    if report.queued_for_review > 0:
        print(f"\nReview queue: {REVIEW_FILE}")
        print("Run with --apply after reviewing to process high-confidence updates.")

    print()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    parser = argparse.ArgumentParser(
        description="Import job application responses from Gmail.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview only — no writes")
    mode.add_argument("--apply",   action="store_true", help="Write updates and queue")
    parser.add_argument(
        "--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
        help=f"Lookback window in days (default: {DEFAULT_LOOKBACK_DAYS})"
    )

    args = parser.parse_args()

    try:
        report = run_import(dry_run=args.dry_run, lookback_days=args.days)
        _print_report(report)
        return 0
    except FileNotFoundError as exc:
        print(f"\n✗ Setup required: {exc}\n")
        return 1
    except Exception:
        logger.exception("gmail_import_failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
