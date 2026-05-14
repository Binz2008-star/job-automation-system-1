"""
scripts/run_browser_apply.py
Indeed Easy Apply runner — only targets jobs with the "Easily apply" badge.

Flow:
  1. Scrape Indeed search results for each role
  2. Filter cards that show the "Easily apply" badge (.iaLabel)
  3. Apply manager-level title filter and score threshold
  4. For each eligible job: navigate to page, click Apply, fill form, submit
  5. Track results in applied_jobs.json and DB

Usage:
    python scripts/run_browser_apply.py --dry-run   # show badge jobs, no apply
    python scripts/run_browser_apply.py             # live run (max 2)
    python scripts/run_browser_apply.py --max 5     # override cap
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.db import get_db_connection, mark_applied as db_mark_applied
from src.applications import load_applied_jobs, save_applied_jobs, get_job_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("browser_apply")

BASE_DIR    = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "data" / "ng_profile"
RATE_FILE   = BASE_DIR / "data" / "browser_apply_rate.json"
CV_PATH     = BASE_DIR / "data" / "cv.pdf"

SCORE_THRESHOLD = 50   # lower bar — Easy Apply jobs rarely have description text
DAILY_LIMIT     = 5
COOLDOWN_S      = 90

INDEED_BASE = "https://ae.indeed.com"
INDEED_SEARCH_ROLES = [
    "HSE Manager",
    "QHSE Manager",
    "EHS Manager",
    "Safety Manager",
    "Environmental Manager",
    "Compliance Manager",
]

SKIP_TITLE_TERMS = [
    "uae national", "intern",
    "inspector", "officer", "specialist", "coordinator", "supervisor",
]
KEEP_TITLE_TERMS = ["manager", "director", "lead", "head", "chief"]


# ── Rate limiter ──────────────────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self) -> None:
        self._state = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(RATE_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"date": "", "count": 0, "last_apply": None}

    def _save(self) -> None:
        RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        RATE_FILE.write_text(json.dumps(self._state))

    def _reset_if_new_day(self) -> None:
        today = date.today().isoformat()
        if self._state.get("date") != today:
            self._state = {"date": today, "count": 0, "last_apply": None}
            self._save()

    def can_apply(self) -> tuple[bool, str]:
        self._reset_if_new_day()
        if self._state["count"] >= DAILY_LIMIT:
            return False, f"daily limit reached ({self._state['count']}/{DAILY_LIMIT})"
        last = self._state.get("last_apply")
        if last:
            elapsed = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
            if elapsed < COOLDOWN_S:
                return False, f"cooldown: {int(COOLDOWN_S - elapsed)}s remaining"
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


# ── Card-level helpers ────────────────────────────────────────────────────────

def _card_text(card, selector: str) -> str:
    try:
        n = card.query_selector(selector)
        return n.inner_text().strip() if n else ""
    except Exception:
        return ""


def _card_href(card, selector: str, base: str) -> str:
    try:
        n = card.query_selector(selector)
        if not n:
            return ""
        href = n.get_attribute("href") or ""
        return href if href.startswith("http") else base + href
    except Exception:
        return ""


# ── Candidate scraping ────────────────────────────────────────────────────────

def _already_applied_links() -> set[str]:
    return {j.get("link", "") for j in load_applied_jobs()}


def _wait_for_cloudflare(page, timeout_s: int = 15) -> bool:
    """Wait out Cloudflare's 'Just a moment...' JS challenge."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        title = page.title()
        if "just a moment" not in title.lower():
            return True
        page.wait_for_timeout(1_500)
    logger.warning("cloudflare_challenge_timeout after %ds", timeout_s)
    return False


def scrape_indeed_easy_apply_candidates(page) -> list[dict]:
    """
    Iterate Indeed search results for every role.
    Return only cards with the 'Easily apply' badge, scored and title-filtered.
    """
    from src.scoring import score_job

    # Warm up — land on homepage and wait for Cloudflare JS challenge to clear
    try:
        page.goto(INDEED_BASE, wait_until="networkidle", timeout=30_000)
        _wait_for_cloudflare(page, timeout_s=20)
        page.wait_for_timeout(1_500)
        logger.info("homepage_ready title=%r", page.title()[:60])
    except Exception:
        logger.warning("homepage_warmup_failed — proceeding anyway")

    seen: set[str]          = set()
    applied_links: set[str] = _already_applied_links()
    candidates: list[dict]  = []

    for role in INDEED_SEARCH_ROLES:
        url = f"{INDEED_BASE}/jobs?q={quote_plus(role)}&l=UAE&filter=0"
        try:
            page.goto(url, wait_until="networkidle", timeout=30_000)
            _wait_for_cloudflare(page, timeout_s=20)
            page.wait_for_timeout(1_500)
        except Exception:
            logger.warning("nav_failed role=%r", role)
            continue

        cards = page.query_selector_all(".job_seen_beacon")
        badge_count = 0

        for card in cards:
            # Only process cards with the "Easily apply" badge
            badge = card.query_selector(".iaLabel, [aria-label*='Easily apply']")
            if not badge:
                continue

            title   = _card_text(card, ".jobTitle span") or _card_text(card, "h2 span")
            company = _card_text(card, ".companyName") or _card_text(card, "span.companyName")
            link    = _card_href(card, "a.jcs-JobTitle", INDEED_BASE)

            if not link or link in seen or link in applied_links:
                continue

            t = (title or "").lower()
            if any(term in t for term in SKIP_TITLE_TERMS):
                continue
            if not any(term in t for term in KEEP_TITLE_TERMS):
                continue

            seen.add(link)
            badge_count += 1

            job = {
                "title":       title,
                "company":     company,
                "location":    "UAE",
                "link":        link,
                "description": "",
                "source":      "indeed_easy_apply",
            }
            job["score"] = score_job(job)
            candidates.append(job)

        logger.info("indeed_search role=%r cards=%d easy_apply_badge=%d", role, len(cards), badge_count)

    candidates.sort(key=lambda j: j["score"], reverse=True)
    return candidates


# ── Apply flow ────────────────────────────────────────────────────────────────

def _fill_if_empty(page, selector: str, value: str) -> None:
    try:
        el = page.query_selector(selector)
        if el and el.is_visible() and not (el.input_value() or "").strip():
            el.fill(value)
    except Exception:
        pass


def _upload_cv(page) -> bool:
    if not CV_PATH.exists():
        logger.warning("cv_missing path=%s", CV_PATH)
        return False
    try:
        inp = page.query_selector("input[type='file']")
        if inp:
            inp.set_input_files(str(CV_PATH))
            page.wait_for_timeout(1_000)
            logger.info("cv_uploaded")
            return True
    except Exception:
        pass
    return False


def _click_first(page, selectors: list[str], timeout: int = 4_000) -> bool:
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=timeout, state="visible")
            page.click(sel)
            return True
        except Exception:
            continue
    return False


def _apply_indeed(page, job: dict) -> tuple[str, str]:
    """
    Navigate to an Indeed job page, confirm Easy Apply button is present,
    and walk through the multi-step apply modal.
    """
    page.wait_for_timeout(2_000)

    # Confirm the job page has an Indeed Apply button (not external ATS)
    apply_btn_selectors = [
        "button.ia-IndeedApplyButton",
        "button[id^='indeedApply']",
        ".ia-IndeedApplyButton",
        "button:has-text('Apply now')",
    ]
    apply_btn = None
    for sel in apply_btn_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                apply_btn = el
                logger.info("apply_btn_found sel=%r", sel)
                break
        except Exception:
            continue

    # Check for external-only signal before giving up
    if not apply_btn:
        ext = page.query_selector(
            "a:has-text('Apply on company site'), a:has-text('Apply on employer site')"
        )
        if ext:
            return "external_redirect", "no Indeed Apply button — external ATS only"
        return "no_apply_button", "no apply button found on job page"

    apply_btn.click()
    page.wait_for_timeout(3_000)

    # Indeed Apply opens in a new page or overlay — detect which
    all_pages = page.context.pages
    apply_page = all_pages[-1] if len(all_pages) > 1 else page

    # Wait for apply form to load
    form_ready_sels = [
        ".ia-BasePage",
        ".ia-container",
        "[class*='IndeedApply']",
        "form[data-testid]",
        "button[data-testid='continue-button']",
    ]
    form_loaded = False
    for sel in form_ready_sels:
        try:
            apply_page.wait_for_selector(sel, timeout=6_000)
            form_loaded = True
            break
        except Exception:
            continue

    if not form_loaded:
        if "indeed.com" not in apply_page.url:
            return "external_redirect", f"redirected to {apply_page.url}"
        return "failed", "apply form did not load"

    # Walk up to 6 steps (Indeed Apply is a wizard)
    MAX_STEPS = 6
    for step in range(MAX_STEPS):
        apply_page.wait_for_timeout(1_500)

        # Upload CV if file input appears
        _upload_cv(apply_page)

        # Fill contact fields if empty
        _fill_if_empty(apply_page,
            "input[name*='name' i]:not([type='hidden']), input[placeholder*='name' i]",
            "Roben Edwan")
        _fill_if_empty(apply_page,
            "input[type='email']",
            "robenedwan@gmail.com")
        _fill_if_empty(apply_page,
            "input[type='tel'], input[name*='phone' i]",
            "+971")

        apply_page.wait_for_timeout(500)

        # Check for success/confirmation page
        body = apply_page.inner_text("body").lower()
        if any(t in body for t in [
            "application submitted", "you applied", "application sent",
            "successfully applied", "your application has been submitted",
        ]):
            return "applied", f"submitted at step {step + 1}"

        # Try submit first (final step)
        submitted = _click_first(apply_page, [
            "button[data-testid='submit-button']",
            "button:has-text('Submit your application')",
            "button:has-text('Submit application')",
        ], timeout=2_000)
        if submitted:
            apply_page.wait_for_timeout(2_500)
            body = apply_page.inner_text("body").lower()
            if any(t in body for t in ["application submitted", "you applied", "successfully applied"]):
                return "applied", "submitted successfully"
            return "applied", "submit clicked (no explicit confirmation)"

        # Not the final step — click Continue/Next
        continued = _click_first(apply_page, [
            "button[data-testid='continue-button']",
            "button:has-text('Continue')",
            "button:has-text('Next')",
        ], timeout=3_000)
        if not continued:
            return "failed", f"stuck at step {step + 1} — no continue/submit found"

    return "failed", f"exceeded {MAX_STEPS} steps without confirmation"


# ── Result tracking ───────────────────────────────────────────────────────────

def _record_result(job: dict, status: str, message: str) -> None:
    """Persist result to applied_jobs.json and DB (for applied status)."""
    applied_jobs = load_applied_jobs()
    job_id = get_job_id(job)

    for entry in applied_jobs:
        if entry.get("job_id") == job_id:
            entry["status"]       = status
            entry["date_updated"] = datetime.now().isoformat()
            entry["notes"]        = message
            save_applied_jobs(applied_jobs)
            break
    else:
        applied_jobs.append({
            "job_id":       job_id,
            "title":        job.get("title", ""),
            "company":      job.get("company", ""),
            "location":     job.get("location", ""),
            "link":         job.get("link", ""),
            "score":        job.get("score", 0),
            "source":       job.get("source", ""),
            "status":       status,
            "date_applied": datetime.now().isoformat(),
            "date_updated": datetime.now().isoformat(),
            "notes":        message,
        })
        save_applied_jobs(applied_jobs)

    if status == "applied":
        db_mark_applied(job.get("link", ""), notes=message)


# ── Main runner ───────────────────────────────────────────────────────────────

def run(dry_run: bool = False, max_applies: int = 2) -> list[dict]:
    from playwright.sync_api import sync_playwright

    pw_instance = sync_playwright().start()
    ctx = pw_instance.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=False,
        slow_mo=250,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_https_errors=True,
    )
    page = ctx.new_page()

    candidates = scrape_indeed_easy_apply_candidates(page)

    if not candidates:
        ctx.close()
        pw_instance.stop()
        print("No eligible Indeed Easy Apply jobs found.")
        return []

    print()
    print(f"{'='*68}")
    print(f"  Indeed Easy Apply candidates  (score >= {SCORE_THRESHOLD}, manager-level)")
    print(f"{'='*68}")
    for i, j in enumerate(candidates, 1):
        print(f"  {i:2}. [{j['score']:3d}] {j['title'][:48]:<48} [Easy Apply]")
        print(f"       {j['company'][:55]}")
        print(f"       {j['link'][:72]}")
    print()

    eligible = [j for j in candidates if j["score"] >= SCORE_THRESHOLD]

    if dry_run:
        ctx.close()
        pw_instance.stop()
        if not eligible:
            print(f"  DRY RUN — {len(candidates)} badge jobs found but none meet "
                  f"score threshold ({SCORE_THRESHOLD}). "
                  f"Highest: {candidates[0]['score']} — {candidates[0]['title']}")
        else:
            print(f"  DRY RUN — {len(candidates)} badge jobs found, "
                  f"{len(eligible)} above score {SCORE_THRESHOLD}. "
                  f"Would apply to top {min(max_applies, len(eligible))}.")
        return candidates

    if not eligible:
        ctx.close()
        pw_instance.stop()
        print(f"  No jobs meet score threshold ({SCORE_THRESHOLD}).")
        return candidates

    # ── Live run ──────────────────────────────────────────────────────────────
    rate = _RateLimiter()
    ok, reason = rate.can_apply()
    if not ok:
        logger.warning("rate_limited: %s", reason)
        ctx.close()
        pw_instance.stop()
        return []

    results        = []
    applied_count  = 0

    for job in eligible:
        if applied_count >= max_applies:
            break

        ok, reason = rate.can_apply()
        if not ok:
            logger.info("stopping: %s", reason)
            break

        title   = job["title"]
        company = job["company"]
        score   = job["score"]
        link    = job["link"]

        logger.info("processing [%d] %s @ %s", score, title, company)

        try:
            page.goto(link, wait_until="domcontentloaded", timeout=25_000)
        except Exception as exc:
            status, msg = "failed", f"nav error: {exc}"
            logger.warning("nav_failed %s: %s", link, exc)
            _record_result(job, status, msg)
            results.append({**job, "apply_status": status, "message": msg})
            continue

        status, msg = _apply_indeed(page, job)

        icon = "✅" if status == "applied" else "↗" if status == "external_redirect" else "⚠"
        print(f"  {icon} [{score}] {title[:48]} | {status} | {msg}")

        _record_result(job, status, msg)
        results.append({**job, "apply_status": status, "message": msg})

        if status == "applied":
            rate.record()
            applied_count += 1
            if applied_count < max_applies:
                logger.info("cooldown %ds", COOLDOWN_S)
                time.sleep(COOLDOWN_S)

    ctx.close()
    pw_instance.stop()

    print()
    applied  = sum(1 for r in results if r["apply_status"] == "applied")
    external = sum(1 for r in results if r["apply_status"] == "external_redirect")
    other    = len(results) - applied - external
    print(f"  Run complete — applied: {applied}  external: {external}  other: {other}")
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Indeed Easy Apply runner")
    parser.add_argument("--dry-run", action="store_true", help="show candidates, no apply")
    parser.add_argument("--max",     type=int, default=2,  help="max applies per run (default: 2)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, max_applies=args.max)


if __name__ == "__main__":
    main()
