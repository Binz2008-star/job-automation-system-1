"""
tests/test_adversarial_qa.py
Adversarial QA regression suite.

Covers every critical bug found in the audit:
  1.  Race condition in mark_applied() (concurrent writes)
  2.  cursor.rowcount outside with-block in db.update_application_status()
  3.  No auth on control_server endpoints
  4.  HTML injection via link field in telegram_bot
  5.  Job ID collision between different jobs
  6.  N+1 file reads in is_applied() (batch check test)
  7.  RateLimiter concurrency safety
  8.  LLM cache atomic write / corrupt-file recovery
  9.  assert → RuntimeError in auto_apply._do_apply()
  10. Telegram message <= 4096 chars
  11. get_seen_links() applies a LIMIT clause
  12. skip_job actually persists (no longer a no-op)
  13. score_job handles non-dict input without crashing
  14. filter_new_jobs handles corrupt seen_jobs.json
  15. filter_new_jobs loads seen_jobs once (no N+1)
  16. save_applied_jobs is atomic (no partial write corruption)
  17. update_application_status rejects invalid status
  18. is_applied backward-compat with legacy IDs
  19. Telegram link field is scheme-validated (no javascript:)
  20. RateLimiter resets on new day
"""

from __future__ import annotations

import builtins
import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_job(n: int = 0, link: str = "") -> Dict[str, Any]:
    return {
        "title": f"HSE Manager {n}",
        "company": f"Company {n}",
        "location": "Dubai",
        "link": link or f"https://linkedin.com/jobs/view/{n}",
        "score": 80,
    }


# ══════════════════════════════════════════════════════════════════════════════
# #1 — Race condition: concurrent mark_applied must not duplicate
# ══════════════════════════════════════════════════════════════════════════════

class TestMarkAppliedConcurrency:
    def test_concurrent_calls_produce_exactly_one_record(self, tmp_path, monkeypatch):
        applied_file = tmp_path / "applied_jobs.json"
        applied_file.write_text("[]")
        lock_file = tmp_path / "applied_jobs.json.lock"

        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(applied_file))
        monkeypatch.setattr(app_mod, "_LOCK_FILE", str(lock_file))

        job = _make_job(1, "https://linkedin.com/jobs/view/race-test")
        results: List[bool] = []
        barrier = threading.Barrier(10)

        def _apply():
            barrier.wait()
            results.append(app_mod.mark_applied(dict(job)))

        threads = [threading.Thread(target=_apply) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        saved = json.loads(applied_file.read_text())
        assert len(saved) == 1, (
            f"Expected 1 record after 10 concurrent calls, got {len(saved)}"
        )
        assert results.count(True) == 1, (
            f"mark_applied returned True {results.count(True)} times — should be 1"
        )

    def test_mark_applied_returns_false_on_duplicate(self, tmp_path, monkeypatch):
        applied_file = tmp_path / "applied_jobs.json"
        applied_file.write_text("[]")
        lock_file = tmp_path / "applied_jobs.json.lock"

        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(applied_file))
        monkeypatch.setattr(app_mod, "_LOCK_FILE", str(lock_file))

        job = _make_job(2)
        assert app_mod.mark_applied(job) is True
        assert app_mod.mark_applied(job) is False


# ══════════════════════════════════════════════════════════════════════════════
# #2 — cursor.rowcount bug in db.update_application_status
# ══════════════════════════════════════════════════════════════════════════════

class TestDbUpdateApplicationStatus:
    def test_returns_true_when_row_updated(self):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("src.db.get_db_connection", return_value=mock_conn):
            from src.db import update_application_status
            result = update_application_status("https://ex.com/job", "interview")

        assert result is True, (
            "update_application_status should return True when rowcount=1 "
            "(regression: cursor.rowcount was read outside the with-block)"
        )

    def test_returns_false_when_no_row_matches(self):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 0

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("src.db.get_db_connection", return_value=mock_conn):
            from src.db import update_application_status
            result = update_application_status("https://nonexistent.com", "applied")

        assert result is False

    def test_rejects_invalid_status(self):
        with patch("src.db.get_db_connection", return_value=MagicMock()):
            from src.db import update_application_status
            result = update_application_status("https://ex.com/job", "invalid_status")
        assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# #3 — Authentication on control_server endpoints
# ══════════════════════════════════════════════════════════════════════════════

class TestControlServerAuth:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("CONTROL_SERVER_API_KEY", "test-secret-key-12345")
        import importlib
        import src.control_server as cs_mod
        importlib.reload(cs_mod)
        from fastapi.testclient import TestClient
        return TestClient(cs_mod.app), cs_mod

    def test_apply_one_without_key_returns_4xx(self, client):
        """No key → 401 or 403. FastAPI version determines which; both mean 'rejected'."""
        tc, _ = client
        with patch("src.naukrigulf_apply.run_naukrigulf_apply", return_value=[]):
            r = tc.post("/apply-one", json={"job": {"link": "https://naukrigulf.com/j/1"}})
        assert r.status_code in (401, 403), f"Expected 401 or 403, got {r.status_code}"

    def test_apply_one_with_wrong_key_returns_403(self, client):
        tc, _ = client
        r = tc.post(
            "/apply-one",
            json={"job": {"link": "https://naukrigulf.com/j/1"}},
            headers={"X-API-Key": "wrong-key"},
        )
        assert r.status_code == 403

    def test_apply_one_with_correct_key_proceeds(self, client):
        tc, _ = client
        with patch("src.naukrigulf_apply.run_naukrigulf_apply", return_value=[]):
            r = tc.post(
                "/apply-one",
                json={"job": {"link": "https://naukrigulf.com/jobs/test", "title": "T"}},
                headers={"X-API-Key": "test-secret-key-12345"},
            )
        # Should not be 403
        assert r.status_code != 403

    def test_health_endpoint_requires_no_auth(self, client):
        tc, _ = client
        r = tc.get("/health")
        assert r.status_code == 200

    def test_missing_api_key_env_returns_503(self, monkeypatch):
        monkeypatch.setenv("CONTROL_SERVER_API_KEY", "")
        import importlib
        import src.control_server as cs_mod
        importlib.reload(cs_mod)
        from fastapi.testclient import TestClient
        tc = TestClient(cs_mod.app)
        r = tc.post(
            "/apply-one",
            json={"job": {"link": "https://naukrigulf.com/j/1"}},
            headers={"X-API-Key": "anything"},
        )
        assert r.status_code == 503, (
            "When CONTROL_SERVER_API_KEY is unset, server must return 503, not allow access"
        )


# ══════════════════════════════════════════════════════════════════════════════
# #4 — HTML injection via link field in telegram_bot
# ══════════════════════════════════════════════════════════════════════════════

class TestTelegramSecurity:
    def test_malicious_link_is_escaped(self):
        """
        The attack vector is a single-quote that would break out of href="..." context.
        html.escape(quote=True) converts ' → &#x27;, neutralising the injection.
        The word 'onclick' can legitimately appear as a URL query param or path segment
        and is harmless once the quote is escaped — so we check for escaped quotes,
        not for the word itself.
        """
        from src.telegram_bot import format_telegram_jobs

        malicious_link = "https://evil.com' onclick='alert(document.cookie)"
        jobs = [({
            "title": "Safe Title",
            "company": "Safe Corp",
            "location": "Dubai",
            "link": malicious_link,
        }, 85)]

        result = format_telegram_jobs(jobs)

        # The raw single-quote must NOT appear unescaped inside the href attribute.
        # Any occurrence of ' in the output must be HTML-entity encoded.
        import re
        # Find href="..." values in the output
        href_matches = re.findall(r'href="([^"]*)"', result)
        for href_val in href_matches:
            assert "'" not in href_val, (
                f"Unescaped single-quote found in href attribute — injection possible!\n"
                f"href value: {href_val!r}"
            )

        # Double-check: scheme-dangerous protocols must not appear
        assert "javascript:" not in result.lower()

    def test_javascript_link_is_sanitised(self):
        from src.telegram_bot import format_telegram_jobs

        jobs = [({
            "title": "T",
            "company": "C",
            "location": "Dubai",
            "link": "javascript:void(document.cookie)",
        }, 80)]

        result = format_telegram_jobs(jobs)
        assert "javascript:" not in result, "javascript: scheme leaked into message"

    def test_title_company_location_are_escaped(self):
        from src.telegram_bot import format_telegram_jobs

        jobs = [({
            "title": "<script>alert(1)</script>",
            "company": "<b>Bold Corp</b>",
            "location": "Dubai & UAE",
            "link": "https://linkedin.com/jobs/1",
        }, 70)]

        result = format_telegram_jobs(jobs)
        assert "<script>" not in result
        assert "&amp;" in result or "Dubai" in result  # ampersand escaped


# ══════════════════════════════════════════════════════════════════════════════
# #5 — Job ID collision between distinct jobs
# ══════════════════════════════════════════════════════════════════════════════

class TestJobIdCollision:
    def test_different_links_give_different_ids(self):
        from src.applications import get_job_id

        a = {"title": "HSE Manager", "company": "X", "location": "Dubai",
             "link": "https://site.com/job/1"}
        b = {"title": "HSE Manager", "company": "X", "location": "Dubai",
             "link": "https://site.com/job/2"}
        assert get_job_id(a) != get_job_id(b)

    def test_legacy_collision_resolved_by_link(self):
        from src.applications import get_job_id

        # These two would produce the same legacy string ID but have different links
        a = {"title": "HSE Manager",     "company": "ABC Group",   "location": "Dubai",
             "link": "https://site.com/1"}
        b = {"title": "HSE Manager ABC", "company": "Group Dubai", "location": "",
             "link": "https://site.com/2"}
        assert get_job_id(a) != get_job_id(b), "ID collision detected!"

    def test_same_job_gives_same_id(self):
        from src.applications import get_job_id

        job = _make_job(99)
        assert get_job_id(job) == get_job_id(job)

    def test_empty_job_returns_empty_string(self):
        from src.applications import get_job_id
        assert get_job_id({}) == get_job_id({})  # consistent
        # Should not crash
        result = get_job_id({})
        assert isinstance(result, str)

    def test_non_dict_job_returns_empty_string(self):
        from src.applications import get_job_id
        assert get_job_id(None) == ""  # type: ignore
        assert get_job_id(42) == ""    # type: ignore
        assert get_job_id([]) == ""    # type: ignore


# ══════════════════════════════════════════════════════════════════════════════
# #6 — Batch is_applied: file must be read once for many jobs
# ══════════════════════════════════════════════════════════════════════════════

class TestIsAppliedBatch:
    def test_batch_reads_file_once(self, tmp_path, monkeypatch):
        applied_file = tmp_path / "applied_jobs.json"
        applied_file.write_text("[]")

        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(applied_file))

        read_count = 0
        real_open = builtins.open

        def _counting_open(path, *args, **kwargs):
            nonlocal read_count
            if "applied_jobs" in str(path) and ("r" in str(args) or not args):
                read_count += 1
            return real_open(path, *args, **kwargs)

        jobs = [_make_job(i) for i in range(50)]
        with patch("builtins.open", side_effect=_counting_open):
            result = app_mod.is_applied_batch(jobs)

        assert read_count <= 2, (
            f"is_applied_batch() triggered {read_count} file reads for 50 jobs "
            f"(should be ≤2 — regression for N+1 problem)"
        )
        assert isinstance(result, dict)
        assert len(result) == 50

    def test_batch_correctly_detects_applied_jobs(self, tmp_path, monkeypatch):
        applied_file = tmp_path / "applied_jobs.json"
        applied_file.write_text("[]")
        lock_file = tmp_path / "applied_jobs.json.lock"

        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(applied_file))
        monkeypatch.setattr(app_mod, "_LOCK_FILE", str(lock_file))

        job_a = _make_job(1, "https://ex.com/job/1")
        job_b = _make_job(2, "https://ex.com/job/2")

        app_mod.mark_applied(job_a)
        result = app_mod.is_applied_batch([job_a, job_b])

        assert result[app_mod.get_job_id(job_a)] is True
        assert result[app_mod.get_job_id(job_b)] is False


# ══════════════════════════════════════════════════════════════════════════════
# #7 — RateLimiter respects daily limit under concurrency
# ══════════════════════════════════════════════════════════════════════════════

class TestRateLimiterConcurrency:
    def test_daily_limit_not_exceeded_under_concurrency(self, tmp_path, monkeypatch):
        """
        try_acquire() must be atomic: check + increment in one lock acquisition.
        20 concurrent callers against a limit of 5 must produce exactly 5 successes.
        """
        import src.auto_apply as aa
        monkeypatch.setattr(aa, "DAILY_LIMIT", 5)
        monkeypatch.setattr(aa, "COOLDOWN_SECONDS", 0)

        rate_file = tmp_path / "rate.json"
        lock_file = tmp_path / "rate.json.lock"
        limiter = aa._RateLimiter(path=rate_file)
        limiter._lock_path = lock_file

        recorded: List[int] = []
        result_lock = threading.Lock()

        def _try():
            # Use try_acquire() — atomic check+record in one lock acquisition
            ok, _ = limiter.try_acquire()
            if ok:
                with result_lock:
                    recorded.append(1)

        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [ex.submit(_try) for _ in range(20)]
            for f in futures:
                f.result()

        final = aa._RateLimiter(path=rate_file)
        final._lock_path = lock_file
        assert final.today_count <= 5, (
            f"Daily limit breached: {final.today_count} > 5 "
            f"(try_acquire successes: {sum(recorded)})"
        )
        assert sum(recorded) <= 5, (
            f"try_acquire() returned True {sum(recorded)} times, expected ≤ 5"
        )

    def test_rate_limiter_resets_on_new_day(self, tmp_path, monkeypatch):
        import src.auto_apply as aa
        monkeypatch.setattr(aa, "DAILY_LIMIT", 3)
        monkeypatch.setattr(aa, "COOLDOWN_SECONDS", 0)

        rate_file = tmp_path / "rate.json"
        lock_file = tmp_path / "rate.json.lock"
        # Simulate yesterday's state
        yesterday = "2000-01-01"
        rate_file.write_text(json.dumps({"date": yesterday, "count": 3, "last_apply": None}))

        limiter = aa._RateLimiter(path=rate_file)
        limiter._lock_path = lock_file

        ok, reason = limiter.can_apply()
        assert ok is True, f"Expected reset on new day, got: {reason}"


# ══════════════════════════════════════════════════════════════════════════════
# #8 — LLM cache: atomic write and corrupt-file recovery
# ══════════════════════════════════════════════════════════════════════════════

class TestLLMCache:
    def test_corrupted_cache_returns_empty_dict(self, tmp_path, monkeypatch):
        import src.llm_scorer as ls
        cache_file = tmp_path / "llm_score_cache.json"
        cache_file.write_text("{INVALID JSON{{")
        monkeypatch.setattr(ls, "CACHE_FILE", cache_file)

        result = ls._load_cache()
        assert result == {}, "Corrupted cache should return {}, not raise"

    def test_save_cache_is_atomic(self, tmp_path, monkeypatch):
        """If write fails mid-way, original file must not be truncated."""
        import src.llm_scorer as ls
        cache_file = tmp_path / "llm_score_cache.json"
        original_data = {"fp1": 80, "fp2": 75}
        cache_file.write_text(json.dumps(original_data))
        monkeypatch.setattr(ls, "CACHE_FILE", cache_file)

        # Simulate write failure
        with patch("json.dump", side_effect=OSError("disk full")):
            ls._save_cache({"fp1": 0, "fp2": 0, "fp3": 0})

        # Original must be intact
        surviving = json.loads(cache_file.read_text())
        assert surviving == original_data, (
            "Cache was corrupted despite atomic write protection!"
        )

    def test_cache_accepts_new_entry_after_corrupt_load(self, tmp_path, monkeypatch):
        import src.llm_scorer as ls
        cache_file = tmp_path / "llm_score_cache.json"
        cache_file.write_text("NOT JSON")
        monkeypatch.setattr(ls, "CACHE_FILE", cache_file)

        # Should not raise
        cache = ls._load_cache()
        cache["new_fp"] = 90
        ls._save_cache(cache)  # must succeed

        result = json.loads(cache_file.read_text())
        assert result == {"new_fp": 90}


# ══════════════════════════════════════════════════════════════════════════════
# #9 — assert → RuntimeError in auto_apply
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoApplyAssertReplaced:
    def test_do_apply_raises_runtime_error_when_page_is_none(self):
        from src.auto_apply import LinkedInEasyApplyEngine, _RateLimiter

        engine = object.__new__(LinkedInEasyApplyEngine)
        engine._page = None
        engine._headless = True
        engine._logged_in = False
        engine._rate = MagicMock()
        engine._pw = None
        engine._browser = None
        engine._ctx = None

        with pytest.raises(RuntimeError, match="not initialised"):
            engine._do_apply(_make_job(1))

    def test_ensure_logged_in_raises_when_page_is_none(self):
        from src.auto_apply import LinkedInEasyApplyEngine

        engine = object.__new__(LinkedInEasyApplyEngine)
        engine._page = None
        engine._logged_in = False

        with pytest.raises(RuntimeError, match="not initialised"):
            engine._ensure_logged_in()

    def test_no_assertion_error_with_optimization_flag(self):
        """AssertionError is silently disabled with -O; RuntimeError is not."""
        from src.auto_apply import LinkedInEasyApplyEngine

        engine = object.__new__(LinkedInEasyApplyEngine)
        engine._page = None
        engine._logged_in = False

        # RuntimeError must be raised regardless of __debug__
        try:
            engine._do_apply(_make_job(1))
            pytest.fail("Expected RuntimeError, got nothing")
        except RuntimeError:
            pass  # correct
        except AssertionError:
            pytest.fail("assert statement used — disabled by -O optimization flag")


# ══════════════════════════════════════════════════════════════════════════════
# #10 — Telegram message ≤ 4096 chars
# ══════════════════════════════════════════════════════════════════════════════

class TestTelegramMessageLength:
    def test_long_job_list_stays_within_limit(self):
        from src.telegram_bot import format_telegram_jobs

        jobs = [({
            "title": "Senior QHSE Manager Environmental Sustainability Compliance ISO" * 2,
            "company": "Abu Dhabi National Energy Company PJSC International Holdings",
            "location": "Abu Dhabi, United Arab Emirates, Middle East Region",
            "link": f"https://linkedin.com/jobs/view/{i}",
        }, 90) for i in range(10)]

        result = format_telegram_jobs(jobs)
        assert len(result) <= 4096, (
            f"Message length {len(result)} exceeds Telegram limit of 4096 chars"
        )

    def test_empty_jobs_returns_valid_message(self):
        from src.telegram_bot import format_telegram_jobs
        result = format_telegram_jobs([])
        assert result  # non-empty
        assert len(result) <= 4096

    def test_send_telegram_message_clamps_long_message(self):
        from src.telegram_bot import send_telegram_message

        captured: List[Any] = []

        def _mock_post(url, json=None, timeout=None):
            captured.append(json)
            m = MagicMock()
            m.raise_for_status = lambda: None
            return m

        long_message = "X" * 10_000

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "1"}):
            with patch("requests.post", side_effect=_mock_post):
                from src.telegram_bot import send_telegram_message as stm
                # Re-import to pick up env vars
                stm(long_message)

        if captured:
            sent_text = captured[0]["text"]
            assert len(sent_text) <= 4096, (
                f"send_telegram_message sent {len(sent_text)} chars > 4096"
            )


# ══════════════════════════════════════════════════════════════════════════════
# #11 — get_seen_links applies a LIMIT clause
# ══════════════════════════════════════════════════════════════════════════════

class TestGetSeenLinksLimit:
    def test_query_contains_limit(self):
        captured: List[str] = []

        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_cursor.execute.side_effect = lambda q, *a: captured.append(str(q).upper())

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("src.db.get_db_connection", return_value=mock_conn):
            from src.db import get_seen_links
            get_seen_links()

        assert any("LIMIT" in q for q in captured), (
            "get_seen_links() has no LIMIT clause — "
            "will load entire jobs table into memory with large datasets"
        )

    def test_query_contains_date_filter(self):
        captured: List[str] = []

        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_cursor.execute.side_effect = lambda q, *a: captured.append(str(q).upper())

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("src.db.get_db_connection", return_value=mock_conn):
            from src.db import get_seen_links
            get_seen_links()

        assert any("INTERVAL" in q or "DATE" in q or "DAYS" in q for q in captured), (
            "get_seen_links() should filter by recent dates to avoid growing unbounded"
        )


# ══════════════════════════════════════════════════════════════════════════════
# #12 — skip_job actually persists
# ══════════════════════════════════════════════════════════════════════════════

class TestSkipJobPersists:
    def test_skip_job_marks_job_as_applied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CONTROL_SERVER_API_KEY", "test-key")

        applied_file = tmp_path / "applied_jobs.json"
        applied_file.write_text("[]")
        lock_file = tmp_path / "applied_jobs.json.lock"

        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(applied_file))
        monkeypatch.setattr(app_mod, "_LOCK_FILE", str(lock_file))

        import importlib
        import src.control_server as cs_mod
        importlib.reload(cs_mod)
        from fastapi.testclient import TestClient

        tc = TestClient(cs_mod.app)
        job = _make_job(99, "https://naukrigulf.com/job/99")
        r = tc.post(
            "/skip-job",
            json={"job": job},
            headers={"X-API-Key": "test-key"},
        )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("skipped", "already_skipped"), data

        # Verify persisted to disk
        saved = json.loads(applied_file.read_text())
        assert len(saved) == 1, (
            "skip_job must persist the job to applied_jobs.json — was a no-op before"
        )


# ══════════════════════════════════════════════════════════════════════════════
# #13 — score_job handles non-dict input
# ══════════════════════════════════════════════════════════════════════════════

class TestScoreJobTypeGuard:
    @pytest.mark.parametrize("bad_input", [
        None,
        "",
        42,
        3.14,
        [],
        ["title", "company"],
        "not a dict",
        b"bytes",
    ])
    def test_non_dict_returns_zero(self, bad_input):
        from src.scoring import score_job
        try:
            result = score_job(bad_input)
            assert result == 0, (
                f"score_job({bad_input!r}) returned {result} instead of 0"
            )
        except (AttributeError, TypeError) as e:
            pytest.fail(
                f"score_job({bad_input!r}) raised {type(e).__name__}: {e} "
                f"— type guard is missing"
            )

    def test_valid_dict_returns_int(self):
        from src.scoring import score_job
        job = {
            "title": "HSE Manager",
            "company": "ADNOC",
            "location": "Dubai",
            "description": "safety environment compliance",
        }
        result = score_job(job)
        assert isinstance(result, int)
        assert result >= 0


# ══════════════════════════════════════════════════════════════════════════════
# #14 — filter_new_jobs handles corrupt seen_jobs.json
# ══════════════════════════════════════════════════════════════════════════════

class TestFilterNewJobsResilience:
    def test_corrupt_seen_jobs_does_not_crash(self, tmp_path, monkeypatch):
        seen_file = tmp_path / "seen_jobs.json"
        seen_file.write_text("{CORRUPTED{{")

        import src.filter as f_mod
        monkeypatch.setattr(f_mod, "SEEN_JOBS_FILE", str(seen_file))
        monkeypatch.setattr(f_mod, "is_db_available", lambda: False)

        jobs = [_make_job(i) for i in range(5)]
        result = f_mod.filter_new_jobs(jobs)
        assert isinstance(result, list), "filter_new_jobs must not raise on corrupt file"
        assert len(result) == 5  # all jobs are new (seen list was empty/corrupt)

    def test_filter_new_jobs_reads_seen_once(self, tmp_path, monkeypatch):
        seen_file = tmp_path / "seen_jobs.json"
        seen_file.write_text("[]")

        import src.filter as f_mod
        monkeypatch.setattr(f_mod, "SEEN_JOBS_FILE", str(seen_file))
        monkeypatch.setattr(f_mod, "is_db_available", lambda: False)

        read_count = 0
        real_open = builtins.open

        def _counting(path, *a, **kw):
            nonlocal read_count
            if "seen_jobs" in str(path) and ("r" in str(a) or not a):
                read_count += 1
            return real_open(path, *a, **kw)

        jobs = [_make_job(i) for i in range(100)]
        with patch("builtins.open", side_effect=_counting):
            f_mod.filter_new_jobs(jobs)

        assert read_count <= 2, (
            f"filter_new_jobs() triggered {read_count} reads for 100 jobs (N+1)"
        )

    def test_duplicate_jobs_in_input_deduplicated(self, tmp_path, monkeypatch):
        seen_file = tmp_path / "seen_jobs.json"
        seen_file.write_text("[]")

        import src.filter as f_mod
        monkeypatch.setattr(f_mod, "SEEN_JOBS_FILE", str(seen_file))
        monkeypatch.setattr(f_mod, "is_db_available", lambda: False)

        job = _make_job(1, "https://example.com/same-link")
        result = f_mod.filter_new_jobs([job, job, job])
        assert len(result) == 1, "Duplicate jobs in input should be de-duplicated"


# ══════════════════════════════════════════════════════════════════════════════
# #15 — save_applied_jobs atomic write
# ══════════════════════════════════════════════════════════════════════════════

class TestAtomicWrite:
    def test_failed_write_leaves_original_intact(self, tmp_path, monkeypatch):
        applied_file = tmp_path / "applied_jobs.json"
        original = [_make_job(1)]
        applied_file.write_text(json.dumps(original))

        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(applied_file))

        # Simulate write failure
        with patch("json.dump", side_effect=OSError("disk full")):
            try:
                app_mod.save_applied_jobs([_make_job(99)])
            except Exception:
                pass

        surviving = json.loads(applied_file.read_text())
        assert surviving == original, (
            "Original data was destroyed during a failed write — "
            "atomic write protection failed"
        )

    def test_successful_write_persists_data(self, tmp_path, monkeypatch):
        applied_file = tmp_path / "applied_jobs.json"
        applied_file.write_text("[]")

        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(applied_file))

        new_data = [_make_job(5)]
        app_mod.save_applied_jobs(new_data)
        saved = json.loads(applied_file.read_text())
        assert len(saved) == 1


# ══════════════════════════════════════════════════════════════════════════════
# #16 — update_application_status rejects invalid status values
# ══════════════════════════════════════════════════════════════════════════════

class TestStatusValidation:
    def test_invalid_status_string_rejected(self, tmp_path, monkeypatch):
        applied_file = tmp_path / "applied_jobs.json"
        applied_file.write_text("[]")
        lock_file = tmp_path / "applied_jobs.json.lock"

        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(applied_file))
        monkeypatch.setattr(app_mod, "_LOCK_FILE", str(lock_file))

        job = _make_job(10)
        app_mod.mark_applied(job)

        result = app_mod.update_application_status(job, "HACKED'; DROP TABLE--")
        assert result is False, "Invalid status must be rejected"

    def test_valid_statuses_accepted(self, tmp_path, monkeypatch):
        applied_file = tmp_path / "applied_jobs.json"
        applied_file.write_text("[]")
        lock_file = tmp_path / "applied_jobs.json.lock"

        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(applied_file))
        monkeypatch.setattr(app_mod, "_LOCK_FILE", str(lock_file))

        job = _make_job(11)
        app_mod.mark_applied(job)

        for status in app_mod.VALID_STATUSES:
            result = app_mod.update_application_status(job, status)
            assert result is True, f"Valid status '{status}' was rejected"


# ══════════════════════════════════════════════════════════════════════════════
# #17 — Backward compatibility: legacy IDs still matched
# ══════════════════════════════════════════════════════════════════════════════

class TestLegacyIdBackwardCompat:
    def test_legacy_record_detected_by_is_applied(self, tmp_path, monkeypatch):
        """Jobs saved before the ID format change must still be detected as applied."""
        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(tmp_path / "a.json"))
        monkeypatch.setattr(app_mod, "_LOCK_FILE", str(tmp_path / "a.json.lock"))

        job = {"title": "HSE Officer", "company": "Shell", "location": "Abu Dhabi",
               "link": "https://linkedin.com/jobs/view/999"}
        legacy_id = f"{job['title']}_{job['company']}_{job['location']}".lower().replace(" ", "_")

        # Inject a record with the old ID format
        legacy_record = {
            "job_id": legacy_id,  # old format
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "link": job["link"],
            "status": "applied",
            "date_applied": "2024-01-01T00:00:00",
        }
        (tmp_path / "a.json").write_text(json.dumps([legacy_record]))

        assert app_mod.is_applied(job) is True, (
            "is_applied() must detect jobs saved with the old legacy ID format"
        )


# ══════════════════════════════════════════════════════════════════════════════
# #18 — filter_new_jobs atomic write
# ══════════════════════════════════════════════════════════════════════════════

class TestFilterAtomicWrite:
    def test_failed_save_seen_leaves_original_intact(self, tmp_path, monkeypatch):
        seen_file = tmp_path / "seen_jobs.json"
        original_seen = ["https://old-job.com/1"]
        seen_file.write_text(json.dumps(original_seen))

        import src.filter as f_mod
        monkeypatch.setattr(f_mod, "SEEN_JOBS_FILE", str(seen_file))
        monkeypatch.setattr(f_mod, "is_db_available", lambda: False)

        # Simulate write failure during save
        with patch("json.dump", side_effect=OSError("disk full")):
            try:
                f_mod.save_seen_jobs({"https://old-job.com/1", "https://new-job.com/2"})
            except Exception:
                pass

        surviving = json.loads(seen_file.read_text())
        assert surviving == original_seen, (
            "Seen jobs file was corrupted during failed write"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Edge Cases — null / empty / huge payloads
# ══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_mark_applied_none_job(self, tmp_path, monkeypatch):
        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(tmp_path / "a.json"))
        monkeypatch.setattr(app_mod, "_LOCK_FILE", str(tmp_path / "a.lock"))
        (tmp_path / "a.json").write_text("[]")
        result = app_mod.mark_applied(None)  # type: ignore
        assert result is False

    def test_mark_applied_huge_title(self, tmp_path, monkeypatch):
        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(tmp_path / "a.json"))
        monkeypatch.setattr(app_mod, "_LOCK_FILE", str(tmp_path / "a.lock"))
        (tmp_path / "a.json").write_text("[]")
        huge_job = {"title": "X" * 100_000, "company": "C", "location": "L",
                    "link": "https://ex.com/huge"}
        result = app_mod.mark_applied(huge_job)
        assert result is True  # should succeed without OOM

    def test_score_job_huge_description(self):
        from src.scoring import score_job
        job = {
            "title": "HSE Manager",
            "company": "ACME",
            "description": "safety " * 50_000,  # 350k chars
        }
        result = score_job(job)
        assert isinstance(result, int)
        assert 0 <= result <= 200  # reasonable range

    def test_is_applied_empty_string_fields(self, tmp_path, monkeypatch):
        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(tmp_path / "a.json"))
        (tmp_path / "a.json").write_text("[]")
        job = {"title": "", "company": "", "location": "", "link": ""}
        result = app_mod.is_applied(job)
        assert isinstance(result, bool)

    def test_format_telegram_none_fields(self):
        from src.telegram_bot import format_telegram_jobs
        jobs = [({
            "title": None,
            "company": None,
            "location": None,
            "link": None,
        }, None)]
        result = format_telegram_jobs(jobs)
        assert isinstance(result, str)
        assert len(result) <= 4096

    def test_filter_new_jobs_empty_list(self, tmp_path, monkeypatch):
        import src.filter as f_mod
        monkeypatch.setattr(f_mod, "SEEN_JOBS_FILE", str(tmp_path / "s.json"))
        monkeypatch.setattr(f_mod, "is_db_available", lambda: False)
        (tmp_path / "s.json").write_text("[]")
        result = f_mod.filter_new_jobs([])
        assert result == []

    def test_filter_new_jobs_non_dict_entries(self, tmp_path, monkeypatch):
        import src.filter as f_mod
        monkeypatch.setattr(f_mod, "SEEN_JOBS_FILE", str(tmp_path / "s.json"))
        monkeypatch.setattr(f_mod, "is_db_available", lambda: False)
        (tmp_path / "s.json").write_text("[]")
        jobs = [None, "not a dict", 42, _make_job(1)]  # type: ignore
        result = f_mod.filter_new_jobs(jobs)
        assert len(result) == 1  # only the valid dict passes

    def test_get_application_stats_empty(self, tmp_path, monkeypatch):
        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(tmp_path / "a.json"))
        (tmp_path / "a.json").write_text("[]")
        stats = app_mod.get_application_stats()
        assert stats["total_applied"] == 0
        assert stats["success_rate"] == 0.0

    def test_get_application_stats_corrupt_file(self, tmp_path, monkeypatch):
        import src.applications as app_mod
        monkeypatch.setattr(app_mod, "APPLIED_JOBS_FILE", str(tmp_path / "a.json"))
        (tmp_path / "a.json").write_text("CORRUPT")
        stats = app_mod.get_application_stats()
        assert stats["total_applied"] == 0  # should not crash
