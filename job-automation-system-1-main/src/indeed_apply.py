"""
src/indeed_apply.py
Indeed Easy Apply Engine

Only targets jobs that show the "Easily apply" badge — all external ATS
redirects are skipped at the card-scan stage, before any page load.

Architecture:
  Phase 1 — Search : scrape ae.indeed.com for target roles
  Phase 2 — Filter : badge present + dedup + spam/age guard
  Phase 3 — Apply  : fill Indeed in-platform apply widget (iframe)
  Phase 4 — Track  : persist to applied_jobs.json + DB

Environment variables:
    INDEED_ENABLED=false
    INDEED_DRY_RUN=false
    INDEED_HEADLESS=false
    INDEED_MAX_PER_RUN=3
    INDEED_DAILY_LIMIT=15
    INDEED_COOLDOWN_SECONDS=120
    INDEED_SLOW_MO=800
    INDEED_MAX_JOB_AGE_DAYS=14
    INDEED_SCORE_THRESHOLD=0
    NG_PROFILE_DIR=data/ng_profile   (shared persistent browser profile)
    CV_PATH=data/cv.pdf
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

from dotenv import load_dotenv
from playwright.sync_api import (
    BrowserContext,
    Frame,
    Page,
    Playwright,
    TimeoutError as PWTimeout,
    sync_playwright,
)

from src.applications import is_applied, mark_applied
from src.db import is_db_available

load_dotenv()
logger = logging.getLogger("indeed_apply")

BASE_DIR       = Path(__file__).resolve().parent.parent
RATE_FILE      = BASE_DIR / "data" / "indeed_apply_rate.json"
INDEED_BASE    = "https://ae.indeed.com"


# ── Config ────────────────────────────────────────────────────────────────────

def _env_bool(k: str, d: bool = False) -> bool:
    return os.getenv(k, str(d)).lower() in ("1", "true", "yes")

def _env_int(k: str, d: int) -> int:
    try:
        return int(os.getenv(k, str(d)))
    except ValueError:
        return d


INDEED_ENABLED    = _env_bool("INDEED_ENABLED", False)
INDEED_DRY_RUN    = _env_bool("INDEED_DRY_RUN", False)
INDEED_HEADLESS   = _env_bool("INDEED_HEADLESS", False)
INDEED_MAX_PER_RUN    = _env_int("INDEED_MAX_PER_RUN", 3)
INDEED_DAILY_LIMIT    = _env_int("INDEED_DAILY_LIMIT", 15)
INDEED_COOLDOWN       = _env_int("INDEED_COOLDOWN_SECONDS", 120)
INDEED_SLOW_MO        = _env_int("INDEED_SLOW_MO", 800)
INDEED_MAX_AGE_DAYS   = _env_int("INDEED_MAX_JOB_AGE_DAYS", 14)
INDEED_SCORE_THRESHOLD      = _env_int("INDEED_SCORE_THRESHOLD", 0)
INDEED_STREET_ADDRESS       = os.getenv("INDEED_STREET_ADDRESS", "")
INDEED_RELEVANT_JOB_TITLE   = os.getenv("INDEED_RELEVANT_JOB_TITLE", "")
INDEED_RELEVANT_COMPANY     = os.getenv("INDEED_RELEVANT_COMPANY", "")
INDEED_PROFILE_DIR          = BASE_DIR / os.getenv("NG_PROFILE_DIR", "data/ng_profile")
CV_PATH                 = BASE_DIR / os.getenv("CV_PATH", "data/cv.pdf")
INDEED_SKIP_COMPANIES    = os.getenv("INDEED_SKIP_COMPANIES", "").lower()


# ── Target roles ──────────────────────────────────────────────────────────────

TARGET_ROLES: List[str] = [
    "HSE Manager",
    "QHSE Manager",
    "EHS Manager",
    "Environmental Manager",
    "Compliance Manager",
    "Safety Manager",
]


# ── Title pre-filter ─────────────────────────────────────────────────────────────

KEEP_TITLE_KEYWORDS = [
    "hse", "qhse", "ehs", "hsse", "safety",
    "environmental", "environment", "esg", "sustainability"
]

REJECT_TITLE_KEYWORDS = [
    "project manager", "construction manager", "civil engineer",
    "site engineer", "quantity surveyor", "document controller",
    "coating technician", "automotive workshop", "cad supervisor",
    "f&b", "plumbing engineer", "electrical engineer",
    "architect", "draftsman", "sales", "healthcare",
    "nurse", "doctor", "intern", "uae national",
    "project engineer", "executive - ehs", "assistant manager",
    "hse officer"
]

def _title_allowed(title: str) -> bool:
    """Check if title passes keyword filters."""
    t = title.lower()
    if any(bad in t for bad in REJECT_TITLE_KEYWORDS):
        return False
    return any(good in t for good in KEEP_TITLE_KEYWORDS)


# ── Selectors ─────────────────────────────────────────────────────────────────

class _S:
    # Search results page
    SEARCH_URL   = INDEED_BASE + "/jobs?q={query}&l=UAE&filter=0"
    JOB_CARD     = ".job_seen_beacon"
    TITLE        = ".jobTitle span, h2 span[title]"
    COMPANY      = ".companyName, [data-testid='company-name']"
    # Easy Apply badge — present only for in-platform applications.
    # Multiple fallbacks because Indeed's class names change frequently.
    EASY_BADGE   = (
        ".iaLabel, "
        "[aria-label*='Easily apply'], "
        "[class*='easyApply'], "
        "[class*='ia-IndeedApply'], "
        "[data-testid='result-footer-item']:has-text('Easily apply'), "
        "[data-testid='attribute_snippet_testid']:has-text('Easily apply'), "
        "span:has-text('Easily apply'), "
        "div:has-text('Easily apply')"
    )
    CARD_LINK    = "a.jcs-JobTitle, h2 a"

    # Job detail page — ae.indeed.com uses "Apply with Indeed" for Easy Apply
    APPLY_BTN    = (
        "button[aria-label='Apply with Indeed'], "
        "button:has-text('Apply with Indeed'), "
        "[class*='indeed-apply-st'] button, "
        "#indeedApplyButton, "
        ".ia-IndeedApplyButton, "
        "button[aria-label*='Apply now'], "
        "button:has-text('Apply now')"
    )
    # Easy Apply iframe widget
    APPLY_IFRAME = "iframe[title*='Apply'], .ia-BasePage-iframe, iframe[src*='apply.indeed']"

    # Inside the apply iframe — multi-step wizard
    FIELD_NAME    = "[name='applicant.name'], #applicant\\.name, input[autocomplete='name']"
    FIELD_EMAIL   = "[name='applicant.emailAddress'], #applicant\\.emailAddress, input[type='email']"
    FIELD_PHONE   = "[name='applicant.phoneNumber'], #applicant\\.phoneNumber, input[type='tel']"
    FIELD_ADDRESS = (
        "input[aria-label*='Street address' i], "
        "input[aria-label*='street' i], "
        "input[id*='streetAddress' i], "
        "input[id*='street_address' i], "
        "input[name*='streetAddress' i], "
        "input[name*='street_address' i], "
        "input[placeholder*='Street address' i], "
        "input[placeholder*='street' i]"
    )
    FIELD_JOB_TITLE = (
        "input[aria-label*='Job title' i], "
        "input[id*='jobTitle' i], "
        "input[name*='jobTitle' i], "
        "input[placeholder*='Job title' i]"
    )
    FIELD_COMPANY = (
        "input[aria-label*='Company' i], "
        "input[id*='company' i], "
        "input[name*='company' i], "
        "input[placeholder*='Company' i]"
    )
    FILE_INPUT    = "input[type='file']"
    CONTINUE_BTN  = "[data-testid='continue-button'], button:has-text('Continue'), button:has-text('Next')"
    SUBMIT_BTN   = (
        "[data-testid='submit-application-button'], "
        "button:has-text('Submit your application'), "
        "button:has-text('Submit application')"
    )
    SUCCESS      = (
        "[data-testid='application-submitted'], "
        "h1:has-text('has been submitted'), "
        "h1:has-text('Application submitted'), "
        "[class*='PostApply'], "
        "button:has-text('Return to job search'), "
        "a:has-text('Return to job search')"
    )


# ── Status + Result ───────────────────────────────────────────────────────────

class IndeedApplyStatus(str, Enum):
    SUCCESS           = "success"
    DRY_RUN           = "dry_run"
    ALREADY_APPLIED   = "already_applied"
    DISABLED          = "disabled"
    NO_EASY_APPLY     = "no_easy_apply"
    EXTERNAL_REDIRECT = "external_redirect"
    NO_APPLY_BUTTON   = "no_apply_button"
    IFRAME_MISSING    = "iframe_missing"
    SUBMIT_FAILED     = "submit_failed"
    NEEDS_PROFILE_DATA= "needs_profile_data"
    RATE_LIMITED      = "rate_limited"
    FAILED            = "failed"
    AUTH_REQUIRED     = "auth_required"
    SKIPPED_COMPANY   = "skipped_company"


@dataclass
class IndeedApplyResult:
    job_id:    str
    title:     str
    company:   str
    status:    IndeedApplyStatus
    message:   str
    easy_apply: bool = False
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ── Rate limiter ──────────────────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self, path: Path = RATE_FILE) -> None:
        self._path  = path
        self._state = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            with self._path.open() as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"date": "", "count": 0, "last_apply": None}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w") as f:
            json.dump(self._state, f)

    def _reset_if_new_day(self) -> None:
        today = date.today().isoformat()
        if self._state.get("date") != today:
            self._state = {"date": today, "count": 0, "last_apply": None}
            self._save()

    def can_apply(self) -> tuple[bool, str]:
        self._reset_if_new_day()
        if self._state["count"] >= INDEED_DAILY_LIMIT:
            return False, f"daily_limit {self._state['count']}/{INDEED_DAILY_LIMIT}"
        last = self._state.get("last_apply")
        if last:
            elapsed = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
            if elapsed < INDEED_COOLDOWN:
                return False, f"cooldown remaining={int(INDEED_COOLDOWN - elapsed)}s"
        return True, "ok"

    def record(self) -> None:
        self._reset_if_new_day()
        self._state["count"] += 1
        self._state["last_apply"] = datetime.utcnow().isoformat()
        self._save()

    @property
    def today_count(self) -> int:
        self._reset_if_new_day()
        return self._state["count"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jitter(base: float, extra: float = 60.0) -> None:
    time.sleep(random.uniform(base, base + extra))

def _wait(page: Any, lo: int = 1500, hi: int = 4000) -> None:
    page.wait_for_timeout(random.randint(lo, hi))

def _loc_text(scope: Any, sel: str) -> str:
    try:
        loc = scope.locator(sel)
        if loc.count() > 0:
            return loc.first.inner_text().strip()
    except Exception:
        pass
    return ""

def _loc_href(scope: Any, sel: str) -> str:
    try:
        loc = scope.locator(sel)
        if loc.count() > 0:
            href = loc.first.get_attribute("href") or ""
            return href if href.startswith("http") else urljoin(INDEED_BASE, href)
    except Exception:
        pass
    return ""

def _loc_exists(scope: Any, sel: str) -> bool:
    try:
        return scope.locator(sel).count() > 0
    except Exception:
        return False

def _detect_auth_required(scope: Any) -> bool:
    """Detect if current page/frame requires auth or Google SSO."""
    try:
        # Check URL
        url = scope.url.lower() if hasattr(scope, 'url') else ""
        auth_url_patterns = [
            "secure.indeed.com/auth",
            "/auth?",
            "/account/login",
            "accounts.google.com",
        ]
        if any(pattern in url for pattern in auth_url_patterns):
            return True

        # Check page text
        if _loc_exists(scope, "body"):
            page_text = scope.inner_text("body").lower()
            auth_text_patterns = [
                "continue with google",
                "create an account or sign in",
                "email address",
                "(not you?)",
                "sign in",
                "google",
            ]
            if any(pattern in page_text for pattern in auth_text_patterns):
                return True
    except Exception:
        pass
    return False

def _job_key(url: str) -> str:
    """Extract Indeed job key (jk=...) from URL for dedup."""
    if "jk=" in url:
        return url.split("jk=")[1].split("&")[0]
    return url


# ── Engine ────────────────────────────────────────────────────────────────────

class IndeedApplyEngine:
    """
    Indeed Easy Apply automation using persistent Chrome profile.

    Only applies to jobs showing the "Easily apply" badge — all external ATS
    links are skipped before any job page is loaded.

    Usage:
        with IndeedApplyEngine() as engine:
            results = engine.run(dry_run=True)   # scan only
            results = engine.run(dry_run=False)  # live apply
    """

    def __init__(self, rate_limiter: Optional[_RateLimiter] = None) -> None:
        self._rate          = rate_limiter or _RateLimiter()
        self._pw:   Optional[Playwright]    = None
        self._ctx:  Optional[BrowserContext] = None
        self._page: Optional[Page]          = None
        self._missing_field: str            = ""  # set by _fill_apply_form on profile-data gap

    def __enter__(self) -> "IndeedApplyEngine":
        INDEED_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._pw  = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(INDEED_PROFILE_DIR),
            headless=INDEED_HEADLESS,
            slow_mo=INDEED_SLOW_MO,
            ignore_https_errors=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1280, "height": 800},
        )
        self._page = (
            self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        )
        self._page.set_default_timeout(25_000)
        return self

    def __exit__(self, *_: Any) -> None:
        try:
            if self._ctx:
                self._ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        dry_run: bool = INDEED_DRY_RUN,
        max_applies: int = INDEED_MAX_PER_RUN,
    ) -> List[IndeedApplyResult]:
        """
        Scan Indeed for Easy Apply jobs and optionally apply.
        dry_run=True  → print badge-positive cards, no applications submitted.
        dry_run=False → apply up to max_applies jobs with Easy Apply.
        """
        if not INDEED_ENABLED and not dry_run:
            logger.info("indeed_apply_disabled INDEED_ENABLED=false")
            return [IndeedApplyResult(
                job_id="", title="", company="",
                status=IndeedApplyStatus.DISABLED,
                message="Set INDEED_ENABLED=true to enable live applies",
            )]

        easy_jobs, raw_badge_count, title_filtered_count = self._scan_all_roles()
        logger.info("indeed_easy_apply_found count=%d", len(easy_jobs))

        if dry_run:
            # Filter out already-applied jobs before displaying
            skipped_applied = 0
            eligible_jobs = []
            for job in easy_jobs:
                if is_applied(job):
                    skipped_applied += 1
                    logger.info("indeed_skip_applied title=%s company=%s",
                               job.get('title', '')[:60], job.get('company', '')[:40])
                else:
                    eligible_jobs.append(job)

            self._print_dry_run_report(eligible_jobs, raw_badge_count, title_filtered_count, skipped_applied)
            return [
                IndeedApplyResult(
                    job_id=j["link"], title=j["title"], company=j["company"],
                    status=IndeedApplyStatus.DRY_RUN,
                    message="dry_run — badge confirmed",
                    easy_apply=True,
                )
                for j in easy_jobs
            ]

        results: List[IndeedApplyResult] = []
        attempted = 0

        for job in easy_jobs:
            if attempted >= max_applies:
                break
            score = int(job.get("score", 0))
            if score < INDEED_SCORE_THRESHOLD:
                logger.info(
                    "indeed_skip_score score=%d threshold=%d title=%s",
                    score, INDEED_SCORE_THRESHOLD, job.get("title"),
                )
                continue
            r = self._process_job(job)
            if r:
                # Only count as attempt for statuses that actually try the apply flow
                if r.status in {
                    IndeedApplyStatus.SUCCESS,
                    IndeedApplyStatus.AUTH_REQUIRED,
                    IndeedApplyStatus.NEEDS_PROFILE_DATA,
                    IndeedApplyStatus.SUBMIT_FAILED,
                    IndeedApplyStatus.FAILED,
                    IndeedApplyStatus.NO_APPLY_BUTTON,
                    IndeedApplyStatus.IFRAME_MISSING,
                    IndeedApplyStatus.EXTERNAL_REDIRECT,
                }:
                    attempted += 1
                results.append(r)
                logger.info("indeed_result %s", json.dumps(r.to_dict()))
                if r.status == IndeedApplyStatus.AUTH_REQUIRED:
                    logger.warning("indeed_stopping_auth_required msg=%s", r.message)
                    break
                if r.status == IndeedApplyStatus.NEEDS_PROFILE_DATA:
                    logger.warning("indeed_stopping_needs_profile_data msg=%s", r.message)
                    break
                if r.status == IndeedApplyStatus.SUCCESS:
                    _jitter(INDEED_COOLDOWN, extra=60)

        logger.info(
            "indeed_run_complete applied=%d attempted=%d total=%d",
            sum(1 for r in results if r.status == IndeedApplyStatus.SUCCESS),
            attempted,
            len(results),
        )
        return results

    def apply_one(self, job: Dict[str, Any]) -> "IndeedApplyResult":
        """Apply to a single pre-fetched job dict.

        Unlike run(), this does not scan Indeed — it applies directly to the
        job passed in (which has already been discovered by the pipeline).
        Returns ALREADY_APPLIED when _process_job returns None.
        """
        result = self._process_job(job)
        if result is None:
            return IndeedApplyResult(
                job_id=job.get("link", ""),
                title=job.get("title", ""),
                company=job.get("company", ""),
                status=IndeedApplyStatus.ALREADY_APPLIED,
                message="job already applied",
            )
        return result

    # ── Phase 1: scan search pages for Easy Apply cards ───────────────────────

    def _scan_all_roles(self) -> tuple[List[Dict[str, Any]], int, int]:
        seen: set[str] = set()
        jobs: List[Dict[str, Any]] = []
        total_raw_badge = 0
        total_title_filtered = 0
        for role in TARGET_ROLES:
            role_jobs, raw_badge, title_filtered = self._scan_role(role)
            total_raw_badge += raw_badge
            total_title_filtered += title_filtered
            for job in role_jobs:
                key = _job_key(job["link"])
                if key and key not in seen:
                    seen.add(key)
                    jobs.append(job)
            _wait(self._page, 800, 1500)
        return self._score_jobs(jobs), total_raw_badge, total_title_filtered

    def _score_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not jobs:
            return jobs
        try:
            from src.scoring import score_job
            for job in jobs:
                job["score"] = score_job(job)
        except Exception:
            for job in jobs:
                job.setdefault("score", 0)
        return sorted(jobs, key=lambda j: int(j.get("score", 0)), reverse=True)

    def _scan_role(self, role: str) -> tuple[List[Dict[str, Any]], int, int]:
        assert self._page
        url = _S.SEARCH_URL.format(query=quote_plus(role))
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            _wait(self._page, 2000, 3500)
            # Wait for at least one card; if none appear within 8s the page
            # is likely a CAPTCHA or block — log the URL and move on.
            try:
                self._page.wait_for_selector(_S.JOB_CARD, timeout=8_000)
            except PWTimeout:
                logger.warning("indeed_no_cards_timeout role=%s url=%s",
                               role, self._page.url[:120])
        except Exception as exc:
            logger.warning("indeed_scan_failed role=%s error=%s", role, exc)
            return [], 0, 0

        cards = self._page.locator(_S.JOB_CARD)
        count = cards.count()
        logger.info("indeed_scan role=%r cards=%d", role, count)

        jobs: List[Dict[str, Any]] = []
        raw_badge_count = 0
        title_filtered_count = 0
        for i in range(count):
            card = cards.nth(i)
            # Badge check — only proceed for Easy Apply cards
            if not _loc_exists(card, _S.EASY_BADGE):
                continue

            raw_badge_count += 1
            title   = _loc_text(card, _S.TITLE)
            company = _loc_text(card, _S.COMPANY)
            link    = _loc_href(card, _S.CARD_LINK)

            if not link:
                continue

            # Title pre-filter - check BEFORE logging or appending
            if not _title_allowed(title):
                logger.info("indeed_skip_title title=%s company=%s", title[:80], company[:50])
                title_filtered_count += 1
                continue

            logger.info(
                "indeed_easy_apply_card title=%s company=%s link=%s",
                title[:60], company[:40], link[:80],
            )
            jobs.append({
                "title":    title,
                "company":  company,
                "location": "UAE",
                "link":     link,
                "source":   "indeed_easy_apply",
                "score":    0,
            })

        logger.info("indeed_scan_easy role=%r raw_badge=%d title_filtered=%d found=%d",
                   role, raw_badge_count, title_filtered_count, len(jobs))
        return jobs, raw_badge_count, title_filtered_count

    # ── Phase 2: filter ───────────────────────────────────────────────────────

    def _process_job(self, job: Dict[str, Any]) -> Optional[IndeedApplyResult]:
        if is_applied(job):
            return None

        allowed, reason = self._rate.can_apply()
        if not allowed:
            return IndeedApplyResult(
                job_id=job["link"], title=job["title"], company=job["company"],
                status=IndeedApplyStatus.RATE_LIMITED, message=reason,
            )

        try:
            return self._apply_one(job)
        except Exception as exc:
            logger.exception("indeed_apply_unhandled title=%s", job.get("title"))
            return IndeedApplyResult(
                job_id=job["link"], title=job["title"], company=job["company"],
                status=IndeedApplyStatus.FAILED, message=str(exc),
            )

    # ── Phase 3: apply ────────────────────────────────────────────────────────

    def _apply_one(self, job: Dict[str, Any]) -> IndeedApplyResult:
        assert self._page
        link    = job["link"]
        title   = job.get("title", "Unknown")
        company = job.get("company", "Unknown")

        def r(s: IndeedApplyStatus, m: str) -> IndeedApplyResult:
            return IndeedApplyResult(
                job_id=link, title=title, company=company,
                status=s, message=m, easy_apply=True,
            )

        # Check if company is in skip list
        if INDEED_SKIP_COMPANIES:
            company_lower = company.lower()
            skip_terms = [term.strip() for term in INDEED_SKIP_COMPANIES.split(",")]
            if any(term in company_lower for term in skip_terms):
                logger.info("indeed_skip_company company=%s skip_list=%s", company, INDEED_SKIP_COMPANIES)
                return r(IndeedApplyStatus.SKIPPED_COMPANY, f"company skipped: {company}")

        self._page.goto(link, wait_until="domcontentloaded", timeout=30_000)
        _wait(self._page, 2000, 3500)

        # Confirm we're still on Indeed (not an external redirect on page load)
        if "indeed.com" not in self._page.url:
            return r(IndeedApplyStatus.EXTERNAL_REDIRECT,
                     f"redirected to {self._page.url[:80]}")

        # Click the apply button — badge was confirmed on the search card,
        # no need to re-check on the detail page (different DOM element there)
        apply_loc = self._page.locator(_S.APPLY_BTN)
        if apply_loc.count() == 0:
            return r(IndeedApplyStatus.NO_APPLY_BUTTON, "apply button not found")

        apply_loc.first.click()
        _wait(self._page, 2000, 4000)

        # Check for auth interruption after clicking Apply
        if _detect_auth_required(self._page):
            return r(IndeedApplyStatus.AUTH_REQUIRED,
                     "auth required / Google SSO detected — skipped")

        # If click navigated away from Indeed it's an external ATS link
        if "indeed.com" not in self._page.url:
            return r(IndeedApplyStatus.EXTERNAL_REDIRECT,
                     f"apply redirected to {self._page.url[:80]}")

        # Locate the apply iframe (in-platform Easy Apply widget)
        frame = self._get_apply_frame()
        if frame is None:
            return r(IndeedApplyStatus.IFRAME_MISSING, "apply iframe not found")

        # Fill multi-step form
        self._missing_field = ""
        success = self._fill_apply_form(frame, job)
        if not success:
            if self._missing_field == "AUTH_REQUIRED":
                return r(IndeedApplyStatus.AUTH_REQUIRED,
                         "auth required / Google SSO detected — skipped")
            if self._missing_field:
                field, self._missing_field = self._missing_field, ""
                return r(IndeedApplyStatus.NEEDS_PROFILE_DATA,
                         f"missing {field} — set env var to fill required address field")
            return r(IndeedApplyStatus.SUBMIT_FAILED,
                     "form fill or submit failed — check browser")

        mark_applied(job, status="applied")
        self._rate.record()
        logger.info("indeed_apply_success title=%s daily=%d",
                    title, self._rate.today_count)
        return IndeedApplyResult(
            job_id=link, title=title, company=company,
            status=IndeedApplyStatus.SUCCESS,
            message="applied via Indeed Easy Apply",
            easy_apply=True,
        )

    def _get_apply_frame(self) -> Optional[Frame]:
        """Wait for and return the Indeed apply iframe frame context."""
        assert self._page
        try:
            iframe_el = self._page.wait_for_selector(
                _S.APPLY_IFRAME, timeout=10_000
            )
            if iframe_el:
                return iframe_el.content_frame()
        except PWTimeout:
            pass

        # Fallback: search all frames for apply.indeed.com
        for frame in self._page.frames:
            if "apply.indeed.com" in (frame.url or ""):
                return frame
        return None

    def _fill_apply_form(self, frame: Frame, job: Dict[str, Any]) -> bool:
        """Navigate Indeed's multi-step Easy Apply wizard."""
        name  = "Roben Edwan"
        email = os.getenv("INDEED_EMAIL", "robenedwan@gmail.com")
        phone = os.getenv("INDEED_PHONE", "")

        max_steps = 12
        for step in range(max_steps):
            _wait(frame.page, 1500, 2500)
            # Wait for any loading indicator to fully clear.
            # wait_for_selector(state='hidden') returns immediately when the
            # element doesn't yet exist, so we use wait_for_function instead,
            # which polls continuously until loading is gone.
            try:
                frame.wait_for_function(
                    """() => {
                        const el = document.querySelector('[data-testid="loading-indicator"]');
                        return !el || el.offsetParent === null
                            || getComputedStyle(el).display === 'none'
                            || getComputedStyle(el).visibility === 'hidden';
                    }""",
                    timeout=15_000,
                )
            except PWTimeout:
                logger.debug("indeed_loading_timeout step=%d", step)
            _wait(frame.page, 500, 1000)

            # Check for auth interruption at each step
            if _detect_auth_required(frame) or _detect_auth_required(frame.page):
                logger.warning("indeed_auth_detected step=%d", step)
                self._missing_field = "AUTH_REQUIRED"
                return False

            # Check for success
            if _loc_exists(frame, _S.SUCCESS):
                logger.info("indeed_form_success step=%d", step)
                return True

            # Upload resume if file input visible
            self._maybe_upload_cv(frame)

            # Fill contact fields (only when empty)
            self._fill_field(frame, _S.FIELD_NAME,  name)
            self._fill_field(frame, _S.FIELD_EMAIL, email)
            if phone:
                self._fill_field(frame, _S.FIELD_PHONE, phone)

            # Fill address field (profile-location step)
            if _loc_exists(frame, _S.FIELD_ADDRESS):
                if not INDEED_STREET_ADDRESS:
                    logger.warning("indeed_form_needs_address step=%d — set INDEED_STREET_ADDRESS", step)
                    self._missing_field = "INDEED_STREET_ADDRESS"
                    self._dump_form_debug(frame, step, job)
                    return False
                self._fill_field(frame, _S.FIELD_ADDRESS, INDEED_STREET_ADDRESS)

            # Fill relevant-experience step (job title + company)
            if _loc_exists(frame, _S.FIELD_JOB_TITLE) or _loc_exists(frame, _S.FIELD_COMPANY):
                if INDEED_RELEVANT_JOB_TITLE:
                    self._fill_field(frame, _S.FIELD_JOB_TITLE, INDEED_RELEVANT_JOB_TITLE)
                    self._fill_by_label(frame, "Job title", INDEED_RELEVANT_JOB_TITLE)
                if INDEED_RELEVANT_COMPANY:
                    self._fill_field(frame, _S.FIELD_COMPANY, INDEED_RELEVANT_COMPANY)
                    self._fill_by_label(frame, "Company", INDEED_RELEVANT_COMPANY)

            # Try submit button first, then continue/next
            if self._click_if_present(frame, _S.SUBMIT_BTN):
                _wait(frame.page, 2000, 4000)
                if _loc_exists(frame, _S.SUCCESS):
                    return True
                continue

            if self._click_if_present(frame, _S.CONTINUE_BTN):
                continue

            # No actionable button found — dump debug info and bail
            logger.warning("indeed_form_stuck step=%d title=%s",
                           step, job.get("title"))
            self._dump_form_debug(frame, step, job)
            return False

        logger.warning("indeed_form_max_steps_exceeded title=%s", job.get("title"))
        self._dump_form_debug(frame, max_steps, job)
        return False

    def _maybe_upload_cv(self, frame: Frame) -> None:
        if not CV_PATH.exists():
            return
        inp = frame.query_selector(_S.FILE_INPUT)
        if inp:
            try:
                inp.set_input_files(str(CV_PATH))
                frame.page.wait_for_timeout(1_000)
                logger.debug("cv_uploaded")
            except Exception as exc:
                logger.warning("cv_upload_failed error=%s", exc)

    def _fill_field(self, frame: Frame, sel: str, value: str) -> None:
        if not value:
            return
        try:
            inp = frame.query_selector(sel)
            if inp and not inp.input_value():
                inp.fill(value)
        except Exception:
            pass

    def _fill_by_label(self, frame: Any, label_text: str, value: str) -> None:
        """Fill the input associated with a label whose text contains label_text."""
        if not value:
            return
        try:
            result = frame.evaluate(
                """([text, val]) => {
                    const labels = [...document.querySelectorAll('label')];
                    const label = labels.find(l =>
                        l.innerText.toLowerCase().includes(text.toLowerCase())
                    );
                    if (!label) return 'no_label';
                    // find input via for= attr or next sibling/child
                    let inp = label.htmlFor
                        ? document.getElementById(label.htmlFor)
                        : label.querySelector('input, textarea, select')
                          || label.nextElementSibling?.querySelector('input, textarea, select')
                          || label.nextElementSibling;
                    if (!inp || !['INPUT','TEXTAREA','SELECT'].includes(inp.tagName)) return 'no_input';
                    if (inp.value) return 'already_filled';
                    inp.focus();
                    inp.value = val;
                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                    return 'filled';
                }""",
                [label_text, value],
            )
            logger.debug("fill_by_label label=%r result=%s", label_text, result)
        except Exception as exc:
            logger.debug("fill_by_label_failed label=%r error=%s", label_text, exc)

    def _click_if_present(self, frame: Any, sel: str) -> bool:
        """Click the first visible+enabled match. Skips hidden elements."""
        try:
            loc = frame.locator(sel)
            n = loc.count()
            for i in range(n):
                item = loc.nth(i)
                try:
                    if item.is_visible() and item.is_enabled():
                        item.click(timeout=8_000)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    # ── Debug dump ────────────────────────────────────────────────────────────

    def _dump_form_debug(self, frame: Frame, step: int, job: Dict[str, Any]) -> None:
        assert self._page
        ts      = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        stem    = f"indeed_form_stuck_{ts}"

        try:
            self._page.screenshot(path=str(log_dir / f"{stem}.png"), full_page=True)
            logger.info("debug_screenshot %s.png", stem)
        except Exception as exc:
            logger.warning("debug_screenshot_failed error=%s", exc)

        try:
            html = frame.content()
            (log_dir / f"{stem}.html").write_text(html, encoding="utf-8")
            logger.info("debug_html %s.html", stem)
        except Exception as exc:
            logger.warning("debug_html_failed error=%s", exc)

        try:
            info = frame.evaluate("""() => {
                const buttons = [...document.querySelectorAll(
                    'button, [role="button"], input[type="submit"], input[type="button"]'
                )].map(b => ({
                    tag:      b.tagName,
                    text:     (b.innerText || b.value || '').trim().slice(0, 120),
                    testid:   b.getAttribute('data-testid') || '',
                    type:     b.type || '',
                    disabled: b.disabled,
                    visible:  b.offsetParent !== null,
                }));
                const inputs = [...document.querySelectorAll('input, select, textarea')]
                    .map(i => ({
                        name:        i.name        || '',
                        id:          i.id          || '',
                        type:        i.type        || i.tagName.toLowerCase(),
                        placeholder: i.placeholder || '',
                        required:    i.required,
                        visible:     i.offsetParent !== null,
                    }));
                const labels = [...document.querySelectorAll('label')]
                    .map(l => l.innerText.trim().slice(0, 100))
                    .filter(t => t);
                const required = [...document.querySelectorAll('[required], [aria-required="true"]')]
                    .map(e => e.outerHTML.slice(0, 200));
                return { buttons, inputs, labels, required };
            }""")

            logger.info("debug_dump step=%d title=%s", step, job.get("title"))
            logger.info("  BUTTONS (%d):", len(info["buttons"]))
            for b in info["buttons"]:
                logger.info("    text=%r  testid=%r  type=%r  disabled=%s  visible=%s",
                            b["text"], b["testid"], b["type"], b["disabled"], b["visible"])
            logger.info("  INPUTS (%d):", len(info["inputs"]))
            for inp in info["inputs"]:
                logger.info("    name=%r  id=%r  type=%r  placeholder=%r  required=%s  visible=%s",
                            inp["name"], inp["id"], inp["type"],
                            inp["placeholder"], inp["required"], inp["visible"])
            logger.info("  LABELS: %s", info["labels"][:30])
            if info["required"]:
                logger.info("  REQUIRED FIELDS (%d):", len(info["required"]))
                for r in info["required"]:
                    logger.info("    %s", r[:200])
        except Exception as exc:
            logger.warning("debug_eval_failed error=%s", exc)

    # ── Dry-run report ────────────────────────────────────────────────────────

    def _print_dry_run_report(self, jobs: List[Dict[str, Any]], raw_badge_count: int, title_filtered_count: int, skipped_applied: int) -> None:
        threshold = INDEED_SCORE_THRESHOLD
        print(f"\n{'='*72}")
        print(f"  Indeed Easy Apply — DRY RUN  ({len(jobs)} badge-confirmed, scored)")
        print(f"{'='*72}")
        print(f"  {'#':>3}  {'Score':>5}  {'Title':<48}  Company")
        print(f"  {'-'*3}  {'-'*5}  {'-'*48}  {'-'*30}")
        if not jobs:
            print("  No 'Easily apply' jobs found for target roles.")
        for i, j in enumerate(jobs, 1):
            score = int(j.get("score", 0))
            flag  = " *" if score >= threshold else ""
            print(
                f"  {i:>3}  {score:>5}  {j['title'][:48]:<48}  {j['company'][:30]}{flag}"
            )
            print(f"         {j['link'][:72]}")
        print(f"{'='*72}")
        passing = sum(1 for j in jobs if int(j.get("score", 0)) >= threshold)
        score_filtered = len(jobs) - passing
        print(f"\n  Filter Summary:")
        print(f"    Raw badge count:          {raw_badge_count}")
        print(f"    Title filtered:           {title_filtered_count}")
        print(f"    Skipped (already applied): {skipped_applied}")
        print(f"    Score filtered (<{threshold}):     {score_filtered}")
        print(f"    Final eligible count:     {passing}")
        print(f"\n  * = score ≥ {threshold}  ({passing} jobs would proceed to apply)\n")


# ── Pipeline entry point ──────────────────────────────────────────────────────

def run_indeed_apply(
    dry_run: bool = INDEED_DRY_RUN,
    max_applies: int = INDEED_MAX_PER_RUN,
) -> List[IndeedApplyResult]:
    """
    Entry point for external callers and run_daily pipeline.

    dry_run=True  → scan and report, no applications submitted.
    dry_run=False → apply to Easy Apply jobs (requires INDEED_ENABLED=true).
    """
    with IndeedApplyEngine() as engine:
        return engine.run(dry_run=dry_run, max_applies=max_applies)
