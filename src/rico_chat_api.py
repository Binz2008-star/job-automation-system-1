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


class RicoChatAPI:
    """Simple conversational controller for Rico AI."""

    def __init__(self) -> None:
        self.memory = RicoMemoryStore()
        self.agent = RicoAgent(profile_store=self.memory)
        self.system = RicoSystem()
        self.openai_agent = RicoOpenAIAgent()

    @staticmethod
    def _build_openai_context(profile: Any) -> Dict[str, Any]:
        """Convert a loaded profile into a JSON-serialisable context dict for the LLM.

        Drops empty/None fields so the prompt stays focused on what is actually
        known about the user. Returns ``{"profile_exists": False}`` when the
        user has no saved profile yet.
        """
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

    # Stable enum of where a chat reply originated. The frontend never sees
    # secrets — only this label, the model name, and presence booleans.
    SOURCE_KEYWORD = "keyword"
    SOURCE_OPENAI = "openai"
    SOURCE_HF = "huggingface"
    SOURCE_FALLBACK = "fallback"

    @staticmethod
    def _source_for_openai_response(response: Dict[str, Any]) -> str:
        """Map a RicoOpenAIAgent response to the correct source label.

        openai_response → ``openai``
        hf_response     → ``huggingface``
        everything else → ``fallback``
        """
        rtype = response.get("type")
        if rtype == "openai_response":
            return RicoChatAPI.SOURCE_OPENAI
        if rtype == "hf_response":
            return RicoChatAPI.SOURCE_HF
        return RicoChatAPI.SOURCE_FALLBACK

    def _finalize(
        self,
        response: Dict[str, Any],
        source: str,
        *,
        profile: Any = None,
    ) -> Dict[str, Any]:
        """Return a copy of ``response`` with safe diagnostic metadata attached.

        Adds:
          * ``response_source``  — keyword | openai | huggingface | fallback
          * ``provider``         — openai | huggingface | fallback
          * ``openai_available`` — whether OPENAI_API_KEY (or legacy OPEN_AI_API) is set
          * ``hf_available``     — whether HF_API_KEY / HF_TOKEN / HUGGINGFACE_API_KEY is set
          * ``openai_model``     — model name only, never the key
          * ``profile_context_present`` — whether a loaded profile was available

        Never returns the API key, the user's profile contents, or the user's
        message. The new dict is fresh so class-level constants like
        ``_JOB_SEARCH_OPTIONS`` are not mutated.
        """
        return {
            **response,
            "response_source": source,
            "provider": response.get("provider", source),
            "openai_available": self.openai_agent.available,
            "hf_available": self.openai_agent.hf_available,
            "openai_model": self.openai_agent.model,
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
        """Switch profile setup into CV-first mode instead of long manual forms.

        The actual file bytes are normally handled by the upload/webhook layer.
        This guard prevents Rico from continuing the manual wizard after a CV
        filename or CV-upload event reaches chat.
        """
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
                ("salary_expectation", "salary expectation"),
                ("avoid", "roles or companies to avoid"),
            ]
            if not getattr(profile, key, None) and not (isinstance(profile, dict) and profile.get(key))
        ]

        response = {
            "type": "cv_first_profile",
            "message": (
                f"I received {filename}. I will use the CV-first profile flow: extract every available detail "
                "from the CV, pre-fill the career profile, and only ask for missing or unclear fields. "
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

    def process_message(self, user_id: str, message: str) -> Dict[str, Any]:
        """Main Rico chat entrypoint."""
        self.memory.append_chat_message(user_id, "user", message)

        # ── Load server-side onboarding state first ───────────────────────────
        # This is the authoritative source. A completed user must never be sent
        # back through onboarding even if their local profile JSON is missing.
        completed = is_onboarding_complete(user_id)

        if completed:
            return self._handle_active_user(user_id, message)

        # ── CV uploads override onboarding entirely ───────────────────────────
        if self._looks_like_cv_upload(message):
            mark_onboarding_complete(user_id)
            return self._finalize(
                self._cv_first_profile_response(user_id, message),
                self.SOURCE_KEYWORD,
                profile=None,
            )

        # ── First-time onboarding ─────────────────────────────────────────────
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

        # ── Profile exists but onboarding not yet marked complete in DB ───────
        mark_onboarding_complete(user_id)
        return self._handle_active_user(user_id, message)

    def _handle_active_user(self, user_id: str, message: str) -> Dict[str, Any]:
        """Handle messages from users who have completed onboarding."""
        profile = get_profile(user_id)
        lower = message.lower()

        # "what's next?" → always return job-search options, never onboarding
        if any(phrase in lower for phrase in self._WHATS_NEXT_PHRASES):
            self.memory.append_chat_message(
                user_id, "assistant", json.dumps(self._JOB_SEARCH_OPTIONS)
            )
            return self._finalize(self._JOB_SEARCH_OPTIONS, self.SOURCE_KEYWORD, profile=profile)

        if any(phrase in lower for phrase in ["skip this question", "skip", "don't know", "do not know"]):
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

        if "change salary" in lower or "salary" in lower:
            response = {
                "type": "preferences",
                "message": "I updated your salary preferences. I will prioritize stronger salary matches.",
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        if any(keyword in lower for keyword in ["find jobs", "search jobs", "jobs", "recommend"]):
            workflow_result = self.system.run_for_profile(profile)
            top_matches = workflow_result.get("matches", [])[:5]

            formatted = []
            for match in top_matches:
                formatted.append({
                    "title": match.get("title"),
                    "company": match.get("company"),
                    "location": match.get("location"),
                    "score": match.get("rico_score"),
                    "why": match.get("rico_explanation"),
                    "actions": [
                        "Apply Now",
                        "Save",
                        "Ignore",
                        "See Details",
                        "Write Cover Letter",
                        "Prepare Interview",
                    ],
                })

            response = {
                "type": "job_matches",
                "message": f"I found {len(top_matches)} strong UAE job matches for you.",
                "matches": formatted,
            }
            self.memory.append_chat_message(user_id, "assistant", json.dumps(response))
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        if "apply" in lower:
            response = {
                "type": "application",
                "message": (
                    "I can prepare a tailored application message and cover letter. "
                    "I will also track the application status for follow-up reminders."
                ),
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        if "interview" in lower:
            response = {
                "type": "interview_prep",
                "message": (
                    "I will generate interview preparation notes, likely questions, "
                    "company insights, and suggested answers based on the role."
                ),
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return self._finalize(response, self.SOURCE_KEYWORD, profile=profile)

        # Open-ended message — delegate to the OpenAI reasoning layer with the
        # user's profile as context. RicoOpenAIAgent.respond() already handles
        # the missing-key path with a safe templated fallback, so this is a
        # no-op upgrade when OPENAI_API_KEY is not configured.
        user_context = self._build_openai_context(profile)
        response = self.openai_agent.respond(message, user_context=user_context)
        self.memory.append_chat_message(user_id, "assistant", response.get("message", ""))
        return self._finalize(response, self._source_for_openai_response(response), profile=profile)


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
