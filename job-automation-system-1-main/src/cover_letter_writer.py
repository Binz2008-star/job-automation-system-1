"""Personalized cover letter writer for UAE ESG/HSE/Environmental roles."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

NAME = "Roben Edwan"
LOCATION = "Ajman, UAE"
PROFILE_LINE = "10+ years in environmental management, HSE leadership, UAE regulatory compliance, and multi-site operations"

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


def _role_specific_lines(job: Dict[str, Any], limit: int = 3) -> List[str]:
    text = f"{job.get('title','')} {job.get('description','')}".lower()
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


def generate_cover_letter(job: Dict[str, Any]) -> str:
    title = _clean(job.get("title")) or "the advertised role"
    company = _clean(job.get("company")) or "your organization"
    location = _clean(job.get("location")) or "the UAE"
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

    return f"""Dear Hiring Manager,

I am writing to express my interest in the {title} position at {company} in {location}.

I bring {PROFILE_LINE}. This background aligns strongly with the role's focus on {opening_focus}.

Relevant experience I would bring to {company}:
{bullets}
- Led multi-site operations involving 80+ locations and coordinated teams across compliance, service delivery, and reporting requirements.

I would welcome the opportunity to discuss how my UAE environmental compliance and HSE experience can support {company}'s operational and sustainability goals.

Sincerely,
{NAME}
{LOCATION}
"""


def generate_batch_cover_letters(jobs: List[Dict[str, Any]]) -> Dict[str, str]:
    letters: Dict[str, str] = {}
    for job in jobs:
        key = job.get("link") or f"{job.get('company','')}_{job.get('title','')}"
        letters[str(key)] = generate_cover_letter(job)
    logger.info("batch_cover_letters_complete total=%s", len(letters))
    return letters
