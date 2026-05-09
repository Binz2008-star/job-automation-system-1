"""Adapter that feeds existing repository capabilities into Rico AI.

This module is the bridge between the old pipeline and the new agent-first
product. Rico should call this adapter to reuse job fetching, filtering,
scoring, Telegram alerts, application tracking, feedback learning, Gmail sync,
and dashboard generation without duplicating pipeline logic.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

from src.rico_agent import RicoAgent, RicoProfile

logger = logging.getLogger("rico_repo_adapter")


class RicoRepoAdapter:
    """Feed existing repo services into Rico AI."""

    def fetch_jobs(self) -> List[Dict[str, Any]]:
        from src.job_sources import get_jobs
        from src.filter import filter_new_jobs

        jobs = get_jobs()
        return filter_new_jobs(jobs)

    def score_jobs_with_existing_engine(self, jobs: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], int]]:
        """Use the repo scoring stack, preferring the LLM scorer when available."""
        try:
            from src.llm_scorer import score_jobs_llm

            scored_jobs = score_jobs_llm(jobs)
            return [(job, int(job.get("score", 0))) for job in scored_jobs]
        except Exception:
            logger.exception("llm_scoring_failed falling_back_to_keyword_scoring")
            from src.scoring import score_job

            return [(job, int(score_job(job))) for job in jobs]

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

        for job, score in matches:
            if score >= 75 and not is_applied(job):
                mark_applied(job, status="rico_recommended")

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

    def __init__(self) -> None:
        self.repo = RicoRepoAdapter()
        self.agent = RicoAgent()

    def run_for_profile(self, profile: RicoProfile, limit: int = 10) -> Dict[str, Any]:
        """Run Rico's autonomous workflow for a single profile."""
        started_at = datetime.utcnow().isoformat()

        jobs = self.repo.fetch_jobs()
        scored = self.repo.score_jobs_with_existing_engine(jobs)
        self.repo.persist_jobs(scored)

        decisions = self.repo.make_agent_decisions(scored)
        selected: List[Tuple[Dict[str, Any], int]] = []

        for decision in decisions:
            if getattr(decision, "decision", None) in {"apply", "watch"}:
                selected.append((decision.job, int(decision.final_score)))

        selected = sorted(selected, key=lambda item: item[1], reverse=True)
        selected = self.repo.remove_applied_jobs(selected)
        selected = selected[:limit]

        rico_recommendations = self.agent.recommend_jobs(
            profile=profile,
            jobs=[job for job, _ in selected],
        )

        # Preserve existing pipeline scores alongside Rico explanations.
        by_identity = {
            (str(job.get("title", "")), str(job.get("company", ""))): score
            for job, score in selected
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

        return {
            "status": "completed",
            "started_at": started_at,
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
                    "url": job.get("url") or job.get("job_url"),
                }
                for job, score in final_matches
            ],
        }


def run_rico_for_default_profile() -> Dict[str, Any]:
    """Use existing repo profile data to run Rico immediately.

    This lets the current system feed Rico before a full multi-user profile DB
    exists.
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
    return RicoSystem().run_for_profile(profile)


if __name__ == "__main__":
    import json

    print(json.dumps(run_rico_for_default_profile(), indent=2))
