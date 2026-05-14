"""Identity flow mapper — decide whether an incoming user signal matches
an existing profile, requires user clarification, or should create a new profile.

This module is intentionally pure (no I/O, no DB calls).  Callers are
expected to load candidate profiles from the repository and pass them in.

#96 gave us ``ProfileContext``; #97 uses it to compare incoming signals
against known profiles and produces a deterministic resolution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

from src.services.profile_context_resolver import ProfileContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IdentitySignal:
    """An incoming identity signal from any source (chat, Jotform, Telegram, CV)."""

    source: str  # e.g. "jotform", "telegram", "chat", "cv_upload"
    user_id: Optional[str] = None  # pre-known user_id (e.g. from cookie/session)
    telegram_username: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    profile: Optional[ProfileContext] = None


@dataclass(frozen=True, slots=True)
class IdentityResolution:
    """The result of comparing an incoming signal against candidate profiles."""

    action: Literal["merge", "ask_user", "create_new", "ignore"]
    confidence: float  # 0.0–1.0
    matched_user_id: Optional[str]
    reasons: List[str] = field(default_factory=list)
    conflicts: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IdentityScore = float


def _norm_phone(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    # Strip all non-digits for comparison
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-10:] if len(digits) >= 7 else None  # last 10 digits


def _norm_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    return v if "@" in v else None


def _norm_telegram(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lstrip("@").lower()
    return v if v else None


def _norm_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    return v if v else None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_STRONG_WEIGHT = 1.0
_MEDIUM_WEIGHT = 0.4
_WEAK_WEIGHT = 0.15


def _score_candidate(signal: IdentitySignal, candidate: ProfileContext) -> _IdentityScore:
    """Return a similarity score (0.0–∞) for a candidate.

    Scoring is additive so multiple matching signals compound.
    """
    score = 0.0

    # Strong signals — exact matches on unique identifiers
    if signal.telegram_username and _norm_telegram(
        signal.telegram_username
    ) == _norm_telegram(candidate.telegram_username):
        score += _STRONG_WEIGHT
    if signal.email and _norm_email(signal.email) == _norm_email(candidate.email):
        score += _STRONG_WEIGHT
    if signal.phone and _norm_phone(signal.phone) == _norm_phone(candidate.phone):
        score += _STRONG_WEIGHT
    if signal.user_id and signal.user_id == candidate.user_id:
        score += _STRONG_WEIGHT

    # Overlap count (shared fields between signal and candidate)
    overlap_count = 0
    if signal.profile:
        for attr in ("skills", "industries", "current_role", "target_roles"):
            incoming = set(getattr(signal.profile, attr, []) or [])
            existing = set(getattr(candidate, attr, []) or [])
            if incoming and existing and incoming & existing:
                overlap_count += 1

    # Medium signal — name match + field overlap
    name_match = signal.name and _norm_name(signal.name) == _norm_name(candidate.name)
    if name_match:
        if overlap_count >= 2:
            score += 0.8
        elif overlap_count == 1:
            score += 0.45
        else:
            score += 0.25  # name alone → weak, not enough for medium threshold

    # Weak signal — field overlap without name match
    elif signal.profile:
        if overlap_count >= 2:
            score += 0.3
        elif overlap_count == 1:
            score += 0.15

    return score


def _find_conflicts(
    signal: IdentitySignal, candidate: ProfileContext
) -> Dict[str, Tuple[Any, Any]]:
    """Detect field conflicts between signal and candidate."""
    conflicts: Dict[str, Tuple[Any, Any]] = {}

    # If signal has email and candidate has a *different* email → conflict
    s_email = _norm_email(signal.email)
    c_email = _norm_email(candidate.email)
    if s_email and c_email and s_email != c_email:
        conflicts["email"] = (signal.email, candidate.email)

    # Same for phone
    s_phone = _norm_phone(signal.phone)
    c_phone = _norm_phone(candidate.phone)
    if s_phone and c_phone and s_phone != c_phone:
        conflicts["phone"] = (signal.phone, candidate.phone)

    # Same for telegram username
    s_tg = _norm_telegram(signal.telegram_username)
    c_tg = _norm_telegram(candidate.telegram_username)
    if s_tg and c_tg and s_tg != c_tg:
        conflicts["telegram_username"] = (signal.telegram_username, candidate.telegram_username)

    return conflicts


def _missing_fields(signal: IdentitySignal, candidate: ProfileContext) -> List[str]:
    """List fields present in signal.profile but empty in candidate."""
    if not signal.profile:
        return []
    missing: List[str] = []
    for attr in _COMPLETENESS_FIELDS:
        incoming = getattr(signal.profile, attr)
        existing = getattr(candidate, attr)
        # Incoming has data, candidate is empty
        if incoming and (existing is None or existing == [] or existing == ""):
            missing.append(attr)
    return missing


# Fields used for missing-field comparison
_COMPLETENESS_FIELDS = [
    "skills",
    "years_experience",
    "target_roles",
    "preferred_cities",
    "salary_expectation_aed",
    "current_role",
    "industries",
]


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_STRONG_MATCH_THRESHOLD = 0.9   # one or more strong signals matched
_MEDIUM_MATCH_THRESHOLD = 0.4   # medium signal (name + overlap)
_MIN_SIGNAL_QUALITY = 0.15     # at least one usable identifier


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_identity_flow(
    incoming: IdentitySignal,
    candidates: List[ProfileContext],
) -> IdentityResolution:
    """Determine how to handle an incoming identity signal.

    Returns ``IdentityResolution`` with action one of:
    * ``merge``      — high-confidence match to an existing profile
    * ``ask_user``   — ambiguous / conflicting data; requires human choice
    * ``create_new`` — no existing profile matches
    * ``ignore``     — signal is too low-quality to act on
    """

    # 1. Check signal quality
    has_identifier = bool(
        incoming.user_id
        or incoming.email
        or incoming.phone
        or incoming.telegram_username
        or incoming.name
    )
    if not has_identifier:
        return IdentityResolution(
            action="ignore",
            confidence=0.0,
            matched_user_id=None,
            reasons=["Signal lacks any identifiable field (email, phone, telegram, name)"],
        )

    # 2. Score all candidates
    scored: List[Tuple[_IdentityScore, ProfileContext]] = []
    for cand in candidates:
        score = _score_candidate(incoming, cand)
        if score > 0:
            scored.append((score, cand))

    # Sort descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # 3. No candidate matched at all
    if not scored:
        return IdentityResolution(
            action="create_new",
            confidence=0.0,
            matched_user_id=None,
            reasons=["No existing profile matches this signal"],
        )

    top_score, top_candidate = scored[0]

    # 4. Check for multiple strong matches (ambiguous)
    strong_matches = [(s, c) for s, c in scored if s >= _STRONG_MATCH_THRESHOLD]
    if len(strong_matches) > 1:
        reasons = [
            f"Multiple profiles match strongly: {', '.join(c.user_id for _, c in strong_matches[:3])}"
        ]
        return IdentityResolution(
            action="ask_user",
            confidence=0.3,
            matched_user_id=None,
            reasons=reasons,
            conflicts={},
        )

    # 5. Strong single match — check for conflicts
    if top_score >= _STRONG_MATCH_THRESHOLD:
        conflicts = _find_conflicts(incoming, top_candidate)
        if conflicts:
            return IdentityResolution(
                action="ask_user",
                confidence=0.6,
                matched_user_id=top_candidate.user_id,
                reasons=[
                    f"Strong match to {top_candidate.user_id} but fields conflict: {', '.join(conflicts.keys())}"
                ],
                conflicts=conflicts,
                missing_fields=_missing_fields(incoming, top_candidate),
            )
        return IdentityResolution(
            action="merge",
            confidence=min(top_score, 1.0),
            matched_user_id=top_candidate.user_id,
            reasons=[
                f"Strong match to existing user {top_candidate.user_id} "
                f"via {incoming.source}"
            ],
            conflicts={},
            missing_fields=_missing_fields(incoming, top_candidate),
        )

    # 6. Medium match — name + overlap, but no strong identifiers
    if top_score >= _MEDIUM_MATCH_THRESHOLD:
        return IdentityResolution(
            action="ask_user",
            confidence=top_score,
            matched_user_id=top_candidate.user_id,
            reasons=[
                f"Medium match to {top_candidate.user_id} (name or field overlap). "
                "No strong identifier (email/phone/telegram) — recommend user confirmation."
            ],
            conflicts=_find_conflicts(incoming, top_candidate),
            missing_fields=_missing_fields(incoming, top_candidate),
        )

    # 7. Weak / no meaningful match
    return IdentityResolution(
        action="create_new",
        confidence=0.0,
        matched_user_id=None,
        reasons=["No existing profile matches this signal with sufficient confidence"],
    )
