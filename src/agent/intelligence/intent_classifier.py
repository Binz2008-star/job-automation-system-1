"""src/agent/intelligence/intent_classifier.py

Unified intent classifier for Rico chat messages.

Classifies every user message into a canonical intent BEFORE any action is
taken.  Replaces the permissive short-text fallback that treated arbitrary
text as job titles.

Classification pipeline:
  1. Exact-phrase fast-path (zero cost, high confidence)
  2. Regex pattern matching (zero cost, medium confidence)
  3. Fallback to ``unknown`` — never to job search

Intent list (from Issue #110 blueprint):
  - job_search_explicit          user names a role / asks to search
  - job_search_profile_match     "find me one that matches", "use my CV"
  - application_tracking         "show my tracked applications"
  - role_change                  "switch to X", "what about X"
  - profile_summary              "show my profile"
  - profile_update               "update my salary", "change my city"
  - cv_upload_or_parse           CV file reference or "use my CV"
  - onboarding_answer            answering an onboarding question
  - help                         "what can you do", "options"
  - smalltalk                    greetings, thanks, etc.
  - nonsense                     random/unrecognizable text
  - unknown                      uncertain — ask for clarification
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentResult:
    """Result of intent classification."""
    intent: str
    confidence: float
    source: str  # "exact", "regex", "fallback"
    extracted_role: Optional[str] = None


# ── Exact-phrase sets ────────────────────────────────────────────────────────

_PROFILE_MATCH_PHRASES = frozenset([
    "find me one that matches",
    "match my cv",
    "use my cv",
    "show matching jobs",
    "what can i apply for",
    "find me a match",
    "find matching jobs",
    "jobs for my profile",
    "jobs matching my cv",
    "what suits me",
    "what fits my profile",
    "use my profile",
    "based on my cv",
    "based on my profile",
    "jobs for me",
])

_APPLICATION_TRACKING_PHRASES = frozenset([
    "show my tracked applications",
    "show my applications",
    "application status",
    "applications status",
    "tracked applications",
    "my applications",
    "show applications",
    "show applied jobs",
    "applied jobs",
    "show my applied jobs",
    "show interviews",
    "interview status",
    "my interviews",
    "show offers",
    "show rejections",
    "follow up",
    "remind me to follow up",
])

_HELP_PHRASES = frozenset([
    "help", "menu", "options", "what can you do", "commands",
    "start", "get started", "what's next", "whats next", "what next",
    "what now", "show options", "show menu", "next steps",
])

_SMALLTALK_PHRASES = frozenset([
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
    "thanks", "thank you", "ok", "okay", "cool", "great", "nice",
    "bye", "goodbye", "see you", "cheers",
])

_PROFILE_SUMMARY_PHRASES = frozenset([
    "show my profile", "my profile", "profile summary",
    "what do you know about me", "my details",
])

_PROFILE_ROLE_SUGGESTIONS_PHRASES = frozenset([
    "show roles from my cv",
    "what roles fit my cv",
    "roles from my cv",
    "suggest roles from my cv",
    "best roles for my profile",
    "what jobs match my cv",
    "what roles match my profile",
    "suggest roles for me",
    "role suggestions",
    "what roles should i apply for",
])

_SKIP_PHRASES = frozenset([
    "skip this question", "don't know", "do not know", "skip",
    "not sure", "pass", "next question",
])

_FOLLOW_UP_CONFIRMATION_PHRASES = frozenset([
    "both please", "both", "all", "keep all", "keep them all", "yes keep all",
    "continue", "ok continue", "okay continue", "yes continue",
    "yes", "confirm", "confirmed", "proceed", "go ahead",
])

# ── Regex patterns ───────────────────────────────────────────────────────────

_ROLE_CHANGE_RE = re.compile(
    r"\b(what about|switch to|change to|try|how about|search for|look for|find)\s+(.+)",
    re.IGNORECASE,
)

_JOB_SEARCH_EXPLICIT_RE = re.compile(
    r"\b(find|search|show|get|look for|looking for|any|need|want)\b.{0,60}"
    r"\b(jobs?|roles?|positions?|vacancy|vacancies|openings?|work)\b",
    re.IGNORECASE,
)

_CV_UPLOAD_RE = re.compile(
    r"\b[\w .()_-]+\.(?:pdf|docx?|txt)\b"
    r"|uploaded?\s+(?:my\s+)?(?:cv|resume)"
    r"|(?:cv|resume)\s+(?:attached|uploaded|here)"
    r"|here(?:'s| is) my (?:cv|resume)",
    re.IGNORECASE,
)

_PROFILE_UPDATE_RE = re.compile(
    r"\b(update|change|set|modify|adjust)\b.{0,40}"
    r"\b(salary|city|location|preference|role|title|industry|experience|notice|email|phone)\b",
    re.IGNORECASE,
)

_APPLICATION_TRACKING_RE = re.compile(
    r"\b(tracked?|applied|application|applications|interviews?|offers?|rejected|status)\b",
    re.IGNORECASE,
)

_SAVE_JOB_RE = re.compile(
    r"\b(save|bookmark|keep|shortlist)\b.{0,30}\b(job|this|it|one|role)\b",
    re.IGNORECASE,
)

_APPLY_JOB_RE = re.compile(
    r"\b(apply|apply to|apply for|submit|send application)\b",
    re.IGNORECASE,
)

_EXPLAIN_MATCH_RE = re.compile(
    r"\b(why|explain|how come|reason)\b.{0,50}\b(recommend|match|suggest|pick|this job)\b",
    re.IGNORECASE,
)

_INTERVIEW_PREP_RE = re.compile(
    r"\b(interview|prep(?:are)?|practice|get ready)\b.{0,40}\b(interview|role|job|company|questions?)\b"
    r"|\binterview\s+(?:prep|preparation|questions|tips)\b",
    re.IGNORECASE,
)

_DRAFT_RE = re.compile(
    r"\b(draft|write|generate|create)\b.{0,40}\b(cover letter|message|email|letter)\b",
    re.IGNORECASE,
)

# ── Nonsense / safety heuristics ─────────────────────────────────────────────

_NONSENSE_RE = re.compile(
    r"^[^a-zA-Z]*$"                       # no letters at all
    r"|^(.)\1{4,}$"                        # repeated single char
    r"|^[a-z]{1,2}$"                       # single/double letter
    r"|^\d+$",                             # only digits
    re.IGNORECASE,
)

_MIN_MEANINGFUL_LENGTH = 2
_MAX_WORD_COUNT_FOR_ROLE = 6


def classify_intent(message: str, *, has_cv_profile: bool = False) -> IntentResult:
    """Classify a user message into a canonical intent.

    Args:
        message: Raw user message text.
        has_cv_profile: Whether the user has a parsed CV / populated profile.

    Returns:
        IntentResult with intent name, confidence, and source.
    """
    text = (message or "").strip()
    lower = text.lower()

    if not text or len(text) < _MIN_MEANINGFUL_LENGTH:
        return IntentResult("unknown", 0.0, "fallback")

    # ── 1. Exact-phrase fast paths (before any regex) ────────────────────
    if lower in _SMALLTALK_PHRASES:
        return IntentResult("smalltalk", 1.0, "exact")

    # ── 1b. Nonsense gate (after smalltalk check) ───────────────────────
    if _NONSENSE_RE.match(text):
        return IntentResult("nonsense", 0.95, "regex")

    # ── 2. Exact-phrase fast paths (continued) ───────────────────────────
    if lower in _PROFILE_MATCH_PHRASES:
        return IntentResult("job_search_profile_match", 1.0, "exact")

    if lower in _APPLICATION_TRACKING_PHRASES:
        return IntentResult("application_tracking", 1.0, "exact")

    if lower in _HELP_PHRASES:
        return IntentResult("help", 1.0, "exact")

    if lower in _PROFILE_SUMMARY_PHRASES:
        return IntentResult("profile_summary", 1.0, "exact")

    if lower in _PROFILE_ROLE_SUGGESTIONS_PHRASES:
        return IntentResult("profile_role_suggestions", 1.0, "exact")

    if lower in _SKIP_PHRASES:
        return IntentResult("onboarding_answer", 0.9, "exact")

    if lower in _FOLLOW_UP_CONFIRMATION_PHRASES:
        return IntentResult("follow_up_confirmation", 1.0, "exact")

    # ── 3. Regex patterns (ordered by specificity) ───────────────────────

    if _CV_UPLOAD_RE.search(text):
        return IntentResult("cv_upload_or_parse", 0.95, "regex")

    if _APPLY_JOB_RE.search(text):
        return IntentResult("apply_job", 0.95, "regex")

    if _SAVE_JOB_RE.search(text):
        return IntentResult("save_job", 0.95, "regex")

    if _EXPLAIN_MATCH_RE.search(text):
        return IntentResult("explain_match", 0.9, "regex")

    if _DRAFT_RE.search(text):
        return IntentResult("draft_message", 0.9, "regex")

    if _INTERVIEW_PREP_RE.search(text):
        return IntentResult("interview_prep", 0.9, "regex")

    if _PROFILE_UPDATE_RE.search(text):
        return IntentResult("profile_update", 0.85, "regex")

    # Application tracking regex (looser than exact phrases)
    if _APPLICATION_TRACKING_RE.search(text) and not _JOB_SEARCH_EXPLICIT_RE.search(text):
        return IntentResult("application_tracking", 0.8, "regex")

    # ── 4. Job search patterns ───────────────────────────────────────────
    # Check explicit job search FIRST (has job/role/position keyword)
    if _JOB_SEARCH_EXPLICIT_RE.search(text):
        return IntentResult("job_search_explicit", 0.85, "regex")

    # Role change — only if no explicit job-search keyword present
    role_match = _ROLE_CHANGE_RE.match(text)
    if role_match:
        extracted = role_match.group(2).strip()
        return IntentResult("role_change", 0.9, "regex", extracted_role=extracted)

    # ── 5. Profile-match inference (only if CV exists) ───────────────────
    # Generic short requests with CV profile → profile match, NOT job search
    _GENERIC_MATCH_WORDS = {"match", "matches", "matching", "suitable", "fit", "recommend"}
    if has_cv_profile and any(w in lower.split() for w in _GENERIC_MATCH_WORDS):
        return IntentResult("job_search_profile_match", 0.8, "regex")

    # ── 6. Unknown — DO NOT default to job search ────────────────────────
    return IntentResult("unknown", 0.0, "fallback")
