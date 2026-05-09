"""High-standard quality controls for Rico AI.

This module defines the operating standard for Rico as a trusted AI hiring
partner. It adds response quality checks, recommendation standards, trust
principles, and product-level expectations before Rico sends content to users.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RicoQualityResult:
    passed: bool
    score: int
    issues: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)


class RicoQualityGate:
    """Quality gate for Rico messages, recommendations, and actions."""

    MIN_RECOMMENDATION_SCORE = 55
    MIN_STRONG_MATCH_SCORE = 75

    def check_recommendation(self, recommendation: Dict[str, Any]) -> RicoQualityResult:
        issues: List[str] = []
        improvements: List[str] = []
        score = 100

        if not recommendation.get("title"):
            issues.append("Missing job title")
            score -= 20
        if not recommendation.get("company"):
            issues.append("Missing company")
            score -= 15
        if not recommendation.get("why") and not recommendation.get("rico_explanation"):
            issues.append("Missing match explanation")
            score -= 25
        if recommendation.get("score") is None and recommendation.get("rico_score") is None:
            issues.append("Missing Rico match score")
            score -= 20
        if not recommendation.get("actions"):
            improvements.append("Add clear next-step buttons")
            score -= 10

        return RicoQualityResult(passed=score >= 70 and not issues, score=max(score, 0), issues=issues, improvements=improvements)

    def check_user_response(self, response: Dict[str, Any]) -> RicoQualityResult:
        issues: List[str] = []
        improvements: List[str] = []
        score = 100
        message = str(response.get("message", "")).strip()

        if not message:
            issues.append("Missing assistant message")
            score -= 40
        if "guarantee" in message.lower() and "job" in message.lower():
            issues.append("Avoid guaranteeing employment outcomes")
            score -= 35
        if len(message) > 1200:
            improvements.append("Shorten response for chat readability")
            score -= 10
        if response.get("type") == "job_matches" and not response.get("matches"):
            improvements.append("Explain why no matches were found and suggest preference changes")
            score -= 15

        return RicoQualityResult(passed=score >= 75 and not issues, score=max(score, 0), issues=issues, improvements=improvements)

    def improve_empty_matches_response(self) -> Dict[str, Any]:
        return {
            "type": "no_matches",
            "message": (
                "I did not find a strong match yet. I will keep searching, but you may get better results "
                "by widening one of these: preferred city, salary range, target title, or industry."
            ),
            "suggested_actions": [
                "Broaden preferred cities",
                "Lower minimum salary slightly",
                "Add related job titles",
                "Show broader matches",
            ],
        }


RICO_HIGH_STANDARD_PRINCIPLES = [
    "Every recommendation needs a reason, score, and next step.",
    "Rico should protect the user before optimizing for speed.",
    "Rico should prioritize strong matches over long lists.",
    "Rico should be warm but not dishonest or overpromising.",
    "Rico should remember user choices and learn from outcomes.",
    "Rico should keep the user in control of applications and personal data.",
]
