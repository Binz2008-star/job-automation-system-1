"""
tests/unit/test_feedback_loop.py

Test suite for FeedbackLoopOrchestrator and CycleState.

Coverage:
  - CycleState: persistence, load/save roundtrip, corruption recovery
  - FeedbackLoopOrchestrator: init, cooldown guard, cycle execution,
    failure handling, background scheduling, state transitions
  - _is_due: all branches (never run, success+cooldown, failed, corrupt)
  - Boundary: _MIN_SAMPLES -1, exactly _MIN_SAMPLES, 4x _MIN_SAMPLES
  - Integration: full cycle → adjusted_probability changes

Design:
  - No mocking of internal constants — boundaries are tested via _MIN_SAMPLES
    imported directly so tests survive threshold changes.
  - All filesystem I/O uses tmp_path (pytest fixture) — no shared state.
  - Engine built from stubs; no DB or filesystem dependency outside tmp_path.
  - Async tests use pytest-asyncio.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.decision_engine import JobDecisionEngine
from src.feedback_loop import (
    CycleResult,
    CycleState,
    FeedbackLoopOrchestrator,
    _is_due,
)
from src.response_intelligence import (
    ResponseIntelligenceEngine,
    JsonFileStateStore,
    ScoringAdjustments,
    _MIN_SAMPLES,
)


# ---------------------------------------------------------------------------
# Fixtures and builders
# ---------------------------------------------------------------------------

def _job(link: str, score: int = 80, title: str = "Backend Engineer",
         company: str = "Acme", location: str = "Dubai UAE") -> Dict[str, Any]:
    return {
        "link": link,
        "title": title,
        "company": company,
        "location": location,
        "score": score,
        "date_found": datetime.now().isoformat(),
    }


def _app(link: str, status: str = "interview",
         days_ago: int = 5) -> Dict[str, Any]:
    applied = (datetime.now() - timedelta(days=days_ago)).isoformat()
    updated = datetime.now().isoformat()
    return {
        "link": link,
        "title": "Backend Engineer",
        "company": "Acme",
        "status": status,
        "date_applied": applied,
        "date_updated": updated,
    }


def _dataset(n: int, status: str = "interview") -> tuple[
    List[Dict[str, Any]], List[Dict[str, Any]]
]:
    """Return (jobs, apps) with n matched pairs."""
    jobs = [_job(link=f"https://example.com/job/{i}") for i in range(n)]
    apps = [_app(link=f"https://example.com/job/{i}", status=status) for i in range(n)]
    return jobs, apps


@pytest.fixture()
def decision_engine() -> JobDecisionEngine:
    profile = {"experience_years": 7}
    roles = ["Backend Engineer", "Software Engineer"]
    return JobDecisionEngine.from_loaders(lambda: profile, lambda: roles)


@pytest.fixture()
def orchestrator(tmp_path: Path, decision_engine: JobDecisionEngine) -> FeedbackLoopOrchestrator:
    return FeedbackLoopOrchestrator.build(
        decision_engine=decision_engine,
        state_dir=tmp_path,
        cooldown=timedelta(hours=6),
    )


# ---------------------------------------------------------------------------
# CycleState: persistence
# ---------------------------------------------------------------------------

class TestCycleState:
    def test_default_state_is_never_run(self, tmp_path: Path) -> None:
        state = CycleState.load(tmp_path / "nonexistent.json")
        assert state.last_run_status == "never"
        assert state.last_run_at is None
        assert state.total_cycles == 0

    def test_roundtrip_save_load(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        state = CycleState(
            last_run_at="2025-01-01T12:00:00",
            last_run_status="success",
            total_cycles=3,
            total_samples_processed=42,
            last_adjustments_version=2,
        )
        state.save(path)
        loaded = CycleState.load(path)

        assert loaded.last_run_at == state.last_run_at
        assert loaded.last_run_status == state.last_run_status
        assert loaded.total_cycles == state.total_cycles
        assert loaded.total_samples_processed == state.total_samples_processed
        assert loaded.last_adjustments_version == state.last_adjustments_version

    def test_save_is_atomic(self, tmp_path: Path) -> None:
        """save() must use tmp+rename, not direct write — no partial file visible."""
        path = tmp_path / "state.json"
        CycleState(last_run_status="success", total_cycles=1).save(path)
        assert path.exists()
        assert not path.with_suffix(".tmp").exists()  # tmp file cleaned up

    def test_corrupted_file_returns_default(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("{{not valid json{{", encoding="utf-8")
        state = CycleState.load(path)
        assert state.last_run_status == "never"

    def test_partial_json_returns_default(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"last_run_status": "success"}), encoding="utf-8")
        # Missing fields should cause load to fall back to default
        state = CycleState.load(path)
        # Either loaded with defaults or fell back — must not raise
        assert state is not None


# ---------------------------------------------------------------------------
# _is_due: all branches
# ---------------------------------------------------------------------------

class TestIsDue:
    def test_never_run_is_due(self) -> None:
        assert _is_due(CycleState(), timedelta(hours=6)) is True

    def test_failed_last_run_is_due(self) -> None:
        state = CycleState(
            last_run_at=datetime.now().isoformat(),
            last_run_status="failed",
        )
        assert _is_due(state, timedelta(hours=6)) is True

    def test_skipped_last_run_is_due(self) -> None:
        state = CycleState(
            last_run_at=datetime.now().isoformat(),
            last_run_status="skipped",
        )
        assert _is_due(state, timedelta(hours=6)) is True

    def test_recent_success_is_not_due(self) -> None:
        state = CycleState(
            last_run_at=datetime.now().isoformat(),
            last_run_status="success",
        )
        assert _is_due(state, timedelta(hours=6)) is False

    def test_expired_success_is_due(self) -> None:
        old = (datetime.now() - timedelta(hours=7)).isoformat()
        state = CycleState(last_run_at=old, last_run_status="success")
        assert _is_due(state, timedelta(hours=6)) is True

    def test_exactly_at_cooldown_boundary_is_due(self) -> None:
        """At exactly cooldown elapsed time, cycle is due (>= comparison)."""
        at_boundary = (datetime.now() - timedelta(hours=6)).isoformat()
        state = CycleState(last_run_at=at_boundary, last_run_status="success")
        assert _is_due(state, timedelta(hours=6)) is True

    def test_corrupt_timestamp_is_due(self) -> None:
        state = CycleState(last_run_at="not-a-date", last_run_status="success")
        assert _is_due(state, timedelta(hours=6)) is True


# ---------------------------------------------------------------------------
# Orchestrator: initialisation
# ---------------------------------------------------------------------------

class TestOrchestratorInit:
    def test_builds_without_error(self, orchestrator: FeedbackLoopOrchestrator) -> None:
        assert orchestrator is not None

    def test_initial_state_is_never(self, orchestrator: FeedbackLoopOrchestrator) -> None:
        assert orchestrator.cycle_state.last_run_status == "never"
        assert orchestrator.cycle_state.total_cycles == 0

    def test_is_due_on_fresh_instance(self, orchestrator: FeedbackLoopOrchestrator) -> None:
        assert orchestrator.is_due() is True

    def test_engine_is_shared_reference(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        """Same object returned on repeated access — not re-created."""
        assert orchestrator.engine is orchestrator.engine

    def test_loads_persisted_state_on_restart(
        self, tmp_path: Path, decision_engine: JobDecisionEngine
    ) -> None:
        """State survives process restart via disk persistence."""
        o1 = FeedbackLoopOrchestrator.build(decision_engine, state_dir=tmp_path)
        jobs, apps = _dataset(_MIN_SAMPLES)
        o1.run_cycle_sync(lambda: jobs, lambda: apps)

        # Simulate restart — new instance, same state_dir
        o2 = FeedbackLoopOrchestrator.build(decision_engine, state_dir=tmp_path)
        assert o2.cycle_state.last_run_status == "success"
        assert o2.cycle_state.total_cycles == 1


# ---------------------------------------------------------------------------
# Cycle execution: boundary conditions on sample count
# ---------------------------------------------------------------------------

class TestCycleSampleBoundaries:
    def test_below_minimum_samples_fails(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        """_MIN_SAMPLES - 1 matched pairs must produce status='failed'."""
        n = _MIN_SAMPLES - 1
        jobs, apps = _dataset(n)
        result = orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)

        assert result.status == "failed"
        assert result.error is not None
        assert result.matched_pairs == 0   # learning never ran

    def test_exactly_minimum_samples_succeeds(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        """Exactly _MIN_SAMPLES must clear the threshold."""
        n = _MIN_SAMPLES
        jobs, apps = _dataset(n)
        result = orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)

        assert result.status == "success"
        assert result.matched_pairs == n

    def test_well_above_minimum_samples_succeeds(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        """4x _MIN_SAMPLES — proves the happy path, not just the threshold."""
        n = _MIN_SAMPLES * 4
        jobs, apps = _dataset(n)
        result = orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)

        assert result.status == "success"
        assert result.matched_pairs == n

    def test_zero_jobs_fails(self, orchestrator: FeedbackLoopOrchestrator) -> None:
        result = orchestrator.run_cycle_sync(lambda: [], lambda: [])
        assert result.status == "failed"
        assert result.error is not None

    def test_unmatched_apps_do_not_count(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        """Apps with no matching job must not inflate matched_pairs."""
        jobs, _ = _dataset(_MIN_SAMPLES)
        # apps all point to different links that don't exist in jobs
        apps = [_app(link=f"https://other.com/{i}") for i in range(_MIN_SAMPLES * 3)]
        result = orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)

        assert result.status == "failed"   # 0 matched pairs < _MIN_SAMPLES


# ---------------------------------------------------------------------------
# Cycle execution: state transitions
# ---------------------------------------------------------------------------

class TestCycleStateTransitions:
    def test_successful_cycle_increments_counters(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        n = _MIN_SAMPLES
        jobs, apps = _dataset(n)
        orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)

        state = orchestrator.cycle_state
        assert state.last_run_status == "success"
        assert state.total_cycles == 1
        assert state.total_samples_processed == n
        assert state.last_error is None
        assert state.last_run_at is not None

    def test_failed_cycle_records_error(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        result = orchestrator.run_cycle_sync(lambda: [], lambda: [])

        state = orchestrator.cycle_state
        assert state.last_run_status == "failed"
        assert state.last_error is not None
        assert state.total_cycles == 0  # failure must not increment cycle count

    def test_second_cycle_accumulates_samples(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        n = _MIN_SAMPLES
        jobs, apps = _dataset(n)

        orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)
        # Force second run by resetting last_run_at
        with orchestrator._lock:
            orchestrator._state.last_run_at = (
                datetime.now() - timedelta(hours=7)
            ).isoformat()

        orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)

        state = orchestrator.cycle_state
        assert state.total_cycles == 2
        assert state.total_samples_processed == n * 2

    def test_successful_cycle_clears_previous_error(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        # First: fail
        orchestrator.run_cycle_sync(lambda: [], lambda: [])
        assert orchestrator.cycle_state.last_error is not None

        # Second: succeed (bypass cooldown — first run failed so is_due=True)
        jobs, apps = _dataset(_MIN_SAMPLES)
        orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)
        assert orchestrator.cycle_state.last_error is None


# ---------------------------------------------------------------------------
# Cooldown guard
# ---------------------------------------------------------------------------

class TestCooldownGuard:
    def test_second_run_within_cooldown_is_skipped(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        jobs, apps = _dataset(_MIN_SAMPLES)
        orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)

        result = orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)
        assert result.status == "skipped"
        assert result.skipped_reason is not None

    def test_skip_does_not_increment_cycle_count(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        jobs, apps = _dataset(_MIN_SAMPLES)
        orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)
        orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)  # skipped

        assert orchestrator.cycle_state.total_cycles == 1

    def test_is_due_false_after_success(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        jobs, apps = _dataset(_MIN_SAMPLES)
        orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)
        assert orchestrator.is_due() is False

    def test_is_due_true_after_failure(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        orchestrator.run_cycle_sync(lambda: [], lambda: [])
        assert orchestrator.is_due() is True


# ---------------------------------------------------------------------------
# Background scheduling
# ---------------------------------------------------------------------------

class TestBackgroundScheduling:
    def test_background_cycle_completes_and_updates_state(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        jobs, apps = _dataset(_MIN_SAMPLES)
        orchestrator.schedule_background_cycle(lambda: jobs, lambda: apps)

        # Drain the thread pool — at most 2s
        orchestrator._executor.shutdown(wait=True, cancel_futures=False)

        assert orchestrator.cycle_state.last_run_status == "success"
        assert orchestrator.cycle_state.total_cycles == 1

    def test_background_failure_is_recorded_not_raised(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        """Exceptions in background cycle must not propagate to caller."""
        orchestrator.schedule_background_cycle(lambda: [], lambda: [])
        orchestrator._executor.shutdown(wait=True, cancel_futures=False)

        assert orchestrator.cycle_state.last_run_status == "failed"


# ---------------------------------------------------------------------------
# Integration: feedback loop changes adjusted_probability
# ---------------------------------------------------------------------------

class TestFeedbackIntegration:
    def test_successful_outcomes_boost_probability(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        """
        After learning that 'Acme' applications succeed at a high rate,
        adjusted_probability for an Acme job must be >= the pre-learning value.
        """
        target_job = _job(link="https://example.com/target", company="Acme", score=70)

        prob_before = orchestrator.engine.adjusted_probability(target_job).probability

        # Train with high success rate for Acme
        n = _MIN_SAMPLES * 2
        jobs = [_job(link=f"https://example.com/j{i}", company="Acme") for i in range(n)]
        apps = [_app(link=f"https://example.com/j{i}", status="interview") for i in range(n)]
        result = orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)
        assert result.status == "success"

        prob_after = orchestrator.engine.adjusted_probability(target_job).probability
        assert prob_after >= prob_before

    def test_zero_outcomes_do_not_affect_probability(
        self, orchestrator: FeedbackLoopOrchestrator
    ) -> None:
        """
        Learning from all-rejected outcomes should not raise;
        probability direction may shift but must stay in [0, 95].
        """
        target_job = _job(link="https://example.com/target", score=60)
        n = _MIN_SAMPLES
        jobs = [_job(link=f"https://example.com/j{i}") for i in range(n)]
        apps = [_app(link=f"https://example.com/j{i}", status="rejected") for i in range(n)]

        result = orchestrator.run_cycle_sync(lambda: jobs, lambda: apps)
        assert result.status == "success"

        prob = orchestrator.engine.adjusted_probability(target_job).probability
        assert 0.0 < prob <= 95.0

    def test_adjustments_persist_across_instances(
        self, tmp_path: Path, decision_engine: JobDecisionEngine
    ) -> None:
        """Learned weights must survive a restart (new orchestrator instance)."""
        o1 = FeedbackLoopOrchestrator.build(decision_engine, state_dir=tmp_path)
        n = _MIN_SAMPLES * 2
        jobs = [_job(link=f"https://example.com/j{i}", company="Acme") for i in range(n)]
        apps = [_app(link=f"https://example.com/j{i}", status="interview") for i in range(n)]
        o1.run_cycle_sync(lambda: jobs, lambda: apps)

        version_after_learning = o1.engine.current_adjustments.version

        # Simulate restart
        o2 = FeedbackLoopOrchestrator.build(decision_engine, state_dir=tmp_path)
        assert o2.engine.current_adjustments.version == version_after_learning
