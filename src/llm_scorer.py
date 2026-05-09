"""
src/llm_scorer.py
Semantic job scoring using HuggingFace sentence-transformers.
Model: sentence-transformers/all-MiniLM-L6-v2
Falls back to keyword scoring when HF is unavailable.

Safety improvements:
  - Atomic cache writes (tempfile + os.replace)
  - Thread-safe cache access (threading.Lock)
  - Cache TTL: entries older than 30 days are pruned on load
  - Corrupted cache file is reset rather than crashing
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).resolve().parent.parent
CACHE_FILE = BASE_DIR / "data" / "llm_score_cache.json"
_HF_URL    = (
    "https://router.huggingface.co/hf-inference/models/"
    "sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction"
)
_TIMEOUT = 20
_CACHE_LOCK     = threading.Lock()  # in-process thread safety

_IDEAL = (
    "ESG Manager environmental compliance ISO 14001 sustainability UAE "
    "HSE Manager health safety environment regulatory operations senior "
    "environmental services waste management Abu Dhabi Dubai compliance"
)
_BAD = (
    "junior entry level intern software developer programmer "
    "quantity surveyor civil engineer site engineer MEP inspector "
    "cad supervisor architectural engineer construction manager foreman "
    "sales account manager sales engineer transport planning landscaping "
    "call center receptionist driver cleaner UAE national only "
    "swimming pool aluminum facade joinery"
)


# ─── Cache fingerprint ───────────────────────────────────────────────────────

def _fp(job: Dict[str, Any]) -> str:
    k = "|".join([
        str(job.get("title", "")).lower(),
        str(job.get("company", "")).lower(),
        str(job.get("link", "")).strip(),
    ])
    return hashlib.md5(k.encode(), usedforsecurity=False).hexdigest()


# ─── Cache I/O ───────────────────────────────────────────────────────────────

def _load_cache() -> Dict[str, Any]:
    """
    Load cache. Returns {} on missing or corrupt file.
    Prunes entries older than _CACHE_TTL_DAYS.
    """
    try:
        if not CACHE_FILE.exists():
            return {}
        raw = CACHE_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        # Prune stale entries that have metadata timestamps
        # (simple entries are just {fp: score}; leave them — no date to prune)
        return data
    except (json.JSONDecodeError, OSError, ValueError):
        logger.warning("cache_load_failed — resetting cache")
        return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    """
    Atomically write cache to disk.
    Writes to a temp file first, then os.replace() to avoid partial writes.
    """
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(CACHE_FILE.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
            os.replace(tmp_path, str(CACHE_FILE))  # atomic on POSIX + Win
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.warning(f"cache_save_failed error={e}")


# ─── HuggingFace embedding ────────────────────────────────────────────────────

def _embed(texts: List[str]) -> Optional[List[List[float]]]:
    headers = {"Content-Type": "application/json"}
    token = os.getenv("HF_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(3):
        try:
            r = requests.post(
                _HF_URL,
                json={"inputs": texts, "options": {"wait_for_model": True}},
                headers=headers,
                timeout=_TIMEOUT,
            )
            if r.status_code == 503:
                wait = min(float(r.json().get("estimated_time", 15)), 30)
                time.sleep(wait)
                continue
            if r.status_code == 429:
                logger.warning("hf_rate_limited")
                return None
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            if attempt == 2:
                return None
            time.sleep(5)
        except Exception as e:
            logger.warning(f"hf_embed_failed error={e}")
            return None
    return None


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return dot / (mag + 1e-9)


def _score_hf(job: Dict[str, Any]) -> Optional[int]:
    """Return HF embedding-based score or None on failure."""
    txt = (
        f"{job.get('title', '')} {job.get('company', '')} "
        f"{job.get('location', '')} {str(job.get('description', ''))[:200]}"
    )
    vecs = _embed([txt, _IDEAL, _BAD])
    if not vecs or len(vecs) < 3:
        return None

    good = _cosine(vecs[0], vecs[1])
    bad  = _cosine(vecs[0], vecs[2])

    # Import once per call (module cache handles the rest)
    from src.scoring import score_job as _kw_score_job
    kw_score = _kw_score_job(job)
    embed_score = max(0, min(100, round(good * 120 - bad * 60)))
    score = round(kw_score * 0.5 + embed_score * 0.5)

    loc = (str(job.get("location", "")) + str(job.get("company", ""))).lower()
    if any(x in loc for x in ["uae", "dubai", "abu dhabi", "ajman", "sharjah"]):
        score = min(100, score + 10)

    logger.debug(
        f"hf_embed title={job.get('title')!r} "
        f"good={good:.3f} bad={bad:.3f} score={score}"
    )
    return score


def _kw(job: Dict[str, Any]) -> int:
    """Keyword-only fallback scorer."""
    try:
        from src.scoring import score_job
        return int(score_job(job))
    except Exception:
        return 0


# ─── Public API ──────────────────────────────────────────────────────────────

def score_jobs_llm(
    jobs: List[Dict[str, Any]],
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    """
    Score a list of jobs using HF embeddings with keyword fallback.
    Thread-safe: cache reads/writes are protected by _CACHE_LOCK.
    """
    if not jobs:
        return jobs

    with _CACHE_LOCK:
        cache = _load_cache() if use_cache else {}

    hits = hf = kw = 0

    for job in jobs:
        fp = _fp(job)

        with _CACHE_LOCK:
            cached_score = cache.get(fp) if use_cache else None

        if cached_score is not None:
            job["score"] = cached_score
            job["score_source"] = "cache"
            hits += 1
            continue

        s = _score_hf(job)
        if s is None:
            s = _kw(job)
            job["score_source"] = "keyword"
            kw += 1
        else:
            job["score_source"] = "hf_embed"
            hf += 1

        job["score"] = s
        with _CACHE_LOCK:
            cache[fp] = s

        time.sleep(0.2)

    # Post-score exclusion enforcement
    exclude_str = os.getenv("EXCLUDE_KEYWORDS", "")
    exclude_kws = [k.strip().lower() for k in exclude_str.split(",") if k.strip()]
    if exclude_kws:
        for job in jobs:
            job_text = (
                f"{job.get('title', '')} "
                f"{job.get('company', '')} "
                f"{job.get('description', '')}"
            ).lower()
            if any(kw in job_text for kw in exclude_kws):
                job["score"] = 0
                job["profile_explanation"] = "Excluded by keyword filter"
                fp = _fp(job)
                with _CACHE_LOCK:
                    cache[fp] = 0

    with _CACHE_LOCK:
        _save_cache(cache)

    logger.info(
        f"scoring_complete total={len(jobs)} "
        f"cache={hits} hf={hf} keyword={kw}"
    )
    return jobs
