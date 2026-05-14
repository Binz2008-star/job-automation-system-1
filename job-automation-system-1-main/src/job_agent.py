"""
Real AI job decision agent for ESG/HSE job hunting.

Decision engine combines:
- semantic/keyword score
- title/domain relevance
- seniority
- location
- company intelligence
- disqualifiers
- dynamic threshold from application feedback
- optional instruction-tuned LLM JSON reasoning (Mistral/Llama), with safe fallback
- LinkedIn data integration (skills, company follows, application history)
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# LinkedIn integration
_linkedin_loader = None
_linkedin_skill_matcher = None
_linkedin_company_targeter = None
_linkedin_analyzer = None

_HF_MODEL = os.getenv("HF_DECISION_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")
_HF_URL = os.getenv("HF_TEXTGEN_URL", f"https://api-inference.huggingface.co/models/{_HF_MODEL}")
_TIMEOUT = int(os.getenv("HF_DECISION_TIMEOUT", "35"))
_USE_LLM = os.getenv("USE_LLM_AGENT", "false").lower() in {"1", "true", "yes"}

PREFERRED_COMPANIES = {
    "adnoc": 14,
    "beeah": 14,
    "veolia": 14,
    "parsons": 12,
    "aecom": 12,
    "wsp": 12,
    "emirates global aluminium": 12,
    "ega": 12,
    "masdar": 14,
    "enoc": 10,
    "dnata": 8,
    "amazon": 8,
    "al jomaih energy": 8,
}

BLACKLISTED_COMPANIES = {
    "theuaejobs": -45,
    "confidential": -12,
    "unknown": -15,
    "talentmate": -8,
    "shine.com": -8,
}

TITLE_DOMAIN = ["hse", "ehs", "qhse", "hsse", "esg", "sustainability", "environment", "environmental", "compliance"]
SENIORITY = ["manager", "senior", "lead", "head", "director", "regional"]
DISQUALIFIERS = [
    "intern", "junior", "trainee", "fresh graduate", "graduate programme",
    "nurse", "driver", "cleaner", "receptionist", "secretary",
    "quantity surveyor", "site engineer", "civil engineer", "mep",
    "cad supervisor", "cad manager", "architectural engineer",
    "landscape", "landscaping", "swimming pool", "facade", "aluminum",
    "sales account", "sales engineer", "transport planner",
    "foreman", "superintendent", "uae national only", "nationals only",
]
LOCATIONS = ["uae", "dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah"]


@dataclass
class JobDecision:
    job: Dict[str, Any]
    decision: str  # apply | watch | skip
    reasoning: str
    cover_letter: Optional[str] = None
    confidence: float = 0.0
    final_score: int = 0
    factors: Optional[Dict[str, Any]] = None
    created_at: str = ""


def _token() -> str:
    return os.getenv("HF_TOKEN", "").strip()


def _txt(value: Any) -> str:
    return str(value or "").lower()


def _job_text(job: Dict[str, Any]) -> str:
    return " ".join(_txt(job.get(k, "")) for k in ["title", "company", "location", "description"])


def _init_linkedin_data():
    """Initialize LinkedIn data integration"""
    global _linkedin_loader, _linkedin_skill_matcher, _linkedin_company_targeter, _linkedin_analyzer

    try:
        from src.linkedin_integration import LinkedInDataLoader, SkillMatcher, CompanyTargeter, ApplicationAnalyzer
    except ImportError:
        from linkedin_integration import LinkedInDataLoader, SkillMatcher, CompanyTargeter, ApplicationAnalyzer

    if _linkedin_loader is None:
        try:
            loader = LinkedInDataLoader()
            loader.load_all()
            _linkedin_loader = loader
            _linkedin_skill_matcher = SkillMatcher(loader.skills)
            _linkedin_company_targeter = CompanyTargeter(loader.company_follows)
            _linkedin_analyzer = ApplicationAnalyzer(loader.job_applications)
            logger.info("LinkedIn data initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize LinkedIn data: {e}")


def _company_delta(company: str) -> Tuple[int, str]:
    c = _txt(company)

    # Check LinkedIn company follows first
    if _linkedin_company_targeter and _linkedin_company_targeter.is_target_company(company):
        return 20, f"LinkedIn followed company: {company} +20"

    # Check hardcoded preferred companies
    for name, delta in PREFERRED_COMPANIES.items():
        if name in c:
            return delta, f"preferred company: {name} +{delta}"
    for name, delta in BLACKLISTED_COMPANIES.items():
        if name in c:
            return delta, f"low-trust/source company: {name} {delta}"
    return 0, "neutral company"


def feedback_threshold(default: int = 60) -> int:
    """Adjust apply threshold using local application outcomes, if available."""
    path = Path(os.getenv("APPLIED_JOBS_FILE", "data/applied_jobs.json"))
    if not path.exists():
        # Also support flat uploaded-file layout.
        path = Path("applied_jobs.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if len(data) < 5:
            return default
        total = len(data)
        interviews = sum(1 for j in data if _txt(j.get("status")) in {"interview", "interview_scheduled", "offer", "offer_extended"})
        rejections = sum(1 for j in data if _txt(j.get("status")) == "rejected")
        positive_rate = interviews / max(1, total)
        rejection_rate = rejections / max(1, total)
        if positive_rate >= 0.25:
            return max(55, default - 7)
        if rejection_rate >= 0.55:
            return min(75, default + 8)
        return default
    except Exception as exc:
        logger.warning("feedback_threshold_failed error=%s", exc)
        return default


def _factor_score(job: Dict[str, Any]) -> Tuple[int, Dict[str, Any], List[str]]:
    title = _txt(job.get("title"))
    location = _txt(job.get("location"))
    text = _job_text(job)
    base = int(float(job.get("score", 0)))
    reasons: List[str] = [f"base score {base}"]
    # Reduce semantic amplification
    final = int(base * 1.15)

    # Initialize LinkedIn data if not already loaded
    _init_linkedin_data()

    # Check disqualifiers only in title, not full description
    disq = [d for d in DISQUALIFIERS if d in title]
    if disq:
        final -= 20
        reasons.append(f"disqualifier detected: {', '.join(disq)} -20")

    title_hits = [k for k in TITLE_DOMAIN if k in title]
    if title_hits:
        boost = 18 if len(title_hits) >= 2 else 12
        final += boost
        reasons.append(f"target title/domain match: {', '.join(title_hits[:3])} +{boost}")
    elif any(k in title for k in ["operations", "compliance", "qaqc", "qhse"]):
        final += 6
        reasons.append("related title match (operations/compliance/qhse) +6")
    else:
        final -= 10
        reasons.append("weak ESG/HSE title match -10")

    seniority_hits = [k for k in SENIORITY if k in title]
    if seniority_hits:
        final += 8
        reasons.append(f"correct seniority: {', '.join(seniority_hits[:2])} +8")
    elif "senior" in title:
        final += 6
        reasons.append("senior level +6")
    else:
        final -= 2
        reasons.append("seniority unclear/low -2")

    loc_hits = [k for k in LOCATIONS if k in location or k in text]
    if loc_hits:
        final += 6
        reasons.append(f"UAE location fit: {loc_hits[0]} +6")

    company_delta, company_reason = _company_delta(str(job.get("company", "")))
    # Reduce boost stacking - cap company boost to 10
    company_delta = min(company_delta, 10)
    final += company_delta
    reasons.append(company_reason)

    # LinkedIn skill matching
    if _linkedin_skill_matcher:
        matching_skills = _linkedin_skill_matcher.get_matching_skills(text)
        if matching_skills:
            # Reduce boost stacking - cap skill boost to 10
            skill_boost = min(len(matching_skills) * 4, 10)
            final += skill_boost
            reasons.append(f"LinkedIn skills match: {', '.join(matching_skills[:3])} +{skill_boost}")

    # Normalize final score to max 100
    final = min(final, 100)
    factors = {
        "base_score": base,
        "title_hits": title_hits,
        "seniority_hits": seniority_hits,
        "location_hits": loc_hits,
        "disqualifiers": disq,
        "company_delta": company_delta,
        "dynamic_apply_threshold": feedback_threshold(),
        "linkedin_skills": matching_skills if _linkedin_skill_matcher else [],
    }
    return final, factors, reasons


def _fallback_decision(job: Dict[str, Any]) -> Tuple[str, str, float, int, Dict[str, Any]]:
    final, factors, reasons = _factor_score(job)
    threshold = factors["dynamic_apply_threshold"]

    # Strict title filter - must have at least one TITLE_DOMAIN keyword before any apply decision
    title = _txt(job.get("title"))
    title_hits = factors["title_hits"]
    if not title_hits and not any(k in title for k in ["operations", "compliance", "qaqc", "qhse"]):
        return "skip", "title does not match ESG/HSE domain (no target keywords)", 0.9, 0, factors

    # Only skip for true hard disqualifiers
    if factors["disqualifiers"]:
        return "skip", "hard disqualifier", 0.9, 0, factors

    # Always produce candidates - rank instead of filter
    if final >= 75:
        decision = "apply"
    elif final >= 55:
        decision = "watch"
    else:
        decision = "watch"  # NOT skip - always produce candidates

    return decision, " | ".join(reasons), 0.7, final, factors


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _llm_decision(job: Dict[str, Any], fallback: Tuple[str, str, float, int, Dict[str, Any]]) -> Tuple[str, str, float, int, Dict[str, Any]]:
    token = _token()
    if not (_USE_LLM and token):
        return fallback

    final = fallback[3]
    factors = fallback[4]
    prompt = f"""<s>[INST]
You are an expert UAE ESG/HSE recruitment decision agent.
Candidate: Roben Edwan, Ajman UAE, 10+ years ESG/HSE/environmental compliance, ISO 14001, UAE municipalities, waste management, wastewater/FOG, multi-site operations, ESG reporting.

Return JSON only with keys: decision, reasoning, confidence.
Allowed decision values: apply, watch, skip.

Rules:
- Skip for hard disqualifiers: intern, junior, nurse, driver
- Skip if title does NOT contain any ESG/HSE keywords (hse, ehs, qhse, hsse, esg, sustainability, environment, environmental, compliance, operations, qaqc)
- Apply if final_score >= 60 AND title matches ESG/HSE domain
- Watch if final_score >= 40
- Always produce candidates (rank, don't filter) - prefer watch over skip

Precomputed final_score: {final}
Factors: {json.dumps(factors)}
Job title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description: {str(job.get('description', ''))[:1800]}
[/INST]"""

    try:
        resp = requests.post(
            _HF_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"inputs": prompt, "parameters": {"max_new_tokens": 180, "temperature": 0.1, "return_full_text": False}, "options": {"wait_for_model": True}},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        generated = data[0].get("generated_text", "") if isinstance(data, list) and data else str(data)
        parsed = _extract_json(generated)
        if not parsed:
            return fallback
        decision = str(parsed.get("decision", fallback[0])).lower().strip()
        if decision not in {"apply", "watch", "skip"}:
            decision = fallback[0]
        confidence = float(parsed.get("confidence", fallback[2]))
        reasoning = str(parsed.get("reasoning", fallback[1]))
        return decision, reasoning, max(0.0, min(1.0, confidence)), final, factors
    except Exception as exc:
        logger.warning("llm_decision_failed_using_fallback error=%s", exc)
        return fallback


def decide_job(job: Dict[str, Any], generate_letter: bool = True) -> JobDecision:
    fallback = _fallback_decision(job)
    decision, reasoning, confidence, final_score, factors = _llm_decision(job, fallback)

    cover_letter = None
    if decision == "apply" and generate_letter:
        try:
            from src.cover_letter_writer import generate_cover_letter
        except ImportError:
            from cover_letter_writer import generate_cover_letter  # type: ignore
        cover_letter = generate_cover_letter(job)

    return JobDecision(
        job=job,
        decision=decision,
        reasoning=reasoning,
        cover_letter=cover_letter,
        confidence=confidence,
        final_score=final_score,
        factors=factors,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def decide_jobs(jobs: List[Dict[str, Any]], generate_letters: bool = True) -> List[JobDecision]:
    decisions: List[JobDecision] = []
    for job in jobs:
        try:
            decisions.append(decide_job(job, generate_letter=generate_letters))
            time.sleep(0.03)
        except Exception as exc:
            logger.error("job_decision_failed title=%s error=%s", job.get("title"), exc)
            decisions.append(JobDecision(job=job, decision="skip", reasoning=f"Decision failed: {exc}", confidence=0.0, final_score=0, factors={}, created_at=datetime.now(timezone.utc).isoformat()))
    logger.info("job_decisions_complete total=%s apply=%s watch=%s skip=%s", len(decisions), sum(d.decision == "apply" for d in decisions), sum(d.decision == "watch" for d in decisions), sum(d.decision == "skip" for d in decisions))
    return decisions


def get_apply_candidates(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [d.job for d in decide_jobs(jobs, generate_letters=False) if d.decision == "apply"]


def get_watch_candidates(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [d.job for d in decide_jobs(jobs, generate_letters=False) if d.decision == "watch"]


def decisions_to_dicts(decisions: List[JobDecision]) -> List[Dict[str, Any]]:
    return [asdict(d) for d in decisions]
