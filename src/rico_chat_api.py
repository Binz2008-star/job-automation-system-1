"""Rico conversational AI API.

This module transforms the existing automation system into a chat-first
career agent. Rico accepts natural language messages, updates memory,
triggers workflows, and responds with autonomous actions.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from src.rico_agent import RicoAgent
from src.rico_memory import RicoMemoryStore
from src.rico_repo_adapter import RicoSystem


class RicoChatAPI:
    """Simple conversational controller for Rico AI."""

    def __init__(self) -> None:
        self.memory = RicoMemoryStore()
        self.agent = RicoAgent(profile_store=self.memory)
        self.system = RicoSystem()

    def process_message(self, user_id: str, message: str) -> Dict[str, Any]:
        """Main Rico chat entrypoint."""
        self.memory.append_chat_message(user_id, "user", message)

        profile = self.memory.load_profile(user_id)

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
                    "Welcome to Rico AI. Tell me your target role, UAE city preferences, "
                    "salary expectations, and upload your CV so I can begin searching jobs for you."
                ),
            }
            self.memory.append_chat_message(user_id, "assistant", response["message"])
            return response

        lower = message.lower()

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
