"""Personalized cover letter writer for UAE ESG/HSE/Environmental roles."""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DEFAULT_NAME = os.getenv("COVER_LETTER_NAME", "").strip()
DEFAULT_LOCATION = os.getenv("COVER_LETTER_LOCATION", "").strip()
DEFAULT_PROFILE_LINE = os.getenv("COVER_LETTER_PROFILE", "").strip()

MAX_FIELD_LEN = 300
MAX_DESCRIPTION_LEN = 5000
MAX_BATCH_SIZE = 100

SKILL_LINES = {
    "iso": "implemented and maintained ISO 14001-aligned environmental compliance systems",
    "compliance": "managed environmental compliance, audits, permits, and UAE municipality requirements",
    "hse": "led HSE/QHSE systems with practical site-level safety and environmental controls",
    "ehs": "led EHS systems with practical site-level safety and environmental controls",
    "qhse": "managed integrated QHSE systems across operational teams",
    "sustainability": "supported sustainability programs and ESG reporting initiatives",
    "esg": "supported ESG reporting, sustainability strategy, and compliance documentation",
    "waste": "managed waste operations and environmental service delivery across 80+ locations",
    "wastewater": "handled wastewater, FOG control, and operational environmental risks",
    "municipality": "worked with UAE municipal regulations, inspections, and approval processes",
    "audit": "prepared teams and documentation for audits and regulatory inspections",
}


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _truncate(text: Any, max_len: int) -> str:
    value = _clean(text)
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "…"


def _profile_value(profile: Dict[str, Any], key: str, fallback: str = "") -> str:
    value = _clean(profile.get(key))
    return value or fallback


def _role_specific_lines(job: Dict[str, Any], limit: int = 3) -> List[str]:
    title = _truncate(job.get("title"), MAX_FIELD_LEN)
    description = _truncate(job.get("description"), MAX_DESCRIPTION_LEN)
    text = f"{title} {description}".lower()
    lines: List[str] = []
    for key, line in SKILL_LINES.items():
        if key in text and line not in lines:
            lines.append(line)
    if not lines:
        lines = [
            "managed environmental operations, regulatory compliance, and HSE coordination in the UAE",
            "led multi-site teams and improved operational controls across environmental service environments",
        ]
    return lines[:limit]


def generate_cover_letter(
    job: Dict[str, Any],
    profile: Dict[str, Any] | None = None,
) -> str:
    profile = profile or {}

    name = _profile_value(profile, "name", DEFAULT_NAME) or "Candidate"
    candidate_location = _profile_value(profile, "location", DEFAULT_LOCATION)
    profile_line = _profile_value(
        profile,
        "profile_line",
        DEFAULT_PROFILE_LINE,
    ) or "relevant experience in environmental compliance, HSE coordination, and UAE operations"

    title = _truncate(job.get("title"), MAX_FIELD_LEN) or "the advertised role"
    company = _truncate(job.get("company"), MAX_FIELD_LEN) or "your organization"
    location = _truncate(job.get("location"), MAX_FIELD_LEN) or "the UAE"

    role_lines = _role_specific_lines(job)
    title_lower = title.lower()

    if "esg" in title_lower or "sustain" in title_lower:
        opening_focus = "ESG, sustainability strategy, environmental reporting, and compliance governance"
    elif "hse" in title_lower or "ehs" in title_lower or "qhse" in title_lower or "hsse" in title_lower:
        opening_focus = "HSE leadership, risk control, compliance, and operational safety systems"
    elif "environment" in title_lower:
        opening_focus = "environmental compliance, waste operations, regulatory approvals, and site performance"
    else:
        opening_focus = "environmental compliance, HSE leadership, and UAE operational execution"

    bullets = "\n".join(f"- {line.capitalize()}." for line in role_lines)

    signature_location = f"\n{candidate_location}" if candidate_location else ""

    return f"""Dear Hiring Manager,

I am writing to express my interest in the {title} position at {company} in {location}.

I bring {profile_line}. This background aligns strongly with the role's focus on {opening_focus}.

Relevant experience I would bring to {company}:
{bullets}
- Led multi-site operations involving 80+ locations and coordinated teams across compliance, service delivery, and reporting requirements.

I would welcome the opportunity to discuss how my UAE environmental compliance and HSE experience can support {company}'s operational and sustainability goals.

Sincerely,
{name}{signature_location}
"""


def generate_batch_cover_letters(
    jobs: List[Dict[str, Any]],
    profile: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    if len(jobs) > MAX_BATCH_SIZE:
        raise ValueError(f"Cannot generate more than {MAX_BATCH_SIZE} cover letters at once")

    letters: Dict[str, str] = {}
    for idx, job in enumerate(jobs):
        base_key = _clean(job.get("link")) or f"{_clean(job.get('company'))}_{_clean(job.get('title'))}" or f"job_{idx}"
        key = base_key
        counter = 2
        while key in letters:
            key = f"{base_key}#{counter}"
            counter += 1

        letters[key] = generate_cover_letter(job, profile=profile)
    logger.info("batch_cover_letters_complete total=%s", len(letters))
    return letters
