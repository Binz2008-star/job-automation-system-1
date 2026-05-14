"""
src/rico_hf_client.py
Hugging Face Inference API client for Rico AI.

Primary provider for Rico's NLP capabilities (text generation, classification,
summarization). OpenAI is optional and reserved for future premium mode.

Environment variables:
  HF_API_TOKEN            -- primary token (canonical)
  HF_TOKEN / HF_API_KEY   -- legacy aliases, tried in order
  HF_TEXT_MODEL           -- text generation model (default: HuggingFaceH4/zephyr-7b-beta)
  HF_CLASSIFICATION_MODEL -- zero-shot classification model (default: facebook/bart-large-mnli)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_HF_API_BASE = "https://api-inference.huggingface.co/models"
_DEFAULT_TEXT_MODEL = "HuggingFaceH4/zephyr-7b-beta"
_DEFAULT_CLASSIFICATION_MODEL = "facebook/bart-large-mnli"
_REQUEST_TIMEOUT = 25


def _get_token() -> str:
    return (
        os.getenv("HF_API_TOKEN", "").strip()
        or os.getenv("HF_TOKEN", "").strip()
        or os.getenv("HF_API_KEY", "").strip()
        or os.getenv("HUGGINGFACE_API_KEY", "").strip()
    )


def _headers() -> Dict[str, str]:
    return {
        "Authorization": "Bearer " + _get_token(),
        "Content-Type": "application/json",
    }


def is_available() -> bool:
    """Return True when an HF token is present in the environment."""
    return bool(_get_token())


def generate_text(
    prompt: str,
    *,
    system: str = "",
    max_new_tokens: int = 300,
    temperature: float = 0.7,
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Call HF text generation inference.

    Returns the generated text string on success, None on any failure.
    Never raises -- all errors are caught and logged.
    """
    token = _get_token()
    if not token:
        logger.debug("hf_generate: no token configured")
        return None

    model_id = model or os.getenv("HF_TEXT_MODEL", _DEFAULT_TEXT_MODEL)
    url = _HF_API_BASE + "/" + model_id

    _lt = chr(60)
    _gt = chr(62)
    _sys_tag  = _lt + "|system|" + _gt
    _end_tag  = _lt + "/s" + _gt
    _usr_tag  = _lt + "|user|" + _gt
    _asst_tag = _lt + "|assistant|" + _gt

    parts = []
    if system:
        parts.append(_sys_tag + "\n" + system + _end_tag)
    parts.append(_usr_tag + "\n" + prompt + _end_tag)
    parts.append(_asst_tag)
    full_prompt = "\n".join(parts)

    try:
        resp = requests.post(
            url,
            json={
                "inputs": full_prompt,
                "parameters": {
                    "max_new_tokens": max_new_tokens,
                    "temperature": temperature,
                    "return_full_text": False,
                },
            },
            headers=_headers(),
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code in (429, 503):
            logger.debug("hf_generate: rate_limited/overloaded status=%s model=%s", resp.status_code, model_id)
            return None
        if resp.status_code == 404:
            logger.debug("hf_generate: model_not_found model=%s", model_id)
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            raw = data[0].get("generated_text", "") if isinstance(data[0], dict) else str(data[0])
        elif isinstance(data, dict):
            raw = data.get("generated_text", "")
        else:
            raw = str(data)
        return raw.strip() or None
    except Exception as exc:
        logger.debug("hf_generate: error=%s model=%s", exc, model_id)
        return None


def classify_intent(
    text: str,
    candidate_labels: List[str],
    *,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Zero-shot classification via HF inference.

    Returns dict with 'labels' and 'scores' sorted by score descending,
    or None on failure.
    """
    token = _get_token()
    if not token:
        logger.debug("hf_classify: no token configured")
        return None

    model_id = model or os.getenv("HF_CLASSIFICATION_MODEL", _DEFAULT_CLASSIFICATION_MODEL)
    url = _HF_API_BASE + "/" + model_id

    try:
        resp = requests.post(
            url,
            json={
                "inputs": text,
                "parameters": {"candidate_labels": candidate_labels},
            },
            headers=_headers(),
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code in (429, 503, 404):
            logger.debug("hf_classify: non_ok status=%s model=%s", resp.status_code, model_id)
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "labels" in data and "scores" in data:
            paired = sorted(zip(data["labels"], data["scores"]), key=lambda x: x[1], reverse=True)
            return {
                "labels": [p[0] for p in paired],
                "scores": [p[1] for p in paired],
                "top_label": paired[0][0] if paired else "",
                "top_score": paired[0][1] if paired else 0.0,
            }
        return None
    except Exception as exc:
        logger.debug("hf_classify: error=%s model=%s", exc, model_id)
        return None


def summarize(
    text: str,
    *,
    max_length: int = 120,
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Summarize text via HF inference.

    Returns summarized string or None on failure.
    """
    token = _get_token()
    if not token:
        return None

    model_id = model or os.getenv("HF_SUMMARIZATION_MODEL", "facebook/bart-large-cnn")
    url = _HF_API_BASE + "/" + model_id

    try:
        resp = requests.post(
            url,
            json={
                "inputs": text[:2000],
                "parameters": {"max_length": max_length, "min_length": 30},
            },
            headers=_headers(),
            timeout=_REQUEST_TIMEOUT,
        )
        if not resp.ok:
            return None
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0].get("summary_text", "").strip() or None
        return None
    except Exception as exc:
        logger.debug("hf_summarize: error=%s", exc)
        return None
