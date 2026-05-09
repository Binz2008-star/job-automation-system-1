"""Rico conversational AI API.

This module transforms the existing automation system into a chat-first
career agent. Rico accepts natural language messages, updates memory,
triggers workflows, and responds with autonomous actions.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from src.rico_agent import RicoAgent
from src.rico_memory import RicoMemoryStore
from src.rico_repo_adapter import RicoSystem


CV_FILE_RE = re.compile(r"\b[\w .()_-]+\.(?:pdf|docx?|txt)\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


class RicoChatAPI:
    """Simple conversational controller for Rico AI."""

    def __init__(self) -> None:
        self.memory = RicoMemoryStore()
        self.agent = RicoAgent(profile_store=self.memory)
        self.system = RicoSystem()

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
        profile = self.memory.upsert_profile_from_dict(user_id=user_id, updates=updates)

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

    def process_message(self, user_id: str, message: str) -> Dict[str, Any]:
        """Main Rico chat entrypoint."""
        self.memory.append_chat_message(user_id, "user", message)

        profile = self.memory.load_profile(user_id)

        # CV uploads override first-time onboarding and the manual profile wizard.
        if self._looks_like_cv_upload(message):
            return self._cv_first_profile_response(user_id, message)

        # First-time onboarding shortcut.
        if profile is None:
            profile = self.memory.upsert_profile_from_dict(
                user_id=user_id,
                updates={
                    "name": user_id,
                },
            )
            response = {
                "type": "onboarding",
                "message": (
                    "Welcome to Rico AI. Upload your CV or tell me your target role, UAE city preferences, "
                    "and salary expectations. If you upload a CV, I will pre-fill the profile and only ask "
                    "for anything missing or unclear."
                ),
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return response

        lower = message.lower()

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
            return response

        if any(phrase in lower for phrase in ["extract", "from the cv", "take it from", "use my cv", "use the cv"]):
            return self._cv_first_profile_response(user_id, message)

        if "change salary" in lower or "salary" in lower:
            response = {
                "type": "preferences",
                "message": "I updated your salary preferences. I will prioritize stronger salary matches.",
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return response

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
            return response

        if "apply" in lower:
            response = {
                "type": "application",
                "message": (
                    "I can prepare a tailored application message and cover letter. "
                    "I will also track the application status for follow-up reminders."
                ),
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return response

        if "interview" in lower:
            response = {
                "type": "interview_prep",
                "message": (
                    "I will generate interview preparation notes, likely questions, "
                    "company insights, and suggested answers based on the role."
                ),
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return response

        response = {
            "type": "assistant",
            "message": (
                "I understand. I can search UAE jobs, explain matches, track applications, "
                "prepare cover letters, and help with interview preparation."
            ),
        }

        self.memory.append_chat_message(user_id, "assistant", response["message"])
        return response


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
