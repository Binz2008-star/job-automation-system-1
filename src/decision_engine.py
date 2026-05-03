"""
Job Search Decision Engine V2 - Refactored with Proper Architecture
AI-powered analytics and decision support with clean separation of concerns.

Design principles:
- All I/O injected at construction; analysis methods are pure
- Probability model uses multiplicative log-odds compounding
- Score trend compares recent cohort against historical cohort
- Fully typed and testable with dependency injection
- Structured logging throughout
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Any, Callable, Dict, List, Optional, Tuple, Protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration - all thresholds in one place
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineConfig:
    very_high_score: int = 85
    high_score: int = 75
    medium_score: int = 65
    low_score: int = 40

    # Probability model multipliers (applied as log-odds adjustments)
    role_match_boost: float = 0.20
    exp_match_boost: float = 0.12
    preferred_location_boost: float = 0.06
    large_corp_boost: float = 0.10
    mid_company_boost: float = 0.05
    startup_penalty: float = -0.08

    # Market health weights
    availability_weight: float = 0.40
    quality_weight: float = 0.40
    competition_weight: float = 0.20

    # Application strategy
    optimal_apply_pct: float = 0.30   # fraction of high-quality jobs to target
    max_daily_applications: int = 5

    # Seniority keywords
    senior_keywords: Tuple[str, ...] = ("senior", "executive", "lead", "principal", "head", "chief")
    management_keywords: Tuple[str, ...] = ("manager", "supervisor", "director")

    # Regional preference keywords
    preferred_location_keywords: Tuple[str, ...] = ("dubai", "abu dhabi", "uae", "sharjah", "ajman")

    # Large corporation heuristics (UAE-specific)
    large_corp_names: Tuple[str, ...] = (
        "etihad", "emirates", "dnata", "mubadala", "adnoc",
        "dp world", "du", "etisalat", "e&",
    )
    mid_company_keywords: Tuple[str, ...] = ("group", "holding", "international", "global")
    startup_keywords: Tuple[str, ...] = ("startup", "ventures", "labs")


DEFAULT_CONFIG = EngineConfig()

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ProbabilityResult:
    probability: float          # 0–100
    confidence: str
    recommendation: str
    factors: Dict[str, float]   # individual contributions in percentage points


@dataclass
class MarketTrends:
    market_overview: Dict[str, Any]
    top_companies: List[Dict[str, Any]]
    location_analysis: Dict[str, int]
    role_patterns: Dict[str, Any]
    quality_distribution: Dict[str, Any]
    market_health: Dict[str, Any]
    recommendations: List[str]


@dataclass
class ApplicationStrategy:
    optimal_daily_applications: float
    prioritized_jobs: List[Dict[str, Any]]
    current_success_rate: float
    strategic_focus: str
    action_items: List[str]


# ---------------------------------------------------------------------------
# Protocols for dependency injection
# ---------------------------------------------------------------------------

class ProfileLoader(Protocol):
    def __call__(self) -> Dict[str, Any]: ...

class RolesLoader(Protocol):
    def __call__(self) -> List[str]: ...

class JobsLoader(Protocol):
    def __call__(self) -> List[Dict[str, Any]]: ...

class ApplicationsLoader(Protocol):
    def __call__(self) -> List[Dict[str, Any]]: ...

# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class JobDecisionEngine:
    """
    Decision engine for job search optimization with clean architecture.
    
    All external I/O is injected via protocols so the engine is fully
    unit-testable without database or filesystem dependencies.
    """

    def __init__(
        self,
        profile: Dict[str, Any],
        target_roles: List[str],
        config: EngineConfig = DEFAULT_CONFIG,
    ) -> None:
        self._profile = profile
        self._target_roles = [r.lower() for r in target_roles]
        self._config = config
        self._level = self._determine_candidate_level()

    # ------------------------------------------------------------------
    # Factory - keeps I/O out of __init__ while keeping call site clean
    # ------------------------------------------------------------------

    @classmethod
    def from_loaders(
        cls,
        profile_loader: ProfileLoader,
        roles_loader: RolesLoader,
        config: EngineConfig = DEFAULT_CONFIG,
    ) -> "JobDecisionEngine":
        """
        Preferred constructor for production use.
        
        Example:
            engine = JobDecisionEngine.from_loaders(
                get_candidate_profile,
                get_target_roles,
            )
        """
        try:
            profile = profile_loader()
            roles = roles_loader()
        except Exception:
            logger.exception("decision_engine_load_failed")
            raise
        return cls(profile=profile, target_roles=roles, config=config)

    # ------------------------------------------------------------------
    # Public API - all pure functions, no I/O
    # ------------------------------------------------------------------

    def calculate_success_probability(self, job: Dict[str, Any]) -> ProbabilityResult:
        """
        Calculate application success probability using multiplicative
        log-odds compounding rather than additive bonus stacking.
        
        The base probability comes from the job's match score.
        Each factor adjusts the log-odds independently, so factors
        compound without the ceiling-collision problem of additive models.
        """
        cfg = self._config
        score = float(job.get("score") or 0)
        title = (job.get("title") or "").lower()
        company = (job.get("company") or "").lower()
        location = (job.get("location") or "").lower()

        # Base: score → probability (score is already 0-100)
        base_prob = score / 100.0
        log_odds = _to_log_odds(base_prob)

        factors: Dict[str, float] = {}

        # Role match
        role_delta = 0.0
        if any(r in title for r in self._target_roles):
            role_delta = cfg.role_match_boost
        factors["role_match"] = role_delta
        log_odds += _to_log_odds_delta(role_delta)

        # Experience level match
        exp_delta = 0.0
        is_senior_role = any(kw in title for kw in cfg.senior_keywords)
        if is_senior_role and self._level in ("Executive", "Senior"):
            exp_delta = cfg.exp_match_boost
        factors["experience_match"] = exp_delta
        log_odds += _to_log_odds_delta(exp_delta)

        # Company size
        company_delta = self._company_size_delta(company)
        factors["company_factor"] = company_delta
        log_odds += _to_log_odds_delta(company_delta)

        # Location preference
        loc_delta = 0.0
        if any(kw in location for kw in cfg.preferred_location_keywords):
            loc_delta = cfg.preferred_location_boost
        factors["location_bonus"] = loc_delta
        log_odds += _to_log_odds_delta(loc_delta)

        # Recover probability, cap at 95%
        probability = min(_from_log_odds(log_odds) * 100.0, 95.0)

        # Convert factors to percentage points for display
        factors["base_score"] = round(base_prob * 100, 1)
        factors = {k: round(v * 100, 1) for k, v in factors.items() if k != "base_score"}

        confidence, recommendation = _classify_probability(probability)

        logger.debug(
            "success_probability_calculated",
            extra={
                "job_id": job.get("link", ""),
                "score": score,
                "probability": probability,
                "confidence": confidence,
            },
        )

        return ProbabilityResult(
            probability=round(probability, 1),
            confidence=confidence,
            recommendation=recommendation,
            factors=factors,
        )

    def analyze_market_trends(
        self,
        jobs: List[Dict[str, Any]],
        applications: List[Dict[str, Any]],
    ) -> MarketTrends:
        """
        Analyze job market trends.
        
        Both `jobs` and `applications` are passed in — no I/O here.
        """
        if not jobs:
            logger.warning("analyze_market_trends_no_data")
            return MarketTrends(
                market_overview={"error": "No jobs data"},
                top_companies=[],
                location_analysis={},
                role_patterns={},
                quality_distribution={},
                market_health={"health_score": 0, "status": "No data"},
                recommendations=[],
            )

        now = datetime.now()
        cutoff = now - timedelta(days=30)
        older_cutoff = now - timedelta(days=60)

        recent_jobs = [j for j in jobs if _is_after(j.get("date_found"), cutoff)]
        historical_jobs = [
            j for j in jobs
            if _is_between(j.get("date_found"), older_cutoff, cutoff)
        ]

        scores = [float(j["score"]) for j in jobs if j.get("score") is not None]
        recent_scores = [float(j["score"]) for j in recent_jobs if j.get("score") is not None]
        historical_scores = [float(j["score"]) for j in historical_jobs if j.get("score") is not None]

        # Trend: recent vs *previous* cohort — not recent vs all
        score_trend = _score_trend(recent_scores, historical_scores)

        company_counts = Counter(j.get("company") or "Unknown" for j in jobs)
        location_counts = Counter(j.get("location") or "Unknown" for j in jobs)

        market_health = self._calculate_market_health(recent_jobs, recent_scores, applications)
        quality_dist = _quality_distribution(scores, self._config)

        logger.info(
            "market_trends_analysed",
            extra={
                "total_jobs": len(jobs),
                "recent_jobs": len(recent_jobs),
                "score_trend": score_trend,
                "market_health": market_health.get("status"),
            },
        )

        return MarketTrends(
            market_overview={
                "total_jobs": len(jobs),
                "recent_jobs": len(recent_jobs),
                "avg_score": round(mean(scores), 1) if scores else 0,
                "recent_avg_score": round(mean(recent_scores), 1) if recent_scores else 0,
                "score_trend": score_trend,
            },
            top_companies=[
                {"name": name, "count": count, "market_share": round(count / len(jobs) * 100, 1)}
                for name, count in company_counts.most_common(10)
            ],
            location_analysis=dict(location_counts.most_common(10)),
            role_patterns=self._role_patterns(jobs),
            quality_distribution=quality_dist,
            market_health=market_health,
            recommendations=self._market_recommendations(market_health, quality_dist),
        )

    def generate_application_strategy(
        self,
        jobs: List[Dict[str, Any]],
        applications: List[Dict[str, Any]],
        app_stats: Dict[str, Any],
    ) -> ApplicationStrategy:
        """
        Generate a prioritized application strategy.
        
        All data is passed in — callers must resolve I/O before calling.
        """
        cfg = self._config
        if not jobs:
            return ApplicationStrategy(
                optimal_daily_applications=0,
                prioritized_jobs=[],
                current_success_rate=0.0,
                strategic_focus="No data available",
                action_items=["Expand job search criteria"],
            )

        success_rate = float(app_stats.get("success_rate") or 0)
        high_quality = [j for j in jobs if float(j.get("score") or 0) >= cfg.medium_score]
        optimal_rate = min(len(high_quality) * cfg.optimal_apply_pct, cfg.max_daily_applications)

        prioritized: List[Dict[str, Any]] = []
        for job in jobs:
            score = float(job.get("score") or 0)
            prob_result = self.calculate_success_probability(job)
            priority = score * 0.6 + prob_result.probability * 0.4
            prioritized.append({
                "job": job,
                "priority_score": round(priority, 1),
                "success_probability": prob_result.probability,
                "recommendation": prob_result.recommendation,
                "apply_today": priority >= 70 and len([p for p in prioritized if p["priority_score"] >= 70]) < optimal_rate
            })

        prioritized.sort(key=lambda x: x["priority_score"], reverse=True)

        strategic_focus, action_items = self._strategy_focus(success_rate, len(high_quality), optimal_rate)

        logger.info(
            "application_strategy_generated",
            extra={
                "total_jobs": len(jobs),
                "high_quality": len(high_quality),
                "optimal_rate": optimal_rate,
                "success_rate": success_rate,
            },
        )

        return ApplicationStrategy(
            optimal_daily_applications=round(optimal_rate, 1),
            prioritized_jobs=prioritized[:20],
            current_success_rate=success_rate,
            strategic_focus=strategic_focus,
            action_items=action_items,
        )

    # ------------------------------------------------------------------
    # Private helpers - all pure, no I/O
    # ------------------------------------------------------------------

    def _determine_candidate_level(self) -> str:
        years = int(self._profile.get("experience_years") or 0)
        if years >= 10:
            return "Executive"
        if years >= 7:
            return "Senior"
        if years >= 4:
            return "Mid"
        return "Junior"

    def _company_size_delta(self, company_lower: str) -> float:
        cfg = self._config
        if any(name in company_lower for name in cfg.large_corp_names):
            return cfg.large_corp_boost
        if any(kw in company_lower for kw in cfg.mid_company_keywords):
            return cfg.mid_company_boost
        if any(kw in company_lower for kw in cfg.startup_keywords):
            return cfg.startup_penalty
        return 0.0

    def _role_patterns(self, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        role_freq: Dict[str, int] = defaultdict(int)
        seniority: Dict[str, int] = defaultdict(int)
        cfg = self._config

        for job in jobs:
            title = (job.get("title") or "").lower()
            for role in self._target_roles:
                if role in title:
                    role_freq[role] += 1
            if any(kw in title for kw in cfg.senior_keywords):
                seniority["Senior+"] += 1
            elif any(kw in title for kw in cfg.management_keywords):
                seniority["Management"] += 1
            else:
                seniority["Other"] += 1

        most_common = max(role_freq.items(), key=lambda x: x[1])[0] if role_freq else "None"
        return {
            "target_role_frequency": dict(role_freq),
            "seniority_distribution": dict(seniority),
            "most_common_role": most_common,
        }

    def _calculate_market_health(
        self,
        recent_jobs: List[Dict[str, Any]],
        recent_scores: List[float],
        applications: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        cfg = self._config
        if not recent_jobs:
            return {"health_score": 0, "status": "No data"}

        availability = min(len(recent_jobs) / 10.0, 1.0)
        avg_quality = mean(recent_scores) / 100.0 if recent_scores else 0.0
        # competition: more applications relative to recent jobs → worse
        competition = 1.0 - min(len(applications) / max(len(recent_jobs), 1), 0.8)

        health = (
            availability * cfg.availability_weight
            + avg_quality * cfg.quality_weight
            + competition * cfg.competition_weight
        ) * 100.0

        status = (
            "Excellent" if health >= 80
            else "Good" if health >= 60
            else "Fair" if health >= 40
            else "Poor"
        )

        return {
            "health_score": round(health, 1),
            "status": status,
            "job_availability": round(availability * 100, 1),
            "quality_score": round(avg_quality * 100, 1),
            "competition_factor": round(competition * 100, 1),
        }

    def _market_recommendations(
        self,
        market_health: Dict[str, Any],
        quality_dist: Dict[str, Any],
    ) -> List[str]:
        cfg = self._config
        status = market_health.get("status", "Unknown")
        recs: List[str] = {
            "Excellent": [
                "Market is optimal — increase application rate",
                f"Prioritise matches with score ≥ {cfg.very_high_score}",
            ],
            "Good": [
                "Good conditions — maintain current cadence",
                f"Target matches with score ≥ {cfg.high_score}",
            ],
            "Fair": [
                "Competitive market — be selective, quality over quantity",
                f"Focus on roles scoring ≥ {cfg.medium_score}",
            ],
        }.get(status, [
            "Market is challenging — broaden search criteria",
            f"Consider roles scoring ≥ {cfg.low_score}",
        ])

        vh_pct = quality_dist.get("very_high", {}).get("percentage", 0)
        if vh_pct > 20:
            recs.append("High density of strong matches — remain selective")
        elif vh_pct < 5:
            recs.append("Few high-quality roles — consider expanding keywords or locations")

        return recs

    def _strategy_focus(
        self,
        success_rate: float,
        high_quality_count: int,
        optimal_rate: float,
    ) -> Tuple[str, List[str]]:
        if success_rate >= 30:
            focus = "Selective — you're converting well; protect quality"
            actions = [
                f"Apply to ≤ {int(optimal_rate)} roles/day, all score ≥ {self._config.high_score}",
                "Invest more time per application (research, tailored cover notes)",
                "Track which companies are moving fastest to offer",
            ]
        elif success_rate >= 10:
            focus = "Balanced — good volume, moderate conversion"
            actions = [
                f"Target {int(optimal_rate)}–{int(optimal_rate) + 2} applications/day",
                f"Prioritise top {int(optimal_rate)} jobs by priority_score",
                "Follow up on pending applications older than 10 days",
            ]
        else:
            focus = "Volume — broaden pipeline, test messaging"
            actions = [
                "Increase daily application target by 30 %",
                "A/B test two cover note styles across 10 applications each",
                f"Lower score threshold to {self._config.low_score} temporarily",
                "Review rejection patterns for signal",
            ]
        return focus, actions


# ---------------------------------------------------------------------------
# Module-level convenience function (used by dashboard)
# ---------------------------------------------------------------------------

def generate_decision_insights(
    jobs: List[Dict[str, Any]],
    applications: List[Dict[str, Any]],
    app_stats: Dict[str, Any],
    engine: JobDecisionEngine,
) -> Dict[str, Any]:
    """
    Generate a complete decision insight bundle for dashboard consumption.
    
    Returns a dict ready to serialize to JSON or embed in the HTML template.
    Callers own I/O; this function is pure given its inputs.
    """
    trends = engine.analyze_market_trends(jobs, applications)
    strategy = engine.generate_application_strategy(jobs, applications, app_stats)

    top_opportunities: List[Dict[str, Any]] = []
    for entry in strategy.prioritized_jobs[:5]:
        job = entry["job"]
        top_opportunities.append({
            "title": job.get("title"),
            "company": job.get("company"),
            "score": job.get("score"),
            "priority_score": entry["priority_score"],
            "success_probability": entry["success_probability"],
            "recommendation": entry["recommendation"],
            "link": job.get("link"),
        })

    return {
        "generated_at": datetime.now().isoformat(),
        "market_analysis": {
            "market_health": trends.market_health,
            "score_trend": trends.market_overview.get("score_trend"),
            "recommendations": trends.recommendations,
            "quality_distribution": trends.quality_distribution,
        },
        "application_strategy": {
            "strategic_focus": strategy.strategic_focus,
            "optimal_daily_applications": strategy.optimal_daily_applications,
            "action_items": strategy.action_items,
            "prioritized_jobs": strategy.prioritized_jobs[:10],
        },
        "competitive_analysis": {
            "top_opportunities": top_opportunities,
        },
        "candidate_profile": {
            "level": engine._level,
            "target_roles": engine._target_roles,
            "competitive_advantages": [
                f"{engine._level}-level experience",
                "UAE market knowledge",
                f"Targeted {len(engine._target_roles)} role focus",
            ],
        },
    }


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------

def _to_log_odds(p: float) -> float:
    """Convert probability to log-odds. Clamps to avoid ±inf."""
    p = max(0.01, min(0.99, p))
    return math.log(p / (1.0 - p))


def _from_log_odds(lo: float) -> float:
    """Convert log-odds back to probability."""
    return 1.0 / (1.0 + math.exp(-lo))


def _to_log_odds_delta(delta: float) -> float:
    """
    Convert a fractional boost/penalty (e.g. 0.15 = +15 pp) into a
    log-odds shift calibrated at p=0.5 (neutral baseline).
    """
    if delta == 0.0:
        return 0.0
    p_with = max(0.01, min(0.99, 0.5 + delta))
    return _to_log_odds(p_with) - _to_log_odds(0.5)


def _classify_probability(probability: float) -> Tuple[str, str]:
    if probability >= 80:
        return "Very High", "Apply immediately — excellent match"
    if probability >= 65:
        return "High", "Strong candidate — apply with confidence"
    if probability >= 50:
        return "Medium", "Good fit — consider applying"
    return "Low", "Consider other opportunities first"


def _score_trend(recent: List[float], historical: List[float]) -> str:
    """
    Compare recent cohort against the *previous* cohort (not the full set).
    Returns 'improving', 'declining', or 'stable'.
    """
    if not recent or not historical:
        return "insufficient_data"
    diff = mean(recent) - mean(historical)
    if diff > 2.0:
        return "improving"
    if diff < -2.0:
        return "declining"
    return "stable"


def _quality_distribution(scores: List[float], cfg: EngineConfig) -> Dict[str, Any]:
    if not scores:
        return {}
    total = len(scores)
    bands = {
        "very_high": [s for s in scores if s >= cfg.very_high_score],
        "high": [s for s in scores if cfg.high_score <= s < cfg.very_high_score],
        "medium": [s for s in scores if cfg.medium_score <= s < cfg.high_score],
        "low": [s for s in scores if cfg.low_score <= s < cfg.medium_score],
        "very_low": [s for s in scores if s < cfg.low_score],
    }
    return {
        band: {"count": len(items), "percentage": round(len(items) / total * 100, 1)}
        for band, items in bands.items()
    } | {"median_score": median(scores)}


def _is_after(date_str: Optional[str], cutoff: datetime) -> bool:
    dt = _parse_date(date_str)
    return dt is not None and dt >= cutoff


def _is_between(date_str: Optional[str], start: datetime, end: datetime) -> bool:
    dt = _parse_date(date_str)
    return dt is not None and start <= dt < end


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string with specific exception handling."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as e:
        logger.debug("date_parse_failed", extra={"raw": date_str, "error": str(e)})
        return None
