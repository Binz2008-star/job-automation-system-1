"""src/repositories/learning_repo.py

Learning signals repository for Rico agent.

Stores and retrieves behavioral learning signals:
- Target role preferences (from job actions)
- Location preferences (from saved jobs)
- Skill relevance (from applied jobs)
- Company preferences (deal breakers, green flags)
- Feedback events (positive/negative feedback on matches)
- Interview preferences (types of roles, companies, locations)
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any
from pathlib import Path

# Core dependencies
try:
    import spacy
    from skillner.skill_extractor_class import SkillExtractor
    SKILLNER_AVAILABLE = True
except ImportError:
    SKILLNER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("SkillNER not installed. Run: pip install skillner spacy en_core_web_sm")

try:
    from diskcache import Cache
    DISKCACHE_AVAILABLE = True
except ImportError:
    DISKCACHE_AVAILABLE = False

from src.db import get_db_connection, is_db_available

logger = logging.getLogger(__name__)
_UTC = timezone.utc

# NLP setup for skill extraction
_nlp = None
_skill_extractor = None
_nlp_lock = threading.Lock()

def _init_nlp():
    """Lazy initialize NLP components."""
    global _nlp, _skill_extractor
    if _nlp is None and SKILLNER_AVAILABLE:
        try:
            _nlp = spacy.load("en_core_web_sm")
            # Load SKILL_DB from package or custom path
            from skillner.skill_extractor_class import SKILL_DB
            _skill_extractor = SkillExtractor(_nlp, SKILL_DB, PhraseMatcher)
            logger.info("Skill extraction initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize SkillNER: {e}")

# Common stopwords for skill filtering
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "he", "in", "is", "it", "its", "of", "on", "that", "the", "to", "was",
    "were", "will", "with", "experience", "ability", "knowledge", "proficiency"
}

# Skill synonym mapper for normalization
SKILL_SYNONYMS = {
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "reactjs": "react",
    "node": "node.js",
    "golang": "go",
    "css3": "css",
    "html5": "html",
    "db": "database",
    "rdbms": "database",
    "nosql": "database",
    "ci": "ci/cd",
    "cd": "ci/cd",
}

# Role extraction patterns
ROLE_PATTERNS = [
    # Seniority + Role (Senior Software Engineer)
    re.compile(r"(?P<seniority>Senior|Mid|Junior|Lead|Principal|Staff)?\s*(?P<role>[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)"),
    # Role with area (Product Manager, Technical)
    re.compile(r"(?P<role>[A-Z][a-zA-Z]+)[\s-]+(?:Manager|Engineer|Developer|Architect|Analyst|Consultant|Specialist)"),
    # Compound roles (Machine Learning Engineer)
    re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Engineer|Developer|Scientist|Analyst)"),
]

# UAE salary ranges (monthly AED)
SALARY_TIERS = {
    "entry": (5000, 15000),
    "mid": (15000, 30000),
    "senior": (30000, 50000),
    "executive": (50000, 1000000),
}


@dataclass
class LearningSignal:
    """A single learning signal with decayable timestamp."""
    signal_type: str  # "role_preference", "location_preference", "skill_relevance", "company_sentiment", "feedback"
    signal_value: str  # The value (e.g., "Senior Engineer", "Dubai", "Python", "Google")
    signal_weight: float  # 0.0-1.0 confidence weight
    source: str  # "job_action", "chat", "jotform", "feedback"
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def decayed_weight(self, half_life_days: int = 30) -> float:
        """Apply exponential decay based on age."""
        days_old = (datetime.now(_UTC) - self.timestamp).days
        decay_factor = 2 ** (-days_old / half_life_days)
        return self.signal_weight * decay_factor


@dataclass
class LearningProfile:
    """Aggregated learning signals for a user with signal history."""
    canonical_user_id: str
    role_preferences: dict[str, float] = field(default_factory=dict)  # role -> aggregated weight
    location_preferences: dict[str, float] = field(default_factory=dict)  # location -> weight
    skill_relevance: dict[str, float] = field(default_factory=dict)  # skill -> weight
    company_sentiment: dict[str, float] = field(default_factory=dict)  # company -> -1.0 to 1.0
    feedback_events: list[dict[str, Any]] = field(default_factory=list)
    signal_history: list[LearningSignal] = field(default_factory=list)  # For decay calculation
    last_updated: datetime | None = None
    salary_preference: tuple[float, float] | None = None  # min, max monthly AED


class LearningRepository:
    """
    Repository for storing and retrieving learning signals with time decay.

    Learning signals are behavioral cues extracted from user actions.
    Supports caching with TTL and exponential decay for recent behavior weighting.
    """

    def __init__(self, cache_ttl_seconds: int = 3600):
        """Initialize repository with optional persistent cache."""
        self._cache_ttl = cache_ttl_seconds

        # Use diskcache if available, else in-memory dict
        if DISKCACHE_AVAILABLE:
            self._cache = Cache("learning_cache", expire=cache_ttl_seconds)
            logger.info("Using diskcache for learning repository")
        else:
            self._cache = {}
            logger.warning("diskcache not available, using in-memory cache (no TTL)")

        # Initialize NLP lazily
        if SKILLNER_AVAILABLE:
            _init_nlp()

    def record_signal(
        self,
        canonical_user_id: str,
        signal_type: str,
        signal_value: str,
        signal_weight: float = 0.5,
        source: str = "job_action",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Record a learning signal with EMA aggregation.

        Args:
            canonical_user_id: User ID from IdentityResolver
            signal_type: Type of signal (role_preference, location_preference, etc.)
            signal_value: The value being learned
            signal_weight: Confidence weight 0.0-1.0 (can be negative for dislikes)
            source: Where this signal came from
            metadata: Additional context

        Returns:
            True if signal was recorded successfully
        """
        signal = LearningSignal(
            signal_type=signal_type,
            signal_value=signal_value,
            signal_weight=signal_weight,
            source=source,
            timestamp=datetime.now(_UTC),
            metadata=metadata or {},
        )

        # Persist to database (non-blocking, log errors)
        db_success = False
        if is_db_available():
            try:
                self._db_write_signal(canonical_user_id, signal)
                db_success = True
            except Exception as e:
                logger.error(f"learning_signal_db_write_failed user={canonical_user_id} type={signal_type}: {e}")

        # Update cache
        if canonical_user_id not in self._cache:
            self._cache[canonical_user_id] = LearningProfile(canonical_user_id=canonical_user_id)

        profile = self._cache[canonical_user_id]
        profile.last_updated = datetime.now(_UTC)
        profile.signal_history.append(signal)

        # Keep history bounded (max 1000 signals per user for memory)
        if len(profile.signal_history) > 1000:
            profile.signal_history = profile.signal_history[-1000:]

        # Update appropriate field with EMA
        if signal_type == "role_preference":
            self._update_weighted_ema(profile.role_preferences, signal_value, signal_weight)
        elif signal_type == "location_preference":
            self._update_weighted_ema(profile.location_preferences, signal_value, signal_weight)
        elif signal_type == "skill_relevance":
            # Normalize skill using synonym mapper before recording
            normalized_skill = SKILL_SYNONYMS.get(signal_value.lower(), signal_value)
            self._update_weighted_ema(profile.skill_relevance, normalized_skill, signal_weight)
        elif signal_type == "company_sentiment":
            self._update_company_sentiment(profile.company_sentiment, signal_value, signal_weight)
        elif signal_type == "feedback":
            profile.feedback_events.append({
                "value": signal_value,
                "weight": signal_weight,
                "source": source,
                "timestamp": signal.timestamp.isoformat(),
                "metadata": metadata,
            })
        elif signal_type == "salary_preference":
            self._update_salary_preference(profile, signal_value, signal_weight)

        logger.debug(
            "learning_signal_recorded user=%s type=%s value=%s weight=%.2f db_success=%s",
            canonical_user_id, signal_type, signal_value, signal_weight, db_success,
        )

        return True

    def _update_weighted_ema(
        self,
        weights: dict[str, float],
        value: str,
        new_weight: float,
        alpha: float = 0.3,
    ) -> None:
        """
        Update weighted dictionary using Exponential Moving Average.

        Alpha controls how much new signal influences the weight (0.0-1.0).
        Higher alpha = more responsive to recent signals.
        """
        current_weight = weights.get(value, 0.5)  # Neutral baseline
        # EMA: new = α * signal + (1-α) * old
        updated_weight = alpha * new_weight + (1 - alpha) * current_weight
        # Clamp to [0, 1] range
        weights[value] = max(0.0, min(1.0, updated_weight))

    def _update_company_sentiment(
        self,
        sentiment: dict[str, float],
        company: str,
        new_sentiment: float,
        alpha: float = 0.25,
    ) -> None:
        """
        Update company sentiment with EMA, keeping in [-1, 1] range.

        Negative sentiment (blocked company) should persist strongly.
        """
        current = sentiment.get(company, 0.0)
        # Use lower alpha for negative signals (stronger persistence)
        if new_sentiment < 0:
            alpha = 0.1  # Strong negative signals persist longer

        updated = alpha * new_sentiment + (1 - alpha) * current
        sentiment[company] = max(-1.0, min(1.0, updated))

    def _update_salary_preference(
        self,
        profile: LearningProfile,
        salary_str: str,
        weight: float,
    ) -> None:
        """Extract and update salary preference from string like '20k-30k AED'."""
        # Minimum confidence gate - ignore low-confidence signals
        if weight < 0.3:
            return

        # Parse salary range
        match = re.search(r'(\d+[kK]?)\s*[-–]\s*(\d+[kK]?)', salary_str)
        if match:
            min_str, max_str = match.groups()
            min_val = self._parse_salary_value(min_str)
            max_val = self._parse_salary_value(max_str)

            if profile.salary_preference is None:
                profile.salary_preference = (min_val, max_val)
            else:
                # Weighted average based on signal confidence
                curr_min, curr_max = profile.salary_preference
                profile.salary_preference = (
                    curr_min * (1 - weight) + min_val * weight,
                    curr_max * (1 - weight) + max_val * weight,
                )

    def _parse_salary_value(self, value: str) -> float:
        """Parse salary string like '20k' to 20000."""
        value = value.lower().replace('k', '000').replace(',', '')
        try:
            return float(value)
        except ValueError:
            return 15000  # Default mid-range

    def get_learning_profile(self, canonical_user_id: str, apply_decay: bool = True) -> LearningProfile:
        """
        Get aggregated learning profile for a user with optional time decay.

        Args:
            canonical_user_id: User ID
            apply_decay: If True, apply exponential decay to weights based on signal age
        """
        # Try cache first
        if canonical_user_id in self._cache:
            profile = self._cache[canonical_user_id]
            if apply_decay and profile.signal_history:
                return self._apply_decay_to_profile(profile)
            return profile

        # Load from database
        profile = LearningProfile(canonical_user_id=canonical_user_id)
        if is_db_available():
            try:
                profile = self._db_load_profile(canonical_user_id)
            except Exception as e:
                logger.error(f"learning_profile_db_load_failed user={canonical_user_id}: {e}")

        self._cache[canonical_user_id] = profile

        if apply_decay and profile.signal_history:
            return self._apply_decay_to_profile(profile)
        return profile

    def _apply_decay_to_profile(self, profile: LearningProfile) -> LearningProfile:
        """Create a copy of profile with decayed weights."""
        decayed = LearningProfile(canonical_user_id=profile.canonical_user_id)

        # Recalculate all weights from signal history
        for signal in profile.signal_history:
            decayed_weight = signal.decayed_weight()
            if signal.signal_type == "role_preference":
                self._update_weighted_ema(decayed.role_preferences, signal.signal_value, decayed_weight, alpha=0.5)
            elif signal.signal_type == "location_preference":
                self._update_weighted_ema(decayed.location_preferences, signal.signal_value, decayed_weight, alpha=0.5)
            elif signal.signal_type == "skill_relevance":
                self._update_weighted_ema(decayed.skill_relevance, signal.signal_value, decayed_weight, alpha=0.5)
            elif signal.signal_type == "company_sentiment":
                self._update_company_sentiment(decayed.company_sentiment, signal.signal_value, decayed_weight)

        decayed.feedback_events = profile.feedback_events.copy()
        decayed.salary_preference = profile.salary_preference
        decayed.last_updated = profile.last_updated

        return decayed

    def infer_signals_from_job_action(
        self,
        canonical_user_id: str,
        action_type: str,
        job: dict[str, Any],
    ) -> None:
        """
        Infer learning signals from a job action.

        Args:
            canonical_user_id: User ID
            action_type: "apply", "save", "skip", "block", "not_relevant"
            job: Job dict with title, company, location, description, skills
        """
        title = job.get("title", "")
        company = job.get("company", "")
        location = job.get("location", "") or job.get("city", "")
        description = job.get("description", "")
        skills = job.get("skills", [])

        # Extract role from title
        role = self._extract_role_from_title(title)
        if role:
            if action_type in ("apply", "save"):
                weight = 0.8 if action_type == "apply" else 0.5
                self.record_signal(
                    canonical_user_id,
                    "role_preference",
                    role,
                    signal_weight=weight,
                    source="job_action",
                    metadata={"action": action_type, "job_title": title},
                )
            elif action_type in ("skip", "not_relevant"):
                self.record_signal(
                    canonical_user_id,
                    "role_preference",
                    role,
                    signal_weight=-0.2,
                    source="job_action",
                    metadata={"action": action_type, "job_title": title},
                )
            elif action_type == "block":
                self.record_signal(
                    canonical_user_id,
                    "role_preference",
                    role,
                    signal_weight=-0.8,
                    source="job_action",
                    metadata={"action": action_type, "job_title": title},
                )

        # Extract location
        if location:
            if action_type in ("apply", "save"):
                weight = 0.7 if action_type == "apply" else 0.4
                self.record_signal(
                    canonical_user_id,
                    "location_preference",
                    location,
                    signal_weight=weight,
                    source="job_action",
                    metadata={"action": action_type, "location": location},
                )

        # Company sentiment
        if company:
            if action_type == "block":
                self.record_signal(
                    canonical_user_id,
                    "company_sentiment",
                    company,
                    signal_weight=-1.0,
                    source="job_action",
                    metadata={"action": action_type},
                )
            elif action_type == "apply":
                self.record_signal(
                    canonical_user_id,
                    "company_sentiment",
                    company,
                    signal_weight=0.7,
                    source="job_action",
                    metadata={"action": action_type},
                )
            elif action_type == "save":
                self.record_signal(
                    canonical_user_id,
                    "company_sentiment",
                    company,
                    signal_weight=0.3,
                    source="job_action",
                    metadata={"action": action_type},
                )

        # Extract skills from description and job skills
        extracted_skills = self._extract_skills_from_description(description)
        all_skills = list(set(skills + extracted_skills))

        for skill in all_skills[:10]:  # Limit to top 10 skills per job
            if action_type == "apply":
                self.record_signal(
                    canonical_user_id,
                    "skill_relevance",
                    skill,
                    signal_weight=0.4,
                    source="job_action",
                    metadata={"action": action_type},
                )
            elif action_type == "save":
                self.record_signal(
                    canonical_user_id,
                    "skill_relevance",
                    skill,
                    signal_weight=0.2,
                    source="job_action",
                    metadata={"action": action_type},
                )

    def _extract_role_from_title(self, title: str) -> str | None:
        """Extract canonical role from job title using regex patterns."""
        if not title:
            return None

        for pattern in ROLE_PATTERNS:
            match = pattern.search(title)
            if match:
                role = match.group("role") if "role" in match.groupdict() else match.group(0)
                # Clean and normalize
                role = role.strip().title()
                # Remove common non-role words
                role = re.sub(r'\b(?:Remote|Hybrid|Full[-\s]time|Part[-\s]time|Contract)\b', '', role, flags=re.I)
                return role.strip()

        # Fallback: return first 3 words as role
        words = title.split()[:3]
        return " ".join(words).strip() if words else None

    def _extract_skills_from_description(self, description: str) -> list[str]:
        """Extract skills from job description using SkillNER or fallback regex."""
        if not description:
            return []

        # Try SkillNER if available with thread safety
        if SKILLNER_AVAILABLE and _skill_extractor:
            with _nlp_lock:
                try:
                    annotations = _skill_extractor.annotate(description)
                    skills = []
                    for skill in annotations.get("skills", []):
                        skill_text = skill["doc_node"].text.lower()
                        if skill_text not in STOPWORDS and len(skill_text) > 2:
                            # Normalize using synonym mapper
                            normalized = SKILL_SYNONYMS.get(skill_text, skill_text)
                            skills.append(normalized)
                    return list(set(skills))  # Deduplicate
                except Exception as e:
                    logger.warning(f"SkillNER extraction failed: {e}")

        # Fallback: regex for common skill patterns
        skill_patterns = [
            r'\b(Python|Java|JavaScript|TypeScript|React|Angular|Vue|Node\.js|Django|Flask)\b',
            r'\b(SQL|PostgreSQL|MySQL|MongoDB|Redis|Elasticsearch)\b',
            r'\b(Docker|Kubernetes|AWS|Azure|GCP|Terraform|Jenkins)\b',
            r'\b(Machine Learning|AI|NLP|Computer Vision|Data Science|Analytics)\b',
        ]

        skills = []
        for pattern in skill_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            skills.extend([m.lower() for m in matches])

        # Remove duplicates and stopwords, normalize synonyms
        skills = [SKILL_SYNONYMS.get(s, s) for s in set(skills) if s not in STOPWORDS]
        return skills[:10]  # Return top 10 skills

    def get_top_preferences(
        self,
        canonical_user_id: str,
        preference_type: str,
        limit: int = 5,
        apply_decay: bool = True,
    ) -> list[tuple[str, float]]:
        """
        Get top preferences for a given type with optional time decay.

        Args:
            canonical_user_id: User ID
            preference_type: "role", "location", "skill", "company"
            limit: Max number of results
            apply_decay: Apply time decay to recent preferences
        """
        profile = self.get_learning_profile(canonical_user_id, apply_decay=apply_decay)

        pref_map = {
            "role": profile.role_preferences,
            "location": profile.location_preferences,
            "skill": profile.skill_relevance,
            "company": profile.company_sentiment,
        }

        prefs = pref_map.get(preference_type, {})

        # Filter and sort
        if preference_type == "company":
            # For companies, favor negative sentiment for blocking
            filtered = [(k, v) for k, v in prefs.items() if abs(v) > 0.3]
        else:
            filtered = [(k, v) for k, v in prefs.items() if v > 0.2]

        sorted_prefs = sorted(filtered, key=lambda x: x[1], reverse=True)
        return sorted_prefs[:limit]

    def invalidate_cache(self, canonical_user_id: str) -> None:
        """Invalidate cache for a specific user."""
        if canonical_user_id in self._cache:
            del self._cache[canonical_user_id]
            logger.debug(f"Cache invalidated for user {canonical_user_id}")

    def _db_write_signal(self, canonical_user_id: str, signal: LearningSignal) -> None:
        """Write signal to database."""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # Check if table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = 'learning_signals'
                    )
                """)
                table_exists = cur.fetchone()[0]

                if not table_exists:
                    # Create table with index for performance
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS learning_signals (
                            id SERIAL PRIMARY KEY,
                            canonical_user_id VARCHAR(255) NOT NULL,
                            signal_type VARCHAR(100) NOT NULL,
                            signal_value TEXT NOT NULL,
                            signal_weight FLOAT NOT NULL,
                            source VARCHAR(50) NOT NULL,
                            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                            metadata JSONB,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        )
                    """)
                    # Add index for N+1 prevention on user_id, timestamp DESC
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_learning_signals_user_timestamp
                        ON learning_signals(canonical_user_id, timestamp DESC)
                    """)
                    conn.commit()

                # Insert signal
                cur.execute(
                    """
                    INSERT INTO learning_signals
                    (canonical_user_id, signal_type, signal_value, signal_weight, source, timestamp, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        canonical_user_id,
                        signal.signal_type,
                        signal.signal_value,
                        signal.signal_weight,
                        signal.source,
                        signal.timestamp,
                        json.dumps(signal.metadata),
                    ),
                )
                conn.commit()
        finally:
            conn.close()

    def _db_load_profile(self, canonical_user_id: str) -> LearningProfile:
        """Load full profile from database."""
        profile = LearningProfile(canonical_user_id=canonical_user_id)
        conn = get_db_connection()

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT signal_type, signal_value, signal_weight, source, timestamp, metadata
                    FROM learning_signals
                    WHERE canonical_user_id = %s
                    ORDER BY timestamp DESC
                    LIMIT 1000
                """, (canonical_user_id,))

                for row in cur.fetchall():
                    signal = LearningSignal(
                        signal_type=row[0],
                        signal_value=row[1],
                        signal_weight=row[2],
                        source=row[3],
                        timestamp=row[4],
                        metadata=json.loads(row[5]) if row[5] else {},
                    )
                    profile.signal_history.append(signal)
        finally:
            conn.close()

        return profile


# Module-level singleton with thread-safe lazy initialization
_repo: LearningRepository | None = None
_repo_lock = threading.Lock()


def get_learning_repository() -> LearningRepository:
    """Get the singleton learning repository instance with thread-safe initialization."""
    global _repo
    if _repo is None:
        with _repo_lock:
            if _repo is None:
                _repo = LearningRepository()
    return _repo
