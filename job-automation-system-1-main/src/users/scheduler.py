"""src/users/scheduler.py
Multi-user daily pipeline scheduler.

Phase 1: skeleton only.  Lists active users and delegates to a per-user
runner function.  The legacy `run_daily.py` pipeline is untouched.

Future Phase 2 will replace `_run_for_user` with a shared pipeline core
that accepts a `PipelineContext(user_id=...)`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Runner signature: fn(user_id: str) -> int  (return code 0 = success)
PipelineRunner = Callable[[str], int]


class UserScheduler:
    """Iterate over active users and run the daily pipeline for each."""

    def __init__(self, runner: Optional[PipelineRunner] = None) -> None:
        """
        Args:
            runner: Callable that executes the pipeline for one user.
                    Defaults to the legacy single-user runner (Phase 1 stub).
        """
        self.runner = runner or self._default_runner

    # ── Public API ────────────────────────────────────────────────────────────

    def run_all(self) -> Dict[str, int]:
        """Run the daily pipeline for every active user.

        Returns a mapping {user_email: return_code}.
        Missing/skipped users are omitted from the result dict.
        """
        from src.repositories.users_repo import list_active_users

        users = list_active_users()
        if not users:
            logger.warning("scheduler_no_active_users")
            return {}

        logger.info("scheduler_start user_count=%d", len(users))
        results: Dict[str, int] = {}

        for user in users:
            email = user.email
            logger.info("scheduler_user_start email=%s", email)
            try:
                rc = self.runner(email)
                results[email] = rc
                if rc == 0:
                    logger.info("scheduler_user_done email=%s rc=0", email)
                else:
                    logger.warning("scheduler_user_error email=%s rc=%s", email, rc)
            except Exception:
                logger.exception("scheduler_user_exception email=%s", email)

        logger.info("scheduler_complete ran=%d total=%d", len(results), len(users))
        return results

    # ── Phase 1 default runner ───────────────────────────────────────────────

    @staticmethod
    def _default_runner(user_id: str) -> int:
        """Phase 1 stub: delegates to the legacy single-user pipeline.

        Phase 2 will import and call a shared `PipelineContext` instead.
        For now this exists only so the scheduler skeleton can be tested.
        """
        logger.info("scheduler_legacy_runner user_id=%s", user_id)
        # Import deferred to avoid circular dependencies at module load time.
        from src.run_daily import run_pipeline

        return run_pipeline()
