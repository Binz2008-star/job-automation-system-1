"""
Feedback Loop Orchestrator
Coordinates the full learning cycle: collect → analyse → learn → persist → schedule.

Design:
  - Single shared ResponseIntelligenceEngine instance — never per-call.
  - CycleState persisted to disk; survives restarts without re-learning.
  - Async-safe: learning runs in a thread pool; callers never block.
  - Cycle guard: will not re-learn if last cycle ran within the cooldown window.
  - All I/O injected; orchestrator is unit-testable with mocks.
  - Structured logging on every transition.
"""

from __future__ import annotations

import asyncio
import logging
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.decision_engine import JobDecisionEngine
from src.response_intelligence import (
    ResponseIntelligenceEngine,
    ScoringAdjustments,
    create_engine,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cycle state — persisted so the scheduler survives restarts
# ---------------------------------------------------------------------------

@dataclass
class CycleState:
    last_run_at: Optional[str] = None          # ISO timestamp
    last_run_status: str = "never"             # "success" | "failed" | "skipped" | "never"
    total_cycles: int = 0
    total_samples_processed: int = 0
    last_adjustments_version: int = 0
    last_error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "CycleState":
        return cls(**json.loads(raw))

    @classmethod
    def load(cls, path: Path) -> "CycleState":
        if not path.exists():
            return cls()
        try:
            return cls.from_json(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("cycle_state_load_failed", extra={"path": str(path)})
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)


# ---------------------------------------------------------------------------
# Cycle result
# ---------------------------------------------------------------------------

@dataclass
class CycleResult:
    status: str                          # "success" | "skipped" | "failed"
    ran_at: str
    duration_seconds: float
    matched_pairs: int = 0
    adjustments_version: int = 0
    insights_count: int = 0
    skipped_reason: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class FeedbackLoopOrchestrator:
    """
    Owns one ResponseIntelligenceEngine and drives the full feedback cycle.

    Callers share one orchestrator instance — never instantiate per-request.

    Usage:
        orchestrator = FeedbackLoopOrchestrator.build(decision_engine)

        # Sync (CLI / scripts):
        result = orchestrator.run_cycle_sync(jobs_loader, apps_loader)

        # Async (web server / task queue):
        result = await orchestrator.run_cycle(jobs_loader, apps_loader)

        # Background (fire-and-forget from a scheduler):
        orchestrator.schedule_background_cycle(jobs_loader, apps_loader)
    """

    def __init__(
        self,
        engine: ResponseIntelligenceEngine,
        cycle_state_path: Path,
        cooldown: timedelta = timedelta(hours=6),
        executor: Optional[ThreadPoolExecutor] = None,
    ) -> None:
        self._engine = engine
        self._state_path = cycle_state_path
        self._cooldown = cooldown
        self._executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="feedback")
        self._lock = threading.Lock()
        self._state = CycleState.load(cycle_state_path)

        logger.info(
            "feedback_loop_orchestrator_ready",
            extra={
                "last_run": self._state.last_run_at,
                "total_cycles": self._state.total_cycles,
                "adjustments_version": self._state.last_adjustments_version,
            },
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        decision_engine: JobDecisionEngine,
        state_dir: Path = Path("data"),
        cooldown: timedelta = timedelta(hours=6),
    ) -> "FeedbackLoopOrchestrator":
        """
        Production factory. Call once at process startup.

        Example:
            orchestrator = FeedbackLoopOrchestrator.build(decision_engine)
        """
        ri_engine = create_engine(
            decision_engine=decision_engine,
            state_path=state_dir / "scoring_adjustments.json",
        )
        return cls(
            engine=ri_engine,
            cycle_state_path=state_dir / "cycle_state.json",
            cooldown=cooldown,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_cycle(
        self,
        jobs_loader: Callable[[], List[Dict[str, Any]]],
        apps_loader: Callable[[], List[Dict[str, Any]]],
    ) -> CycleResult:
        """
        Run a full feedback cycle asynchronously.

        Offloads blocking I/O and CPU work to the thread pool;
        never blocks the event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self._run_cycle_locked,
            jobs_loader,
            apps_loader,
        )

    def run_cycle_sync(
        self,
        jobs_loader: Callable[[], List[Dict[str, Any]]],
        apps_loader: Callable[[], List[Dict[str, Any]]],
    ) -> CycleResult:
        """Blocking variant for CLI / scripts."""
        return self._run_cycle_locked(jobs_loader, apps_loader)

    def schedule_background_cycle(
        self,
        jobs_loader: Callable[[], List[Dict[str, Any]]],
        apps_loader: Callable[[], List[Dict[str, Any]]],
    ) -> None:
        """
        Submit a cycle to the background thread pool and return immediately.
        Exceptions are logged; they do not propagate to the caller.
        """
        future = self._executor.submit(self._run_cycle_locked, jobs_loader, apps_loader)
        future.add_done_callback(_log_background_result)

    @property
    def cycle_state(self) -> CycleState:
        with self._lock:
            return self._state

    @property
    def engine(self) -> ResponseIntelligenceEngine:
        """Expose the shared engine for direct probability queries."""
        return self._engine

    def is_due(self) -> bool:
        """True if the cooldown has elapsed since the last successful cycle."""
        with self._lock:
            return _is_due(self._state, self._cooldown)

    # ------------------------------------------------------------------
    # Core cycle — all locking, guards, and state transitions here
    # ------------------------------------------------------------------

    def _run_cycle_locked(
        self,
        jobs_loader: Callable[[], List[Dict[str, Any]]],
        apps_loader: Callable[[], List[Dict[str, Any]]],
    ) -> CycleResult:
        with self._lock:
            if not _is_due(self._state, self._cooldown):
                reason = (
                    f"Last cycle ran at {self._state.last_run_at}; "
                    f"cooldown is {self._cooldown}"
                )
                logger.info("feedback_cycle_skipped", extra={"reason": reason})
                return CycleResult(
                    status="skipped",
                    ran_at=datetime.now().isoformat(),
                    duration_seconds=0.0,
                    skipped_reason=reason,
                )

        started = datetime.now()
        logger.info("feedback_cycle_started", extra={"started_at": started.isoformat()})

        try:
            result = self._execute_cycle(jobs_loader, apps_loader, started)
        except Exception as exc:
            duration = (datetime.now() - started).total_seconds()
            logger.exception("feedback_cycle_failed", extra={"duration_s": duration})
            with self._lock:
                self._state.last_run_at = started.isoformat()
                self._state.last_run_status = "failed"
                self._state.last_error = str(exc)
                self._state.save(self._state_path)
            return CycleResult(
                status="failed",
                ran_at=started.isoformat(),
                duration_seconds=duration,
                error=str(exc),
            )

        with self._lock:
            self._state.last_run_at = started.isoformat()
            self._state.last_run_status = "success"
            self._state.total_cycles += 1
            self._state.total_samples_processed += result.matched_pairs
            self._state.last_adjustments_version = result.adjustments_version
            self._state.last_error = None
            self._state.save(self._state_path)

        logger.info(
            "feedback_cycle_completed",
            extra={
                "duration_s": result.duration_seconds,
                "matched_pairs": result.matched_pairs,
                "adjustments_version": result.adjustments_version,
                "insights": result.insights_count,
                "total_cycles": self._state.total_cycles,
            },
        )

        return result

    def _execute_cycle(
        self,
        jobs_loader: Callable[[], List[Dict[str, Any]]],
        apps_loader: Callable[[], List[Dict[str, Any]]],
        started: datetime,
    ) -> CycleResult:
        """
        Inner cycle execution — no locking, no state mutation.
        All side effects are in _run_cycle_locked.
        """
        jobs = jobs_loader()
        apps = apps_loader()

        if not jobs or not apps:
            raise ValueError(
                f"Insufficient data for learning cycle: "
                f"{len(jobs)} jobs, {len(apps)} applications"
            )

        learn_result = self._engine.learn_from_outcomes(apps, jobs)

        if "error" in learn_result:
            raise RuntimeError(f"Learning failed: {learn_result['error']}")

        duration = (datetime.now() - started).total_seconds()

        return CycleResult(
            status="success",
            ran_at=started.isoformat(),
            duration_seconds=duration,
            matched_pairs=learn_result.get("matched_pairs", 0),
            adjustments_version=learn_result.get("adjustments_version", 0),
            insights_count=len(learn_result.get("insights", [])),
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _is_due(state: CycleState, cooldown: timedelta) -> bool:
    if not state.last_run_at or state.last_run_status != "success":
        return True
    try:
        last = datetime.fromisoformat(state.last_run_at)
        return datetime.now() - last >= cooldown
    except (ValueError, TypeError):
        return True


def _log_background_result(future: Any) -> None:
    try:
        result: CycleResult = future.result()
        if result.status == "failed":
            logger.error("background_feedback_cycle_failed", extra={"error": result.error})
        else:
            logger.info("background_feedback_cycle_done", extra={"status": result.status})
    except Exception as exc:
        logger.exception("background_feedback_cycle_exception", extra={"error": str(exc)})
