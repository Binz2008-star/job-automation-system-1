"""src/agent/intelligence/normalizer.py

Role normalization layer for Rico Agent OS.

Maps various role title variants to canonical forms:
- sales man → Sales Representative
- dev → Software Engineer
- PM → Product Manager
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Common role variants mapping to canonical forms
_ROLE_VARIANTS: Dict[str, str] = {
    # Sales roles
    "sales man": "Sales Representative",
    "salesman": "Sales Representative",
    "sales rep": "Sales Representative",
    "salesperson": "Sales Representative",
    "account executive": "Sales Representative",
    "ae": "Sales Representative",
    "business development": "Business Development Representative",
    "bdr": "Business Development Representative",
    "sales executive": "Sales Executive",

    # Engineering roles
    "dev": "Software Engineer",
    "developer": "Software Engineer",
    "software dev": "Software Engineer",
    "swe": "Software Engineer",
    "backend dev": "Backend Engineer",
    "frontend dev": "Frontend Engineer",
    "fullstack": "Full Stack Engineer",
    "full stack": "Full Stack Engineer",
    "fullstack dev": "Full Stack Engineer",
    "web dev": "Web Developer",
    "web developer": "Web Developer",
    "mobile dev": "Mobile Developer",
    "ios dev": "iOS Developer",
    "android dev": "Android Developer",

    # Product roles
    "pm": "Product Manager",
    "product owner": "Product Manager",
    "product lead": "Product Lead",
    "apm": "Associate Product Manager",
    "senior pm": "Senior Product Manager",
    "head of product": "Head of Product",

    # Data roles
    "data scientist": "Data Scientist",
    "data science": "Data Scientist",
    "ml engineer": "Machine Learning Engineer",
    "machine learning engineer": "Machine Learning Engineer",
    "data analyst": "Data Analyst",
    "data engineer": "Data Engineer",

    # Design roles
    "ux designer": "UX Designer",
    "ui designer": "UI Designer",
    "product designer": "Product Designer",
    "graphic designer": "Graphic Designer",
    "design lead": "Design Lead",

    # Marketing roles
    "marketing manager": "Marketing Manager",
    "digital marketing": "Digital Marketing Specialist",
    "growth marketer": "Growth Marketer",
    "content writer": "Content Writer",
    "seo specialist": "SEO Specialist",

    # Operations roles
    "ops": "Operations Manager",
    "operations": "Operations Manager",
    "devops": "DevOps Engineer",
    "devops engineer": "DevOps Engineer",
    "sre": "Site Reliability Engineer",
    "site reliability engineer": "Site Reliability Engineer",

    # HR roles
    "hr": "Human Resources Manager",
    "human resources": "Human Resources Manager",
    "recruiter": "Recruiter",
    "talent acquisition": "Talent Acquisition Specialist",

    # Finance roles
    "accountant": "Accountant",
    "finance manager": "Finance Manager",
    "financial analyst": "Financial Analyst",
}

# Common prefixes to strip
_PREFIXES: Set[str] = {
    "senior ",
    "sr ",
    "lead ",
    "principal ",
    "staff ",
    "junior ",
    "jr ",
    "associate ",
    "mid-level ",
    "mid level ",
    "head of ",
    "vp of ",
    "vice president of ",
    "chief ",
    "cto ",
    "ceo ",
    "cfo ",
    "coo ",
}

# Common suffixes to strip
_SUFFIXES: Set[str] = {
    " i",
    " ii",
    " iii",
    " iv",
    " 1",
    " 2",
    " 3",
    " (remote)",
    " (hybrid)",
    " (onsite)",
}


class RoleNormalizer:
    """
    Normalizes role titles to canonical forms.

    Handles:
    - Variant mapping (sales man → Sales Representative)
    - Prefix/suffix stripping (Senior Software Engineer → Software Engineer)
    - Case normalization (software engineer → Software Engineer)
    - Special character handling
    """

    def __init__(self):
        self._cache: Dict[str, str] = {}

    def normalize(self, role: str) -> str:
        """
        Normalize a role title to its canonical form.

        Args:
            role: Raw role title (e.g., "senior sales man")

        Returns:
            Canonical role title (e.g., "Sales Representative")
        """
        try:
            if not role or not isinstance(role, str):
                return "Unknown"

            # Check cache
            role_lower = role.lower().strip()
            if role_lower in self._cache:
                return self._cache[role_lower]

            # Step 1: Clean the input
            cleaned = self._clean_input(role)

            # Step 2: Check direct variant mapping
            if cleaned.lower() in _ROLE_VARIANTS:
                canonical = _ROLE_VARIANTS[cleaned.lower()]
                self._cache[role_lower] = canonical
                return canonical

            # Step 3: Strip prefixes and suffixes
            base_role = self._strip_prefixes_suffixes(cleaned)

            # Step 4: Check variant mapping on base role
            if base_role.lower() in _ROLE_VARIANTS:
                canonical = _ROLE_VARIANTS[base_role.lower()]
                self._cache[role_lower] = canonical
                return canonical

            # Step 5: Capitalize properly
            canonical = self._capitalize_properly(base_role)

            self._cache[role_lower] = canonical
            return canonical
        except Exception as e:
            logger.warning(f"Role normalization failed for '{role}': {e}")
            return self._capitalize_properly(role) if role else "Unknown"

    def _clean_input(self, role: str) -> str:
        """Clean the raw role input."""
        try:
            if not role:
                return ""
            # Remove special characters
            cleaned = re.sub(r"[^\w\s\-]", "", role)
            # Normalize whitespace
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            return cleaned
        except Exception as e:
            logger.warning(f"Input cleaning failed for '{role}': {e}")
            return role or ""

    def _strip_prefixes_suffixes(self, role: str) -> str:
        """Strip common prefixes and suffixes."""
        result = role

        # Strip prefixes
        for prefix in sorted(_PREFIXES, key=len, reverse=True):
            if result.lower().startswith(prefix):
                result = result[len(prefix):].strip()
                break

        # Strip suffixes
        for suffix in sorted(_SUFFIXES, key=len, reverse=True):
            if result.lower().endswith(suffix):
                result = result[:-len(suffix)].strip()
                break

        return result

    def _capitalize_properly(self, role: str) -> str:
        """Capitalize the role title properly."""
        try:
            if not role:
                return ""
            words = role.split()
            capitalized = []
            for word in words:
                # Capitalize first letter, lowercase rest
                if word:
                    capitalized.append(word[0].upper() + word[1:].lower())
            return " ".join(capitalized)
        except Exception as e:
            logger.warning(f"Capitalization failed for '{role}': {e}")
            return role.title() if role else ""

    def get_variants(self, canonical_role: str) -> List[str]:
        """
        Get all known variants for a canonical role.

        Args:
            canonical_role: Canonical role title

        Returns:
            List of variant titles that map to this canonical role
        """
        variants = []
        canonical_lower = canonical_role.lower()

        for variant, canonical in _ROLE_VARIANTS.items():
            if canonical.lower() == canonical_lower:
                variants.append(variant)

        return sorted(variants)


# Module-level singleton
_role_normalizer = RoleNormalizer()


def normalize_role(role: str) -> str:
    """
    Convenience function to normalize a role title.

    Uses the singleton RoleNormalizer instance.
    """
    return _role_normalizer.normalize(role)


def get_role_variants(canonical_role: str) -> List[str]:
    """
    Convenience function to get role variants.

    Uses the singleton RoleNormalizer instance.
    """
    return _role_normalizer.get_variants(canonical_role)
