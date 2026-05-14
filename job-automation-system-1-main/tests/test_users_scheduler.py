"""
tests/test_users_scheduler.py
Tests for the multi-user scheduler skeleton (Phase 1).

All DB calls are patched — no real database required.
Invariants verified:
  - run_all iterates over every active user returned by list_active_users
  - run_all returns {email: rc} mapping
  - custom runner can be injected
  - exceptions in a single user do not abort the whole batch
  - empty user list returns {} and logs a warning
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.repositories.users_repo import User


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_user(email: str, user_id: int = 1) -> User:
    from datetime import datetime, timezone
    return User(
        id=user_id,
        email=email,
        password_hash="fake",
        role="user",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_login_at=None,
    )


# ── Scheduler construction ────────────────────────────────────────────────────

class TestSchedulerConstruction:
    def test_default_runner_is_legacy_stub(self):
        from src.users.scheduler import UserScheduler

        sched = UserScheduler()
        assert sched.runner is not None

    def test_custom_runner_can_be_injected(self):
        from src.users.scheduler import UserScheduler

        custom = MagicMock(return_value=0)
        sched = UserScheduler(runner=custom)
        assert sched.runner is custom


# ── run_all ───────────────────────────────────────────────────────────────────

class TestRunAll:
    def test_calls_runner_for_every_active_user(self):
        from src.users.scheduler import UserScheduler

        users = [_make_user("alice@rico.ai", 1), _make_user("bob@rico.ai", 2)]
        runner = MagicMock(return_value=0)

        with patch("src.repositories.users_repo.list_active_users", return_value=users):
            sched = UserScheduler(runner=runner)
            results = sched.run_all()

        assert runner.call_count == 2
        assert results == {"alice@rico.ai": 0, "bob@rico.ai": 0}

    def test_returns_nonzero_rc_when_user_fails(self):
        from src.users.scheduler import UserScheduler

        users = [_make_user("alice@rico.ai"), _make_user("bob@rico.ai")]
        runner = MagicMock(side_effect=[0, 1])

        with patch("src.repositories.users_repo.list_active_users", return_value=users):
            sched = UserScheduler(runner=runner)
            results = sched.run_all()

        assert results == {"alice@rico.ai": 0, "bob@rico.ai": 1}

    def test_empty_user_list_returns_empty_dict(self):
        from src.users.scheduler import UserScheduler

        with patch("src.repositories.users_repo.list_active_users", return_value=[]):
            sched = UserScheduler(runner=MagicMock())
            results = sched.run_all()

        assert results == {}

    def test_exception_for_one_user_does_not_abort_batch(self):
        from src.users.scheduler import UserScheduler

        users = [_make_user("alice@rico.ai"), _make_user("bob@rico.ai")]
        runner = MagicMock(side_effect=[RuntimeError("boom"), 0])

        with patch("src.repositories.users_repo.list_active_users", return_value=users):
            sched = UserScheduler(runner=runner)
            results = sched.run_all()

        # alice raised → not in results; bob succeeded → in results
        assert "alice@rico.ai" not in results
        assert results.get("bob@rico.ai") == 0
        assert runner.call_count == 2

    def test_injected_runner_receives_user_id(self):
        from src.users.scheduler import UserScheduler

        users = [_make_user("charlie@rico.ai")]
        runner = MagicMock(return_value=0)

        with patch("src.repositories.users_repo.list_active_users", return_value=users):
            sched = UserScheduler(runner=runner)
            sched.run_all()

        runner.assert_called_once_with("charlie@rico.ai")


# ── list_active_users integration (patched) ──────────────────────────────────

class TestListActiveUsersStub:
    def test_list_active_users_returns_empty_when_db_unavailable(self):
        from src.repositories.users_repo import list_active_users

        with patch("src.db.is_db_available", return_value=False):
            result = list_active_users()

        assert result == []

    def test_list_active_users_returns_user_objects(self):
        from src.repositories.users_repo import list_active_users

        rows = [
            (1, "alice@rico.ai", "hash1", "user", True, None, None),
            (2, "bob@rico.ai", "hash2", "admin", True, None, None),
        ]
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = rows
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.db.is_db_available", return_value=True), \
             patch("src.db.get_db_connection", return_value=conn):
            result = list_active_users()

        assert len(result) == 2
        assert result[0].email == "alice@rico.ai"
        assert result[1].email == "bob@rico.ai"
        assert result[1].role == "admin"
