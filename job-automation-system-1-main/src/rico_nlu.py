"""Natural language understanding for Rico AI.

Rico should feel intuitive: users can speak naturally in English, Arabic,
Arabizi, or mixed language. This module detects language, intent, entities,
and preference updates before the chat controller decides what action to take.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RicoNLUResult:
    language: str = "en"
    intent: str = "general"
    confidence: float = 0.5
    entities: Dict[str, object] = field(default_factory=dict)
    normalized_message: str = ""


class RicoNLU:
    """Rule-first NLU with clear upgrade path to LLM/tool-calling."""

    UAE_CITIES = [
        "dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah",
        "fujairah", "umm al quwain", "دبي", "أبوظبي", "ابوظبي",
        "الشارقة", "عجمان",
    ]

    INTENT_KEYWORDS = {
        "search_jobs": [
            "find jobs", "search jobs", "show jobs", "recommend jobs", "jobs for me",
            "وظائف", "شغل", "فرص", "دور على", "ابحث", "عايز شغل", "اريد وظيفة",
        ],
        "apply": ["apply", "apply now", "submit", "قدم", "تقديم", "ابعت", "ارسل"],
        "save": ["save", "bookmark", "keep", "احفظ", "خزن"],
        "ignore": ["ignore", "skip", "not interested", "تجاهل", "مش مناسب"],
        "cover_letter": ["cover letter", "application message", "رسالة تقديم", "خطاب"],
        "interview_prep": ["interview", "prepare me", "مقابلة", "انترفيو", "جهزني"],
        "change_preferences": ["change preferences", "update preferences", "change salary", "change city", "غير", "عدل", "تحديث", "راتب", "مدينة"],
        "status": ["status", "track", "application status", "حالة", "متابعة"],
        "help": ["help", "what can you do", "مساعدة", "تقدر تعمل ايه"],
    }

    ROLE_HINTS = [
        "manager", "officer", "engineer", "specialist", "coordinator", "assistant",
        "director", "analyst", "executive", "consultant", "hse", "qhse", "ehs",
        "marketing", "sales", "accountant", "hr", "operations", "safety",
    ]

    def parse(self, message: str) -> RicoNLUResult:
        normalized = self._normalize(message)
        language = self._detect_language(message)
        intent, confidence = self._detect_intent(normalized)
        entities = self._extract_entities(normalized)
        return RicoNLUResult(language=language, intent=intent, confidence=confidence, entities=entities, normalized_message=normalized)

    def _normalize(self, message: str) -> str:
        return re.sub(r"\s+", " ", message.strip().lower())

    def _detect_language(self, message: str) -> str:
        arabic_chars = re.findall(r"[\u0600-\u06FF]", message)
        latin_chars = re.findall(r"[A-Za-z]", message)
        if arabic_chars and latin_chars:
            return "mixed"
        if arabic_chars:
            return "ar"
        return "en"

    def _detect_intent(self, normalized: str) -> tuple[str, float]:
        best_intent = "general"
        best_score = 0
        for intent, keywords in self.INTENT_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in normalized)
            if score > best_score:
                best_score = score
                best_intent = intent
        if best_score == 0:
            return "general", 0.4
        return best_intent, min(0.95, 0.55 + best_score * 0.15)

    def _extract_entities(self, normalized: str) -> Dict[str, object]:
        entities: Dict[str, object] = {}
        cities = [city for city in self.UAE_CITIES if city in normalized]
        if cities:
            entities["preferred_cities"] = cities
        salary = self._extract_salary(normalized)
        if salary:
            entities["salary_expectation_aed"] = salary
        years = self._extract_years_experience(normalized)
        if years is not None:
            entities["years_experience"] = years
        roles = self._extract_roles(normalized)
        if roles:
            entities["target_roles"] = roles
        skills = self._extract_skills(normalized)
        if skills:
            entities["skills"] = skills
        return entities

    def _extract_salary(self, normalized: str) -> Optional[int]:
        for pattern in [r"(?:aed|dirham|درهم)?\s*(\d{2,3})\s*k", r"(?:aed|dirham|درهم)\s*(\d{4,6})", r"(\d{4,6})\s*(?:aed|dirham|درهم)"]:
            match = re.search(pattern, normalized)
            if match:
                amount = int(match.group(1))
                return amount * 1000 if amount < 1000 else amount
        return None

    def _extract_years_experience(self, normalized: str) -> Optional[float]:
        for pattern in [r"(\d+(?:\.\d+)?)\+?\s*(?:years|yrs|year|سنوات|سنة)", r"experience\s*(?:of)?\s*(\d+(?:\.\d+)?)"]:
            match = re.search(pattern, normalized)
            if match:
                return float(match.group(1))
        return None

    def _extract_roles(self, normalized: str) -> List[str]:
        roles = [hint.title() for hint in self.ROLE_HINTS if hint in normalized]
        for pattern in [r"(?:need|want|looking for|searching for)\s+(.+?)\s+(?:jobs|roles|in|with|salary|for)", r"(?:وظائف|شغل)\s+(.+?)\s+(?:في|براتب|مع)"]:
            match = re.search(pattern, normalized)
            if match:
                candidate = match.group(1).strip()
                if 2 <= len(candidate) <= 60:
                    roles.append(candidate.title())
        return list(dict.fromkeys(roles))[:5]

    def _extract_skills(self, normalized: str) -> List[str]:
        common_skills = ["hse", "qhse", "ehs", "safety", "iso", "audit", "compliance", "risk assessment", "marketing", "seo", "google ads", "meta ads", "salesforce", "excel", "power bi", "python", "sql", "project management", "operations", "crm"]
        return [skill for skill in common_skills if skill in normalized]
