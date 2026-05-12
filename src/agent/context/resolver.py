"""src/agent/context/resolver.py

Profile context resolver for Rico agent.

Loads user profile from DB, hydrates from CV/Jotform/chat/actions,
computes missing fields, and prevents repeated questions.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from typing import Any
from collections import defaultdict

try:
    import spacy
    from spacy.matcher import Matcher
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("spaCy not available, chat hydration will be limited")

from src.rico_agent import RicoProfile, RicoAgentSettings
from src.repositories.profile_repo import get_profile, upsert_profile
from src.repositories.audit_repo import get_recent, write_audit_log

logger = logging.getLogger(__name__)
_UTC = timezone.utc

# Completeness threshold - stop asking optional fields above this score
COMPLETENESS_THRESHOLD = 0.9

# Minimum count threshold for inferred roles (prevent spray-and-pray)
MIN_ROLE_APPLY_COUNT = 2

# UAE-specific location entities
UAE_CITIES = {
    "dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah",
    "fujairah", "umm al quwain", "al ain"
}

UAE_INDUSTRIES = {
    "oil & gas", "construction", "technology", "fintech", "healthcare",
    "logistics", "retail", "ecommerce", "real estate", "hospitality",
    "ai", "software", "trading", "saas"
}

# Field weights for completeness scoring (0-1)
_FIELD_WEIGHTS = {
    # Required fields (70% of total score)
    "email": 0.15,
    "target_roles": 0.20,
    "preferred_cities": 0.15,
    "skills": 0.20,
    # Optional fields (30% of total score)
    "years_experience": 0.08,
    "salary_expectation_aed": 0.06,
    "visa_status": 0.05,
    "notice_period": 0.04,
    "linkedin_url": 0.02,
    "portfolio_url": 0.02,
    "preferred_industries": 0.08,
    "english_level": 0.03,
    "arabic_level": 0.02,
}

# Fields that should never be asked about if already present
_REQUIRED_FIELDS: set[str] = {
    "email",
    "target_roles",
    "preferred_cities",
    "skills",
}

# Fields that are nice to have but optional
_OPTIONAL_FIELDS: set[str] = {
    "years_experience",
    "salary_expectation_aed",
    "visa_status",
    "notice_period",
    "linkedin_url",
    "portfolio_url",
    "preferred_industries",
    "english_level",
    "arabic_level",
}

# Fields that should be inferred from behavior rather than asked
_INFERRED_FIELDS: set[str] = {
    "deal_breakers",
    "green_flags",
    "red_flags",
}

# Initialize spaCy for entity extraction
_nlp = None
_location_matcher = None
_skill_matcher = None

if SPACY_AVAILABLE:
    try:
        _nlp = spacy.load("en_core_web_sm")
        _location_matcher = Matcher(_nlp.vocab)

        # Add UAE location patterns
        location_patterns = [
            [{"LOWER": {"IN": ["dubai", "dxb"]}}],
            [{"LOWER": {"IN": ["abu", "abudhabi"]}}, {"LOWER": "dhabi"}],
            [{"LOWER": {"IN": ["ajman", "sharjah", "ras", "fujairah"]}}],
            [{"LOWER": "ras"}, {"LOWER": "al"}, {"LOWER": "khaimah"}],
        ]
        _location_matcher.add("UAE_CITY", location_patterns)

        # Skill pattern matcher (common tech skills)
        _skill_patterns = [
            [{"LOWER": {"IN": ["python", "java", "javascript", "typescript", "react", "angular", "vue"]}}],
            [{"LOWER": {"IN": ["docker", "kubernetes", "aws", "azure", "gcp"]}}],
            [{"LOWER": {"IN": ["sql", "postgresql", "mongodb", "redis"]}}],
            [{"LOWER": {"IN": ["machine learning", "ai", "nlp", "data science"]}}],
        ]
        _skill_matcher = Matcher(_nlp.vocab)
        _skill_matcher.add("TECH_SKILL", _skill_patterns)

        logger.info("spaCy NLP initialized for context resolver")
    except Exception as e:
        _nlp = None
        logger.warning(f"spaCy initialization failed: {e}")


@dataclass
class ProfileContext:
    """Enriched profile context with hydration metadata."""
    profile: RicoProfile | None
    canonical_user_id: str
    completeness_score: float  # 0.0-1.0
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    hydration_sources: list[str] = field(default_factory=list)
    last_hydrated_at: datetime | None = None
    question_history: dict[str, datetime] = field(default_factory=dict)
    behavior_signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for AI context with field prioritization."""
        return {
            "profile": self.profile.__dict__ if self.profile else None,
            "completeness_score": self.completeness_score,
            "missing_required": self.missing_required,
            "missing_optional": self.missing_optional,
            "hydration_sources": self.hydration_sources,
            "should_ask_for": self._compute_questions_to_ask(),
            "top_preferences": self._get_top_preferences(),
        }

    def _compute_questions_to_ask(self) -> list[str]:
        """
        Compute which fields should be asked about now.

        Rules:
        - Never ask about fields already present
        - Never ask about fields asked in the last 24 hours
        - Prioritize required fields over optional
        - Skip fields that can be inferred from behavior
        - If completeness > threshold, skip optional fields entirely
        - Max 3 questions per turn
        """
        now = datetime.now(_UTC)
        to_ask: list[str] = []

        # Required fields first
        for field in sorted(self.missing_required):
            if field in _INFERRED_FIELDS:
                continue
            last_asked = self.question_history.get(field)
            if last_asked and (now - last_asked).total_seconds() < 86400:
                continue
            to_ask.append(field)

        # Optional fields only if:
        # 1. No required missing, AND
        # 2. Completeness below threshold (prevent pestering for minor fields)
        if not to_ask and self.completeness_score < COMPLETENESS_THRESHOLD:
            for field in sorted(self.missing_optional):
                if field in _INFERRED_FIELDS:
                    continue
                last_asked = self.question_history.get(field)
                if last_asked and (now - last_asked).total_seconds() < 86400:
                    continue
                to_ask.append(field)

        return to_ask[:3]  # Max 3 questions per turn

    def _get_top_preferences(self) -> dict[str, list[str]]:
        """Extract top preferences for AI context."""
        prefs = {}
        if self.profile and self.profile.target_roles:
            prefs["target_roles"] = self.profile.target_roles[:3]
        if self.profile and self.profile.preferred_cities:
            prefs["locations"] = self.profile.preferred_cities[:2]
        if self.profile and self.profile.skills:
            prefs["skills"] = self.profile.skills[:5]
        return prefs


class ProfileContextResolver:
    """
    Resolves and hydrates profile context from multiple sources.

    Hydration sources (in priority order):
    1. Database profile (canonical truth)
    2. CV extraction (high-confidence structured data)
    3. Jotform submission (user-provided structured data)
    4. Chat history (natural language extraction with NER)
    5. Action history (behavioral inference)
    """

    def __init__(self, cache_ttl_seconds: int = 3600):
        self._cache: dict[str, tuple[ProfileContext, datetime]] = {}
        self._cache_ttl = cache_ttl_seconds
        # Pending ask cache for write-read consistency (5-minute TTL)
        self._pending_ask_cache: dict[str, dict[str, datetime]] = defaultdict(dict)

    @lru_cache(maxsize=128)
    def _get_cached_profile(self, canonical_user_id: str) -> tuple[ProfileContext, datetime] | None:
        """LRU cache wrapper for profile retrieval."""
        if canonical_user_id in self._cache:
            cached, timestamp = self._cache[canonical_user_id]
            if (datetime.now(_UTC) - timestamp).total_seconds() < self._cache_ttl:
                return (cached, timestamp)
        return None

    def resolve(
        self,
        canonical_user_id: str,
        *,
        cv_data: dict[str, Any] | None = None,
        jotform_data: dict[str, Any] | None = None,
        chat_history: list[dict[str, Any]] | None = None,
        force_refresh: bool = False,
    ) -> ProfileContext:
        """
        Resolve profile context for a user.

        Args:
            canonical_user_id: Resolved user ID from IdentityResolver
            cv_data: Extracted data from CV parsing
            jotform_data: Normalized Jotform submission payload
            chat_history: Recent chat messages for context extraction
            force_refresh: Bypass cache and rehydrate

        Returns:
            ProfileContext with hydrated profile and metadata
        """
        # Check cache first
        if not force_refresh:
            cached_result = self._get_cached_profile(canonical_user_id)
            if cached_result:
                context, _ = cached_result
                return context

        # Load base profile from DB
        profile = get_profile(canonical_user_id)
        hydration_sources: list[str] = []

        if profile is None:
            profile = RicoProfile(user_id=canonical_user_id)
            hydration_sources.append("created_blank")

        # Track original fields to detect what was added
        original_fields = self._get_profile_fieldset(profile)

        # Hydrate from sources in priority order
        if cv_data:
            profile = self._hydrate_from_cv(profile, cv_data)
            hydration_sources.append("cv")

        if jotform_data:
            profile = self._hydrate_from_jotform(profile, jotform_data)
            hydration_sources.append("jotform")

        if chat_history and _nlp:
            profile = self._hydrate_from_chat(profile, chat_history)
            hydration_sources.append("chat")

        # Always hydrate from actions (non-destructive)
        profile = self._hydrate_from_actions(profile, canonical_user_id)
        if profile.behavior_signals:  # type: ignore
            hydration_sources.append("actions")

        # Persist only if fields changed
        new_fields = self._get_profile_fieldset(profile)
        if new_fields != original_fields:
            try:
                upsert_profile(user_id=canonical_user_id, updates=profile.__dict__)
                logger.debug(f"Profile persisted for {canonical_user_id}")
            except Exception as e:
                logger.error(f"Failed to persist profile: {e}")

        # Load question history from audit logs
        question_history = self._load_question_history(canonical_user_id)

        # Load behavior signals from action repository
        behavior_signals = self._load_behavior_signals(canonical_user_id)

        # Compute completeness with weighted scoring
        completeness, missing_required, missing_optional = self._compute_completeness(profile)

        context = ProfileContext(
            profile=profile,
            canonical_user_id=canonical_user_id,
            completeness_score=completeness,
            missing_required=missing_required,
            missing_optional=missing_optional,
            hydration_sources=hydration_sources,
            last_hydrated_at=datetime.now(_UTC),
            question_history=question_history,
            behavior_signals=behavior_signals,
        )

        # Cache the result
        self._cache[canonical_user_id] = (context, datetime.now(_UTC))

        logger.info(
            "profile_context_resolved user=%s completeness=%.2f sources=%s missing_required=%d",
            canonical_user_id,
            completeness,
            hydration_sources,
            len(missing_required),
        )

        return context

    def _get_profile_fieldset(self, profile: RicoProfile) -> set[str]:
        """Get set of populated fields in profile for change detection."""
        fields = set()
        for field in _REQUIRED_FIELDS | _OPTIONAL_FIELDS:
            value = getattr(profile, field, None)
            if value and (not isinstance(value, (list, str)) or len(value) > 0):
                fields.add(field)
        return fields

    def _hydrate_from_cv(self, profile: RicoProfile, cv_data: dict[str, Any]) -> RicoProfile:
        """Hydrate profile from CV extraction results."""
        updates = {}

        # Direct field mappings
        if cv_data.get("emails") and not profile.email:
            updates["email"] = cv_data["emails"][0]
        if cv_data.get("phones") and not profile.phone:
            updates["phone"] = cv_data["phones"][0]
        if cv_data.get("skills") and not profile.skills:
            updates["skills"] = cv_data["skills"][:20]  # Limit to top 20
        if cv_data.get("years_experience_hint") and not profile.years_experience:
            updates["years_experience"] = cv_data["years_experience_hint"]

        # Extract industries from CV
        if cv_data.get("industries") and not getattr(profile, "preferred_industries", None):
            updates["preferred_industries"] = cv_data["industries"][:5]

        # Infer target roles from experience section
        if not profile.target_roles and cv_data.get("experience"):
            roles = self._extract_roles_from_experience(cv_data["experience"])
            if roles:
                updates["target_roles"] = roles[:5]

        # Apply updates
        for key, value in updates.items():
            if hasattr(profile, key) and value:
                setattr(profile, key, value)

        return profile

    def _hydrate_from_jotform(self, profile: RicoProfile, jotform_data: dict[str, Any]) -> RicoProfile:
        """Hydrate profile from Jotform submission."""
        answers = jotform_data.get("pretty", jotform_data)

        # Field mappings with validation
        mappings = {
            "email": lambda x: x if "@" in x else None,
            "phone": lambda x: x,
            "telegram_username": lambda x: x,
            "target_roles": self._as_list,
            "preferred_cities": self._as_list,
            "skills": self._as_list,
            "visa_status": lambda x: x,
            "notice_period": lambda x: self._parse_notice_period(x),
            "years_experience": self._parse_years,
            "salary_expectation_aed": self._parse_salary,
            "preferred_industries": self._as_list,
            "english_level": lambda x: self._validate_language_level(x),
            "arabic_level": lambda x: self._validate_language_level(x),
        }

        for field, parser in mappings.items():
            if field in answers and not getattr(profile, field, None):
                value = parser(answers[field])
                if value and hasattr(profile, field):
                    setattr(profile, field, value)

        # Settings from Jotform
        if hasattr(profile, "settings"):
            settings_mappings = {
                "autonomy_level": lambda x: min(1.0, max(0.0, float(x))),
                "communication_style": lambda x: x,
                "match_strictness": lambda x: min(1.0, max(0.0, float(x))),
            }

            for setting, parser in settings_mappings.items():
                if setting in answers and hasattr(profile.settings, setting):
                    value = parser(answers[setting])
                    setattr(profile.settings, setting, value)

        return profile

    def _hydrate_from_chat(self, profile: RicoProfile, chat_history: list[dict[str, Any]]) -> RicoProfile:
        """Extract preferences from chat history using spaCy NER with batch processing."""
        if not _nlp:
            return profile

        # Track extracted entities to avoid duplicates
        extracted_locations = set(profile.preferred_cities or [])
        extracted_skills = set(profile.skills or [])
        extracted_roles = set(profile.target_roles or [])
        extracted_industries = set(getattr(profile, "preferred_industries", []) or [])

        # Process recent user messages (last 15)
        user_messages = [
            msg.get("content", "")
            for msg in (chat_history or [])[-15:]
            if msg.get("role") == "user"
        ]

        # Use batch processing with nlp.pipe() for better performance
        for doc in _nlp.pipe(user_messages, batch_size=5):
            # Extract locations using matcher
            if _location_matcher:
                location_matches = _location_matcher(doc)
                for match_id, start, end in location_matches:
                    span = doc[start:end]
                    location = span.text.title()
                    if location.lower() in UAE_CITIES:
                        extracted_locations.add(location)

            # Extract GPE entities (cities/countries)
            for ent in doc.ents:
                if ent.label_ in ("GPE", "LOC"):
                    location = ent.text.title()
                    if location.lower() in UAE_CITIES:
                        extracted_locations.add(location)
                    elif "remote" in location.lower():
                        extracted_locations.add("Remote")

            # Extract skills using matcher
            if _skill_matcher:
                skill_matches = _skill_matcher(doc)
                for match_id, start, end in skill_matches:
                    span = doc[start:end]
                    extracted_skills.add(span.text)

            # Extract roles using patterns
            role_pattern = re.compile(r'(?:as a|role of|position of|job as)\s+([a-z][a-z\s&/+-]{2,40})', re.I)
            role_matches = role_pattern.findall(doc.text)
            for role in role_matches:
                cleaned = role.strip().title()
                if len(cleaned.split()) <= 6:  # Reasonable role length
                    extracted_roles.add(cleaned)

            # Extract industries
            for industry in UAE_INDUSTRIES:
                if industry in doc.text.lower():
                    extracted_industries.add(industry.title())

        # Update profile with extracted data
        if extracted_locations and not profile.preferred_cities:
            profile.preferred_cities = list(extracted_locations)[:5]
        elif extracted_locations and profile.preferred_cities:
            # Append new locations not already present
            new_locs = extracted_locations - set(profile.preferred_cities)
            if new_locs:
                profile.preferred_cities.extend(list(new_locs)[:5])

        if extracted_skills and not profile.skills:
            profile.skills = list(extracted_skills)[:20]
        elif extracted_skills and profile.skills:
            new_skills = extracted_skills - set(profile.skills)
            if new_skills:
                profile.skills.extend(list(new_skills)[:10])

        if extracted_roles and not profile.target_roles:
            profile.target_roles = list(extracted_roles)[:5]
        elif extracted_roles and profile.target_roles:
            new_roles = extracted_roles - set(profile.target_roles)
            if new_roles:
                profile.target_roles.extend(list(new_roles)[:3])

        if extracted_industries and not getattr(profile, "preferred_industries", None):
            profile.preferred_industries = list(extracted_industries)[:5]

        return profile

    def _hydrate_from_actions(self, profile: RicoProfile, canonical_user_id: str) -> RicoProfile:
        """Infer preferences from action history with minimum count threshold."""
        try:
            # Get recent actions for this user (last 7 days)
            week_ago = datetime.now(_UTC) - timedelta(days=7)
            recent_actions = get_recent(
                limit=200,
            )

            # Filter actions for this user
            user_actions = [a for a in recent_actions if a.get("user_email") == canonical_user_id]

            # Analyze action patterns
            action_counts = defaultdict(int)
            company_skips = defaultdict(int)
            applied_roles = defaultdict(int)
            saved_roles = defaultdict(int)

            for action in user_actions:
                action_type = action.get("action_type", "")
                action_counts[action_type] += 1

                if action_type == "skip":
                    company = action.get("job_company")
                    if company:
                        company_skips[company] += 1
                elif action_type == "apply":
                    role = action.get("job_title", "")
                    if role:
                        applied_roles[role] += 1
                elif action_type == "save":
                    role = action.get("job_title", "")
                    if role:
                        saved_roles[role] += 1

            # Infer deal breakers from frequently skipped companies (3+ skips)
            deal_breakers = [
                company for company, count in company_skips.items()
                if count >= 3
            ][:10]
            if deal_breakers:
                profile.deal_breakers = deal_breakers

            # Infer top roles from applications with minimum count threshold
            # Only elevate roles with MIN_ROLE_APPLY_COUNT or more applications
            if applied_roles and not profile.target_roles:
                qualified_roles = [
                    (role, count) for role, count in applied_roles.items()
                    if count >= MIN_ROLE_APPLY_COUNT
                ]
                if qualified_roles:
                    top_applied = sorted(qualified_roles, key=lambda x: x[1], reverse=True)[:3]
                    profile.target_roles = [role for role, _ in top_applied]

            # Store behavioral signals for AI context
            profile.behavior_signals = {  # type: ignore
                "total_actions": sum(action_counts.values()),
                "applied_count": action_counts.get("apply", 0),
                "saved_count": action_counts.get("save", 0),
                "skipped_count": action_counts.get("skip", 0),
                "top_applied_roles": list(applied_roles.keys())[:3],
                "engagement_score": min(1.0, sum(action_counts.values()) / 50),
            }

        except Exception as e:
            logger.error(f"Action hydration failed for {canonical_user_id}: {e}")

        return profile

    def _compute_completeness(self, profile: RicoProfile) -> tuple[float, list[str], list[str]]:
        """Compute weighted profile completeness score."""
        total_weight = sum(_FIELD_WEIGHTS.values())
        earned_weight = 0.0
        missing_required = []
        missing_optional = []

        for field, weight in _FIELD_WEIGHTS.items():
            has_value = self._has_value(getattr(profile, field, None))

            if has_value:
                earned_weight += weight
            else:
                if field in _REQUIRED_FIELDS:
                    missing_required.append(field)
                elif field in _OPTIONAL_FIELDS:
                    missing_optional.append(field)

        completeness = earned_weight / total_weight if total_weight > 0 else 0.0
        return completeness, missing_required, missing_optional

    def _has_value(self, value: Any) -> bool:
        """Check if a field has a meaningful value."""
        if value is None:
            return False
        if isinstance(value, (list, tuple)):
            return len(value) > 0
        if isinstance(value, str):
            return len(value.strip()) > 0
        if isinstance(value, (int, float)):
            return value > 0
        return bool(value)

    def _load_question_history(self, canonical_user_id: str) -> dict[str, datetime]:
        """Load which questions have been asked to this user from audit logs."""
        history = {}
        try:
            # Check pending ask cache first (for write-read consistency)
            if canonical_user_id in self._pending_ask_cache:
                now = datetime.now(_UTC)
                pending = self._pending_ask_cache[canonical_user_id]
                # Filter to only recent pending asks (within 5 minutes)
                for field, timestamp in list(pending.items()):
                    if (now - timestamp).total_seconds() < 300:
                        history[field] = timestamp
                # Clean expired entries
                self._pending_ask_cache[canonical_user_id] = {
                    f: t for f, t in pending.items()
                    if (now - t).total_seconds() < 300
                }

            # Query audit logs for profile_question events
            audits = get_recent(limit=100)
            for audit in audits:
                if audit.get("event_type") == "profile_question":
                    field = audit.get("data", {}).get("field_name")
                    timestamp = audit.get("timestamp")
                    if field and timestamp:
                        if isinstance(timestamp, str):
                            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        history[field] = timestamp
        except Exception as e:
            logger.warning(f"Failed to load question history: {e}")
        return history

    def _load_behavior_signals(self, canonical_user_id: str) -> dict[str, Any]:
        """Load behavioral signals from action repository."""
        signals = {}
        try:
            recent_actions = get_recent(limit=100)
            user_actions = [a for a in recent_actions if a.get("user_email") == canonical_user_id]

            signals["total_actions"] = len(user_actions)
            signals["applied_count"] = len([a for a in user_actions if a.get("action_type") == "apply"])
            signals["saved_count"] = len([a for a in user_actions if a.get("action_type") == "save"])
            signals["skipped_count"] = len([a for a in user_actions if a.get("action_type") == "skip"])

            # Calculate engagement
            signals["engagement_score"] = min(1.0, signals["total_actions"] / 50)

        except Exception as e:
            logger.error(f"Failed to load behavior signals: {e}")

        return signals

    def _extract_roles_from_experience(self, experience: list[dict[str, Any]]) -> list[str]:
        """Extract target roles from CV experience section."""
        roles = set()
        for exp in experience:
            title = exp.get("title", "")
            if title:
                # Clean and normalize role title
                cleaned = re.sub(r'\b(?:remote|hybrid|full-time|contract)\b', '', title, flags=re.I)
                cleaned = cleaned.strip().title()
                if cleaned:
                    roles.add(cleaned)
        return list(roles)

    def _as_list(self, value: Any) -> list[str]:
        """Convert value to list if not already."""
        if isinstance(value, list):
            return [str(v).strip() for v in value if v]
        if isinstance(value, str):
            # Handle comma-separated strings
            if ',' in value:
                return [v.strip() for v in value.split(',') if v.strip()]
            return [value.strip()]
        return []

    def _parse_notice_period(self, value: Any) -> str | None:
        """Parse notice period from various formats."""
        if isinstance(value, str):
            value = value.lower()
            if 'day' in value:
                match = re.search(r'(\d+)', value)
                if match:
                    return f"{match.group(1)} days"
            elif 'week' in value:
                match = re.search(r'(\d+)', value)
                if match:
                    return f"{match.group(1)} weeks"
            elif 'month' in value:
                match = re.search(r'(\d+)', value)
                if match:
                    return f"{match.group(1)} months"
            return value if len(value) < 50 else None
        return None

    def _parse_years(self, value: Any) -> float | None:
        """Parse years of experience from various formats."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                match = re.search(r'(\d+(?:\.\d+)?)', value)
                if match:
                    return float(match.group(1))
        return None

    def _parse_salary(self, value: Any) -> int | None:
        """Parse salary expectation from various formats."""
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            # Extract digits (handle '20k' -> 20000)
            value = value.lower().replace('k', '000').replace(',', '')
            match = re.search(r'(\d+)', value)
            if match:
                return int(match.group())
        return None

    def _validate_language_level(self, value: Any) -> str | None:
        """Validate language proficiency level."""
        valid_levels = {"beginner", "intermediate", "advanced", "fluent", "native"}
        if isinstance(value, str):
            level = value.lower().strip()
            if level in valid_levels:
                return level
            # Map common variations
            if level in {"elem", "elementary"}:
                return "beginner"
            if level in {"int", "mid"}:
                return "intermediate"
            if level in {"adv"}:
                return "advanced"
        return None

    def mark_question_asked(self, canonical_user_id: str, field: str) -> None:
        """Record that a question about a field was asked."""
        try:
            write_audit_log(
                user_id=canonical_user_id,
                event_type="profile_question",
                data={"field_name": field},
                timestamp=datetime.now(_UTC)
            )

            # Add to pending ask cache for immediate consistency
            self._pending_ask_cache[canonical_user_id][field] = datetime.now(_UTC)

            # Update cache if present
            if canonical_user_id in self._cache:
                context, ts = self._cache[canonical_user_id]
                context.question_history[field] = datetime.now(_UTC)
                self._cache[canonical_user_id] = (context, ts)

        except Exception as e:
            logger.error(f"Failed to mark question asked: {e}")

    def invalidate_cache(self, canonical_user_id: str) -> None:
        """Invalidate cached profile for a user."""
        self._cache.pop(canonical_user_id, None)
        self._get_cached_profile.cache_clear()  # Clear LRU cache


# Lazy module-level instance
_resolver: ProfileContextResolver | None = None


def get_profile_context_resolver() -> ProfileContextResolver:
    """Get the singleton profile context resolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = ProfileContextResolver()
    return _resolver


def resolve_profile_context(
    canonical_user_id: str,
    *,
    cv_data: dict[str, Any] | None = None,
    jotform_data: dict[str, Any] | None = None,
    chat_history: list[dict[str, Any]] | None = None,
    force_refresh: bool = False,
) -> ProfileContext:
    """
    Convenience function to resolve profile context.

    Example:
        >>> context = resolve_profile_context("user123", chat_history=messages)
        >>> if context.missing_required:
        >>>     print(f"Need: {context.missing_required}")

    Uses lazy-initialized singleton resolver.
    """
    resolver = get_profile_context_resolver()
    return resolver.resolve(
        canonical_user_id=canonical_user_id,
        cv_data=cv_data,
        jotform_data=jotform_data,
        chat_history=chat_history,
        force_refresh=force_refresh,
    )
