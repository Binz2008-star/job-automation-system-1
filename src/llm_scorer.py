"""
src/llm_scorer.py
Semantic job scoring using HuggingFace sentence-transformers embeddings.
Model: sentence-transformers/all-MiniLM-L6-v2
Falls back to keyword scoring if HF unavailable.
"""
from __future__ import annotations
import hashlib, json, logging, math, os, time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

logger     = logging.getLogger(__name__)
BASE_DIR   = Path(__file__).resolve().parent.parent
CACHE_FILE = BASE_DIR / "data" / "llm_score_cache.json"
_HF_URL    = "https://router.huggingface.co/hf-inference/models/sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction"
_TIMEOUT   = 20

_IDEAL = (
    "ESG Manager environmental compliance ISO 14001 sustainability UAE "
    "HSE Manager health safety environment regulatory operations senior "
    "environmental services waste management Abu Dhabi Dubai compliance"
)
_BAD = (
    "junior entry level intern software developer programmer "
    "quantity surveyor civil engineer site engineer MEP "
    "call center sales receptionist driver cleaner UAE national only"
)


def _fp(job):
    k = "|".join([str(job.get("title","")).lower(), str(job.get("company","")).lower(), str(job.get("link","")).strip()])
    return hashlib.md5(k.encode()).hexdigest()

def _load_cache():
    try:
        if CACHE_FILE.exists(): return json.loads(CACHE_FILE.read_text())
    except: pass
    return {}

def _save_cache(c):
    try:
        CACHE_FILE.parent.mkdir(exist_ok=True)
        CACHE_FILE.write_text(json.dumps(c, indent=2))
    except: pass

def _embed(texts):
    h = {"Content-Type": "application/json"}
    t = os.getenv("HF_TOKEN","")
    t = t.strip()
    if t: h["Authorization"] = f"Bearer {t}"
    for attempt in range(3):
        try:
            r = requests.post(_HF_URL, json={"inputs": texts, "options": {"wait_for_model": True}}, headers=h, timeout=_TIMEOUT)
            if r.status_code == 503:
                time.sleep(min(float(r.json().get("estimated_time",15)), 30)); continue
            if r.status_code == 429:
                logger.warning("hf_rate_limited"); return None
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            if attempt == 2: return None
            time.sleep(5)
        except Exception as e:
            logger.warning(f"hf_embed_failed error={e}"); return None
    return None

def _cos(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    return dot / (math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b)) + 1e-9)

def _score_hf(job):
    txt = f"{job.get('title','')} {job.get('company','')} {job.get('location','')} {str(job.get('description',''))[:200]}"
    vecs = _embed([txt, _IDEAL, _BAD])
    if not vecs or len(vecs) < 3: return None
    good = _cos(vecs[0], vecs[1])
    bad  = _cos(vecs[0], vecs[2])
    kw_score = __import__("src.scoring", fromlist=["score_job"]).score_job(job)
    embed_score = max(0, min(100, round(good * 120 - bad * 60)))
    score = round(kw_score * 0.5 + embed_score * 0.5)
    loc = (str(job.get("location","")) + str(job.get("company",""))).lower()
    if any(x in loc for x in ["uae","dubai","abu dhabi","ajman","sharjah"]):
        score = min(100, score + 10)
    logger.debug(f"hf_embed title={job.get('title')!r} good={good:.3f} bad={bad:.3f} score={score}")
    return score

def _kw(job):
    try:
        from src.scoring import score_job
        return int(score_job(job))
    except: return 0

def score_jobs_llm(jobs, use_cache=True):
    if not jobs: return jobs
    cache = _load_cache() if use_cache else {}
    hits = hf = kw = 0
    for job in jobs:
        fp = _fp(job)
        if use_cache and fp in cache:
            job["score"] = cache[fp]; job["score_source"] = "cache"; hits += 1; continue
        s = _score_hf(job)
        if s is None:
            s = _kw(job); job["score_source"] = "keyword"; kw += 1
        else:
            job["score_source"] = "hf_embed"; hf += 1
        job["score"] = s; cache[fp] = s
        time.sleep(0.2)
    _save_cache(cache)
    logger.info(f"scoring_complete total={len(jobs)} cache={hits} hf={hf} keyword={kw}")
    return jobs
