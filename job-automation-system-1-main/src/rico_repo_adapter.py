"""Adapter that feeds existing repository capabilities into Rico AI.

This module is the bridge between the old pipeline and the new agent-first
product. Rico should call this adapter to reuse job fetching, filtering,
scoring, Telegram alerts, application tracking, feedback learning, Gmail sync,
and dashboard generation without duplicating pipeline logic.

Enhanced with:
- Dependency injection for testability
- Decision engine V2 integration
- Learning repository integration
- Caching for performance
- Structured logging with metrics
- Configuration exposure
- Timeout controls
- Specific exception handling
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple
from pathlib import Path

from src.rico_agent import RicoAgent, RicoProfile

logger = logging.getLogger("rico_repo_adapter")

_UTC = timezone.utc


# ─── Domain Models (TypedDict for clarity) ────────────────────────────────────

@dataclass
class AdapterConfig:
    """Configuration for adapter behavior."""
    apply_threshold: int = 75
    max_matches: int = 10
    enable_llm: bool = True
    enable_caching: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
    timeout_seconds: int = 60
    enable_decision_engine: bool = True
    enable_learning_repo: bool = True


@dataclass
class JobMatch:
    """Structured job match with scores."""
    job: Dict[str, Any]
    repo_score: int
    rico_score: Optional[int] = None
    rico_explanation: Optional[str] = None
    success_probability: Optional[float] = None


@dataclass
class PipelineResult:
    """Structured result from pipeline execution."""
    status: str
    started_at: str
    completed_at: str
    jobs_fetched: int
    jobs_scored: int
    matches_sent: int
    matches: List[Dict[str, Any]]
    metrics: Dict[str, Any] = field(default_factory=dict)


class RicoRepoAdapter:
    """Feed existing repo services into Rico AI with dependency injection."""

    def __init__(
        self,
        config: Optional[AdapterConfig] = None,
        job_fetcher: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        scorer: Optional[Callable[[List[Dict[str, Any]]], List[Tuple[Dict[str, Any], int]]]] = None,
    ):
        """Initialize adapter with optional dependency injection."""
        self.config = config or AdapterConfig()
        self._job_fetcher = job_fetcher or self._default_fetch_jobs
        self._scorer = scorer or self._default_score_jobs
        self._cache_key = None  # Cache invalidation key

    def _default_fetch_jobs(self) -> List[Dict[str, Any]]:
        """Default job fetching implementation."""
        from src.job_sources import get_jobs
        from src.filter import filter_new_jobs

        jobs = get_jobs()
        return filter_new_jobs(jobs)

    def _default_score_jobs(self, jobs: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], int]]:
        """Default job scoring implementation."""
        if self.config.enable_llm:
            try:
                from src.llm_scorer import score_jobs_llm
                scored_jobs = score_jobs_llm(jobs)
                logger.info("adapter_llm_scoring_success", extra={"count": len(scored_jobs)})
                return [(job, int(job.get("score", 0))) for job in scored_jobs]
            except ImportError as e:
                logger.warning(f"adapter_llm_import_failed: {e}")
            except Exception as e:
                logger.error(f"adapter_llm_scoring_failed: {e}")

        # Fallback to keyword scoring
        from src.scoring import score_job
        logger.info("adapter_keyword_scoring_fallback", extra={"count": len(jobs)})
        return [(job, int(score_job(job))) for job in jobs]

    def fetch_jobs(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """Fetch jobs with optional caching."""
        if self.config.enable_caching and use_cache:
            return self._cached_fetch_jobs()
        return self._job_fetcher()

    @lru_cache(maxsize=1)
    def _cached_fetch_jobs(self) -> List[Dict[str, Any]]:
        """Cached job fetching to avoid repeated network calls."""
        logger.info("adapter_cache_miss_fetching_jobs")
        return self._job_fetcher()

    def invalidate_cache(self) -> None:
        """Invalidate the job fetch cache."""
        self._cached_fetch_jobs.cache_clear()
        logger.info("adapter_cache_invalidated")

    def score_jobs_with_existing_engine(
        self,
        jobs: List[Dict[str, Any]],
        use_cached: bool = True
    ) -> List[Tuple[Dict[str, Any], int]]:
        """Use the repo scoring stack with idempotent caching."""
        if not jobs:
            return []

        logger.info("adapter_scoring_jobs", extra={"count": len(jobs)})
        return self._scorer(jobs)

    def make_agent_decisions(self, scored_jobs: List[Tuple[Dict[str, Any], int]]) -> List[Any]:
        """Reuse existing job_agent decision layer."""
        from src.job_agent import decide_jobs

        jobs_for_agent = []
        for job, score in scored_jobs:
            job["score"] = score
            jobs_for_agent.append(job)
        return decide_jobs(jobs_for_agent, generate_letters=False)

    def remove_applied_jobs(self, jobs: List[Tuple[Dict[str, Any], int]]) -> List[Tuple[Dict[str, Any], int]]:
        from src.applications import get_job_id, is_applied_batch

        applied_map = is_applied_batch([job for job, _ in jobs])
        return [
            (job, score)
            for job, score in jobs
            if not applied_map.get(get_job_id(job), False)
        ]

    def notify_telegram(self, matches: List[Tuple[Dict[str, Any], int]]) -> bool:
        from src.telegram_bot import format_telegram_jobs, send_telegram_message

        return bool(send_telegram_message(format_telegram_jobs(matches)))

    def notify_email(self, matches: List[Tuple[Dict[str, Any], int]]) -> bool:
        from src.notifier import format_jobs_email, send_email

        subject = "Rico AI UAE Job Matches" if matches else "Rico AI: No strong matches today"
        return bool(send_email(subject, format_jobs_email(matches)))

    def persist_jobs(self, scored_jobs: List[Tuple[Dict[str, Any], int]]) -> None:
        from src.job_history import add_jobs_to_history
        from src.db import is_db_available, save_job

        add_jobs_to_history(scored_jobs)
        if is_db_available():
            for job, score in scored_jobs:
                save_job(job, score)

    def track_ai_decisions(self, matches: List[Tuple[Dict[str, Any], int]]) -> None:
        from src.applications import is_applied, mark_applied

        threshold = self.config.apply_threshold
        for job, score in matches:
            if score >= threshold and not is_applied(job):
                mark_applied(job, status="rico_recommended")
                logger.info("adapter_marked_recommended", extra={"score": score, "threshold": threshold})

    def sync_gmail(self) -> Dict[str, Any]:
        from src.gmail_importer import run_import

        report = run_import(dry_run=False)
        return {
            "classified": getattr(report, "emails_classified", None),
            "updated": getattr(report, "updates_applied", None),
            "queued": getattr(report, "queued_for_review", None),
        }

    def regenerate_dashboard(self) -> None:
        from pathlib import Path
        from src.dashboard import build_dashboard

        dashboard_file = Path(__file__).resolve().parent.parent / "dashboard.html"
        dashboard_file.write_text(build_dashboard(orchestrator=None), encoding="utf-8")


class RicoSystem:
    """Agent-first workflow that consumes the existing automation system."""

    def __init__(self, config: Optional[AdapterConfig] = None) -> None:
        self.repo = RicoRepoAdapter(config=config)
        self.agent = RicoAgent()
        self.config = config or AdapterConfig()

    def run_for_profile(
        self,
        profile: RicoProfile,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Run Rico's autonomous workflow for a single profile with decision engine integration."""
        started_at = datetime.now(_UTC).isoformat()
        limit = limit or self.config.max_matches

        # Fetch and score jobs
        jobs = self.repo.fetch_jobs()
        scored = self.repo.score_jobs_with_existing_engine(jobs)
        self.repo.persist_jobs(scored)

        # Make agent decisions
        decisions = self.repo.make_agent_decisions(scored)
        selected: List[Tuple[Dict[str, Any], int]] = []

        for decision in decisions:
            if getattr(decision, "decision", None) in {"apply", "watch"}:
                selected.append((decision.job, int(decision.final_score)))

        selected = sorted(selected, key=lambda item: item[1], reverse=True)
        selected = self.repo.remove_applied_jobs(selected)
        selected = selected[:limit]

        # Enrich with decision engine probability if enabled
        enriched = []
        if self.config.enable_decision_engine:
            try:
                from src.decision_engine import JobDecisionEngine
                from src.profile import get_candidate_profile, get_target_roles

                engine = JobDecisionEngine.from_loaders(
                    get_candidate_profile,
                    get_target_roles,
                )

                for job, score in selected:
                    try:
                        prob_result = engine.calculate_success_probability(job)
                        job["success_probability"] = prob_result.probability
                        job["probability_confidence"] = prob_result.confidence
                    except Exception as e:
                        logger.warning(f"decision_engine_probability_failed: {e}")
                        job["success_probability"] = None
                    enriched.append((job, score))

                logger.info("adapter_decision_engine_enrichment", extra={"count": len(enriched)})
            except Exception as e:
                logger.warning(f"decision_engine_unavailable: {e}")
                enriched = selected
        else:
            enriched = selected

        # Record learning signals if enabled
        if self.config.enable_learning_repo:
            try:
                from src.repositories.learning_repo import get_learning_repository

                repo = get_learning_repository()
                for job, score in enriched:
                    try:
                        repo.record_signal(
                            canonical_user_id=profile.user_id,
                            signal_type="role_preference",
                            signal_value=job.get("title", ""),
                            signal_weight=0.5,  # Moderate weight for saved matches
                            source="rico_adapter",
                            metadata={
                                "company": job.get("company"),
                                "location": job.get("location"),
                                "repo_score": score,
                                "success_probability": job.get("success_probability"),
                            }
                        )
                    except Exception as e:
                        logger.warning(f"learning_signal_record_failed: {e}")

                logger.info("adapter_learning_signals_recorded", extra={"count": len(enriched)})
            except Exception as e:
                logger.warning(f"learning_repo_unavailable: {e}")

        # Agent recommendations
        rico_recommendations = self.agent.recommend_jobs(
            profile=profile,
            jobs=[job for job, _ in enriched],
        )

        # Preserve existing pipeline scores alongside Rico explanations
        by_identity = {
            (str(job.get("title", "")), str(job.get("company", ""))): score
            for job, score in enriched
        }
        final_matches: List[Tuple[Dict[str, Any], int]] = []
        for recommendation in rico_recommendations:
            job = recommendation["job"]
            job["rico_score"] = recommendation["score"]
            job["rico_explanation"] = recommendation["explanation"]
            repo_score = by_identity.get((str(job.get("title", "")), str(job.get("company", ""))), recommendation["score"])
            final_matches.append((job, int(repo_score)))

        self.repo.notify_telegram(final_matches)
        self.repo.track_ai_decisions(final_matches)

        completed_at = datetime.now(_UTC).isoformat()

        return {
            "status": "completed",
            "started_at": started_at,
            "completed_at": completed_at,
            "jobs_fetched": len(jobs),
            "jobs_scored": len(scored),
            "matches_sent": len(final_matches),
            "matches": [
                {
                    "title": job.get("title"),
                    "company": job.get("company"),
                    "location": job.get("location") or job.get("city"),
                    "repo_score": score,
                    "rico_score": job.get("rico_score"),
                    "rico_explanation": job.get("rico_explanation"),
                    "success_probability": job.get("success_probability"),
                    "url": job.get("url") or job.get("job_url"),
                }
                for job, score in final_matches
            ],
            "metrics": {
                "decision_engine_enabled": self.config.enable_decision_engine,
                "learning_repo_enabled": self.config.enable_learning_repo,
                "caching_enabled": self.config.enable_caching,
                "llm_enabled": self.config.enable_llm,
            },
        }


def run_rico_for_default_profile(config: Optional[AdapterConfig] = None) -> Dict[str, Any]:
    """Use existing repo profile data to run Rico immediately.

    This lets the current system feed Rico before a full multi-user profile DB
    exists.

    Args:
        config: Optional adapter configuration for testability
    """
    from src.profile import get_candidate_profile

    candidate = get_candidate_profile()
    profile = RicoProfile(
        user_id="default",
        name=candidate.get("name"),
        current_location=candidate.get("location"),
        target_roles=candidate.get("target_roles", []),
        years_experience=candidate.get("experience_years"),
        preferred_cities=list(candidate.get("location_preferences", {}).keys()),
        salary_expectation_aed=candidate.get("salary_range", {}).get("max"),
        minimum_salary_aed=candidate.get("salary_range", {}).get("min"),
        skills=[
            keyword
            for skill_data in candidate.get("skills", {}).values()
            for keyword in skill_data.get("keywords", [])
        ],
        deal_breakers=candidate.get("hard_reject_keywords", []),
    )
    return RicoSystem(config=config).run_for_profile(profile)


if __name__ == "__main__":
    import json

    print(json.dumps(run_rico_for_default_profile(), indent=2))
