"""Safety guardrails for Rico AI.

Rico is an autonomous career agent. This module keeps Rico out of dangerous
zones while dealing with users by classifying risky requests, protecting user
privacy, and restricting high-impact actions such as applying to jobs without
clear permission.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RicoSafetyResult:
    allowed: bool
    category: str = "safe"
    severity: str = "none"
    reason: Optional[str] = None
    safe_response: Optional[str] = None
    required_user_confirmation: bool = False
    metadata: Dict[str, object] = field(default_factory=dict)


class RicoSafetyGuard:
    """Safety and trust layer for Rico AI."""

    DANGEROUS_AUTOMATION_PATTERNS = [
        r"apply\s+to\s+all",
        r"auto\s*apply\s+everything",
        r"submit\s+without\s+asking",
        r"fake\s+experience",
        r"lie\s+on\s+my\s+cv",
        r"make\s+up\s+experience",
        r"create\s+fake\s+certificate",
        r"forge",
    ]

    PRIVACY_RISK_PATTERNS = [
        r"share\s+my\s+passport",
        r"send\s+my\s+emirates\s+id",
        r"send\s+my\s+bank",
        r"password",
        r"otp",
        r"one\s*time\s*password",
        r"credit\s+card",
    ]

    HARASSMENT_OR_ILLEGAL_PATTERNS = [
        r"spam\s+recruiters",
        r"scrape\s+private",
        r"bypass",
        r"hack",
        r"threaten",
        r"harass",
    ]

    DISCRIMINATION_PATTERNS = [
        r"only\s+(men|women|male|female)",
        r"reject\s+(men|women|male|female)",
        r"avoid\s+.*nationality",
        r"religion",
        r"race",
    ]

    HIGH_IMPACT_ACTIONS = {
        "apply",
        "submit_application",
        "send_recruiter_message",
        "send_cover_letter",
        "share_cv",
        "share_phone",
        "share_email",
    }

    def check_message(self, message: str) -> RicoSafetyResult:
        text = message.lower().strip()

        if self._matches_any(text, self.PRIVACY_RISK_PATTERNS):
            return RicoSafetyResult(
                allowed=False,
                category="privacy_risk",
                severity="high",
                reason="The request may expose sensitive personal information.",
                safe_response=(
                    "I cannot share passwords, OTPs, bank details, passport details, "
                    "or Emirates ID information. I can help prepare a safe job application "
                    "using only approved professional information from your CV."
                ),
            )

        if self._matches_any(text, self.DANGEROUS_AUTOMATION_PATTERNS):
            return RicoSafetyResult(
                allowed=False,
                category="unsafe_job_automation",
                severity="high",
                reason="The request asks Rico to misrepresent information or act without approval.",
                safe_response=(
                    "I cannot fake experience, forge documents, or submit applications without clear approval. "
                    "I can help create honest, tailored applications based on your real profile."
                ),
            )

        if self._matches_any(text, self.HARASSMENT_OR_ILLEGAL_PATTERNS):
            return RicoSafetyResult(
                allowed=False,
                category="abuse_or_illegal_request",
                severity="high",
                reason="The request may involve harassment, unauthorized access, or abusive behavior.",
                safe_response=(
                    "I cannot help with spam, harassment, bypassing systems, or unauthorized access. "
                    "I can help with professional recruiter outreach and compliant job applications."
                ),
            )

        if self._matches_any(text, self.DISCRIMINATION_PATTERNS):
            return RicoSafetyResult(
                allowed=False,
                category="discrimination_risk",
                severity="medium",
                reason="The request may involve discriminatory filtering.",
                safe_response=(
                    "I cannot filter or recommend jobs using protected characteristics. "
                    "I can filter by role, salary, location, visa requirements, skills, industry, and work mode."
                ),
            )

        return RicoSafetyResult(allowed=True)

    def check_action(self, action: str, user_has_approved: bool = False) -> RicoSafetyResult:
        normalized = action.lower().strip().replace(" ", "_")

        if normalized in self.HIGH_IMPACT_ACTIONS and not user_has_approved:
            return RicoSafetyResult(
                allowed=False,
                category="approval_required",
                severity="medium",
                reason="High-impact career action requires explicit user approval.",
                safe_response="Please confirm before I send, submit, or share anything on your behalf.",
                required_user_confirmation=True,
            )

        return RicoSafetyResult(allowed=True)

    def redact_sensitive_data(self, text: str) -> str:
        """Redact common sensitive information before logging or model calls."""
        redacted = text
        redacted = re.sub(r"\b\d{3}-?\d{2}-?\d{4}\b", "[REDACTED_ID]", redacted)
        redacted = re.sub(r"\b\d{12,19}\b", "[REDACTED_NUMBER]", redacted)
        redacted = re.sub(r"(?i)(password|otp|pin)\s*[:=]\s*\S+", r"\1=[REDACTED]", redacted)
        return redacted

    def safe_system_rules(self) -> List[str]:
        return [
            "Never fake experience, education, certifications, salary, visa status, or identity.",
            "Never submit applications or send recruiter messages without explicit user approval unless the user's autonomy setting allows it and the action is low risk.",
            "Never share passwords, OTPs, bank information, passport details, or Emirates ID details.",
            "Never make discriminatory recommendations based on protected characteristics.",
            "Prefer truthful, professional, consent-based job-search assistance.",
            "Explain job matches clearly and allow users to override preferences at any time.",
        ]

    def _matches_any(self, text: str, patterns: List[str]) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)
