"""
src/naukrigulf_apply.py
NaukriGulf Auto-Apply Engine

Uses persistent Chrome profile — no login automation needed.
Session cookies are preserved between runs.

Architecture:
  Phase 1 — Search: navigate NaukriGulf search results for target roles
  Phase 2 — Filter: reject spam / wrong roles / old jobs
  Phase 3 — Apply:  Quick Apply or standard Apply form
  Phase 4 — Track: persist results to DB + applied_jobs.json

Environment variables:
    NG_PROFILE_DIR=data/ng_profile        persistent Chrome user data dir
    NG_ENABLED=false                      master switch
    NG_DRY_RUN=false                      log intent without submitting
    NG_MAX_PER_RUN=3                      hard cap per execution
    NG_SCORE_THRESHOLD=0                  NaukriGulf jobs aren't pre-scored
    NG_COOLDOWN_SECONDS=120               between successful applies
    NG_DAILY_LIMIT=15                     conservative daily cap
    NG_SLOW_MO=800                        ms delay between actions
    NG_MAX_JOB_AGE_DAYS=14               reject jobs older than N days
    CV_PATH=data/cv.pdf                   CV file path
"""

from __future__ import annotations

import json
import logging
import os
import random
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.sync_api import (
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PWTimeout,
    sync_playwright,
)

from src.applications import is_applied, mark_applied
from src.db import is_db_available

load_dotenv()
logger = logging.getLogger("naukrigulf_apply")

BASE_DIR   = Path(__file__).resolve().parent.parent
RATE_FILE  = BASE_DIR / "data" / "ng_apply_rate.json"


# ── Config ────────────────────────────────────────────────────────────────────

def _env_bool(k: str, d: bool = False) -> bool:
    return os.getenv(k, str(d)).lower() in ("1", "true", "yes")

def _env_int(k: str, d: int) -> int:
    try:
        return int(os.getenv(k, str(d)))
    except ValueError:
        return d


NG_ENABLED        = _env_bool("NG_ENABLED", False)
NG_DRY_RUN        = _env_bool("NG_DRY_RUN", False)
NG_HEADLESS       = _env_bool("NG_HEADLESS", False)
NG_MAX_PER_RUN    = _env_int("NG_MAX_PER_RUN", 3)
NG_COOLDOWN       = _env_int("NG_COOLDOWN_SECONDS", 120)
NG_DAILY_LIMIT    = _env_int("NG_DAILY_LIMIT", 15)
NG_SLOW_MO        = _env_int("NG_SLOW_MO", 800)
NG_MAX_AGE_DAYS   = _env_int("NG_MAX_JOB_AGE_DAYS", 14)
NG_SCORE_THRESHOLD= _env_int("NG_SCORE_THRESHOLD", 65)
NG_PROFILE_DIR    = BASE_DIR / os.getenv("NG_PROFILE_DIR", "data/ng_profile")
CV_PATH           = BASE_DIR / os.getenv("CV_PATH", "data/cv.pdf")

# Profile corruption recovery: after this many consecutive session failures,
# the profile dir is backed up and cleared for a fresh login.
_MAX_SESSION_FAILURES = _env_int("NG_MAX_SESSION_FAILURES", 3)
_SESSION_FAIL_FILE    = BASE_DIR / "data" / "ng_session_failures.json"


# ── Jitter helpers ────────────────────────────────────────────────────────────

def _jitter_sleep(base_seconds: float, extra: float = 90.0) -> None:
    """Sleep for base + random jitter. Avoids deterministic timing detection."""
    time.sleep(random.uniform(base_seconds, base_seconds + extra))


def _page_wait(page: Any, min_ms: int = 1500, max_ms: int = 4500) -> None:
    """Human-like random wait after page interactions."""
    page.wait_for_timeout(random.randint(min_ms, max_ms))

# Target search roles — drives Phase 1 search
TARGET_ROLES: List[str] = [
    "HSE Manager",
    "Operations Manager",
    "Environmental Manager",
    "Compliance Manager",
    "Project Director",
    "QHSE Manager",
]

# Spam / exclusion signals — any match disqualifies the job
_SPAM_SIGNALS: List[str] = [
    k.strip().lower()
    for k in os.getenv(
        "NG_EXCLUDE_KEYWORDS",
        "uae national,uae national only,emirati only,"
        "consultancy,pay fee,visa fee,commission only,"
        "whatsapp only,whatsapp,unpaid,internship,intern,"
        "co-founder,owner,founding partner,quantity surveyor,"
        "surveyor,civil engineer,estimator",
    ).split(",")
    if k.strip()
]


# ── Status ────────────────────────────────────────────────────────────────────

class NGApplyStatus(str, Enum):
    SUCCESS            = "success"
    ALREADY_APPLIED    = "already_applied"
    DISABLED           = "disabled"
    SESSION_EXPIRED    = "session_expired"
    NETWORK_BLOCKED    = "network_blocked"
    SPAM_FILTERED     = "spam_filtered"
    TOO_OLD            = "too_old"
    RATE_LIMITED       = "rate_limited"
    DRY_RUN            = "dry_run"
    FAILED             = "failed"
    NO_APPLY_BUTTON    = "no_apply_button"
    EXTERNAL_REDIRECT  = "external_redirect"
    SCREENING_REQUIRED = "screening_required"


@dataclass
class NGApplyResult:
    job_id:    str
    title:     str
    company:   str
    status:    NGApplyStatus
    message:   str
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
        if self._state["count"] >= NG_DAILY_LIMIT:
            return False, f"daily_limit {self._state['count']}/{NG_DAILY_LIMIT}"
        last = self._state.get("last_apply")
        if last:
            elapsed = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
            if elapsed < NG_COOLDOWN:
                return False, f"cooldown remaining={int(NG_COOLDOWN - elapsed)}s"
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


# ── Selectors ─────────────────────────────────────────────────────────────────

class _NG:
    # Search results
    SEARCH_URL      = "https://www.naukrigulf.com/jobs-in-uae?keyword={query}&location=UAE"
    JOB_CARDS       = (
        ".tuple-wrap .n-tuple, "
        ".tuple-wrap [data-job-id], "
        ".cust-job-tuple, "
        ".job-tuple"
    )
    JOB_TITLE       = "a[href*='job-listing'], a.title, .title a, .designation-title"
    JOB_COMPANY     = "[class*='company'], .comp-name, .company-name"
    JOB_DATE        = "[class*='date'], .job-posted-date, .posted-date"
    JOB_LINK        = "a"

    # Job detail page
    APPLY_BTN       = (
        "button.apply-btn, "
        "a.apply-btn, "
        "button[data-label='Apply'], "
        ".btn-apply, "
        "button:has-text('Apply'), "
        "a:has-text('Apply Now')"
    )
    QUICK_APPLY_BTN = (
        "button.quick-apply, "
        "button[data-label='Quick Apply'], "
        "button:has-text('Quick Apply')"
    )

    # Quick Apply modal
    MODAL           = ".quick-apply-popup, .apply-popup, [class*='modal']"
    SUBMIT_BTN      = (
        "button[type='submit'], "
        "button:has-text('Submit'), "
        "button:has-text('Send Application')"
    )
    FILE_INPUT      = "input[type='file']"
    TEXT_INPUTS     = "input[type='text']:visible, textarea:visible"
    SUCCESS         = (
        "text=Application Submitted, "
        "text=Successfully Applied, "
        "text=Your application has been sent, "
        ".success-message, [class*='success']"
    )

    # Session check
    LOGIN_INDICATOR = ".nI-gNb-drawer__icon, [class*='user-name'], .user-name"
    LOGIN_PAGE      = "naukrigulf.com/login"


# ── Spam filter ───────────────────────────────────────────────────────────────

def _is_spam(job: Dict[str, Any]) -> bool:
    # Only check title for spam signals to avoid false positives from company descriptions
    title = job.get("title", "").lower()
    return any(sig in title for sig in _SPAM_SIGNALS)


def _is_too_old(job: Dict[str, Any]) -> bool:
    posted = job.get("date_posted") or job.get("date_found", "")
    if not posted:
        return False
    try:
        dt = datetime.fromisoformat(str(posted)[:19])
        return (datetime.utcnow() - dt).days > NG_MAX_AGE_DAYS
    except (ValueError, TypeError):
        return False


# ── LLM screening ─────────────────────────────────────────────────────────────

def _llm_answers(questions: List[str], job: Dict[str, Any]) -> Dict[str, str]:
    if not questions:
        return {}
    try:
        from src.llm_scorer import get_llm_response
        from src.profile import get_candidate_profile

        p   = get_candidate_profile()
        ctx = (
            f"Name: {p.get('name','N/A')}\n"
            f"Experience: {p.get('experience_summary','N/A')}\n"
            f"Skills: {', '.join(p.get('skills',[]))}\n"
            f"Location: UAE (available immediately)"
        )
        qs     = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        prompt = (
            f"NaukriGulf application: {job.get('title')} at {job.get('company')}.\n\n"
            f"CANDIDATE:\n{ctx}\n\nQUESTIONS:\n{qs}\n\n"
            'Reply ONLY with JSON: {"1":"answer","2":"answer"}'
        )
        raw   = get_llm_response(prompt)
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            parsed: Dict[str, str] = json.loads(raw[start:end])
            return {
                questions[int(k) - 1]: v
                for k, v in parsed.items()
                if k.isdigit() and int(k) <= len(questions)
            }
    except Exception as exc:
        logger.warning("llm_screening_failed error=%s", exc)
    return {}


# ── Engine ────────────────────────────────────────────────────────────────────

class NaukriGulfApplyEngine:
    """
    NaukriGulf automation using persistent Chrome profile.

    Requires an active NaukriGulf session in NG_PROFILE_DIR.
    First run: set headless=False, navigate to naukrigulf.com, log in manually.
    Subsequent runs reuse the session automatically.

    Usage:
        with NaukriGulfApplyEngine() as engine:
            results = engine.run(max_applies=3)
    """

    def __init__(
        self,
        rate_limiter: Optional[_RateLimiter] = None,
    ) -> None:
        self._rate  = rate_limiter or _RateLimiter()
        self._pw:   Optional[Playwright]    = None
        self._ctx:  Optional[BrowserContext] = None
        self._page: Optional[Page]          = None

    def __enter__(self) -> "NaukriGulfApplyEngine":
        NG_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._pw  = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(NG_PROFILE_DIR),
            headless=NG_HEADLESS,     # configurable: headless for CI, visible for local
            slow_mo=NG_SLOW_MO,
            ignore_https_errors=True,  # Handle GitHub runner network issues
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-http2",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
            no_viewport=False,
            viewport={"width": 1280, "height": 800},
        )
        self._page = (
            self._ctx.pages[0]
            if self._ctx.pages
            else self._ctx.new_page()
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

    # ── public API ────────────────────────────────────────────────────────────

    def run(self, max_applies: int = NG_MAX_PER_RUN) -> List[NGApplyResult]:
        """
        Search NaukriGulf for target roles, filter, and apply.
        Returns one NGApplyResult per application attempt.
        """
        if not NG_ENABLED:
            logger.info("ng_apply_disabled NG_ENABLED=false")
            return []

        if not self._check_session():
            # Check if this was a network block vs real session issue
            error_str = str(self._last_session_error).lower() if hasattr(self, '_last_session_error') else ""
            if "timeout" in error_str or "network" in error_str:
                logger.error("ng_network_blocked_or_timeout - GitHub runner cannot reach NaukriGulf")
                return [NGApplyResult(
                    job_id="", title="", company="",
                    status=NGApplyStatus.NETWORK_BLOCKED,
                )]
            else:
                logger.error("ng_session_expired login manually then re-run")
                return [NGApplyResult(
                    job_id="", title="", company="",
                    status=NGApplyStatus.SESSION_EXPIRED,
                message="NaukriGulf session expired — open browser and log in",
            )]

        all_jobs = self._search_all_roles()
        logger.info("ng_search_found total=%d", len(all_jobs))

        results: List[NGApplyResult] = []
        applied = 0

        for job in all_jobs:
            if applied >= max_applies:
                break

            r = self._process_job(job)
            if r:
                results.append(r)
                logger.info("ng_result %s", json.dumps(r.to_dict()))
                if r.status == NGApplyStatus.SUCCESS:
                    applied += 1
                    _jitter_sleep(NG_COOLDOWN, extra=90)

        logger.info(
            "ng_run_complete applied=%d dry_run=%d total=%d",
            sum(1 for r in results if r.status == NGApplyStatus.SUCCESS),
            sum(1 for r in results if r.status == NGApplyStatus.DRY_RUN),
            len(results),
        )
        return results

    def apply_jobs(
        self,
        jobs: List[Dict[str, Any]],
        max_applies: int = NG_MAX_PER_RUN,
    ) -> List[NGApplyResult]:
        """
        Apply to a pre-fetched list of jobs (from pipeline DB/history).
        Skips the search phase — useful when jobs are already scored.
        """
        if not NG_ENABLED:
            logger.info("ng_apply_disabled NG_ENABLED=false")
            return []

        if not self._check_session():
            logger.error("ng_session_expired")
            return []

        ng_jobs = [
            j for j in jobs
            if "naukrigulf.com" in j.get("link", "")
            and not is_applied(j)
            and not _is_spam(j)
            and not _is_too_old(j)
        ]
        logger.info("ng_apply_jobs eligible=%d/%d", len(ng_jobs), len(jobs))

        results: List[NGApplyResult] = []
        applied = 0
        for job in ng_jobs[:max_applies]:
            if applied >= max_applies:
                break
            r = self._apply_one(job)
            results.append(r)
            logger.info("ng_result %s", json.dumps(r.to_dict()))
            if r.status == NGApplyStatus.SUCCESS:
                applied += 1
                _jitter_sleep(NG_COOLDOWN, extra=90)
        return results

    # ── session check ─────────────────────────────────────────────────────────

    def _check_session(self) -> bool:
        """
        Multi-signal session check optimized for GitHub runners.
        Signals checked (in order):
          1. Try direct search page load (bypasses homepage blocks)
          2. URL contains 'login' → definitely expired
          3. Login indicator selector present
          4. 'Applied Jobs' page accessible (strong confirmation)
        On repeated failures, backs up and clears the profile dir.
        """
        assert self._page
        try:
            # Try direct search page first - bypasses potential homepage blocks
            search_url = "https://www.naukrigulf.com/jobs-in-uae?keyword=HSE%20Manager&location=UAE"
            self._page.goto(
                search_url,
                wait_until="commit",  # Lighter wait mode for GitHub runners
                timeout=60_000,        # Increased timeout for network issues
            )
            logger.info("ng_search_probe_loaded url=%s", search_url)
            self._page.wait_for_timeout(5000)  # Manual wait after commit

            url = self._page.url.lower()

            # Signal 1: login redirect
            if "login" in url or "signin" in url:
                self._record_session_failure()
                return False

            # Signal 2: profile avatar / username visible
            has_indicator = bool(self._page.query_selector(_NG.LOGIN_INDICATOR))

            # Signal 3: access applied jobs (definitive check)
            has_applied_access = False
            try:
                self._page.goto(
                    "https://www.naukrigulf.com/myapps",
                    wait_until="domcontentloaded",
                    timeout=12_000,
                )
                _page_wait(self._page, 800, 1500)
                has_applied_access = "login" not in self._page.url.lower()
            except Exception:
                pass

            alive = has_indicator or has_applied_access
            if alive:
                self._reset_session_failures()
            else:
                self._record_session_failure()

            return alive

        except Exception as exc:
            # Check if this is a network/timeout issue vs session issue
            error_str = str(exc).lower()
            if "timeout" in error_str or "network" in error_str or "connection" in error_str:
                logger.warning("ng_network_blocked_or_timeout error=%s", exc)
                # Store error for run() method to check
                self._last_session_error = exc
                # Don't record as session failure - this is a network issue
                return False
            else:
                logger.warning("session_check_failed error=%s", exc)
                self._record_session_failure()
                return False

    def _record_session_failure(self) -> None:
        """Track consecutive failures and recover profile if threshold exceeded."""
        try:
            state: Dict[str, Any] = {}
            if _SESSION_FAIL_FILE.exists():
                with _SESSION_FAIL_FILE.open() as f:
                    state = json.load(f)

            count = state.get("count", 0) + 1
            state = {"count": count, "last": datetime.utcnow().isoformat()}
            _SESSION_FAIL_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _SESSION_FAIL_FILE.open("w") as f:
                json.dump(state, f)

            logger.warning("session_failure count=%d/%d", count, _MAX_SESSION_FAILURES)

            if count >= _MAX_SESSION_FAILURES:
                self._recover_profile()
        except Exception as exc:
            logger.warning("session_failure_tracking_error error=%s", exc)

    def _reset_session_failures(self) -> None:
        try:
            if _SESSION_FAIL_FILE.exists():
                _SESSION_FAIL_FILE.write_text('{"count":0}')
        except Exception:
            pass

    def _recover_profile(self) -> None:
        """Back up and remove corrupted profile dir so next run prompts fresh login."""
        backup = Path(str(NG_PROFILE_DIR) + f"_backup_{date.today().isoformat()}")
        try:
            if NG_PROFILE_DIR.exists():
                shutil.copytree(NG_PROFILE_DIR, backup, dirs_exist_ok=True)
                shutil.rmtree(NG_PROFILE_DIR)
                logger.error(
                    "profile_corrupted_recovered backup=%s "
                    "— re-run to trigger fresh login", backup,
                )
            _SESSION_FAIL_FILE.write_text('{"count":0}')
        except Exception as exc:
            logger.error("profile_recovery_failed error=%s", exc)

    # ── Phase 1: search ───────────────────────────────────────────────────────

    def _search_all_roles(self) -> List[Dict[str, Any]]:
        """Search NaukriGulf for all target roles, deduplicate, then LLM-score."""
        seen: set[str] = set()
        raw_jobs: List[Dict[str, Any]] = []

        for role in TARGET_ROLES:
            try:
                found = self._search_role(role)
                for job in found:
                    link = job.get("link", "")
                    if link and link not in seen:
                        seen.add(link)
                        raw_jobs.append(job)
            except Exception as exc:
                logger.warning("search_role_failed role=%s error=%s", role, exc)

        # LLM scoring — reuse existing pipeline scorer
        scored = self._score_jobs(raw_jobs)
        logger.info(
            "search_complete raw=%d scored=%d above_threshold=%d",
            len(raw_jobs),
            len(scored),
            sum(1 for j in scored if int(j.get("score", 0)) >= NG_SCORE_THRESHOLD),
        )
        return [j for j in scored if int(j.get("score", 0)) >= NG_SCORE_THRESHOLD]

    def _score_jobs(self, jobs):
        if not jobs:
            return jobs

        try:
            from src.scoring import score_job

            for job in jobs:
                try:
                    if not job.get("description"):
                        job["description"] = (
                            f"{job.get('title','')} position at "
                            f"{job.get('company','')} in UAE. "
                            f"Relevant to HSE, QHSE, Environmental, Compliance, "
                            f"Operations, or Project leadership roles if title matches."
                        )

                    job["score"] = score_job(job)

                except Exception:
                    job["score"] = 0

            return sorted(
                jobs,
                key=lambda j: int(j.get("score", 0)),
                reverse=True
            )

        except ImportError:
            target_keywords = {
                "hse", "qhse", "ehs", "safety", "environment",
                "environmental", "compliance", "operations",
                "operation", "project director", "hsse"
            }

            negative_keywords = {
                "civil engineer", "site engineer", "quantity surveyor",
                "surveyor", "architect", "fit-out", "sales", "driver",
                "technician", "intern", "uae national"
            }

            for job in jobs:
                title_lower = job.get("title", "").lower()

                if any(kw in title_lower for kw in negative_keywords):
                    job["score"] = 0
                    continue

                matches = sum(1 for kw in target_keywords if kw in title_lower)
                job["score"] = min(matches * 20, 80)

            return sorted(
                jobs,
                key=lambda j: int(j.get("score", 0)),
                reverse=True
            )

    def _search_role(self, role: str) -> List[Dict[str, Any]]:
        """Navigate to search results for one role and extract job cards."""
        assert self._page
        url = _NG.SEARCH_URL.format(query=quote_plus(role))
        self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        self._page.wait_for_timeout(3_000)

        # Debug: Check page content and capture screenshot
        html = self._page.content()
        logger.info("ng_page_loaded role=%s url=%s html_len=%d", role, self._page.url, len(html))
        logger.info("ng_has_job_text=%s", "job" in html.lower())

        # Save screenshot for debugging
        try:
            screenshot_path = BASE_DIR / "data" / f"ng_debug_{role.replace(' ', '_')}.png"
            self._page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info("ng_screenshot_saved path=%s", screenshot_path)
        except Exception as exc:
            logger.warning("ng_screenshot_failed error=%s", exc)

        cards = self._page.query_selector_all(_NG.JOB_CARDS)
        logger.info("ng_cards_found role=%s count=%d", role, len(cards))

        # Dynamic descent: find containers then extract individual job links
        containers = self._page.query_selector_all(".tuple-wrap")
        cards = []

        for container in containers:
            inner_links = container.query_selector_all("a[href]")
            if inner_links:
                cards.extend(inner_links)

        logger.info("ng_cards_found role=%s count=%d (dynamic descent)", role, len(cards))

        jobs: List[Dict[str, Any]] = []

        for card in cards[:20]:  # cap per role
            try:
                # Debug: Test different selectors for this card
                card_html = card.inner_html()[:300]
                logger.debug("ng_card_debug html_sample=%s", card_html.replace('\n', ' '))

                # Dual-mode extraction based on card type
                tag = card.evaluate("el => el.tagName.toLowerCase()")

                # Case 1: card itself is a link
                if tag == "a":
                    title = card.inner_text().strip()
                    link = card.get_attribute("href") or ""
                    company = ""  # Temporarily disabled to avoid wrong extraction
                    posted = ""

                # Case 2: normal container card
                else:
                    title_el = card.query_selector(_NG.JOB_TITLE)
                    comp_el  = card.query_selector(_NG.JOB_COMPANY)
                    date_el  = card.query_selector(_NG.JOB_DATE)

                    title = title_el.inner_text().strip() if title_el else ""
                    company = comp_el.inner_text().strip() if comp_el else ""
                    posted = date_el.inner_text().strip() if date_el else ""

                    link = ""
                    for a in card.query_selector_all("a"):
                        href = a.get_attribute("href") or ""
                        if href:
                            link = href
                            break

                # Try alternative title extraction
                if not title:
                    alt_title_selectors = [
                        "h2", "h3",
                        ".designation",
                        ".title",
                        "[class*='title']",
                        "a"
                    ]

                    for sel in alt_title_selectors:
                        alt_el = card.query_selector(sel)
                        if alt_el:
                            txt = alt_el.inner_text().strip()
                            if txt:
                                title = txt
                                logger.debug(
                                    "ng_alt_title_found selector=%s title=%s",
                                    sel, title[:50]
                                )
                                break

                # Try alternative link extraction
                if not link:
                    all_links = card.query_selector_all("a")

                    for a in all_links:
                        href = a.get_attribute("href") or ""

                        if not href:
                            continue

                        if (
                            "/job/" in href
                            or "/jobs/" in href
                            or "naukrigulf.com" in href
                            or href.startswith("/")
                        ):
                            link = href
                            break

                # Validate AFTER fallbacks
                if not link or not title:
                    logger.debug(
                        "ng_card_skipped missing_link_or_title "
                        "link=%s title=%s",
                        role, bool(title), bool(link),
                    )
                    continue

                # Strong production filtering - combined allow-list and block-list
                BAD_LINK_PATTERNS = {
                    "/register", "/cid-", "careers-cid"
                }

                # Allow-list filtering - must contain at least one target keyword
                TARGET_KEYWORDS = {
                    "hse", "ehs", "qhse", "hsse",
                    "safety", "environment", "environmental",
                    "compliance", "risk", "operations", "operational",
                    "project director", "contracts manager", "contracts lead"
                }

                # Block-list filtering - exclude these terms
                EXCLUDED_TERMS = {
                    "login/register", "register", "sign in", "careers", "career",
                    "company", "companies", "thirtin", "laadlee", "login",
                    "delivery driver", "driver", "architect", "fit-out", "site architect",
                    "site civil engineer", "civil engineer", "ff&e designer", "designer",
                    "office assistant", "irrigation technician", "technician"
                }

                # Seniority filtering - exclude low-level roles
                BAD_SENIORITY = {
                    "coordinator", "assistant", "administrator", "clerk", "secretary"
                }

                title_l = title.lower()
                link_l = link.lower()

                # Apply combined filtering logic
                GOOD = any(k in title_l for k in TARGET_KEYWORDS)
                BAD = any(k in title_l for k in EXCLUDED_TERMS)
                LOW_LEVEL = any(k in title_l for k in BAD_SENIORITY)
                BAD_LINK = any(k in link_l for k in BAD_LINK_PATTERNS)

                if not GOOD or BAD or LOW_LEVEL or BAD_LINK:
                    filter_reason = []
                    if not GOOD: filter_reason.append("no_target_keyword")
                    if BAD: filter_reason.append("excluded_term")
                    if LOW_LEVEL: filter_reason.append("low_seniority")
                    if BAD_LINK: filter_reason.append("bad_link_pattern")

                    logger.debug(
                        f"ng_card_filtered title={title[:40]} reasons={','.join(filter_reason)}"
                    )
                    continue

                # Add detailed telemetry for extraction verification
                logger.info(
                    "card_extract title=%s company=%s link=%s",
                    title[:40],
                    company[:30],
                    link[:60]
                )

                if link.startswith("/"):
                    link = f"https://www.naukrigulf.com{link}"

                jobs.append({
                    "title":       title,
                    "company":     company,
                    "link":        link,
                    "date_posted": posted,
                    "source":      "naukrigulf",
                    "score":       0,
                })
            except Exception:
                pass

        logger.info("search_role role=%s found=%d", role, len(jobs))
        return jobs

    # ── Phase 2 + 3: filter + apply ───────────────────────────────────────────

    def _process_job(self, job: Dict[str, Any]) -> Optional[NGApplyResult]:
        """Filter a single job and attempt apply if eligible."""
        link    = job.get("link", "")
        title   = job.get("title", "Unknown")
        company = job.get("company", "Unknown")

        def r(s: NGApplyStatus, m: str) -> NGApplyResult:
            return NGApplyResult(job_id=link, title=title, company=company,
                                 status=s, message=m)

        if is_applied(job):
            return None  # silent skip — already tracked

        if _is_spam(job):
            logger.debug("ng_spam_filtered title=%s", title)
            return r(NGApplyStatus.SPAM_FILTERED, "spam signal detected")

        if _is_too_old(job):
            return r(NGApplyStatus.TOO_OLD, f"age > {NG_MAX_AGE_DAYS}d")

        return self._apply_one(job)

    def _apply_one(self, job: Dict[str, Any]) -> NGApplyResult:
        link    = job.get("link", "")
        title   = job.get("title", "Unknown")
        company = job.get("company", "Unknown")

        def r(s: NGApplyStatus, m: str) -> NGApplyResult:
            return NGApplyResult(job_id=link, title=title, company=company,
                                 status=s, message=m)

        allowed, reason = self._rate.can_apply()
        if not allowed:
            return r(NGApplyStatus.RATE_LIMITED, reason)

        if NG_DRY_RUN:
            logger.info("ng_dry_run title=%s company=%s", title, company)
            return r(NGApplyStatus.DRY_RUN, f"would_apply title={title}")

        try:
            return self._do_apply(job)
        except Exception as exc:
            logger.exception("ng_apply_unhandled title=%s", title)
            self._save_attempt(link, title, company, "failed", str(exc))
            return r(NGApplyStatus.FAILED, str(exc))

    # ── Phase 3: browser apply flow ───────────────────────────────────────────

    def _do_apply(self, job: Dict[str, Any]) -> NGApplyResult:
        assert self._page
        link    = job.get("link", "")
        title   = job.get("title", "Unknown")
        company = job.get("company", "Unknown")

        def r(s: NGApplyStatus, m: str) -> NGApplyResult:
            return NGApplyResult(job_id=link, title=title, company=company,
                                 status=s, message=m)

        self._page.goto(link, wait_until="domcontentloaded", timeout=30_000)
        _page_wait(self._page, 2000, 4000)

        # Detect apply button type
        quick_btn  = self._page.query_selector(_NG.QUICK_APPLY_BTN)
        apply_btn  = self._page.query_selector(_NG.APPLY_BTN)
        action_btn = quick_btn or apply_btn

        if not action_btn:
            logger.warning("selector_missing selector=apply_btn title=%s", title)
            return r(NGApplyStatus.NO_APPLY_BUTTON, "no apply button found")

        action_btn.click()
        _page_wait(self._page, 1500, 3500)

        # External redirect detection
        if "naukrigulf.com" not in self._page.url:
            return r(NGApplyStatus.EXTERNAL_REDIRECT,
                     f"redirected to {self._page.url[:80]}")

        # Upload CV if file input visible
        self._maybe_upload_cv()

        # Fill screening questions
        self._fill_questions(job)

        # Submit
        try:
            submit = self._page.wait_for_selector(_NG.SUBMIT_BTN, timeout=8_000)
            if submit and submit.is_enabled():
                submit.click()
                _page_wait(self._page, 2500, 4500)
        except PWTimeout:
            logger.warning("selector_missing selector=submit_btn title=%s", title)
            return r(NGApplyStatus.SCREENING_REQUIRED,
                     "submit button not found — manual review needed")

        # Confirm success
        if not self._page.query_selector(_NG.SUCCESS):
            logger.warning("selector_missing selector=success_confirm title=%s", title)
            return r(NGApplyStatus.FAILED, "no success confirmation after submit")

        mark_applied(job, status="applied",
                     notes="Auto-applied via NaukriGulf")
        self._rate.record()
        self._save_attempt(link, title, company, "success")
        logger.info("ng_apply_success title=%s daily=%d",
                    title, self._rate.today_count)
        return NGApplyResult(job_id=link, title=title, company=company,
                             status=NGApplyStatus.SUCCESS,
                             message="applied successfully")

    # ── form helpers ──────────────────────────────────────────────────────────

    def _maybe_upload_cv(self) -> None:
        if not CV_PATH.exists():
            logger.warning("cv_missing path=%s", CV_PATH)
            return
        inp = self._page.query_selector(_NG.FILE_INPUT)
        if inp:
            try:
                inp.set_input_files(str(CV_PATH))
                self._page.wait_for_timeout(1_000)
                logger.debug("cv_uploaded")
            except Exception as exc:
                logger.warning("cv_upload_failed error=%s", exc)

    def _fill_questions(self, job: Dict[str, Any]) -> None:
        questions: List[str] = []
        inputs = self._page.query_selector_all(_NG.TEXT_INPUTS)

        for inp in inputs:
            try:
                lbl: str = inp.evaluate(
                    """el => {
                        if (el.id) {
                            const l = document.querySelector('label[for="'+el.id+'"]');
                            if (l) return l.innerText.trim();
                        }
                        const wrap = el.closest('.form-group,.field-wrap,[class*="question"]');
                        return wrap
                            ? (wrap.querySelector('label')?.innerText?.trim() || '')
                            : '';
                    }"""
                )
                if lbl:
                    questions.append(lbl)
            except Exception:
                pass

        if not questions:
            return

        answers = _llm_answers(questions, job)
        for inp, q in zip(inputs, questions):
            ans = answers.get(q, "")
            if not ans:
                continue
            try:
                if not inp.input_value():
                    inp.fill(ans)
            except Exception as exc:
                logger.debug("fill_failed q=%s err=%s", q[:40], exc)

    # ── DB ────────────────────────────────────────────────────────────────────

    def _save_attempt(
        self,
        job_id: str, title: str, company: str,
        status: str, error: Optional[str] = None,
    ) -> None:
        if not is_db_available():
            return
        try:
            from src.db import get_db_connection
            conn = get_db_connection()
            if not conn:
                return
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auto_apply_attempts
                        (job_id, title, company, status, error, timestamp)
                    VALUES (%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT (job_id) DO UPDATE SET
                        status=EXCLUDED.status,
                        error=EXCLUDED.error,
                        timestamp=NOW()
                    """,
                    (job_id, title, company, status, error),
                )
        except Exception as exc:
            logger.warning("db_save_failed error=%s", exc)


# ── Pipeline entry point ──────────────────────────────────────────────────────

def run_naukrigulf_apply(
    jobs: Optional[List[Dict[str, Any]]] = None,
    max_applies: int = NG_MAX_PER_RUN,
) -> List[NGApplyResult]:
    """
    Entry point for run_daily pipeline.

    If jobs is None → searches NaukriGulf directly (Phase 1–4).
    If jobs provided  → applies to NaukriGulf URLs in the list (Phase 3–4 only).
    """
    if not NG_ENABLED:
        logger.info("ng_apply_disabled NG_ENABLED=false")
        return []

    with NaukriGulfApplyEngine() as engine:
        if jobs is not None:
            return engine.apply_jobs(jobs, max_applies=max_applies)
        return engine.run(max_applies=max_applies)
