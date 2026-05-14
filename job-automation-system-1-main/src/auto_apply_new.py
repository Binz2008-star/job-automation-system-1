"""
src/auto_apply.py
LinkedIn Easy Apply Automation Engine

Architecture note:
  LinkedIn blocks datacenter IPs (GitHub Actions). This engine is designed
  for LOCAL execution only. The CI guard enforces this by default.

  GitHub Actions → scraping / scoring / dashboard / gmail
  Local machine  → LinkedIn Easy Apply (this module)

Environment variables:
    LINKEDIN_EMAIL               required
    LINKEDIN_PASSWORD            required
    AUTO_APPLY_ENABLED=false     master switch (default off)
    AUTO_APPLY_DRY_RUN=false     log intent without submitting
    AUTO_APPLY_MAX_PER_RUN=5
    AUTO_APPLY_SCORE_THRESHOLD=75
    AUTO_APPLY_COOLDOWN_SECONDS=90
    AUTO_APPLY_DAILY_LIMIT=30
    ALLOW_CI_APPLY=false         never set true — LinkedIn blocks CI IPs
    CV_PATH=data/cv.pdf
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PWTimeout,
    sync_playwright,
)

from src.applications import is_applied, mark_applied
from src.db import is_db_available

load_dotenv()
logger = logging.getLogger("auto_apply")

BASE_DIR  = Path(__file__).resolve().parent.parent
RATE_FILE = BASE_DIR / "data" / "auto_apply_rate.json"


# ── Config ────────────────────────────────────────────────────────────────────

def _env_bool(k: str, d: bool = False) -> bool:
    return os.getenv(k, str(d)).lower() in ("1", "true", "yes")

def _env_int(k: str, d: int) -> int:
    try:
        return int(os.getenv(k, str(d)))
    except ValueError:
        return d


AUTO_APPLY_ENABLED = _env_bool("AUTO_APPLY_ENABLED", False)
MAX_PER_RUN        = _env_int("AUTO_APPLY_MAX_PER_RUN", 5)
SCORE_THRESHOLD    = _env_int("AUTO_APPLY_SCORE_THRESHOLD", 75)
COOLDOWN_SECONDS   = _env_int("AUTO_APPLY_COOLDOWN_SECONDS", 90)
DAILY_LIMIT        = _env_int("AUTO_APPLY_DAILY_LIMIT", 30)
DRY_RUN            = _env_bool("AUTO_APPLY_DRY_RUN", False)
ALLOW_CI_APPLY     = _env_bool("ALLOW_CI_APPLY", False)
CV_PATH            = BASE_DIR / os.getenv("CV_PATH", "data/cv.pdf")

LI_EMAIL    = os.getenv("LINKEDIN_EMAIL", "")
LI_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")

# Exclusion keywords — disqualify jobs before auto-apply attempt.
# Override default list via AUTO_APPLY_EXCLUDE_KEYWORDS in .env (comma-separated).
_EXCLUDE: List[str] = [
    k.strip().lower()
    for k in os.getenv(
        "AUTO_APPLY_EXCLUDE_KEYWORDS",
        "uae national,uae nationals only,uae national only,emirati only,"
        "graduate uae national only,quantity surveyor,surveyor,civil engineer,"
        "estimator,site engineer,co-founder,owner,founding partner,intern,internship",
    ).split(",")
    if k.strip()
]


def _is_excluded(job: Dict[str, Any]) -> bool:
    """True if any exclusion keyword is present in the job's combined text."""
    text = " ".join(
        str(job.get(f, ""))
        for f in ("title", "company", "location",
                  "description", "match_reason", "profile_explanation")
    ).lower()
    return any(kw in text for kw in _EXCLUDE)


# ── Status ────────────────────────────────────────────────────────────────────

class ApplyStatus(str, Enum):
    SUCCESS            = "success"
    ALREADY_APPLIED    = "already_applied"
    BELOW_THRESHOLD    = "below_threshold"
    DISABLED           = "disabled"
    RATE_LIMITED       = "rate_limited"
    NO_EASY_APPLY      = "no_easy_apply"
    LOGIN_FAILED       = "login_failed"
    CAPTCHA            = "captcha"
    SCREENING_REQUIRED = "screening_required"
    DRY_RUN            = "dry_run"
    FAILED             = "failed"


@dataclass
class ApplyResult:
    job_id:    str
    title:     str
    company:   str
    status:    ApplyStatus
    message:   str
    score:     int = 0
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ── Persistent rate limiter ───────────────────────────────────────────────────

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
        if self._state["count"] >= DAILY_LIMIT:
            return False, f"daily_limit count={self._state['count']}/{DAILY_LIMIT}"
        last = self._state.get("last_apply")
        if last:
            elapsed = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
            if elapsed < COOLDOWN_SECONDS:
                return False, f"cooldown remaining={int(COOLDOWN_SECONDS - elapsed)}s"
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


# ── Browser setup ─────────────────────────────────────────────────────────────

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_STEALTH = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
window.chrome={runtime:{}};
"""


def _new_context(browser: Browser) -> BrowserContext:
    ctx = browser.new_context(
        user_agent=_UA,
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="Asia/Dubai",
    )
    ctx.add_init_script(_STEALTH)
    return ctx


# ── LinkedIn selectors (verified 2026-05) ────────────────────────────────────

class _Li:
    EMAIL     = "#username"
    PASSWORD  = "#password"
    LOGIN_BTN = "button[type='submit']"
    FEED_URL  = "linkedin.com/feed"

    EASY_APPLY  = "button.jobs-apply-button[aria-label*='Easy Apply']"
    MODAL       = ".jobs-easy-apply-modal, .artdeco-modal"
    NEXT_BTN    = "button[aria-label='Continue to next step']"
    REVIEW_BTN  = "button[aria-label='Review your application']"
    SUBMIT_BTN  = "button[aria-label='Submit application']"
    DISMISS_BTN = "button[aria-label='Dismiss']"

    TEXT_INPUTS = "input[type='text']:visible, textarea:visible"
    FILE_INPUT  = "input[type='file']"

    SUCCESS = (
        "h3:has-text('Application submitted'), "
        ".artdeco-inline-feedback--success, "
        "[data-test-modal-id='easy-apply-success-modal']"
    )
    CAPTCHA = "#captcha-internal, .recaptcha-checkbox"


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
            f"Roles: {', '.join(p.get('target_roles',[]))}\n"
            "Location: UAE (available immediately)"
        )
        qs     = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        prompt = (
            f"LinkedIn Easy Apply for: {job.get('title')} at {job.get('company')}.\n\n"
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

class LinkedInEasyApplyEngine:
    """
    LinkedIn Easy Apply automation.
    Run on residential IP only — datacenter/CI IPs are blocked.
    headless=False is default: visible browser reduces detection risk.
    """

    def __init__(
        self,
        headless: bool = False,
        rate_limiter: Optional[_RateLimiter] = None,
    ) -> None:
        self._headless  = headless
        self._rate      = rate_limiter or _RateLimiter()
        self._pw:       Optional[Playwright]     = None
        self._browser:  Optional[Browser]        = None
        self._ctx:      Optional[BrowserContext] = None
        self._page:     Optional[Page]           = None
        self._logged_in = False

    def __enter__(self) -> "LinkedInEasyApplyEngine":
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self._headless,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        self._ctx  = _new_context(self._browser)
        self._page = self._ctx.new_page()
        self._page.set_default_timeout(25_000)
        return self

    def __exit__(self, *_: Any) -> None:
        for obj in (self._page, self._ctx, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def apply_batch(
        self,
        jobs: List[Dict[str, Any]],
        max_applies: int = MAX_PER_RUN,
    ) -> List[ApplyResult]:
        eligible = [
            j for j in jobs
            if "linkedin.com/jobs/view" in j.get("link", "")
            and int(j.get("score") or 0) >= SCORE_THRESHOLD
            and not is_applied(j)
            and not _is_excluded(j)
        ]
        excluded_count = sum(1 for j in jobs if _is_excluded(j))
        if excluded_count:
            logger.info("apply_batch_excluded count=%d", excluded_count)
        logger.info(
            "apply_batch total=%d eligible=%d max=%d dry_run=%s",
            len(jobs), len(eligible), max_applies, DRY_RUN,
        )
        results: List[ApplyResult] = []
        for job in eligible[:max_applies]:
            r = self._apply_one(job)
            results.append(r)
            logger.info("apply_result %s", json.dumps(r.to_dict()))
            if r.status == ApplyStatus.SUCCESS:
                time.sleep(COOLDOWN_SECONDS)
        return results

    # ── guards ────────────────────────────────────────────────────────────────

    def _apply_one(self, job: Dict[str, Any]) -> ApplyResult:
        link    = job.get("link", "")
        title   = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        score   = int(job.get("score") or 0)

        def r(s: ApplyStatus, m: str) -> ApplyResult:
            return ApplyResult(job_id=link, title=title, company=company,
                               status=s, message=m, score=score)

        if not AUTO_APPLY_ENABLED:
            return r(ApplyStatus.DISABLED, "AUTO_APPLY_ENABLED=false")

        if os.getenv("GITHUB_ACTIONS") and not ALLOW_CI_APPLY:
            return r(ApplyStatus.DISABLED,
                     "CI detected — LinkedIn blocks datacenter IPs")

        if not LI_EMAIL or not LI_PASSWORD:
            return r(ApplyStatus.DISABLED,
                     "LINKEDIN_EMAIL / LINKEDIN_PASSWORD missing in .env")

        if is_applied(job):
            return r(ApplyStatus.ALREADY_APPLIED, "already in tracking")

        if score < SCORE_THRESHOLD:
            return r(ApplyStatus.BELOW_THRESHOLD, f"score={score} < {SCORE_THRESHOLD}")

        allowed, reason = self._rate.can_apply()
        if not allowed:
            return r(ApplyStatus.RATE_LIMITED, reason)

        if DRY_RUN:
            logger.info("dry_run title=%s company=%s score=%d", title, company, score)
            return r(ApplyStatus.DRY_RUN, f"would_apply score={score}")

        try:
            return self._do_apply(job)
        except Exception as exc:
            logger.exception("apply_unhandled title=%s", title)
            self._save_attempt(link, title, company, "failed", str(exc))
            return r(ApplyStatus.FAILED, str(exc))

    # ── login ─────────────────────────────────────────────────────────────────

    def _ensure_logged_in(self) -> bool:
        if self._logged_in:
            return True
        page = self._page
        assert page

        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        page.wait_for_timeout(2_000)

        if _Li.FEED_URL in page.url:
            self._logged_in = True
            return True

        try:
            page.fill(_Li.EMAIL,    LI_EMAIL)
            page.fill(_Li.PASSWORD, LI_PASSWORD)
            page.click(_Li.LOGIN_BTN)
            page.wait_for_url(f"**/{_Li.FEED_URL}**", timeout=20_000)
            self._logged_in = True
            logger.info("linkedin_login_success")
            return True
        except PWTimeout:
            if page.query_selector(_Li.CAPTCHA):
                logger.error("linkedin_captcha_detected")
            else:
                logger.error("linkedin_login_timeout url=%s", page.url)
            return False
        except Exception as exc:
            logger.error("linkedin_login_error error=%s", exc)
            return False

    # ── apply flow ────────────────────────────────────────────────────────────

    def _do_apply(self, job: Dict[str, Any]) -> ApplyResult:
        assert self._page
        link    = job.get("link", "")
        title   = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        score   = int(job.get("score") or 0)

        def r(s: ApplyStatus, m: str) -> ApplyResult:
            return ApplyResult(job_id=link, title=title, company=company,
                               status=s, message=m, score=score)

        if not self._ensure_logged_in():
            return r(ApplyStatus.LOGIN_FAILED, "login failed")

        self._page.goto(link, wait_until="domcontentloaded", timeout=30_000)
        self._page.wait_for_timeout(2_500)

        if self._page.query_selector(_Li.CAPTCHA):
            return r(ApplyStatus.CAPTCHA, "captcha triggered")

        try:
            btn = self._page.wait_for_selector(_Li.EASY_APPLY, timeout=8_000)
        except PWTimeout:
            return r(ApplyStatus.NO_EASY_APPLY, "Easy Apply button not found")

        btn.click()
        self._page.wait_for_timeout(2_000)

        steps = 0
        while steps < 12:
            steps += 1

            if steps == 1:
                self._maybe_upload_cv()

            self._fill_visible_fields(job)

            if self._page.query_selector(_Li.SUCCESS):
                break

            review = self._page.query_selector(_Li.REVIEW_BTN)
            if review and review.is_enabled():
                review.click()
                self._page.wait_for_timeout(1_500)
                continue

            submit = self._page.query_selector(_Li.SUBMIT_BTN)
            if submit and submit.is_enabled():
                submit.click()
                self._page.wait_for_timeout(3_000)
                break

            nxt = self._page.query_selector(_Li.NEXT_BTN)
            if nxt and nxt.is_enabled():
                nxt.click()
                self._page.wait_for_timeout(1_500)
                continue

            return r(ApplyStatus.SCREENING_REQUIRED,
                     f"stuck at step {steps}")

        if not self._page.query_selector(_Li.SUCCESS):
            return r(ApplyStatus.FAILED, "no success confirmation")

        mark_applied(job, status="applied",
                     notes="Auto-applied via LinkedIn Easy Apply")
        self._rate.record()
        self._save_attempt(link, title, company, "success")
        logger.info("apply_success title=%s score=%d daily=%d",
                    title, score, self._rate.today_count)
        return r(ApplyStatus.SUCCESS, f"submitted in {steps} step(s)")

    # ── form helpers ──────────────────────────────────────────────────────────

    def _maybe_upload_cv(self) -> None:
        if not CV_PATH.exists():
            logger.warning("cv_missing path=%s", CV_PATH)
            return
        inp = self._page.query_selector(_Li.FILE_INPUT)
        if inp:
            try:
                inp.set_input_files(str(CV_PATH))
                self._page.wait_for_timeout(1_000)
                logger.debug("cv_uploaded")
            except Exception as exc:
                logger.warning("cv_upload_failed error=%s", exc)

    def _fill_visible_fields(self, job: Dict[str, Any]) -> None:
        questions: List[str] = []
        inputs = self._page.query_selector_all(_Li.TEXT_INPUTS)

        for inp in inputs:
            try:
                lbl: str = inp.evaluate(
                    """el => {
                        if (el.id) {
                            const l = document.querySelector('label[for="'+el.id+'"]');
                            if (l) return l.innerText.trim();
                        }
                        const wrap = el.closest(
                            '.fb-dash-form-element,'
                            + '.jobs-easy-apply-form-section__grouping,'
                            + '[data-test-form-element]'
                        );
                        return wrap
                            ? (wrap.querySelector('label,legend')?.innerText?.trim() || '')
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

def run_auto_apply(
    jobs: List[Dict[str, Any]],
    max_applies: int = MAX_PER_RUN,
    headless: bool = False,
) -> List[ApplyResult]:
    """
    Entry point called from run_daily._auto_apply_linkedin().
    headless=False (default) opens visible browser — recommended for LinkedIn.
    """
    if not AUTO_APPLY_ENABLED:
        logger.info("auto_apply_disabled AUTO_APPLY_ENABLED=false")
        return []

    with LinkedInEasyApplyEngine(headless=headless) as engine:
        return engine.apply_batch(jobs, max_applies=max_applies)
