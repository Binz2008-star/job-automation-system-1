"""Rico conversational AI API.

This module transforms the existing automation system into a chat-first
career agent. Rico accepts natural language messages, updates memory,
triggers workflows, and responds with autonomous actions.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from dataclasses import asdict, is_dataclass

from src.rico_agent import RicoAgent
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
from src.models.onboarding import ONBOARDING_IN_PROGRESS


CV_FILE_RE = re.compile(r"\b[\w .()_-]+\.(?:pdf|docx?|txt)\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
BARE_ROLE_RE = re.compile(r"^[A-Za-z][A-Za-z\s/&+-]{2,80}$")


class RicoChatAPI:
    """Simple conversational controller for Rico AI."""

    def __init__(self) -> None:
        self.memory = RicoMemoryStore()
        self.agent = RicoAgent(profile_store=self.memory)
        self.system = RicoSystem()
        self.openai_agent = RicoOpenAIAgent()

    @staticmethod
    def _build_openai_context(profile: Any) -> Dict[str, Any]:
        if profile is None:
            return {"profile_exists": False}
        if is_dataclass(profile):
            raw = asdict(profile)
        elif isinstance(profile, dict):
            raw = dict(profile)
        else:
            raw = {k: getattr(profile, k) for k in dir(profile) if not k.startswith("_")}
        return {
            "profile_exists": True,
            **{k: v for k, v in raw.items() if v not in (None, "", [], {})},
        }

    @staticmethod
    def _profile_value(profile: Any, key: str, default: Any = None) -> Any:
        if profile is None:
            return default
        if isinstance(profile, dict):
            return profile.get(key, default)
        return getattr(profile, key, default)

    @staticmethod
    def _has_cv_profile(profile: Any) -> bool:
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
    def _as_list(value: Any) -> List[Any]:
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
    def _format_match(m: Dict[str, Any], profile: Any) -> Dict[str, Any]:
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
    def _source_for_openai_response(response: Dict[str, Any]) -> str:
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
        response: Dict[str, Any],
        source: str,
        *,
        profile: Any = None,
    ) -> Dict[str, Any]:
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

    def _extract_inline_contact_updates(self, message: str) -> Dict[str, Any]:
        updates: Dict[str, Any] = {}
        emails = EMAIL_RE.findall(message)
        phones = PHONE_RE.findall(message)
        if emails:
            updates["email"] = emails[0]
        if phones:
            updates["phone"] = phones[0].strip()
        return updates

    def _cv_first_profile_response(self, user_id: str, message: str) -> Dict[str, Any]:
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
            label
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
        self.memory.append_chat_message(user_id, "assistant", json.dumps(response))
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

    def _target_role_search_response(self, user_id: str, role: str, profile: Any) -> Dict[str, Any]:
        target_roles = self._as_list(self._profile_value(profile, "target_roles"))
        if role and role.lower() not in {str(item).lower() for item in target_roles}:
            target_roles.append(role)
            profile = upsert_profile(user_id=user_id, updates={"target_roles": target_roles})

        workflow_result = self.system.run_for_profile(profile)
        top_matches = workflow_result.get("matches", [])[:5]
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

        message = (
            f"Got it — I will target {role} roles{city_text}{basis_text}. "
            f"I found {len(top_matches)} current strong matches."
            if top_matches
            else f"Got it — I will target {role} roles{city_text}{basis_text}. I did not find strong matches yet, so I will keep scanning and use this profile for future matches."
        )

        response = {
            "type": "job_matches",
            "intent": "search_jobs",
            "message": message,
            "matches": formatted,
            "entities": {"job_title": role, "from_cv_profile": True},
        }
        self.memory.append_chat_message(user_id, "assistant", json.dumps(response))
        return response

    def process_message(self, user_id: str, message: str) -> Dict[str, Any]:
        self.memory.append_chat_message(user_id, "user", message)
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
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=None)

        mark_onboarding_complete(user_id)
        return self._handle_active_user(user_id, message)

    def _handle_active_user(self, user_id: str, message: str) -> Dict[str, Any]:
        profile = get_profile(user_id)
        lower = message.lower()

        # ── Always-on fast paths (before router) ──────────────────────────────

        if any(phrase in lower for phrase in self._WHATS_NEXT_PHRASES):
            self.memory.append_chat_message(
                user_id, "assistant", json.dumps(self._JOB_SEARCH_OPTIONS)
            )
            return self._finalize(self._JOB_SEARCH_OPTIONS, self.SOURCE_KEYWORD, profile=profile)

        if any(phrase in lower for phrase in ["skip this question", "don't know", "do not know"]):
            response = {
                "type": "profile_skip",
                "message": (
                    "Skipped. I will leave that field blank and continue without forcing it. "
                    "You can update it later."
                ),
                "field_status": "skipped",
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        if any(phrase in lower for phrase in ["extract", "from the cv", "take it from", "use my cv", "use the cv"]):
            return self._finalize(
                self._cv_first_profile_response(user_id, message),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        if self._looks_like_cv_upload(message):
            return self._finalize(
                self._cv_first_profile_response(user_id, message),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        if self._has_cv_profile(profile) and self._looks_like_bare_target_role(message):
            return self._finalize(
                self._target_role_search_response(user_id, message.strip(), profile),
                self.SOURCE_KEYWORD,
                profile=profile,
            )

        # ── Intent router ─────────────────────────────────────────────────────

        context = self._build_router_context(user_id, profile)
        from src.rico_intent_router import route as _route
        routed = _route(message, user_id=user_id, context=context)

        # Help / menu
        if routed.intent == "help":
            self.memory.append_chat_message(
                user_id, "assistant", json.dumps(self._JOB_SEARCH_OPTIONS)
            )
            return self._finalize(self._JOB_SEARCH_OPTIONS, self.SOURCE_KEYWORD, profile=profile)

        # apply_job: gate on explicit confirmation before touching agent_runtime
        if routed.intent == "apply_job":
            response = {
                "type": "confirmation_required",
                "intent": "apply_job",
                "message": routed.confirmation_prompt or (
                    "To confirm: mark this job as applied and track it. "
                    "Reply YES to confirm or CANCEL to abort."
                ),
                "tool_args": routed.tool_args,
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return self._finalize(response, routed.source, profile=profile)

        # Tool-executable intents: delegate to agent_runtime
        if routed.tool_name and routed.intent not in {"search_jobs", "update_preferences", "prepare_interview", "unknown"}:
            job_key = routed.tool_args.get("job_key", "")
            from src.agent.runtime import agent_runtime
            result = agent_runtime.handle_action(
                user_id=user_id,
                action=routed.intent.replace("_job", "").replace("_message", ""),
                job_key=job_key,
                source="chat",
            )
            response = {
                "type": routed.intent,
                "intent": routed.intent,
                "message": result.message,
                "entities": routed.entities,
                "confidence": routed.confidence,
            }
            self.memory.append_chat_message(user_id, "assistant", result.message)
            return self._finalize(response, routed.source, profile=profile)

        # search_jobs: run workflow with extracted entities
        if routed.intent == "search_jobs":
            workflow_result = self.system.run_for_profile(profile)
            top_matches = workflow_result.get("matches", [])[:5]
            formatted = [self._format_match(m, profile) for m in top_matches]
            response = {
                "type": "job_matches",
                "intent": "search_jobs",
                "message": "I found {} strong UAE job matches for you.".format(len(top_matches)),
                "matches": formatted,
                "entities": routed.entities,
            }
            self.memory.append_chat_message(user_id, "assistant", json.dumps(response))
            return self._finalize(response, routed.source, profile=profile)

        # update_preferences: apply extracted entities to profile
        if routed.intent == "update_preferences":
            prefs = routed.tool_args.get("preferences", {})
            if prefs:
                upsert_profile(user_id=user_id, updates=prefs)
            response = {
                "type": "preferences_updated",
                "message": "Got it. I have updated your preferences and will apply them to future searches.",
                "updated": prefs,
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return self._finalize(response, routed.source, profile=profile)

        # prepare_interview: use HF for richer content
        if routed.intent == "prepare_interview":
            user_context = self._build_openai_context(profile)
            system_prompt = (
                "You are Rico, a UAE career coach. Give concise, practical interview preparation "
                "tips including likely questions, company research pointers, and answer frameworks."
            )
            from src.rico_hf_client import generate_text, is_available as hf_ok
            hf_text = None
            if hf_ok():
                hf_text = generate_text(message, system=system_prompt, max_new_tokens=400)
            msg = hf_text or (
                "I will prepare interview notes, likely questions, and suggested answers based on your target role. "
                "Share the specific job title or company name for a more tailored response."
            )
            response = {"type": "interview_prep", "message": msg}
            self.memory.append_chat_message(user_id, "assistant", msg)
            src = self.SOURCE_HF if hf_text else self.SOURCE_FALLBACK
            return self._finalize(response, src, profile=profile)

        # Fallback: unknown intent — check for role-like message with CV profile
        # If profile has CV data and message looks like a role, trigger search immediately
        if self._has_cv_profile(profile):
            # Extract potential role from message
            words = message.strip().split()
            # If message is short and looks like a role (no digits, reasonable length)
            if len(words) <= 6 and not any(ch.isdigit() for ch in message) and len(message.strip()) >= 2:
                potential_role = message.strip()
                # Trigger immediate search with this role
                return self._finalize(
                    self._target_role_search_response(user_id, potential_role, profile),
                    self.SOURCE_KEYWORD,
                    profile=profile,
                )

        # Otherwise, use HF for natural reply or templated fallback
        user_context = self._build_openai_context(profile)

        # Deterministic suppression: never ask about fields that already exist in profile
        blocked_questions = self._get_blocked_questions(profile)
        if isinstance(user_context, dict):
            user_context["blocked_questions"] = blocked_questions

        ai_response = self._get_openai_agent().respond(message, user_context=user_context)

        # Post-process AI response to remove any blocked questions that slipped through
        ai_response["message"] = self._remove_blocked_questions(ai_response.get("message", ""), blocked_questions)

        self.memory.append_chat_message(user_id, "assistant", ai_response.get("message", ""))
        return self._finalize(ai_response, self._source_for_openai_response(ai_response), profile=profile)

    def _get_blocked_questions(self, profile: Any) -> List[str]:
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

    def _remove_blocked_questions(self, response: str, blocked_questions: List[str]) -> str:
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
                from dataclasses import asdict, is_dataclass
                ctx["profile"] = asdict(profile) if is_dataclass(profile) else dict(profile)
            except Exception:
                pass
        return ctx


def demo() -> None:
    api = RicoChatAPI()

    messages: List[str] = [
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
