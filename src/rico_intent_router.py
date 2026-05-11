"""
src/rico_intent_router.py
Deterministic intent router for Rico AI.

Architecture:
  1. Regex/keyword fast-path catches high-confidence intents instantly (zero cost).
  2. HF zero-shot classification is called only when the fast-path is uncertain.
  3. Entity extraction runs deterministically after intent is confirmed.
  4. Tool name and args are resolved from the intent + entities.

Output contract (RouterResult dataclass):
  intent      -- one of SUPPORTED_INTENTS
  tool_name   -- registered tool name or None for non-tool intents
  tool_args   -- dict ready to pass to agent_runtime / tool
  entities    -- extracted structured data from the message
  confidence  -- 0.0-1.0
  source      -- "keyword" | "hf" | "fallback"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Supported intents ─────────────────────────────────────────────────────────

SUPPORTED_INTENTS = {
    "search_jobs",
    "save_job",
    "skip_job",
    "apply_job",
    "draft_message",
    "explain_match",
    "update_preferences",
    "prepare_interview",
    "set_reminder",
    "help",
    "unknown",
}

# Map intent -> tool name in the registry (None = no direct tool execution)
INTENT_TO_TOOL: Dict[str, Optional[str]] = {
    "search_jobs":        "search_jobs",
    "save_job":           "save_job",
    "skip_job":           "skip_job",
    "apply_job":          "apply_job",
    "draft_message":      "draft_message",
    "explain_match":      "explain_match",
    "update_preferences": None,
    "prepare_interview":  None,
    "set_reminder":       "set_reminder",
    "help":               None,
    "unknown":            None,
}

# apply_job always requires explicit user confirmation before execution
APPROVAL_REQUIRED = frozenset({"apply_job"})


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class RouterResult:
    intent: str
    tool_name: Optional[str]
    tool_args: Dict[str, Any]
    entities: Dict[str, Any]
    confidence: float
    source: str
    requires_confirmation: bool = False
    confirmation_prompt: str = ""


# ── Keyword patterns (fast-path) ──────────────────────────────────────────────

_SEARCH_PATTERNS = re.compile(
    r"\b(find|search|show|get|look for|looking for|any)\b.{0,60}\b(jobs?|roles?|position|vacancy|opening|work)\b"
    r"|\b(jobs?|roles?|position|vacancy|opening)\b.{0,40}\b(in|at|near|for|available)\b"
    r"|\b(jobs?|roles?)\s+(in|at|near|for)\b",
    re.IGNORECASE,
)
_SAVE_PATTERNS = re.compile(
    r"\b(save|bookmark|keep|shortlist|hold on to)\b.{0,30}\b(job|this|it|one|role|position)\b"
    r"|\bsave (the )?(first|second|third|last|this|that)\b",
    re.IGNORECASE,
)
_SKIP_PATTERNS = re.compile(
    r"\b(skip|ignore|not interested|not relevant|pass|dismiss|next)\b.{0,30}"
    r"\b(job|this|it|one|role|that|these)\b"
    r"|\bskip (the )?(first|second|third|last|this|that)\b",
    re.IGNORECASE,
)
_APPLY_PATTERNS = re.compile(
    r"\b(apply|apply to|apply for|submit|send application)\b.{0,40}"
    r"\b(job|this|it|one|role|position|that)\b"
    r"|\b(apply to this|apply for this|apply now|i want to apply|i would like to apply|i'd like to apply)\b",
    re.IGNORECASE,
)
_DRAFT_PATTERNS = re.compile(
    r"\b(draft|write|generate|create|prepare)\b.{0,40}"
    r"\b(cover letter|message|email|application letter|intro|introduction)\b",
    re.IGNORECASE,
)
_EXPLAIN_PATTERNS = re.compile(
    r"\b(why|explain|how come|reason|tell me why|what makes)\b.{0,50}"
    r"\b(recommend|pick|chose|match|suggested|selected|this job|this role)\b"
    r"|\b(why (did )?rico|why this job|why this role)\b",
    re.IGNORECASE,
)
_PREFS_PATTERNS = re.compile(
    r"\b(update|change|set|modify|adjust)\b.{0,40}"
    r"\b(salary|city|location|preference|role|title|industry|experience|notice)\b"
    r"|\b(i (want|prefer|need|am looking for)|my (preference|target|goal) is)\b",
    re.IGNORECASE,
)
_INTERVIEW_PATTERNS = re.compile(
    r"\b(interview|prepare|prep|practice|get ready|questions|what (to|should) (expect|say|answer))\b"
    r".{0,40}\b(interview|role|job|position|company)\b"
    r"|\binterview (prep|preparation|questions|tips)\b",
    re.IGNORECASE,
)
_REMIND_PATTERNS = re.compile(
    r"\b(remind|reminder|follow.?up|follow up|check back|ping me)\b",
    re.IGNORECASE,
)
_HELP_PATTERNS = re.compile(
    r"^\s*(help|menu|options|what can you do|commands|start|get started)\s*[?!.]?\s*$",
    re.IGNORECASE,
)


# ── Entity extraction (deterministic regex) ───────────────────────────────────

_CITY_RE = re.compile(
    r"\b(dubai|abu dhabi|sharjah|ajman|ras al khaimah|fujairah|umm al quwain"
    r"|riyadh|jeddah|doha|kuwait|manama|muscat|cairo|london|berlin|chicago|new york)\b",
    re.IGNORECASE,
)
_SALARY_RE = re.compile(
    r"\b(\d[\d,]*)\s*(aed|usd|gbp|eur|k|thousand)?\b.{0,20}(salary|per month|monthly|a month|pm)\b"
    r"|\b(above|over|minimum|at least|more than)\s+(\d[\d,]*)\s*(aed|k)?\b",
    re.IGNORECASE,
)
_EXPERIENCE_RE = re.compile(
    r"\b(\d+)\+?\s*(years?|yrs?)\b.{0,20}(experience|exp)\b"
    r"|\b(experience|exp)\b.{0,20}\b(\d+)\+?\s*(years?|yrs?)\b",
    re.IGNORECASE,
)
_INDUSTRY_RE = re.compile(
    r"\b(hse|ehs|qhse|esg|sustainability|environment(al)?|oil.?(and|&).?gas|construction"
    r"|banking|finance|fintech|tech(nology)?|healthcare|hospitality|retail|logistics|real estate)\b",
    re.IGNORECASE,
)
_ORDINAL_REF_RE = re.compile(
    r"\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|last|this one|that one)\b",
    re.IGNORECASE,
)
_ORDINAL_MAP = {
    "first": 0, "1st": 0,
    "second": 1, "2nd": 1,
    "third": 2, "3rd": 2,
    "fourth": 3, "4th": 3,
    "fifth": 4, "5th": 4,
}

# Common UAE job title keywords for extraction
_TITLE_PHRASES = [
    "hse manager", "qhse manager", "ehs manager", "esg manager",
    "sustainability manager", "environmental manager", "safety manager",
    "compliance manager", "operations manager", "project manager",
    "software engineer", "developer", "data engineer", "data scientist",
    "marketing manager", "finance manager", "hr manager", "sales manager",
]


def _extract_entities(message: str) -> Dict[str, Any]:
    """Extract structured entities from a user message deterministically."""
    lower = message.lower()
    entities: Dict[str, Any] = {}

    city_match = _CITY_RE.search(message)
    if city_match:
        entities["city"] = city_match.group(0).title()

    salary_match = _SALARY_RE.search(message)
    if salary_match:
        entities["salary_raw"] = salary_match.group(0)

    exp_match = _EXPERIENCE_RE.search(message)
    if exp_match:
        num = exp_match.group(1) or exp_match.group(5)
        if num:
            entities["years_experience"] = int(num)

    industry_match = _INDUSTRY_RE.search(message)
    if industry_match:
        entities["industry"] = industry_match.group(0).lower()

    for phrase in _TITLE_PHRASES:
        if phrase in lower:
            entities["job_title"] = phrase.title()
            break

    ordinal_match = _ORDINAL_REF_RE.search(lower)
    if ordinal_match:
        token = ordinal_match.group(1).lower()
        entities["job_reference"] = token
        entities["job_index"] = _ORDINAL_MAP.get(token)

    return entities


# ── Fast-path keyword classifier ──────────────────────────────────────────────

def _keyword_classify(message: str) -> Tuple[Optional[str], float]:
    """
    Run regex patterns to classify intent.

    Returns (intent, confidence) or (None, 0.0) if no pattern matches.
    Ordered from most-specific to least-specific.
    """
    if _HELP_PATTERNS.match(message):
        return "help", 1.0
    if _APPLY_PATTERNS.search(message):
        return "apply_job", 0.95
    if _SAVE_PATTERNS.search(message):
        return "save_job", 0.95
    if _SKIP_PATTERNS.search(message):
        return "skip_job", 0.95
    if _DRAFT_PATTERNS.search(message):
        return "draft_message", 0.90
    if _EXPLAIN_PATTERNS.search(message):
        return "explain_match", 0.90
    if _REMIND_PATTERNS.search(message):
        return "set_reminder", 0.90
    if _INTERVIEW_PATTERNS.search(message):
        return "prepare_interview", 0.90
    if _PREFS_PATTERNS.search(message):
        return "update_preferences", 0.85
    if _SEARCH_PATTERNS.search(message):
        return "search_jobs", 0.85
    return None, 0.0


# ── HF classification fallback ────────────────────────────────────────────────

_HF_LABELS = [
    "search for jobs",
    "save a job",
    "skip or ignore a job",
    "apply for a job",
    "write a cover letter or draft a message",
    "explain why a job was recommended",
    "update job preferences or salary",
    "prepare for an interview",
    "set a reminder",
    "help or menu",
]

_HF_LABEL_TO_INTENT = {
    "search for jobs":                          "search_jobs",
    "save a job":                               "save_job",
    "skip or ignore a job":                     "skip_job",
    "apply for a job":                          "apply_job",
    "write a cover letter or draft a message":  "draft_message",
    "explain why a job was recommended":        "explain_match",
    "update job preferences or salary":         "update_preferences",
    "prepare for an interview":                 "prepare_interview",
    "set a reminder":                           "set_reminder",
    "help or menu":                             "help",
}

_HF_CONFIDENCE_THRESHOLD = 0.45


def _hf_classify(message: str) -> Tuple[str, float]:
    """
    Use HF zero-shot classification to determine intent.

    Returns (intent, confidence). Falls back to 'unknown' if HF is unavailable
    or confidence is below threshold.
    """
    try:
        from src.rico_hf_client import classify_intent
        result = classify_intent(message, _HF_LABELS)
        if result and result["top_score"] >= _HF_CONFIDENCE_THRESHOLD:
            intent = _HF_LABEL_TO_INTENT.get(result["top_label"], "unknown")
            return intent, result["top_score"]
    except Exception as exc:
        logger.debug("hf_classify_error: %s", exc)
    return "unknown", 0.0


# ── Tool args builder ─────────────────────────────────────────────────────────

def _build_tool_args(
    intent: str,
    entities: Dict[str, Any],
    context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build the tool_args dict from intent + entities + context.

    For job-reference intents (save/skip/apply), resolve job_key from context
    when an ordinal reference like 'first one' is used.
    """
    args: Dict[str, Any] = {}

    if intent == "search_jobs":
        query_parts = []
        if entities.get("job_title"):
            query_parts.append(entities["job_title"])
        if entities.get("industry"):
            query_parts.append(entities["industry"])
        if entities.get("city"):
            query_parts.append(entities["city"])
        args["query"] = " ".join(query_parts) if query_parts else ""
        if entities.get("city"):
            args["city"] = entities["city"]
        if entities.get("years_experience"):
            args["min_experience"] = entities["years_experience"]
        if entities.get("salary_raw"):
            args["salary_hint"] = entities["salary_raw"]

    elif intent in {"save_job", "skip_job", "apply_job", "draft_message",
                    "explain_match", "set_reminder"}:
        job_key = _resolve_job_key(entities, context)
        if job_key:
            args["job_key"] = job_key
        if intent == "apply_job":
            args["user_has_approved"] = False

    elif intent == "update_preferences":
        prefs: Dict[str, Any] = {}
        if entities.get("city"):
            prefs["preferred_city"] = entities["city"]
        if entities.get("salary_raw"):
            prefs["salary_hint"] = entities["salary_raw"]
        if entities.get("job_title"):
            prefs["target_role"] = entities["job_title"]
        args["preferences"] = prefs

    return args


def _resolve_job_key(
    entities: Dict[str, Any],
    context: Optional[Dict[str, Any]],
) -> Optional[str]:
    """
    Resolve job_key from context.

    If user said 'the first one', look up index 0 in context['recent_jobs'].
    If context has 'last_job_key', use that.
    """
    if not context:
        return None

    idx = entities.get("job_index")
    recent = context.get("recent_jobs", [])
    if idx is not None and isinstance(recent, list) and len(recent) > idx:
        job = recent[idx]
        if isinstance(job, dict):
            return job.get("job_key") or job.get("id") or job.get("link")

    return context.get("last_job_key")


# ── Confirmation prompt ───────────────────────────────────────────────────────

def _confirmation_prompt(intent: str, entities: Dict[str, Any], args: Dict[str, Any]) -> str:
    if intent == "apply_job":
        job_key = args.get("job_key", "this job")
        return (
            "To confirm: you want Rico to mark this job as applied and track it. "
            "Reply YES to confirm or CANCEL to abort."
        )
    return ""


# ── Public router ─────────────────────────────────────────────────────────────

def route(
    message: str,
    user_id: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> RouterResult:
    """
    Route a user message to an intent + tool.

    Steps:
      1. Keyword fast-path (free, instant).
      2. HF zero-shot classification if keyword confidence is low.
      3. Entity extraction (always deterministic).
      4. Tool args construction.
      5. Confirmation gate for apply_job.

    Never raises.
    """
    message = (message or "").strip()
    if not message:
        return RouterResult(
            intent="unknown", tool_name=None, tool_args={},
            entities={}, confidence=0.0, source="fallback",
        )

    intent, confidence = _keyword_classify(message)
    source = "keyword"

    if intent is None or confidence < 0.80:
        hf_intent, hf_conf = _hf_classify(message)
        if hf_conf > confidence:
            intent = hf_intent
            confidence = hf_conf
            source = "hf"

    if not intent or intent not in SUPPORTED_INTENTS:
        intent = "unknown"
        source = "fallback"

    entities = _extract_entities(message)
    tool_name = INTENT_TO_TOOL.get(intent)
    tool_args = _build_tool_args(intent, entities, context)

    requires_confirmation = intent in APPROVAL_REQUIRED
    confirm_prompt = _confirmation_prompt(intent, entities, tool_args) if requires_confirmation else ""

    logger.info(
        "intent_routed user=%r intent=%s tool=%s confidence=%.2f source=%s entities=%s",
        user_id, intent, tool_name, confidence, source, list(entities.keys()),
    )

    return RouterResult(
        intent=intent,
        tool_name=tool_name,
        tool_args=tool_args,
        entities=entities,
        confidence=confidence,
        source=source,
        requires_confirmation=requires_confirmation,
        confirmation_prompt=confirm_prompt,
    )
