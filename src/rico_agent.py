"""Rico AI agent orchestration layer.

Rico AI converts the existing job automation pipeline into an agent-first
career assistant. The form, chat UI, Telegram, and dashboard should call this
module instead of directly exposing the old pipeline to the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RicoAgentSettings:
    autonomy_level: str = "recommend_only"
    can_reject_unsuitable_jobs: bool = True
    can_learn_from_actions: bool = True
    can_personalize_recommendations: bool = True
    can_generate_cover_letters: bool = True
    can_generate_recruiter_messages: bool = True
    can_prepare_interview_notes: bool = True
    can_send_follow_up_reminders: bool = True
    can_create_weekly_report: bool = True
    communication_style: str = "professional"
    match_strictness: str = "balanced"


@dataclass
class RicoProfile:
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    current_location: Optional[str] = None
    target_roles: List[str] = field(default_factory=list)
    years_experience: Optional[float] = None
    salary_expectation_aed: Optional[int] = None
    minimum_salary_aed: Optional[int] = None
    preferred_cities: List[str] = field(default_factory=list)
    visa_status: Optional[str] = None
    notice_period: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    industries: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    deal_breakers: List[str] = field(default_factory=list)
    green_flags: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    settings: RicoAgentSettings = field(default_factory=RicoAgentSettings)


class RicoAgent:
    """High-level autonomous career-agent facade.

    This class intentionally wraps the existing pipeline. Existing modules such
    as job_sources, scoring, telegram_bot, follow_up, and application tracking
    can be called from here while the product remains chat-first.
    """

    def __init__(self, profile_store=None, job_searcher=None, scorer=None, notifier=None, tracker=None):
        self.profile_store = profile_store
        self.job_searcher = job_searcher
        self.scorer = scorer
        self.notifier = notifier
        self.tracker = tracker

    def onboard_user(self, profile: RicoProfile, cv_file_url: Optional[str] = None) -> Dict[str, Any]:
        """Create Rico memory and trigger the first job-search process."""
        if self.profile_store:
            self.profile_store.save_profile(profile)

        return {
            "status": "profile_ready",
            "user_id": profile.user_id,
            "next_actions": [
                "parse_cv" if cv_file_url else "request_cv",
                "search_uae_jobs",
                "score_matches",
                "send_best_matches",
            ],
            "message": (
                "Your Rico AI profile is ready. I will search UAE jobs, score matches, "
                "explain why they fit, and track your applications."
            ),
        }

    def recommend_jobs(self, profile: RicoProfile, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score, filter, and explain jobs for a user."""
        recommendations: List[Dict[str, Any]] = []
        for job in jobs:
            score_result = self._score_job(profile, job)
            if self._should_reject(profile, job, score_result):
                continue
            recommendations.append({
                "job": job,
                "score": score_result["score"],
                "explanation": score_result["explanation"],
                "actions": [
                    "Apply Now",
                    "Save",
                    "Ignore",
                    "See Details",
                    "Write Cover Letter",
                    "Prepare Interview",
                    "Change Preferences",
                ],
            })

        return sorted(recommendations, key=lambda item: item["score"], reverse=True)

    def handle_user_action(self, profile: RicoProfile, job_id: str, action: str) -> Dict[str, Any]:
        """Process chat/button actions and update Rico memory."""
        normalized_action = action.strip().lower().replace(" ", "_")

        if self.tracker:
            self.tracker.record_action(profile.user_id, job_id, normalized_action)

        if profile.settings.can_learn_from_actions and self.profile_store:
            self.profile_store.record_learning_signal(profile.user_id, job_id, normalized_action)

        return {
            "status": "recorded",
            "user_id": profile.user_id,
            "job_id": job_id,
            "action": normalized_action,
        }

    def _score_job(self, profile: RicoProfile, job: Dict[str, Any]) -> Dict[str, Any]:
        title = str(job.get("title", "")).lower()
        description = str(job.get("description", "")).lower()
        city = str(job.get("city", job.get("location", ""))).lower()
        combined = f"{title} {description} {city}"

        score = 0
        reasons: List[str] = []

        for role in profile.target_roles:
            if role.lower() in combined:
                score += 25
                reasons.append(f"Matches target role: {role}")

        for skill in profile.skills:
            if skill.lower() in combined:
                score += 5
                reasons.append(f"Uses your skill: {skill}")

        for preferred_city in profile.preferred_cities:
            if preferred_city.lower() in city:
                score += 15
                reasons.append(f"Matches preferred city: {preferred_city}")

        for green_flag in profile.green_flags:
            if green_flag.lower() in combined:
                score += 10
                reasons.append(f"Positive signal: {green_flag}")

        for red_flag in profile.red_flags:
            if red_flag.lower() in combined:
                score -= 15
                reasons.append(f"Red flag found: {red_flag}")

        for deal_breaker in profile.deal_breakers:
            if deal_breaker.lower() in combined:
                score = min(score, 20)
                reasons.append(f"Deal-breaker risk: {deal_breaker}")

        score = max(0, min(100, score))
        explanation = "This job is relevant because " + "; ".join(reasons[:5]) if reasons else "This job has limited visible alignment with your profile."

        return {"score": score, "reasons": reasons, "explanation": explanation}

    def _should_reject(self, profile: RicoProfile, job: Dict[str, Any], score_result: Dict[str, Any]) -> bool:
        if not profile.settings.can_reject_unsuitable_jobs:
            return False

        strictness_thresholds = {
            "strict": 75,
            "balanced": 55,
            "broad": 35,
        }
        threshold = strictness_thresholds.get(profile.settings.match_strictness.lower(), 55)
        return score_result["score"] < threshold
