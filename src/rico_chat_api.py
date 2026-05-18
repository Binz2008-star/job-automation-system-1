"""Rico conversational AI API.

This module transforms the existing automation system into a chat-first
career agent. Rico accepts natural language messages, updates memory,
triggers workflows, and responds with autonomous actions.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, NamedTuple

# Standard library imports first
# Third-party imports (none currently)
# Local imports
from src.agent.intelligence.intent_classifier import classify_intent
from src.agent.intelligence.normalizer import normalize_role
from src.agent.intelligence.recommender import recommend_adjacent_roles
from src.agent.intelligence.role_classifier import classify_role_candidate
from src.agent.intelligence.scorer import score_profile_fit
from src.agent.responses.schema import RicoResponse, build_error_response, _generate_debug_id
from src.agent.runtime import agent_runtime
from src.models.onboarding import ONBOARDING_IN_PROGRESS
from src.rico_agent import RicoAgent
from src.rico_hf_client import generate_text, is_available as hf_ok
from src.rico_intent_router import route as _route
from src.rico_match_explainer import build_match_explanation
from src.rico_memory import RicoMemoryStore
from src.rico_openai_agent import RicoOpenAIAgent
from src.rico_repo_adapter import RicoSystem
from src.repositories.onboarding_repo import (
    is_onboarding_complete,
    mark_onboarding_complete,
    set_onboarding_status,
)
from src.repositories.profile_repo import get_profile, upsert_profile
from src.services.profile_context_resolver import resolve_profile_context

logger = logging.getLogger(__name__)

# Constants
CV_FILE_RE = re.compile(r"\b[\w .()_-]+\.(?:pdf|docx?|txt)\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
FOLLOWUP_BOUNDARY_PUNCT_RE = re.compile(r"^[\s\"'([{]+|[\s\"')\]}.,!?;:]+$")

# Domain-agnostic. A bare role is a short noun phrase. Anything starting with
# one of these tokens is a question, command, greeting, or sentence - never
# a role title.
_NON_ROLE_STARTERS: frozenset[str] = frozenset({
    "what", "whats", "what's", "how", "hows", "how's", "why", "when",
    "where", "who", "whom", "whose", "which",
    "is", "are", "am", "was", "were", "be", "been", "being",
    "do", "does", "did", "doing", "done",
    "have", "has", "had", "having",
    "will", "would", "shall", "should", "can", "could",
    "may", "might", "must", "ought",
    "tell", "show", "give", "find", "search", "get", "fetch", "list",
    "explain", "describe", "compare", "help", "please",
    "want", "need", "looking",
    "hi", "hello", "hey", "greetings", "thanks", "thank", "ok", "okay",
    "yes", "yeah", "yep", "no", "nope", "sure", "fine", "good", "great",
    "cool", "nice", "wow", "oh", "ah",
    "i", "im", "i'm", "me", "my", "mine", "myself",
    "we", "our", "ours", "us",
    "the", "a", "an", "this", "that", "these", "those",
    "some", "any", "every", "all", "none", "each", "many", "few",
    "and", "but", "or", "so", "if", "because", "though", "while", "as",
})
_QUESTION_CHARS: frozenset[str] = frozenset("?？!！;:")
_MAX_ROLE_WORDS: int = 6
_MIN_TOKEN_ALPHA: int = 2

def generate_error_ref() -> str:
    """Generate a unique error reference ID for tracking and support lookup."""
    return f"ERR-{uuid.uuid4().hex[:8].upper()}"

ONBOARDING_FIELD_LABELS = {
    "email": "email address",
    "phone": "phone number",
    "preferred_city": "preferred UAE city",
    "target_roles": "target role",
    "salary_expectation_aed": "salary expectation",
    "deal_breakers": "roles or companies to avoid",
}

# OpenAI context limits
MAX_CONTEXT_MESSAGES = 10
MAX_PROFILE_TOKENS = 200  # Conservative estimate for profile summary


class HandlerResult(NamedTuple):
    """Result type for handler functions."""
    response: dict[str, Any]
    should_save: bool = True


def profile_to_dict(profile: Any) -> dict[str, Any]:
    """Normalize profile to dict, handling dataclass, dict, and object types."""
    if profile is None:
        return {}
    if is_dataclass(profile):
        return {k: v for k, v in asdict(profile).items() if v not in (None, "", [], {})}
    if isinstance(profile, dict):
        return {k: v for k, v in profile.items() if v not in (None, "", [], {})}
    return {
        k: getattr(profile, k)
        for k in dir(profile)
        if not k.startswith("_") and getattr(profile, k, None) not in (None, "", [], {})
    }


class RicoChatAPI:
    """Simple conversational controller for Rico AI."""

    # Deterministic follow-up phrases (must be checked before role classification)
    _FOLLOWUP_BOTH_ACTION_PHRASES = frozenset({
        "both",
        "both please",
        "do both",
        "yes both",
    })

    _FOLLOWUP_KEEP_ALL_PHRASES = frozenset({
        "keep all",
        "keep them all",
        "yes keep all",
        "keep everything",
    })

    def __init__(self) -> None:
        self.memory = RicoMemoryStore()
        self.agent = RicoAgent(profile_store=self.memory)
        self.system = RicoSystem()
        self.openai_agent = RicoOpenAIAgent()

    def _append_chat(self, user_id: str, role: str, message: str | dict[str, Any]) -> None:
        """Append chat message to memory (sync) and DB (async fire-and-forget).

        Memory write is synchronous so subsequent reads see the message immediately.
        DB write is dispatched to a background thread to avoid blocking the request
        path on remote PostgreSQL latency (~1s round-trip on Neon).
        """
        payload = json.dumps(message) if isinstance(message, dict) else message
        self.memory.append_chat_message(user_id, role, payload)
        # Async DB persistence — non-blocking
        import threading
        from src.services.chat_service import db_append_chat
        threading.Thread(
            target=db_append_chat,
            args=(user_id, role, payload),
            daemon=True,
        ).start()

    @staticmethod
    def _build_openai_context(profile: Any) -> dict[str, Any]:
        """Build context for OpenAI agent from profile."""
        if profile is None:
            return {"profile_exists": False}
        if is_dataclass(profile):
            raw = asdict(profile)
        elif isinstance(profile, dict):
            raw = dict(profile)
        else:
            raw = {k: getattr(profile, k) for k in dir(profile) if not k.startswith("_")}

        # Optimize profile to avoid large dumps - only include essential fields
        essential_fields = {
            "email", "phone", "skills", "years_experience",
            "preferred_cities", "target_roles", "industries",
            "salary_expectation_aed", "deal_breakers"
        }

        return {
            "profile_exists": True,
            **{k: v for k, v in raw.items() if k in essential_fields and v not in (None, "", [], {})},
        }

    @staticmethod
    def _profile_value(profile: Any, key: str, default: Any = None) -> Any:
        """Get value from profile, handling dict and object types."""
        if profile is None:
            return default
        if isinstance(profile, dict):
            return profile.get(key, default)
        return getattr(profile, key, default)

    @staticmethod
    def _has_cv_profile(profile: Any) -> bool:
        """Check if profile has CV data."""
        if profile is None:
            return False
        return bool(
            RicoChatAPI._profile_value(profile, "cv_filename")
            or RicoChatAPI._profile_value(profile, "cv_status")
            or RicoChatAPI._profile_value(profile, "skills")
            or RicoChatAPI._profile_value(profile, "years_experience")
        )

    @staticmethod
    def _looks_like_bare_target_role(message: str) -> bool:
        """Accept only short noun-phrase job titles, not questions or commands."""
        text = (message or "").strip()
        if not text:
            return False
        if any(ch in _QUESTION_CHARS for ch in text):
            return False
        if ". " in text or text.endswith("..."):
            return False
        if any(ch.isdigit() for ch in text):
            return False

        tokens = text.split()
        if not tokens or len(tokens) > _MAX_ROLE_WORDS:
            return False

        first = tokens[0].lower().strip(".,/&+-()")
        if first in _NON_ROLE_STARTERS:
            return False
        if not any(
            sum(1 for ch in tok if ch.isalpha()) >= _MIN_TOKEN_ALPHA
            for tok in tokens
        ):
            return False

        if text.lower() in RicoChatAPI._WHATS_NEXT_PHRASES:
            return False
        return True

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        """Convert value to list if not already."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    @staticmethod
    def normalize_role_label(text: str) -> str:
        """Title-case role text while preserving known acronyms."""
        if not text:
            return text
        acronyms = {"HSE", "QHSE", "EHS", "ESG", "UAE", "ISO", "CV", "NEBOSH"}
        words = text.split()
        result = []
        for w in words:
            upper = w.upper()
            if upper in acronyms:
                result.append(upper)
            else:
                result.append(w.capitalize())
        return " ".join(result)

    # ── Live / generic job search detection ────────────────────────────────

    _LIVE_SEARCH_RE = re.compile(
        # live/current near jobs/roles/openings (both word orders)
        r"\b(live|current)\b.{0,40}\b(jobs?|roles?|openings?)\b"
        r"|\b(jobs?|roles?|openings?)\b.{0,40}\b(live|current)\b"
        # "uae jobs/roles" only when a role word follows (>=3 chars after whitespace)
        r"|\buae\s+(?:jobs?|roles?|openings?)\s+(?:for\s+)?\w{3}"
        r"|\b(?:jobs?|roles?|openings?)\s+(?:for\s+)?\w{3}.{0,40}\buae\b"
        # find openings (bare -- strong enough signal on its own)
        r"|\bfind\b.{0,20}\bopenings?\b"
        # show current openings (explicit)
        r"|\bshow\b.{0,20}\bcurrent\b.{0,20}\bopenings?\b",
        re.IGNORECASE,
    )

    _GENERIC_JOB_REQUEST_RE = re.compile(
        r"^\s*(?:i\s+(?:am|m)\s+|am\s+)?(?:looking\s+for|find|show|get|need|want)\s+(?:a\s+)?(?:job|jobs|work|role|roles)\s*$"
        r"|^\s*(?:i\s+)?(?:need|want)\s+(?:a\s+)?(?:job|jobs|work|role|roles)\s*$"
        r"|^\s*(?:find|show|get)\s+(?:me\s+)?(?:a\s+)?(?:job|jobs|role|roles)\s*$"
        r"|^\s*(?:show|find|get)\s+me\s+jobs?\s*$"
        r"|^\s*jobs?\s+(?:for\s+me|please)\s*$",
        re.IGNORECASE,
    )

    @staticmethod
    def _is_live_job_search_request(message: str) -> bool:
        """True when user explicitly asks for live/current/UAE/openings jobs."""
        return bool(RicoChatAPI._LIVE_SEARCH_RE.search(message))

    @staticmethod
    def _looks_like_generic_job_request(message: str) -> bool:
        """True for generic job-search phrases without a specific role."""
        return bool(RicoChatAPI._GENERIC_JOB_REQUEST_RE.search(message))

    @staticmethod
    def _looks_like_next_step_followup(message: str) -> bool:
        """True for short post-confirmation follow-ups like 'so?' or 'what now?'."""
        text = RicoChatAPI._normalize_followup_phrase(message)
        return text in RicoChatAPI._FOLLOWUP_NEXT_STEP_PHRASES

    @staticmethod
    def _normalize_followup_phrase(message: str) -> str:
        """Normalize short follow-up text so punctuation does not break fast paths."""
        text = re.sub(r"\s+", " ", (message or "").strip().lower())
        return FOLLOWUP_BOUNDARY_PUNCT_RE.sub("", text)

    def _handle_next_step_options(self, user_id: str, profile: Any) -> dict[str, Any]:
        """Return instant options after role confirmation — no AI, no pipeline."""
        target_roles = self._as_list(self._profile_value(profile, "target_roles"))
        suggestions = self._generate_role_suggestions(
            self._as_list(self._profile_value(profile, "skills")),
            self._as_list(self._profile_value(profile, "certifications")),
            self._profile_value(profile, "years_experience"),
            self._as_list(self._profile_value(profile, "industries")),
        )
        # Prefer fresh CV-derived suggestions over potentially stale target_roles
        role = (
            suggestions[0]["label"] if suggestions
            else target_roles[0] if target_roles
            else "your target role"
        )

        response: dict[str, Any] = {
            "type": "options",
            "message": "Next, choose what you want me to do.",
            "options": [
                {
                    "action": "find_live_jobs",
                    "label": "Find live UAE jobs",
                    "message": f"find live jobs for {role}",
                    "role": role,
                },
                {
                    "action": "save_target_role",
                    "label": "Save as target role",
                    "message": f"save {role} as target role",
                    "role": role,
                },
                {
                    "action": "prepare_application_angle",
                    "label": "Prepare application angle",
                    "message": f"prepare application angle for {role}",
                    "role": role,
                },
                {
                    "action": "show_profile_roles",
                    "label": "Show roles from my CV",
                    "message": "show roles from my CV",
                },
            ],
            "next_action": "choose_next_step",
        }
        self._append_chat(user_id, "assistant", response["message"])
        return response

    def _handle_keep_all_target_roles(self, user_id: str, profile: Any) -> dict[str, Any]:
        """Handle 'keep all' follow-up - confirm keeping all target roles."""
        target_roles = self._as_list(self._profile_value(profile, "target_roles"))
        role_text = ", ".join(map(str, target_roles)) if target_roles else "your current target roles"

        response = {
            "type": "target_roles_confirmed",
            "message": f"Got it — I will keep all current target roles: {role_text}.",
            "target_roles": target_roles,
            "next_actions": [
                {"action": "find_live_jobs", "label": "Find live UAE jobs", "message": "find live jobs for my target roles"},
                {"action": "prepare_application_angle", "label": "Prepare application angle", "message": "prepare application angle for my target roles"},
                {"action": "show_profile_roles", "label": "Show roles from my CV", "message": "show roles from my CV"},
            ],
            "next_action": "choose_next_step",
        }
        self._append_chat(user_id, "assistant", response["message"])
        return response

    def _handle_both_requested_actions(self, user_id: str, profile: Any) -> dict[str, Any]:
        """Handle 'both please' follow-up - trigger both job search and resume review."""
        target_roles = self._as_list(self._profile_value(profile, "target_roles"))
        role = target_roles[-1] if target_roles else "your target role"

        response = {
            "type": "combined_action_plan",
            "message": (
                f"Got it — I will do both: start with live UAE job matching for {role}, "
                "then prepare your resume/application angle for the strongest matches."
            ),
            "next_actions": [
                {"action": "find_live_jobs", "label": "Find live UAE jobs", "message": f"find live jobs for {role}"},
                {"action": "prepare_application_angle", "label": "Prepare application angle", "message": f"prepare application angle for {role}"},
            ],
            "next_action": "find_live_jobs_then_prepare_application",
        }
        self._append_chat(user_id, "assistant", response["message"])
        return response

    def _looks_like_selected_role(self, message: str, profile: Any) -> bool:
        """True when the message looks like a user selecting a suggested role.

        Guards (checked in order, fail-fast):
          1. Non-empty, not live search, not generic job request
          2. No question mark
          3. No action verbs (find/search/show/...)
          4. Short phrase -- _looks_like_bare_target_role
          5. Exact or fuzzy match: generated suggestions + target_roles
          6. Fallback: classify_role_candidate says profile_relevant or known_but_off_profile
        """
        if not message or not profile:
            return False

        text       = message.strip()
        text_lower = text.lower()

        if self._is_live_job_search_request(text_lower):
            return False
        if self._looks_like_generic_job_request(text_lower):
            return False
        if "?" in text:
            return False
        if set(text_lower.split()) & self._ACTION_WORDS:
            return False
        if not self._looks_like_bare_target_role(text):
            return False

        # Build known-role set: generated suggestions + saved target_roles
        suggested = self._generate_role_suggestions(
            self._as_list(self._profile_value(profile, "skills")),
            self._as_list(self._profile_value(profile, "certifications")),
            self._profile_value(profile, "years_experience"),
            self._as_list(self._profile_value(profile, "industries")),
        )
        known: set[str] = {s["label"].lower() for s in suggested}
        target_roles = self._as_list(self._profile_value(profile, "target_roles"))
        known.update(r.lower() for r in target_roles if isinstance(r, str))

        if text_lower in known:
            return True
        for k in known:
            if k in text_lower or text_lower in k:
                return True

        # Classifier fallback - only profile_relevant roles get fast-path confirmation
        # known_but_off_profile roles should go through _classified_role_search for clarification
        try:
            classification, canonical_role = classify_role_candidate(text, profile)
            if classification == "profile_relevant" and canonical_role:
                return True
        except Exception:
            pass

        return False

    def _extract_selected_role(self, message: str, profile: Any) -> str:
        """Extract the best-matched role label, preserving acronym casing."""
        text       = (message or "").strip()
        text_lower = text.lower()

        suggested = self._generate_role_suggestions(
            self._as_list(self._profile_value(profile, "skills")),
            self._as_list(self._profile_value(profile, "certifications")),
            self._profile_value(profile, "years_experience"),
            self._as_list(self._profile_value(profile, "industries")),
        )
        # Exact match in suggestions
        for s in suggested:
            if s["label"].lower() == text_lower:
                return s["label"]

        # Exact match in target_roles
        target_roles = self._as_list(self._profile_value(profile, "target_roles"))
        for r in target_roles:
            if isinstance(r, str) and r.lower() == text_lower:
                return r

        # Fuzzy: suggestion label contained in message
        for s in suggested:
            if s["label"].lower() in text_lower:
                return s["label"]

        # Fuzzy: saved role contained in message
        for r in target_roles:
            if isinstance(r, str) and r.lower() in text_lower:
                return r

        # Classifier canonical name
        try:
            _, canonical_role = classify_role_candidate(text, profile)
            if canonical_role:
                return canonical_role
        except Exception:
            pass

        return self.normalize_role_label(text)

    def _handle_role_confirmation(
        self, user_id: str, role: str, profile: Any
    ) -> dict[str, Any]:
        """Deterministic role_confirmation -- no AI, no external calls."""
        skills = self._as_list(self._profile_value(profile, "skills"))
        years  = self._profile_value(profile, "years_experience")
        certs  = self._as_list(self._profile_value(profile, "certifications"))

        skill_lower = [s.lower() for s in skills]
        cert_lower  = [c.lower() for c in certs]
        all_lower   = skill_lower + cert_lower

        # Safe numeric parsing
        try:
            years_num = float(years)
        except (TypeError, ValueError):
            years_num = None

        reasons: list[str] = []

        if any(k in s for s in all_lower for k in ("iso", "audit", "compliance")):
            reasons.append("You have ISO, audit, or compliance background.")

        if any(k in c for c in cert_lower for k in ("nebosh", "iosh")):
            reasons.append("Your safety certifications support this role.")

        if any(k in s for s in all_lower for k in ("environmental", "esg", "sustainability")):
            reasons.append("Your background aligns with environmental and sustainability work.")

        if any("hse" in s or "safety" in s for s in skill_lower):
            reasons.append("Your HSE/safety background matches this role.")

        if years_num is not None:
            if years_num >= 10:
                reasons.append("Your experience level supports senior roles.")
            elif years_num >= 5:
                reasons.append("Your experience level supports experienced professional roles.")
            else:
                reasons.append(f"Your ~{int(years_num)} years of experience fits this role.")

        if not reasons:
            reasons.append("This role aligns with your profile.")

        response = {
            "type": "role_confirmation",
            "message": f"{role} is a strong fit for your CV.",
            "role": role,
            "reasons": reasons,
            "next_actions": [
                {
                    "action":  "find_live_jobs",
                    "label":   "Find live UAE jobs",
                    "message": f"find live jobs for {role}",
                    "role":    role,
                },
                {
                    "action":  "save_target_role",
                    "label":   "Save as target role",
                    "message": f"save {role} as target role",
                    "role":    role,
                },
                {
                    "action":  "prepare_application_angle",
                    "label":   "Prepare application angle",
                    "message": f"prepare application angle for {role}",
                    "role":    role,
                },
            ],
            "next_action": "choose_role_next_step",
        }
        self._append_chat(user_id, "assistant", response["message"])
        return response

    @staticmethod
    def _format_match(m: dict[str, Any], profile: Any) -> dict[str, Any]:
        """Return a backward-compatible chat match with v1 structured guidance."""
        explanation = build_match_explanation(m, profile)
        # Normalize score to 0-100 range for display
        raw_score = m.get("rico_score") or m.get("score") or 0
        normalized_score = max(0, min(100, int(raw_score))) if raw_score else 0
        return {
            "title": m.get("title"),
            "company": m.get("company"),
            "location": m.get("location"),
            "score": normalized_score,
            "why": m.get("rico_explanation"),
            "actions": ["Prepare application", "Save", "Ask why", "Skip"],
            **explanation,
        }

    def _get_openai_agent(self) -> RicoOpenAIAgent:
        """Get or create OpenAI agent instance."""
        agent = getattr(self, "openai_agent", None)
        if agent is None:
            agent = RicoOpenAIAgent()
            self.openai_agent = agent
        return agent

    SOURCE_KEYWORD = "keyword"
    SOURCE_OPENAI = "openai"
    SOURCE_DEEPSEEK = "deepseek"
    SOURCE_HF = "huggingface"
    SOURCE_FALLBACK = "fallback"
    SOURCE_RATE_LIMITED = "rate_limited"

    @staticmethod
    def _source_for_openai_response(response: dict[str, Any]) -> str:
        """Determine source type from response metadata."""
        rtype = response.get("type")
        if rtype == "openai_response":
            return RicoChatAPI.SOURCE_OPENAI
        if rtype == "deepseek_response":
            return RicoChatAPI.SOURCE_DEEPSEEK
        if rtype == "hf_response":
            return RicoChatAPI.SOURCE_HF
        if (
            rtype in {"openai_rate_limited", "deepseek_rate_limited"}
            or response.get("provider_state") == "rate_limited"
        ):
            return RicoChatAPI.SOURCE_RATE_LIMITED
        return RicoChatAPI.SOURCE_FALLBACK

    @staticmethod
    def _bool_attr(agent: Any, name: str, *, fallback: str | None = None) -> bool:
        """Get boolean attribute from agent with optional fallback."""
        value = getattr(agent, name, None)
        if isinstance(value, bool):
            return value
        if fallback:
            fallback_value = getattr(agent, fallback, None)
            if isinstance(fallback_value, bool):
                return fallback_value
        return False

    def _finalize(
        self,
        response: dict[str, Any],
        source: str,
        *,
        profile: Any = None,
    ) -> dict[str, Any]:
        """Finalize response with metadata."""
        agent = self._get_openai_agent()

        # Get Jotform form IDs from environment
        jotform_form_id = os.getenv("JOTFORM_FORM_ID") or os.getenv("JOTFORM_RICO_FORM_ID")

        # Provider diagnostics are only logged internally, not exposed to users
        # Admin diagnostics available at /health/ai-provider endpoint
        return {
            **response,
            "response_source": response.get("response_source", source),
            "openai_available": self._bool_attr(agent, "openai_available", fallback="available"),
            "deepseek_available": self._bool_attr(agent, "deepseek_available"),
            "hf_available": self._bool_attr(agent, "hf_available"),
            "provider_available": self._bool_attr(agent, "provider_available", fallback="available"),
            "openai_model": str(getattr(agent, "model", "") or ""),
            "profile_context_present": profile is not None,
            "jotform_form_id": jotform_form_id,
        }

    def _looks_like_cv_upload(self, message: str) -> bool:
        lower = message.lower()
        return bool(CV_FILE_RE.search(message)) or any(
            phrase in lower
            for phrase in [
                "uploaded cv",
                "upload cv",
                "uploaded resume",
                "upload resume",
                "my cv",
                "my resume",
                "resume attached",
                "cv attached",
            ]
        )

    def _extract_inline_contact_updates(self, message: str) -> dict[str, Any]:
        """Extract email and phone from message."""
        updates: dict[str, Any] = {}
        emails = EMAIL_RE.findall(message)
        phones = PHONE_RE.findall(message)
        if emails:
            updates["email"] = emails[0]
        if phones:
            updates["phone"] = phones[0].strip()
        return updates

    def _cv_first_profile_response(self, user_id: str, message: str) -> dict[str, Any]:
        """Handle CV-first profile creation response."""
        filename_match = CV_FILE_RE.search(message)
        filename = filename_match.group(0).strip() if filename_match else "uploaded CV"
        updates = {
            "profile_creation_mode": "cv_first",
            "cv_filename": filename,
            "cv_status": "received_pending_extraction",
            "manual_profile_wizard_disabled": True,
        }
        updates.update(self._extract_inline_contact_updates(message))
        profile = upsert_profile(user_id=user_id, updates=updates)

        missing = [
            ONBOARDING_FIELD_LABELS.get(key, key)
            for key, label in [
                ("email", "email address"),
                ("phone", "phone number"),
                ("preferred_city", "preferred UAE city"),
                ("target_roles", "target role"),
                ("salary_expectation_aed", "salary expectation"),
                ("deal_breakers", "roles or companies to avoid"),
            ]
            if not getattr(profile, key, None) and not (isinstance(profile, dict) and profile.get(key))
        ]

        response = {
            "type": "cv_first_profile",
            "message": (
                f"I received {filename}. I will use the CV-first profile flow: extract every available detail "
                "from the CV, pre-fill the career profile, and only ask for anything missing or unclear. "
                "I will not run the long manual question-by-question form."
            ),
            "next_action": "parse_cv_and_prefill_profile",
            "manual_questions_disabled": True,
            "missing_after_extraction_should_be_limited_to": missing,
            "confirmation_prompt": (
                "After extraction, show the profile summary and ask: save this profile, or edit a field?"
            ),
        }
        self._append_chat(user_id, "assistant", response)
        return response

    _WHATS_NEXT_PHRASES = frozenset([
        "what's next", "whats next", "what next", "what now",
        "what can you do", "what can i do", "help", "options", "menu",
        "show options", "show menu", "next steps",
    ])

    _ACTION_WORDS = frozenset({
        "find", "search", "show", "get", "apply", "save",
        "prepare", "draft", "update", "track",
    })

    _FOLLOWUP_NEXT_STEP_PHRASES = frozenset({
        "so", "so?", "what now", "what now?", "what's next", "whats next",
        "next", "next?", "then", "then?", "now", "now?", "ok", "okay",
        "continue", "go on",
    })

    _JOB_SEARCH_OPTIONS = {
        "type": "options",
        "message": "Here is what I can help you with:",
        "options": [
            {"action": "find_jobs",          "label": "Find matching UAE jobs"},
            {"action": "apply",              "label": "Prepare a job application"},
            {"action": "interview_prep",     "label": "Prepare for an interview"},
            {"action": "update_profile",     "label": "Update my profile"},
            {"action": "track_applications", "label": "Track my applications"},
        ],
    }

    def _target_role_search_response(self, user_id: str, role: str, profile: Any) -> dict[str, Any]:
        """Handle target role search with role intelligence integration."""
        try:
            normalized_role = normalize_role(role)
        except Exception as e:
            logger.warning("Role normalization failed", extra={"user_id": user_id, "role": role, "error": str(e)})
            normalized_role = role

        target_roles = self._as_list(self._profile_value(profile, "target_roles"))
        if normalized_role and normalized_role.lower() not in {str(item).lower() for item in target_roles}:
            target_roles.append(normalized_role)
            profile = upsert_profile(user_id=user_id, updates={"target_roles": target_roles})

        workflow_result = self.system.run_for_profile(profile)
        all_matches = workflow_result.get("matches", [])

        # Filter out already-applied jobs
        try:
            from src.applications import is_applied_batch, get_job_id
            if all_matches:
                applied_map = is_applied_batch(all_matches)
                all_matches = [m for m in all_matches if not applied_map.get(get_job_id(m), False)]
        except Exception as e:
            logger.debug("Applied-job filter unavailable: %s", e)

        top_matches = all_matches[:5]
        formatted = [self._format_match(m, profile) for m in top_matches]

        skills = self._as_list(self._profile_value(profile, "skills"))[:8]
        years = self._profile_value(profile, "years_experience")
        cities = self._as_list(self._profile_value(profile, "preferred_cities"))
        city_text = f" in {', '.join(map(str, cities[:2]))}" if cities else " in the UAE"
        basis = []
        if years:
            basis.append(f"~{years} years experience")
        if skills:
            basis.append("skills: " + ", ".join(map(str, skills[:6])))
        basis_text = " using your CV profile" + (f" ({'; '.join(basis)})" if basis else "")

        role_intelligence_data = self._enrich_with_role_intelligence(
            user_id, normalized_role, profile, skills, years, cities
        )

        message = self._build_role_search_message(
            normalized_role, city_text, basis_text, top_matches, role_intelligence_data
        )

        response = {
            "type": "job_matches",
            "intent": "search_jobs",
            "message": message,
            "matches": formatted,
            "entities": {"job_title": normalized_role, "from_cv_profile": True},
        }

        if role_intelligence_data:
            response["role_intelligence"] = role_intelligence_data

        self._append_chat(user_id, "assistant", response)
        return response

    def _enrich_with_role_intelligence(
        self,
        user_id: str,
        normalized_role: str,
        profile: Any,
        skills: list[Any],
        years: Any,
        cities: list[Any],
    ) -> dict[str, Any] | None:
        """Enrich response with role intelligence data."""
        try:
            from src.rico_agent import RicoProfile

            rico_profile = RicoProfile(
                user_id=user_id,
                skills=skills or [],
                years_experience=years,
                preferred_cities=cities or [],
                industries=self._as_list(self._profile_value(profile, "industries")) or []
            )

            fit_score = score_profile_fit(rico_profile, normalized_role)

            adjacent_roles = []
            if fit_score.overall_score < 0.6:
                adjacent_roles = recommend_adjacent_roles(rico_profile, normalized_role, limit=3)

            if not adjacent_roles:
                return None

            return {
                "normalized_role": normalized_role,
                "fit_score": fit_score.overall_score,
                "adjacent_roles": [
                    {"role": r.canonical_role, "similarity": r.similarity_score, "reason": r.reason}
                    for r in adjacent_roles
                ]
            }
        except Exception as e:
            logger.warning("Role intelligence enrichment failed", extra={"user_id": user_id, "role": normalized_role, "error": str(e)})
            return None

    def _build_role_search_message(
        self,
        normalized_role: str,
        city_text: str,
        basis_text: str,
        top_matches: list[Any],
        role_intelligence_data: dict[str, Any] | None,
    ) -> str:
        """Build message for role search response."""
        if top_matches:
            base_message = f"Got it — I will target {normalized_role} roles{city_text}{basis_text}. I found {len(top_matches)} current strong matches."
        else:
            base_message = f"Got it — I will target {normalized_role} roles{city_text}{basis_text}."

        if role_intelligence_data and role_intelligence_data.get("fit_score", 1.0) < 0.6:
            adjacent = role_intelligence_data.get("adjacent_roles", [])
            role_names = [r["role"] for r in adjacent[:3]]
            base_message += f" Your CV is also strong for {', '.join(role_names)} roles. I'll search those too if needed."
        elif not top_matches:
            base_message += " I did not find strong matches yet, so I will keep scanning and use this profile for future matches."

        return base_message

    def process_message(self, user_id: str, message: str) -> dict[str, Any]:
        debug_id = _generate_debug_id()
        try:
            result = self._process_message_inner(user_id, message)
            # Guarantee debug_id on every response
            if isinstance(result, dict):
                result.setdefault("debug_id", debug_id)
                message_text = str(result.get("message") or "").strip()
                if not message_text:
                    logger.error(
                        "rico_empty_message_response user=%s type=%s source=%s",
                        user_id,
                        result.get("type", "unknown"),
                        result.get("response_source", "unknown"),
                    )
                    error_response = build_error_response(
                        "Rico could not produce a usable reply for that request. Please rephrase your request or ask a more specific question.",
                        debug_id=debug_id,
                        user_id=user_id,
                    )
                    for key in (
                        "provider",
                        "model",
                        "response_source",
                        "provider_state",
                        "profile_context_present",
                        "jotform_form_id",
                        "fallback_model",
                        "openai_model",
                        "deepseek_model",
                        "error",
                        "error_detail",
                        "is_rate_limited",
                    ):
                        if key in result:
                            error_response[key] = result[key]
                    error_response.setdefault("error", "empty_message")
                    return error_response
                result.setdefault("success", True)
            return result
        except Exception as exc:
            return build_error_response(
                "Something went wrong processing your message.",
                debug_id=debug_id,
                log_exc=exc,
                user_id=user_id,
            )

    def _answer_with_ai_fallback(
        self,
        user_id: str,
        message: str,
        profile: Any,
        *,
        save_user_message: bool,
    ) -> dict[str, Any]:
        """Run the single conversational AI fallback path used by chat routing."""
        if save_user_message:
            self._append_chat(user_id, "user", message)
        user_context = self._build_openai_context(profile)
        blocked_questions = self._get_blocked_questions(profile)
        if isinstance(user_context, dict):
            user_context["blocked_questions"] = blocked_questions

        ai_response = self._get_openai_agent().respond(message, user_context=user_context)
        raw_ai_message = ai_response.get("message", "")
        filtered_ai_message = self._preserve_ai_message(raw_ai_message, blocked_questions)
        ai_response["message"] = filtered_ai_message

        if filtered_ai_message:
            self._append_chat(user_id, "assistant", filtered_ai_message)

        result = self._finalize(
            ai_response,
            self._source_for_openai_response(ai_response),
            profile=profile,
        )
        result.setdefault("success", True)
        return result

    def answer_conversationally(self, user_id: str, message: str, profile: Any) -> dict[str, Any]:
        """Route directly to the existing conversational AI fallback path."""
        debug_id = _generate_debug_id()
        try:
            result = self._answer_with_ai_fallback(
                user_id=user_id,
                message=message,
                profile=profile,
                save_user_message=True,
            )
            if isinstance(result, dict):
                result.setdefault("debug_id", debug_id)
                message_text = str(result.get("message") or "").strip()
                if not message_text:
                    logger.error(
                        "rico_empty_message_response user=%s type=%s source=%s",
                        user_id,
                        result.get("type", "unknown"),
                        result.get("response_source", "unknown"),
                    )
                    error_response = build_error_response(
                        "Rico could not produce a usable reply for that request. Please rephrase your request or ask a more specific question.",
                        debug_id=debug_id,
                        user_id=user_id,
                    )
                    for key in (
                        "provider",
                        "model",
                        "response_source",
                        "provider_state",
                        "profile_context_present",
                        "jotform_form_id",
                        "fallback_model",
                        "openai_model",
                        "deepseek_model",
                        "error",
                        "error_detail",
                        "is_rate_limited",
                    ):
                        if key in result:
                            error_response[key] = result[key]
                    error_response.setdefault("error", "empty_message")
                    return error_response
                result.setdefault("success", True)
            return result
        except Exception as exc:
            return build_error_response(
                "Something went wrong processing your message.",
                debug_id=debug_id,
                log_exc=exc,
                user_id=user_id,
            )

    def _process_message_inner(self, user_id: str, message: str) -> dict[str, Any]:
        self._append_chat(user_id, "user", message)
        completed = is_onboarding_complete(user_id)

        if completed:
            return self._handle_active_user(user_id, message)

        if self._looks_like_cv_upload(message):
            mark_onboarding_complete(user_id)
            return self._finalize(
                self._cv_first_profile_response(user_id, message),
                self.SOURCE_KEYWORD,
                profile=None,
            )

        profile = get_profile(user_id)
        if profile is None:
            upsert_profile(user_id=user_id, updates={"name": user_id})
            set_onboarding_status(user_id, ONBOARDING_IN_PROGRESS)
            response = {
                "type": "onboarding",
                "message": (
                    "Welcome to Rico AI. Upload your CV or tell me your target role, UAE city "
                    "preferences, and salary expectations. If you upload a CV, I will pre-fill "
                    "the profile and only ask for anything missing or unclear."
                ),
            }
            self._append_chat(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=None)

        mark_onboarding_complete(user_id)
        return self._handle_active_user(user_id, message)

    def _resolve_profile(self, user_id: str):
        """Load and normalise profile into a ProfileContext.

        This is the migration point for #96 — eventually all callers
        will consume ProfileContext directly instead of raw dict/objects.
        """
        raw = get_profile(user_id)
        return resolve_profile_context(user_id, raw)

    def _handle_active_user(self, user_id: str, message: str) -> dict[str, Any]:
        """Intent-first active-user handler.

        Pipeline:
          1. Deterministic follow-up phrases (before role classification)
          2. Classify intent (never defaults to job search)
          3. Route by intent
          4. For role-like text, use 3-tier role classifier
          5. Unknown / nonsense → clarification, not search
        """
        profile = self._resolve_profile(user_id)
        has_cv = profile.has_cv
        text = self._normalize_followup_phrase(message)

        # ── Deterministic follow-up phrases (must be before role classification) ──
        if text in self._FOLLOWUP_KEEP_ALL_PHRASES:
            return self._finalize(
                self._handle_keep_all_target_roles(user_id, profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        if text in self._FOLLOWUP_BOTH_ACTION_PHRASES:
            return self._finalize(
                self._handle_both_requested_actions(user_id, profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        logger.info(
            "rico_followup_check user=%s has_cv=%s msg=%r followup=%s",
            user_id, has_cv, message, self._looks_like_next_step_followup(message),
        )

        # Fast path: short follow-up after role confirmation → instant options
        if has_cv and self._looks_like_next_step_followup(message):
            logger.info("rico_followup_hit user=%s msg=%r", user_id, message)
            return self._finalize(
                self._handle_next_step_options(user_id, profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        # Fast path: user selected a suggested role → deterministic confirmation
        if has_cv and not self._is_live_job_search_request(message):
            if self._looks_like_selected_role(message, profile):
                return self._finalize(
                    self._handle_role_confirmation(
                        user_id=user_id,
                        role=self._extract_selected_role(message, profile),
                        profile=profile,
                    ),
                    self.SOURCE_KEYWORD,
                    profile=profile,
                )

        # Generic job request with CV → suggest CV-based roles instead of blind search
        if (
            has_cv
            and not self._is_live_job_search_request(message)
            and self._looks_like_generic_job_request(message)
        ):
            return self._finalize(
                self._handle_profile_role_suggestions(profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        # ── Step 1: Unified intent classification ────────────────────────────
        intent_result = classify_intent(message, has_cv_profile=has_cv)
        intent = intent_result.intent

        logger.info(
            "rico_intent user=%s intent=%s confidence=%.2f source=%s",
            user_id, intent, intent_result.confidence, intent_result.source,
        )

        # ── Step 2: Route by intent ──────────────────────────────────────────

        # Help / menu
        if intent == "help":
            self._append_chat(user_id, "assistant", self._JOB_SEARCH_OPTIONS)
            return self._finalize(self._JOB_SEARCH_OPTIONS, self.SOURCE_KEYWORD, profile=profile)

        # Smalltalk
        if intent == "smalltalk":
            response = {
                "type": "clarification",
                "message": "Hi! I am Rico, your job search assistant. Tell me a role to search, upload your CV, or say 'help' for options.",
            }
            self._append_chat(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        # Onboarding skip
        if intent == "onboarding_answer":
            response = {
                "type": "profile_skip",
                "message": (
                    "Skipped. I will leave that field blank and continue without forcing it. "
                    "You can update it later."
                ),
                "field_status": "skipped",
            }
            self._append_chat(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        # CV upload / parse — but if CV is already parsed, don't restart wizard
        if intent == "cv_upload_or_parse":
            cv_status = self._profile_value(profile, "cv_status")
            if cv_status == "parsed" or self._profile_value(profile, "manual_profile_wizard_disabled"):
                response = {
                    "type": "profile_summary",
                    "message": (
                        "Your CV is already parsed and your profile is set up. "
                        "You can say 'show my profile' to review it, or tell me a role to search."
                    ),
                }
                self._append_chat(user_id, "assistant", response["message"])
                return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)
            return self._finalize(
                self._cv_first_profile_response(user_id, message),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        # Profile summary
        if intent == "profile_summary":
            from src.agent.context.resolver import resolve_profile_context
            try:
                ctx = resolve_profile_context(user_id)
                prof_dict = profile_to_dict(ctx.profile) if ctx.profile else {}
            except Exception:
                prof_dict = profile_to_dict(profile) if profile else {}
            response = {
                "type": "profile_summary",
                "message": "Here is your current profile.",
                "profile": prof_dict,
            }
            self._append_chat(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        # Profile role suggestions - deterministic fast path based on CV skills/certifications
        if intent == "profile_role_suggestions":
            return self._finalize(
                self._handle_profile_role_suggestions(profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        # Generic follow-up confirmations should never fall into role classification.
        if intent == "follow_up_confirmation":
            if text == "all":
                return self._finalize(
                    self._handle_keep_all_target_roles(user_id, profile),
                    self.SOURCE_KEYWORD,
                    profile=profile,
                )
            if has_cv:
                return self._finalize(
                    self._handle_next_step_options(user_id, profile),
                    self.SOURCE_KEYWORD,
                    profile=profile,
                )
            response = {
                "type": "clarification",
                "message": (
                    "I am ready to continue. Upload your CV or tell me your target role "
                    "so I know what action to take next."
                ),
            }
            self._append_chat(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        # Application tracking — route to applications repo, NOT job search
        if intent == "application_tracking":
            return self._finalize(
                self._handle_application_tracking(user_id),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        # Profile-match job search (use CV/profile, not a named role)
        if intent == "job_search_profile_match":
            if not has_cv:
                response = {
                    "type": "clarification",
                    "message": (
                        "I don't have enough profile data yet to find matching jobs. "
                        "Upload your CV or tell me your target role, skills, and preferred city."
                    ),
                }
                self._append_chat(user_id, "assistant", response["message"])
                return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)
            # Use profile target roles for search
            target_roles = self._as_list(self._profile_value(profile, "target_roles"))
            logger.info(
                "rico_profile_match_search user=%s target_roles=%s has_cv=%s",
                user_id, target_roles, has_cv,
            )
            role = target_roles[0] if target_roles else "your profile"
            return self._finalize(
                self._target_role_search_response(user_id, role, profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        # Profile update — route BEFORE role-change fallback
        if intent == "profile_update":
            context = self._build_router_context(user_id, profile)
            routed = _route(message, user_id=user_id, context=context)
            prefs = routed.tool_args.get("preferences", {})
            if prefs:
                upsert_profile(user_id=user_id, updates=prefs)
            response = {
                "type": "preferences_updated",
                "message": "Got it. I have updated your preferences and will apply them to future searches.",
                "updated": prefs,
            }
            self._append_chat(user_id, "assistant", response["message"])
            return self._finalize(response, routed.source, profile=profile)

        # Role change — extract role and classify
        if intent == "role_change" and intent_result.extracted_role:
            return self._finalize(
                self._classified_role_search(user_id, intent_result.extracted_role, profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        # Explicit job search (regex-matched "find ... jobs" etc.)
        if intent == "job_search_explicit":
            # Fall through to legacy router for entity extraction
            context = self._build_router_context(user_id, profile)
            routed = _route(message, user_id=user_id, context=context)

            # Check if profile has target role before running job search
            if not profile.target_roles or (isinstance(profile.target_roles, list) and len(profile.target_roles) == 0):
                response = {
                    "type": "profile_incomplete",
                    "intent": "search_jobs",
                    "message": (
                        "I can search jobs using your profile. Please confirm:\n"
                        "• Target role (e.g., HSE Manager, ESG Specialist)\n"
                        "• Preferred city (e.g., Dubai, Abu Dhabi)\n"
                        "• Expected salary (optional)\n\n"
                        "I cannot search for jobs until at least your target role is known."
                    ),
                    "entities": routed.entities,
                }
                self._append_chat(user_id, "assistant", response["message"])
                return self._finalize(response, routed.source, profile=profile)

            # Removed fast-path override to prevent intent interception
            # Previously: generic job searches without job_title were intercepted by profile suggestions
            # Now: all explicit job searches execute through the normal workflow
            workflow_result = self.system.run_for_profile(profile)

            # Handle blocked status from job search
            if workflow_result.get("status") == "blocked":
                response = {
                    "type": "profile_incomplete",
                    "intent": "search_jobs",
                    "message": workflow_result.get("message", "Please provide at least one target role before searching for jobs."),
                    "entities": routed.entities,
                }
                self._append_chat(user_id, "assistant", response["message"])
                return self._finalize(response, routed.source, profile=profile)

            all_explicit = workflow_result.get("matches", [])
            try:
                from src.applications import is_applied_batch, get_job_id
                if all_explicit:
                    app_map = is_applied_batch(all_explicit)
                    all_explicit = [m for m in all_explicit if not app_map.get(get_job_id(m), False)]
            except Exception:
                pass
            top_matches = all_explicit[:5]
            formatted = [self._format_match(m, profile) for m in top_matches]
            response = {
                "type": "job_matches",
                "intent": "search_jobs",
                "message": "I found {} strong UAE job matches for you.".format(len(top_matches)),
                "matches": formatted,
                "entities": routed.entities,
            }
            self._append_chat(user_id, "assistant", response)
            return self._finalize(response, routed.source, profile=profile)

        # Apply job — confirmation gate
        if intent == "apply_job":
            context = self._build_router_context(user_id, profile)
            routed = _route(message, user_id=user_id, context=context)
            response = {
                "type": "confirmation_required",
                "intent": "apply_job",
                "message": routed.confirmation_prompt or (
                    "To confirm: mark this job as applied and track it. "
                    "Reply YES to confirm or CANCEL to abort."
                ),
                "tool_args": routed.tool_args,
            }
            self._append_chat(user_id, "assistant", response["message"])
            return self._finalize(response, routed.source, profile=profile)

        # Save job
        if intent == "save_job":
            context = self._build_router_context(user_id, profile)
            routed = _route(message, user_id=user_id, context=context)
            if routed.tool_name:
                job_key = routed.tool_args.get("job_key", "")
                result = agent_runtime.handle_action(
                    user_id=user_id, action="save", job_key=job_key, source="chat",
                )
                response = {
                    "type": "save_job",
                    "intent": "save_job",
                    "message": result.message,
                    "entities": routed.entities,
                }
                self._append_chat(user_id, "assistant", result.message)
                return self._finalize(response, routed.source, profile=profile)

        # Explain match
        if intent == "explain_match":
            context = self._build_router_context(user_id, profile)
            routed = _route(message, user_id=user_id, context=context)
            if routed.tool_name:
                job_key = routed.tool_args.get("job_key", "")
                result = agent_runtime.handle_action(
                    user_id=user_id, action="why", job_key=job_key, source="chat",
                )
                response = {
                    "type": "explain_match",
                    "intent": "explain_match",
                    "message": result.message,
                }
                self._append_chat(user_id, "assistant", result.message)
                return self._finalize(response, routed.source, profile=profile)

        # Draft message
        if intent == "draft_message":
            context = self._build_router_context(user_id, profile)
            routed = _route(message, user_id=user_id, context=context)
            if routed.tool_name:
                job_key = routed.tool_args.get("job_key", "")
                result = agent_runtime.handle_action(
                    user_id=user_id, action="draft", job_key=job_key, source="chat",
                )
                response = {
                    "type": "draft_message",
                    "intent": "draft_message",
                    "message": result.message,
                }
                self._append_chat(user_id, "assistant", result.message)
                return self._finalize(response, routed.source, profile=profile)

        # Interview prep
        if intent == "interview_prep":
            user_context = self._build_openai_context(profile)
            system_prompt = (
                "You are Rico, a UAE career coach. Give concise, practical interview preparation "
                "tips including likely questions, company research pointers, and answer frameworks."
            )
            hf_text = None
            if hf_ok():
                hf_text = generate_text(message, system=system_prompt, max_new_tokens=400)
            msg = hf_text or (
                "I will prepare interview notes, likely questions, and suggested answers based on your target role. "
                "Share the specific job title or company name for a more tailored response."
            )
            response = {"type": "interview_prep", "message": msg}
            self._append_chat(user_id, "assistant", msg)
            src = self.SOURCE_HF if hf_text else self.SOURCE_FALLBACK
            return self._finalize(response, src, profile=profile)

        # Nonsense — do NOT search
        if intent == "nonsense":
            response = {
                "type": "clarification",
                "message": (
                    "I could not understand that message. "
                    "Try telling me a job role to search, or say 'help' for options."
                ),
            }
            self._append_chat(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        # ── Step 3: Unknown intent — try role classification, then clarify ───
        # Only attempt role search if message looks like a plausible role (short text, no digits)
        if has_cv and self._looks_like_bare_target_role(message):
            logger.info(
                "bare_role_gate_pass user=%s msg_len=%d",
                user_id,
                len(message),
            )
            return self._finalize(
                self._classified_role_search(user_id, message.strip(), profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )
        logger.info(
            "bare_role_gate_reject_to_ai user=%s msg_len=%d",
            user_id,
            len(message),
        )

        # Final fallback: use AI for natural reply, but never treat as job search
        return self._answer_with_ai_fallback(
            user_id=user_id,
            message=message,
            profile=profile,
            save_user_message=False,
        )

    # ── New intent-specific handlers ─────────────────────────────────────────

    def _handle_application_tracking(self, user_id: str) -> dict[str, Any]:
        """Route application tracking requests to the applications repository."""
        try:
            from src.repositories.applications_repo import get_all, get_stats
            apps = get_all(user_id=user_id)
            stats = get_stats(user_id=user_id)
        except Exception:
            # Fallback to legacy file-based store
            from src.applications import get_applied_jobs, get_application_stats
            apps = get_applied_jobs()
            stats = get_application_stats()

        if not apps:
            return {
                "type": "application_status",
                "message": (
                    "You have no tracked applications yet. "
                    "When you apply to a job through Rico, I will track it here. "
                    "You can also say 'mark as applied' on any job."
                ),
                "applications": [],
            }

        return {
            "type": "application_status",
            "message": f"Tracking {len(apps)} application(s).",
            "applications": apps,
            "stats": stats,
        }

    def _handle_profile_role_suggestions(self, profile: Any) -> dict[str, Any]:
        """Generate deterministic role suggestions based on CV skills/certifications.

        Fast path: no OpenAI, no job search, just profile data → role mapping.
        """
        if not profile:
            return {
                "type": "profile_role_suggestions",
                "message": "I need your CV or profile data to suggest roles. Upload your CV first.",
                "options": [],
                "next_action": "upload_cv"
            }

        # Extract profile data
        skills = self._as_list(self._profile_value(profile, "skills"))
        certifications = self._as_list(self._profile_value(profile, "certifications"))
        years_experience = self._profile_value(profile, "years_experience")
        industries = self._as_list(self._profile_value(profile, "industries"))

        # Map skills/certifications to role families
        suggestions = self._generate_role_suggestions(skills, certifications, years_experience, industries)

        if not suggestions:
            return {
                "type": "profile_role_suggestions",
                "message": "Your profile doesn't have enough specific skills or certifications to suggest roles yet.",
                "options": [],
                "next_action": "add_skills"
            }

        return {
            "type": "profile_role_suggestions",
            "message": f"Based on your CV, here are {len(suggestions)} role suggestions that match your skills:",
            "options": suggestions,
            "next_action": "select_role_to_search"
        }

    def _generate_role_suggestions(
        self,
        skills: list[str],
        certifications: list[str],
        years_experience: float | None,
        industries: list[str]
    ) -> list[dict[str, str]]:
        """Generate role suggestions based on profile data."""
        suggestions = []
        skill_lower = [s.lower() for s in skills]
        cert_lower = [c.lower() for c in certifications]

        # Safe numeric parsing
        try:
            years_num = float(years_experience) if years_experience is not None else None
        except (TypeError, ValueError):
            years_num = None
        years_experience = years_num

        # Role family mappings based on skills/certifications
        role_mappings = {
            # HSE/Safety roles
            "hse": ["HSE Officer", "HSE Manager", "Safety Officer", "QHSE Coordinator"],
            "safety": ["Safety Officer", "Safety Manager", "HSE Officer"],
            "qhse": ["QHSE Coordinator", "QHSE Manager", "HSE Manager"],

            # Environmental roles
            "environmental": ["Environmental Officer", "Environmental Manager", "Environmental Specialist"],
            "sustainability": ["Sustainability Officer", "ESG Specialist", "Sustainability Manager"],
            "esg": ["ESG Specialist", "Sustainability Officer", "ESG Manager"],

            # Compliance/Audit roles
            "compliance": ["Compliance Officer", "Compliance Manager", "Regulatory Affairs"],
            "audit": ["Internal Auditor", "External Auditor", "Audit Manager"],
            "iso": ["ISO Coordinator", "ISO 14001 Specialist", "Quality Manager"],

            # Operations roles
            "operations": ["Operations Manager", "Operations Coordinator", "Facilities Manager"],

            # General management
            "management": ["Operations Manager", "Project Manager", "Team Lead"],
        }

        # Add seniority prefix based on experience
        seniority_prefix = ""
        if years_experience:
            if years_experience >= 10:
                seniority_prefix = "Senior "
            elif years_experience >= 5:
                seniority_prefix = ""

        # Generate suggestions based on skill matches
        for skill, roles in role_mappings.items():
            if any(skill in s for s in skill_lower):
                for role in roles:
                    # Check if already added
                    if not any(s["label"] == role for s in suggestions):
                        reason = f"Matches your {skill} background"
                        if years_experience and years_experience >= 5:
                            role_with_seniority = f"{seniority_prefix}{role}"
                        else:
                            role_with_seniority = role
                        suggestions.append({
                            "label": role_with_seniority,
                            "reason": reason
                        })

        # Add certification-based suggestions
        if any("iso" in c for c in cert_lower):
            if not any(s["label"] == "ISO 14001 Specialist" for s in suggestions):
                suggestions.append({
                    "label": "ISO 14001 Specialist",
                    "reason": "Based on your ISO certification"
                })

        if any("nebosh" in c for c in cert_lower):
            if not any(s["label"] == "HSE Manager" for s in suggestions):
                suggestions.append({
                    "label": "HSE Manager",
                    "reason": "Based on your NEBOSH certification"
                })

        # Limit to top 8 suggestions
        return suggestions[:8]

    def _classified_role_search(self, user_id: str, role_text: str, profile: Any) -> dict[str, Any]:
        """Use 3-tier role classifier before searching.

        - profile_relevant → search directly
        - known_but_off_profile → ask confirmation
        - unknown → clarify / redirect
        """
        classification, canonical_role = classify_role_candidate(role_text, profile)

        if classification == "profile_relevant" and canonical_role:
            return self._target_role_search_response(user_id, canonical_role, profile)

        if classification == "known_but_off_profile" and canonical_role:
            response = {
                "type": "clarification",
                "message": (
                    f"'{canonical_role}' is a real role, but it does not look close to your CV profile. "
                    f"Should I search for {canonical_role} jobs anyway? Reply YES or tell me a different role."
                ),
                "options": [
                    {"action": "confirm_search", "label": f"Yes, search {canonical_role}"},
                    {"action": "show_profile_roles", "label": "Show roles from my CV"},
                ],
            }
            self._append_chat(user_id, "assistant", response["message"])
            return response

        # unknown role
        target_roles = self._as_list(self._profile_value(profile, "target_roles"))
        suggestion = ""
        if target_roles:
            suggestion = f" Based on your CV, I can search for: {', '.join(str(r) for r in target_roles[:3])}."
        response = {
            "type": "clarification",
            "message": (
                f"I do not recognize '{role_text}' as a job role.{suggestion} "
                "Try a specific role title, or say 'help' for options."
            ),
        }
        self._append_chat(user_id, "assistant", response["message"])
        return response

    def _get_recent_messages(self, user_id: str, limit: int = MAX_CONTEXT_MESSAGES) -> list[dict[str, str]]:
        """Get recent messages for context, respecting token limits."""
        try:
            # Get messages from memory store
            messages = self.memory.get_recent_messages(user_id, limit=limit)
            return messages[-limit:] if len(messages) > limit else messages
        except Exception as e:
            logger.warning("Failed to get recent messages", extra={"user_id": user_id, "error": str(e)})
            return []

    def _get_blocked_questions(self, profile: Any) -> list[str]:
        """Return list of question types that should not be asked based on profile data."""
        blocked = []
        if profile is None:
            return blocked

        has_cv = bool(
            self._profile_value(profile, "cv_filename")
            or self._profile_value(profile, "cv_status") == "parsed"
        )

        # Check for years_experience (explicit value or any CV upload)
        if self._profile_value(profile, "years_experience") or has_cv:
            blocked.append("experience")

        # Check for preferred_cities
        if self._profile_value(profile, "preferred_cities") or self._profile_value(profile, "cities"):
            blocked.append("location")

        # Check for skills or industries
        skills = self._profile_value(profile, "skills")
        if (skills and len(skills) > 0) or self._profile_value(profile, "industries"):
            blocked.append("industry")

        return blocked

    @staticmethod
    def _contains_blocked_question_pattern(text: str, blocked_questions: list[str]) -> bool:
        lower_text = text.lower()
        for blocked in blocked_questions:
            if blocked == "experience" and any(pattern in lower_text for pattern in [
                "experience level", "years experience", "years of experience",
                "how many years", "how much experience", "entry/mid/senior",
                "experience?", "your experience"
            ]):
                return True
            if blocked == "location" and any(pattern in lower_text for pattern in [
                "location", "city", "where", "uae city", "preferred city",
                "which city", "where are you", "where do you want"
            ]):
                return True
            if blocked == "industry" and any(pattern in lower_text for pattern in [
                "industry", "sector", "field", "which industry", "what industry"
            ]):
                return True
        return False

    def _remove_blocked_questions(self, response: str, blocked_questions: list[str]) -> str:
        """Remove lines that only ask for profile facts we already know."""
        if not response or not blocked_questions:
            return response

        filtered_lines = []
        for line in response.split("\n"):
            if self._contains_blocked_question_pattern(line, blocked_questions):
                continue
            filtered_lines.append(line)

        return "\n".join(filtered_lines).strip()

    def _remove_blocked_question_sentences(self, response: str, blocked_questions: list[str]) -> str:
        """Prefer sentence-level cleanup before falling back to the raw provider reply."""
        if not response or not blocked_questions:
            return response

        fragments = re.split(r"(?<=[.!?])\s+", response.strip())
        kept_fragments = []
        for fragment in fragments:
            trimmed = fragment.strip()
            if not trimmed:
                continue
            if trimmed.endswith("?") and self._contains_blocked_question_pattern(trimmed, blocked_questions):
                continue
            kept_fragments.append(trimmed)

        return " ".join(kept_fragments).strip()

    def _preserve_ai_message(self, response: str, blocked_questions: list[str]) -> str:
        """Never discard a non-empty provider reply just because the broad filter removed it."""
        raw_message = str(response or "").strip()
        if not raw_message:
            return raw_message

        filtered_message = self._remove_blocked_questions(raw_message, blocked_questions)
        if filtered_message:
            return filtered_message

        minimally_filtered = self._remove_blocked_question_sentences(raw_message, blocked_questions)
        if minimally_filtered:
            logger.warning(
                "rico_ai_response_line_filter_empty_using_sentence_fallback blocked=%s",
                blocked_questions,
            )
            return minimally_filtered

        logger.warning(
            "rico_ai_response_filter_empty_using_raw_fallback blocked=%s",
            blocked_questions,
        )
        return raw_message

    @staticmethod
    def _build_router_context(user_id: str, profile: Any) -> dict:
        """Build the context dict passed to the intent router."""
        ctx: dict = {}
        if profile:
            try:
                ctx["profile"] = asdict(profile) if is_dataclass(profile) else dict(profile)
            except Exception as e:
                logger.warning("Failed to build router context", extra={"user_id": user_id, "error": str(e)})
        return ctx


def demo() -> None:
    """Demo function for testing the chat API."""
    api = RicoChatAPI()

    messages: list[str] = [
        "Roben_Edwan_CV.pdf here u go",
        "take it from the c.v!",
        "Please skip this question.",
        "I need HSE Manager jobs in Dubai",
        "Find jobs for me",
        "Prepare me for interview",
    ]

    for message in messages:
        print("USER:", message)
        print("RICO:")
        print(json.dumps(api.process_message("demo-user", message), indent=2))
        print("-" * 80)


if __name__ == "__main__":
    demo()
