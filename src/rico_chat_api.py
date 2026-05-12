"""Rico conversational AI API.

This module transforms the existing automation system into a chat-first
career agent. Rico accepts natural language messages, updates memory,
triggers workflows, and responds with autonomous actions.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, is_dataclass
from typing import Any, NamedTuple

# Standard library imports first
# Third-party imports (none currently)
# Local imports
from src.agent.intelligence.intent_classifier import classify_intent, IntentResult
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

logger = logging.getLogger(__name__)

# Constants
CV_FILE_RE = re.compile(r"\b[\w .()_-]+\.(?:pdf|docx?|txt)\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
BARE_ROLE_RE = re.compile(r"^[A-Za-z][A-Za-z\s/&+-]{2,80}$")

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

    def __init__(self) -> None:
        self.memory = RicoMemoryStore()
        self.agent = RicoAgent(profile_store=self.memory)
        self.system = RicoSystem()
        self.openai_agent = RicoOpenAIAgent()

    def _append_chat(self, user_id: str, role: str, message: str | dict[str, Any]) -> None:
        """Append chat message to memory, handling both string and dict messages."""
        payload = json.dumps(message) if isinstance(message, dict) else message
        self.memory.append_chat_message(user_id, role, payload)

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
        """Check if message looks like a bare target role."""
        text = (message or "").strip()
        if not text or len(text.split()) > 6:
            return False
        lowered = text.lower()
        if lowered in RicoChatAPI._WHATS_NEXT_PHRASES:
            return False
        if any(ch.isdigit() for ch in text):
            return False
        return bool(BARE_ROLE_RE.match(text))

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
    def _format_match(m: dict[str, Any], profile: Any) -> dict[str, Any]:
        """Return a backward-compatible chat match with v1 structured guidance."""
        explanation = build_match_explanation(m, profile)
        return {
            "title": m.get("title"),
            "company": m.get("company"),
            "location": m.get("location"),
            "score": m.get("rico_score"),
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
        return {
            **response,
            "response_source": response.get("response_source", source),
            "provider": response.get("provider", source),
            "provider_state": response.get("provider_state"),
            "openai_available": self._bool_attr(agent, "openai_available", fallback="available"),
            "deepseek_available": self._bool_attr(agent, "deepseek_available"),
            "provider_available": self._bool_attr(agent, "provider_available", fallback="available"),
            "hf_available": self._bool_attr(agent, "hf_available"),
            "openai_model": agent.model,
            "ai_model": agent.model,
            "profile_context_present": profile is not None,
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

    def _handle_active_user(self, user_id: str, message: str) -> dict[str, Any]:
        """Intent-first active-user handler.

        Pipeline:
          1. Classify intent (never defaults to job search)
          2. Route by intent
          3. For role-like text, use 3-tier role classifier
          4. Unknown / nonsense → clarification, not search
        """
        profile = get_profile(user_id)
        has_cv = self._has_cv_profile(profile)

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
            role = target_roles[0] if target_roles else "your profile"
            return self._finalize(
                self._target_role_search_response(user_id, role, profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

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
            workflow_result = self.system.run_for_profile(profile)
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

        # Profile update
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
            return self._finalize(
                self._classified_role_search(user_id, message.strip(), profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        # Final fallback: use AI for natural reply, but never treat as job search
        user_context = self._build_openai_context(profile)
        blocked_questions = self._get_blocked_questions(profile)
        if isinstance(user_context, dict):
            user_context["blocked_questions"] = blocked_questions

        ai_response = self._get_openai_agent().respond(message, user_context=user_context)
        ai_response["message"] = self._remove_blocked_questions(ai_response.get("message", ""), blocked_questions)

        self._append_chat(user_id, "assistant", ai_response.get("message", ""))
        return self._finalize(ai_response, self._source_for_openai_response(ai_response), profile=profile)

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

        total = stats.get("total_applied", len(apps))
        interviews = stats.get("interviews_scheduled", 0)
        msg = f"You have {total} tracked application(s)"
        if interviews:
            msg += f", including {interviews} with interview scheduled"
        msg += "."

        return {
            "type": "application_status",
            "message": msg,
            "applications": apps[:20],
        }

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

        # Check for years_experience
        if self._profile_value(profile, "years_experience") or self._profile_value(profile, "cv_status") == "parsed":
            blocked.append("experience")

        # Check for preferred_cities
        if self._profile_value(profile, "preferred_cities") or self._profile_value(profile, "cities"):
            blocked.append("location")

        # Check for skills or industries
        if self._profile_value(profile, "skills") or self._profile_value(profile, "industries"):
            blocked.append("industry")

        return blocked

    def _remove_blocked_questions(self, response: str, blocked_questions: list[str]) -> str:
        """Remove blocked question patterns from AI response."""
        if not response or not blocked_questions:
            return response

        lines = response.split("\n")
        filtered_lines = []
        skip_next = False

        for line in lines:
            lower_line = line.lower()

            # Skip if line contains blocked question patterns
            should_skip = False
            for blocked in blocked_questions:
                if blocked == "experience" and any(pattern in lower_line for pattern in [
                    "experience level", "years experience", "entry/mid/senior", "experience?"
                ]):
                    should_skip = True
                    break
                elif blocked == "location" and any(pattern in lower_line for pattern in [
                    "location", "city", "where", "uae city"
                ]):
                    should_skip = True
                    break
                elif blocked == "industry" and any(pattern in lower_line for pattern in [
                    "industry", "sector", "field"
                ]):
                    should_skip = True
                    break

            if should_skip:
                continue

            filtered_lines.append(line)

        return "\n".join(filtered_lines).strip()

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
