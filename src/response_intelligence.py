"""
Response Intelligence Layer — v2
High-end AI-powered response analysis with a real, persisted feedback loop.

Architecture:
  - ScoringAdjustments: serialisable overlay applied on top of EngineConfig weights.
  - StateStore (Protocol): pluggable persistence (JSON file, Redis, Postgres).
  - ResponseIntelligenceEngine: pure analysis; all I/O injected.
  - Thread-safe state mutations via RLock.
  - ResponseType / FollowUpTiming: enums used throughout (no raw string matching).
  - O(n) application-job matching via precomputed index.

Feedback loop:
  learn_from_outcomes() → ScoringAdjustments → StateStore.save()
  On next startup: StateStore.load() → adjustments applied to every probability calc.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

from src.decision_engine import (
    EngineConfig,
    JobDecisionEngine,
    ProbabilityResult,
    _from_log_odds,
    _to_log_odds,
)

logger = logging.getLogger(__name__)

_MAX_ADJUSTMENT = 0.30   # max per-factor log-odds shift (≈ ±8 pp at p=0.5)
_MIN_SAMPLES = 5         # minimum outcomes before a factor is trusted


# ---------------------------------------------------------------------------
# Enums — used everywhere; no raw string comparisons
# ---------------------------------------------------------------------------

# Status aliases for common variations in application records
_STATUS_ALIASES: Dict[str, str] = {
    "interview":   "interview_scheduled",
    "offer":       "offer_extended",
    "assessment":  "technical_assessment",
    "screening":   "screening",
    "rejected":    "rejected",
    "applied":     "no_response",
}


class ResponseType(str, Enum):
    REJECTED               = "rejected"
    NO_RESPONSE            = "no_response"
    SCREENING              = "screening"
    INTERVIEW_SCHEDULED    = "interview_scheduled"
    INTERVIEW_COMPLETED    = "interview_completed"
    TECHNICAL_ASSESSMENT   = "technical_assessment"
    OFFER_EXTENDED         = "offer_extended"
    OFFER_ACCEPTED         = "offer_accepted"
    OFFER_DECLINED         = "offer_declined"
    FOLLOW_UP_REQUIRED     = "follow_up_required"

    @classmethod
    def from_raw(cls, raw: Optional[str]) -> "ResponseType":
        normalized = (raw or "").strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            pass
        aliased = _STATUS_ALIASES.get(normalized)
        if aliased:
            try:
                return cls(aliased)
            except ValueError:
                pass
        logger.debug("response_type_unknown", extra={"raw": raw})
        return cls.NO_RESPONSE

    @property
    def is_positive(self) -> bool:
        return self in {
            ResponseType.SCREENING,
            ResponseType.INTERVIEW_SCHEDULED,
            ResponseType.INTERVIEW_COMPLETED,
            ResponseType.TECHNICAL_ASSESSMENT,
            ResponseType.OFFER_EXTENDED,
            ResponseType.OFFER_ACCEPTED,
        }


class FollowUpTiming(str, Enum):
    IMMEDIATE  = "immediate"
    THIS_WEEK  = "this_week"
    NEXT_WEEK  = "next_week"
    NOT_NEEDED = "not_needed"


@dataclass
class ResponsePattern:
    pattern_type: str
    frequency: float
    success_rate: float
    avg_response_time_days: float
    confidence: float
    sample_size: int
    factors: Dict[str, float]


@dataclass
class LearningInsight:
    insight_type: str
    description: str
    impact_score: float
    confidence: float
    actionable: bool
    recommendation: str


@dataclass
class FollowUpAction:
    application_id: str          # link or unique key
    company: str
    role: str
    action_type: str
    priority: str                # "high" | "medium" | "low"
    timing: FollowUpTiming
    template_key: str
    success_probability: float
    days_pending: int

    @property
    def priority_score(self) -> float:
        weights = {"high": 3.0, "medium": 2.0, "low": 1.0}
        return weights.get(self.priority, 1.0) * self.success_probability


# ---------------------------------------------------------------------------
# Scoring adjustments — the persisted output of the feedback loop
# ---------------------------------------------------------------------------

@dataclass
class ScoringAdjustments:
    """
    Learned log-odds deltas applied on top of EngineConfig base weights.

    Each value is a log-odds shift:
      - role_boosts["backend engineer"] = +0.15  →  boost p for that role
      - company_boosts["acme corp"]     = -0.10  →  penalise that company
      - score_band_boosts["very_high"]  = +0.08  →  extra trust in 85+ scored jobs

    Values are clamped to ±_MAX_ADJUSTMENT on save to prevent runaway drift.
    """
    role_boosts: Dict[str, float] = field(default_factory=dict)
    company_boosts: Dict[str, float] = field(default_factory=dict)
    score_band_boosts: Dict[str, float] = field(default_factory=dict)
    version: int = 0
    updated_at: str = ""
    samples_seen: int = 0

    def clamped(self) -> "ScoringAdjustments":
        def clamp(d: Dict[str, float]) -> Dict[str, float]:
            return {k: max(-_MAX_ADJUSTMENT, min(_MAX_ADJUSTMENT, v)) for k, v in d.items()}
        return ScoringAdjustments(
            role_boosts=clamp(self.role_boosts),
            company_boosts=clamp(self.company_boosts),
            score_band_boosts=clamp(self.score_band_boosts),
            version=self.version + 1,
            updated_at=datetime.now().isoformat(),
            samples_seen=self.samples_seen,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "ScoringAdjustments":
        return cls(**json.loads(raw))

    @classmethod
    def empty(cls) -> "ScoringAdjustments":
        return cls(updated_at=datetime.now().isoformat())


# ---------------------------------------------------------------------------
# StateStore — pluggable persistence (inject any backend)
# ---------------------------------------------------------------------------

class StateStore(Protocol):
    def load(self) -> Optional[ScoringAdjustments]: ...
    def save(self, adjustments: ScoringAdjustments) -> None: ...


class JsonFileStateStore:
    """Default persistence: JSON file on disk."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Optional[ScoringAdjustments]:
        if not self._path.exists():
            return None
        try:
            return ScoringAdjustments.from_json(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("state_store_load_failed", extra={"path": str(self._path)})
            return None

    def save(self, adjustments: ScoringAdjustments) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(adjustments.to_json(), encoding="utf-8")
        tmp.replace(self._path)     # atomic on POSIX
        logger.info(
            "state_store_saved",
            extra={
                "path": str(self._path),
                "version": adjustments.version,
                "samples": adjustments.samples_seen,
            },
        )


class ResponseIntelligenceEngine:
    """
    Response intelligence engine with a real, persisted feedback loop.

    Responsibilities:
      - Analyse employer response patterns
      - Learn success factors from outcomes
      - Generate follow-up intelligence
      - Maintain and persist scoring adjustments

    All I/O (data loading, persistence) is injected. Analysis methods are pure
    given their inputs. Thread-safe for concurrent use.
    """

    def __init__(
        self,
        decision_engine: JobDecisionEngine,
        state_store: StateStore,
        config: Optional[EngineConfig] = None,
    ) -> None:
        self._engine = decision_engine
        self._store = state_store
        self._config = config or EngineConfig()
        self._lock = threading.RLock()

        loaded = state_store.load()
        self._adjustments: ScoringAdjustments = loaded if loaded else ScoringAdjustments.empty()

        logger.info(
            "response_intelligence_engine_initialised",
            extra={
                "adjustments_version": self._adjustments.version,
                "samples_seen": self._adjustments.samples_seen,
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def adjusted_probability(self, job: Dict[str, Any]) -> ProbabilityResult:
        """
        Calculate success probability with learned adjustments applied.

        Base engine runs first; learned role/company/band deltas are then
        compounded as additional log-odds shifts.
        """
        base = self._engine.calculate_success_probability(job)
        base_lo = _to_log_odds(base.probability / 100.0)

        with self._lock:
            adj = self._adjustments

        delta = 0.0
        title_lower = (job.get("title") or "").lower()
        company_lower = (job.get("company") or "").lower()
        score = float(job.get("score") or 0)

        # Role boosts
        for role, boost in adj.role_boosts.items():
            if role in title_lower:
                delta += boost

        # Company boosts
        for company, boost in adj.company_boosts.items():
            if company in company_lower:
                delta += boost

        # Score band boosts
        band = _score_band_key(score, self._config)
        delta += adj.score_band_boosts.get(band, 0.0)

        adjusted_prob = min(_from_log_odds(base_lo + delta) * 100.0, 95.0)

        return ProbabilityResult(
            probability=round(adjusted_prob, 1),
            confidence=base.confidence,
            recommendation=base.recommendation,
            factors={**base.factors, "learned_adjustment": round(delta * 10, 2)},
        )

    def analyze_response_patterns(
        self,
        applications: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Analyse patterns in employer responses. Pure given `applications`."""
        if not applications:
            logger.warning("analyze_response_patterns_no_data")
            return {"error": "No application data available"}

        response_counts: Dict[ResponseType, int] = defaultdict(int)
        response_times: List[float] = []
        successful_outcomes: List[Dict[str, Any]] = []

        for app in applications:
            rt = ResponseType.from_raw(app.get("status"))
            response_counts[rt] += 1

            applied = _parse_date(app.get("date_applied"))
            updated = _parse_date(app.get("date_updated"))
            if applied and updated:
                days = (updated - applied).days
                response_times.append(float(days))
                if rt.is_positive:
                    successful_outcomes.append({
                        "status": rt.value,
                        "response_time_days": days,
                        "company": app.get("company"),
                        "role": app.get("title"),
                    })

        total = len(applications)
        success_rate = len(successful_outcomes) / total
        avg_rt = sum(response_times) / len(response_times) if response_times else 0.0

        patterns = self._identify_patterns(response_counts, response_times, total)
        insights = self._generate_response_insights(success_rate, avg_rt, patterns)

        logger.info(
            "response_patterns_analyzed",
            extra={
                "total": total,
                "success_rate": round(success_rate, 3),
                "avg_response_days": round(avg_rt, 1),
                "patterns": len(patterns),
            },
        )

        return {
            "total_applications": total,
            "response_distribution": {rt.value: count for rt, count in response_counts.items()},
            "success_rate_pct": round(success_rate * 100, 1),
            "avg_response_time_days": round(avg_rt, 1),
            "patterns": [_pattern_to_dict(p) for p in patterns],
            "insights": [_insight_to_dict(i) for i in insights],
            "successful_outcomes": successful_outcomes[-10:],
        }

    def learn_from_outcomes(
        self,
        applications: List[Dict[str, Any]],
        jobs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Learn success factors from matched application outcomes.

        Produces and persists updated ScoringAdjustments.
        All computation is deterministic given the inputs.
        """
        # O(n) index — no nested loop
        job_index: Dict[str, Dict[str, Any]] = {j["link"]: j for j in jobs if j.get("link")}
        matched = _match_applications(applications, job_index)

        if len(matched) < _MIN_SAMPLES:
            return {"error": f"Need at least {_MIN_SAMPLES} matched outcomes; got {len(matched)}"}

        success_factors = _analyze_success_factors(matched)
        new_adjustments = self._build_adjustments(success_factors, matched)
        insights = _generate_learning_insights(success_factors)

        with self._lock:
            self._adjustments = new_adjustments
        self._store.save(new_adjustments)

        logger.info(
            "learning_completed",
            extra={
                "matched": len(matched),
                "factors": len(success_factors),
                "adjustments_version": new_adjustments.version,
            },
        )

        return {
            "matched_pairs": len(matched),
            "success_factors": success_factors,
            "insights": [_insight_to_dict(i) for i in insights],
            "adjustments_version": new_adjustments.version,
            "improvement_opportunities": _improvement_opportunities(success_factors),
        }

    def generate_follow_up_intelligence(
        self,
        applications: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate prioritised follow-up actions. Pure given `applications`."""
        if not applications:
            return {"error": "No application data available"}

        now = datetime.now()
        actions: List[FollowUpAction] = []

        for app in applications:
            action = self._follow_up_for(app, now)
            if action:
                actions.append(action)

        actions.sort(key=lambda a: a.priority_score, reverse=True)

        dist = _priority_distribution(actions)
        timing_map = _timing_map(actions)

        logger.info(
            "follow_up_intelligence_generated",
            extra={"analyzed": len(applications), "actions": len(actions)},
        )

        return {
            "follow_up_actions": [_action_to_dict(a) for a in actions[:20]],
            "total_actions": len(actions),
            "priority_distribution": dist,
            "timing": timing_map,
        }

    def update_scoring_from_feedback(
        self,
        outcome_patterns: Dict[str, Any],
        company_responses: Dict[str, float],
        role_success_rates: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Apply explicit feedback to scoring adjustments and persist.

        Raises ValueError if adjustments fail validation.
        """
        with self._lock:
            current = self._adjustments

        role_boosts = dict(current.role_boosts)
        company_boosts = dict(current.company_boosts)

        # Role adjustments — additive update on log-odds
        for role, rate in role_success_rates.items():
            delta = _rate_to_log_odds_delta(rate)
            role_boosts[role] = role_boosts.get(role, 0.0) + delta * 0.5  # EMA-style blend

        # Company adjustments
        for company, rate in company_responses.items():
            delta = _rate_to_log_odds_delta(rate)
            company_boosts[company.lower()] = company_boosts.get(company.lower(), 0.0) + delta * 0.5

        candidate = ScoringAdjustments(
            role_boosts=role_boosts,
            company_boosts=company_boosts,
            score_band_boosts=current.score_band_boosts,
            samples_seen=current.samples_seen,
        ).clamped()

        _validate_adjustments(candidate)   # raises ValueError on bad state

        with self._lock:
            self._adjustments = candidate
        self._store.save(candidate)

        logger.info(
            "scoring_updated_from_feedback",
            extra={
                "version": candidate.version,
                "role_keys": len(role_success_rates),
                "company_keys": len(company_responses),
            },
        )

        return {
            "version": candidate.version,
            "role_boosts_applied": len(role_success_rates),
            "company_boosts_applied": len(company_responses),
            "next_scheduled_update": (datetime.now() + timedelta(days=7)).isoformat(),
        }

    @property
    def current_adjustments(self) -> ScoringAdjustments:
        with self._lock:
            return self._adjustments

    # ------------------------------------------------------------------
    # Private helper methods
    # ------------------------------------------------------------------

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string safely."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError, TypeError):
            return None

    def _identify_patterns(
        self,
        response_counts: Dict[ResponseType, int],
        response_times: List[float],
        total: int,
    ) -> List[ResponsePattern]:
        patterns: List[ResponsePattern] = []

        if response_times:
            avg = sum(response_times) / len(response_times)
            fast = [t for t in response_times if t <= 3]
            patterns.append(ResponsePattern(
                pattern_type="response_time",
                frequency=1.0,
                success_rate=len(fast) / len(response_times),
                avg_response_time_days=avg,
                confidence=min(0.5 + len(response_times) / 100, 0.95),
                sample_size=len(response_times),
                factors={"fast_responses_pct": round(len(fast) / len(response_times) * 100, 1)},
            ))

        for rt, count in response_counts.items():
            if rt.is_positive and total:
                patterns.append(ResponsePattern(
                    pattern_type=f"success_{rt.value}",
                    frequency=count / total,
                    success_rate=count / total,
                    avg_response_time_days=0.0,
                    confidence=min(0.5 + count / 20, 0.95),
                    sample_size=count,
                    factors={"rate_pct": round(count / total * 100, 1)},
                ))

        return patterns

    def _generate_response_insights(
        self,
        success_rate: float,
        avg_response_time: float,
        patterns: List[ResponsePattern],
    ) -> List[LearningInsight]:
        insights: List[LearningInsight] = []

        if success_rate < 0.10:
            insights.append(LearningInsight(
                insight_type="low_success_rate",
                description=f"Success rate is {success_rate*100:.1f}% — below 10% threshold",
                impact_score=0.9,
                confidence=0.85,
                actionable=True,
                recommendation="Audit application quality; increase score threshold to 75+",
            ))
        elif success_rate > 0.30:
            insights.append(LearningInsight(
                insight_type="high_success_rate",
                description=f"Success rate is {success_rate*100:.1f}% — strong conversion",
                impact_score=0.5,
                confidence=0.85,
                actionable=False,
                recommendation="Maintain strategy; consider increasing application volume",
            ))

        if avg_response_time > 14:
            insights.append(LearningInsight(
                insight_type="slow_market_response",
                description=f"Average employer response is {avg_response_time:.0f} days",
                impact_score=0.5,
                confidence=0.75,
                actionable=True,
                recommendation="Schedule follow-up emails at day 10 for pending applications",
            ))

        return insights

    def _build_adjustments(
        self,
        success_factors: Dict[str, Tuple[float, int]],
        matched: List[Dict[str, Any]],
    ) -> ScoringAdjustments:
        """
        Convert success_factors → ScoringAdjustments.

        success_factors[key] = (success_rate, sample_count).
        Only factors with enough samples are trusted.
        """
        with self._lock:
            current = self._adjustments

        role_boosts = dict(current.role_boosts)
        company_boosts = dict(current.company_boosts)
        score_band_boosts = dict(current.score_band_boosts)

        for key, (rate, n) in success_factors.items():
            if n < _MIN_SAMPLES:
                continue
            confidence = min(n / 30.0, 1.0)  # saturates at 30 samples
            delta = _rate_to_log_odds_delta(rate) * confidence

            if key.startswith("role::"):
                role = key[6:]
                role_boosts[role] = role_boosts.get(role, 0.0) + delta * 0.4  # slow blend
            elif key.startswith("company::"):
                company = key[9:]
                company_boosts[company] = company_boosts.get(company, 0.0) + delta * 0.4
            elif key.startswith("band::"):
                band = key[6:]
                score_band_boosts[band] = score_band_boosts.get(band, 0.0) + delta * 0.4

        return ScoringAdjustments(
            role_boosts=role_boosts,
            company_boosts=company_boosts,
            score_band_boosts=score_band_boosts,
            samples_seen=current.samples_seen + len(matched),
        ).clamped()

    def _follow_up_for(
        self,
        app: Dict[str, Any],
        now: datetime,
    ) -> Optional[FollowUpAction]:
        rt = ResponseType.from_raw(app.get("status"))
        applied = _parse_date(app.get("date_applied"))
        updated = _parse_date(app.get("date_updated"))
        if not applied:
            return None

        days_applied = (now - applied).days
        days_updated = (now - updated).days if updated else days_applied

        link = app.get("link") or ""
        company = app.get("company") or "Unknown"
        role = app.get("title") or "Unknown role"

        if rt == ResponseType.NO_RESPONSE and days_applied >= 14:
            return FollowUpAction(
                application_id=link,
                company=company,
                role=role,
                action_type="follow_up_email",
                priority="medium",
                timing=FollowUpTiming.IMMEDIATE,
                template_key="polite_follow_up",
                success_probability=0.30,
                days_pending=days_applied,
            )

        if rt == ResponseType.INTERVIEW_SCHEDULED and days_updated >= 7:
            return FollowUpAction(
                application_id=link,
                company=company,
                role=role,
                action_type="interview_confirmation",
                priority="high",
                timing=FollowUpTiming.IMMEDIATE,
                template_key="interview_confirmation",
                success_probability=0.70,
                days_pending=days_updated,
            )

        if rt == ResponseType.TECHNICAL_ASSESSMENT and days_updated >= 5:
            return FollowUpAction(
                application_id=link,
                company=company,
                role=role,
                action_type="assessment_follow_up",
                priority="medium",
                timing=FollowUpTiming.THIS_WEEK,
                template_key="assessment_follow_up",
                success_probability=0.50,
                days_pending=days_updated,
            )

        if rt == ResponseType.INTERVIEW_COMPLETED and days_updated >= 3:
            return FollowUpAction(
                application_id=link,
                company=company,
                role=role,
                action_type="post_interview_thank_you",
                priority="high",
                timing=FollowUpTiming.IMMEDIATE,
                template_key="post_interview_follow_up",
                success_probability=0.60,
                days_pending=days_updated,
            )

        return None

# ------------------------------------------------------------------
    # Private helpers — all pure
    # ------------------------------------------------------------------

    def _parse_date(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError, TypeError):
            logger.debug("date_parse_failed", extra={"raw": value})
            return None


# ---------------------------------------------------------------------------
# Pure module-level helpers
# ---------------------------------------------------------------------------

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        logger.debug("date_parse_failed", extra={"raw": value})
        return None


def _score_band_key(score: float, cfg: EngineConfig) -> str:
    if score >= cfg.very_high_score:
        return "very_high"
    if score >= cfg.high_score:
        return "high"
    if score >= cfg.medium_score:
        return "medium"
    if score >= cfg.low_score:
        return "low"
    return "very_low"


def _rate_to_log_odds_delta(rate: float) -> float:
    """
    Convert a success rate to a log-odds shift relative to a 0.5 baseline.
    rate=0.8 → positive shift; rate=0.2 → negative shift; rate=0.5 → zero.
    """
    clamped = max(0.05, min(0.95, rate))
    neutral_lo = math.log(0.5 / 0.5)          # = 0
    rate_lo = math.log(clamped / (1.0 - clamped))
    return rate_lo - neutral_lo


def _match_applications(
    applications: List[Dict[str, Any]],
    job_index: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """O(n) matching via precomputed index."""
    matched = []
    for app in applications:
        link = app.get("link", "")
        job = job_index.get(link)
        if job:
            matched.append({
                "application": app,
                "job": job,
                "success": ResponseType.from_raw(app.get("status")).is_positive,
                "score": float(job.get("score") or 0),
            })
    return matched


def _analyze_success_factors(
    matched: List[Dict[str, Any]],
) -> Dict[str, Tuple[float, int]]:
    """
    Returns: {factor_key: (success_rate, sample_count)}

    Keys are namespaced:
      role::<title_lower>
      company::<company_lower>
      band::<very_high|high|medium|low|very_low>
    """
    buckets: Dict[str, List[bool]] = defaultdict(list)

    for m in matched:
        job = m["job"]
        success: bool = m["success"]
        title = (job.get("title") or "").lower()
        company = (job.get("company") or "").lower()

        buckets[f"company::{company}"].append(success)

        score = float(job.get("score") or 0)
        # Score bands — clean separate tracking, no type mixing
        band = (
            "very_high" if score >= 85
            else "high" if score >= 75
            else "medium" if score >= 65
            else "low" if score >= 40
            else "very_low"
        )
        buckets[f"band::{band}"].append(success)

        # Role keywords — first two meaningful tokens
        tokens = [t for t in title.split() if len(t) > 2][:2]
        for token in tokens:
            buckets[f"role::{token}"].append(success)

    return {
        key: (sum(outcomes) / len(outcomes), len(outcomes))
        for key, outcomes in buckets.items()
        if outcomes
    }


def _generate_learning_insights(
    success_factors: Dict[str, Tuple[float, int]],
) -> List[LearningInsight]:
    insights: List[LearningInsight] = []

    band_key = "band::very_high"
    if band_key in success_factors:
        rate, n = success_factors[band_key]
        if n >= _MIN_SAMPLES:
            insights.append(LearningInsight(
                insight_type="score_band_signal",
                description=f"Jobs scoring 85+ convert at {rate*100:.1f}% (n={n})",
                impact_score=0.9,
                confidence=min(n / 30.0, 0.95),
                actionable=True,
                recommendation="Prioritise 85+ scored applications" if rate > 0.4
                               else "Score alone is insufficient — review role targeting",
            ))

    # Best and worst companies by success rate (with enough data)
    company_factors = {
        k: v for k, v in success_factors.items()
        if k.startswith("company::") and v[1] >= _MIN_SAMPLES
    }
    if company_factors:
        best = max(company_factors.items(), key=lambda x: x[1][0])
        worst = min(company_factors.items(), key=lambda x: x[1][0])
        name = best[0].replace("company::", "")
        rate, n = best[1]
        insights.append(LearningInsight(
            insight_type="top_company",
            description=f"{name.title()} converts at {rate*100:.1f}% (n={n})",
            impact_score=0.7,
            confidence=min(n / 30.0, 0.95),
            actionable=True,
            recommendation=f"Increase application volume to {name.title()}",
        ))
        if worst[1][0] < 0.05:
            wname = worst[0].replace("company::", "")
            insights.append(LearningInsight(
                insight_type="low_conversion_company",
                description=f"{wname.title()} converts at {worst[1][0]*100:.1f}%",
                impact_score=0.6,
                confidence=min(worst[1][1] / 30.0, 0.95),
                actionable=True,
                recommendation=f"Deprioritise {wname.title()} — very low conversion",
            ))

    return insights


def _improvement_opportunities(
    success_factors: Dict[str, Tuple[float, int]],
) -> List[str]:
    opportunities: List[str] = []
    for band in ("band::low", "band::medium"):
        if band in success_factors:
            rate, n = success_factors[band]
            if n >= _MIN_SAMPLES and rate < 0.05:
                label = band.replace("band::", "")
                opportunities.append(
                    f"Low conversion on {label}-scored jobs ({rate*100:.1f}%) — raise score threshold"
                )
    return opportunities


def _validate_adjustments(adj: ScoringAdjustments) -> None:
    """Raise ValueError if any adjustment is out of bounds post-clamp."""
    all_values = (
        list(adj.role_boosts.values())
        + list(adj.company_boosts.values())
        + list(adj.score_band_boosts.values())
    )
    outliers = [v for v in all_values if abs(v) > _MAX_ADJUSTMENT + 1e-9]
    if outliers:
        raise ValueError(f"Adjustments exceed bound ±{_MAX_ADJUSTMENT}: {outliers}")


def _priority_distribution(actions: List[FollowUpAction]) -> Dict[str, int]:
    dist: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for a in actions:
        dist[a.priority] = dist.get(a.priority, 0) + 1
    return dist


def _timing_map(actions: List[FollowUpAction]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {t.value: [] for t in FollowUpTiming if t != FollowUpTiming.NOT_NEEDED}
    for a in actions:
        if a.timing != FollowUpTiming.NOT_NEEDED:
            out[a.timing.value].append(f"{a.action_type} → {a.company}")
    return out


# Serialisation helpers — keep dataclasses off the wire boundary
def _pattern_to_dict(p: ResponsePattern) -> Dict[str, Any]:
    return asdict(p)


def _insight_to_dict(i: LearningInsight) -> Dict[str, Any]:
    return asdict(i)


def _action_to_dict(a: FollowUpAction) -> Dict[str, Any]:
    d = asdict(a)
    d["timing"] = a.timing.value
    return d


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_engine(
    decision_engine: JobDecisionEngine,
    state_path: Path = Path("data/scoring_adjustments.json"),
    config: Optional[EngineConfig] = None,
) -> ResponseIntelligenceEngine:
    """
    Production factory. Call once at startup; share the instance.

    Example:
        engine = create_engine(decision_engine, Path("data/scoring.json"))
        # then pass `engine` wherever needed — do NOT call this per-request.
    """
    return ResponseIntelligenceEngine(
        decision_engine=decision_engine,
        state_store=JsonFileStateStore(state_path),
        config=config,
    )
