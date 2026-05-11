"""Environment validation for Rico AI.

This module validates the runtime environment without failing the legacy daily
pipeline. Rico server/worker entrypoints can call it to show clear readiness
status for cloud deployment.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class EnvCheck:
    name: str
    required: bool
    present: bool
    purpose: str


@dataclass
class RicoEnvReport:
    ready_for_api: bool
    ready_for_db: bool
    ready_for_telegram: bool
    ready_for_openai: bool
    ready_for_jotform: bool
    ready_for_hf: bool
    ai_provider: str
    checks: List[EnvCheck]

    def to_dict(self) -> Dict[str, object]:
        return {
            "ready_for_api": self.ready_for_api,
            "ready_for_db": self.ready_for_db,
            "ready_for_telegram": self.ready_for_telegram,
            "ready_for_openai": self.ready_for_openai,
            "ready_for_jotform": self.ready_for_jotform,
            "ready_for_hf": self.ready_for_hf,
            "ai_provider": self.ai_provider,
            "checks": [asdict(check) for check in self.checks],
        }


ENV_SPECS = [
    ("DATABASE_URL", True, "Neon/PostgreSQL persistence for Rico memory and profiles"),
    ("TELEGRAM_BOT_TOKEN", False, "Telegram bot messages and webhook replies"),
    ("TELEGRAM_CHAT_ID", False, "Legacy/default Telegram notification target"),
    ("OPENAI_API_KEY", False, "AI tool-calling, message generation, and advanced reasoning"),
    ("HF_API_KEY", False, "Hugging Face free inference API key for fallback chat responses"),
    ("HF_TOKEN", False, "Legacy Hugging Face token — also checked for HF fallback"),
    ("HUGGINGFACE_API_KEY", False, "Alternative Hugging Face key alias"),
    ("RICO_AI_PROVIDER", False, "AI provider: none|openai|huggingface (default: auto)"),
    ("JOTFORM_API_KEY", False, "Jotform onboarding CV/file retrieval"),
    ("JOTFORM_FORM_ID", False, "Rico onboarding form ID"),
    ("JOTFORM_RICO_FORM_ID", False, "Rico onboarding form ID alias"),
    ("JOTFORM_WEBHOOK_SECRET", False, "Webhook verification when enabled"),
    ("REDIS_URL", False, "Background jobs, reminders, and alert queues"),
    ("RICO_ENABLE_AUTO_APPLY", False, "Feature flag; should default to false"),
    ("RICO_REQUIRE_APPROVAL_FOR_APPLICATIONS", False, "Feature flag; should default to true"),
]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _hf_key_present() -> bool:
    """True when any HF key alias is set."""
    return bool(
        os.getenv("HF_API_KEY") or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY")
    )


def _openai_key_present() -> bool:
    """True when either canonical or legacy OpenAI env var is set."""
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API"))


def get_ai_provider() -> str:
    """Get the AI provider from environment with safe auto-detection.

    Explicit RICO_AI_PROVIDER always wins.
    When not set:
      - If OpenAI is explicitly chosen and key present → "openai"
      - If HF key present → "huggingface" (default free path)
      - Else → "none"

    OpenAI is NEVER auto-enabled to avoid billing surprises.
    """
    provider = os.getenv("RICO_AI_PROVIDER", "").strip().lower()
    if provider:
        if provider in {"none", "openai", "huggingface", "hf"}:
            return "huggingface" if provider == "hf" else provider
        logger.warning(f"Invalid RICO_AI_PROVIDER value: {provider}. Using auto-detect.")

    # Auto-detect: HF is the safe default free path
    if _hf_key_present():
        return "huggingface"
    if _openai_key_present() and provider == "openai":
        return "openai"
    return "none"


def get_rico_env_report() -> RicoEnvReport:
    checks = [
        EnvCheck(name=name, required=required, present=bool(os.getenv(name)), purpose=purpose)
        for name, required, purpose in ENV_SPECS
    ]
    present = {check.name: check.present for check in checks}
    provider = get_ai_provider()
    openai_key_present = _openai_key_present()
    hf_key_present = _hf_key_present()

    # OpenAI is only "ready" when explicitly enabled AND key present
    ready_for_openai = provider == "openai" and openai_key_present

    # HF is ready when any HF key is present
    ready_for_hf = hf_key_present

    # Jotform is ready when form ID is present (webhook secret is production-only)
    jotform_form_id_present = bool(
        present.get("JOTFORM_FORM_ID", False)
        or present.get("JOTFORM_RICO_FORM_ID", False)
    )
    ready_for_jotform = jotform_form_id_present

    return RicoEnvReport(
        ready_for_api=True,
        ready_for_db=present.get("DATABASE_URL", False),
        ready_for_telegram=present.get("TELEGRAM_BOT_TOKEN", False),
        ready_for_openai=ready_for_openai,
        ready_for_jotform=ready_for_jotform,
        ready_for_hf=ready_for_hf,
        ai_provider=provider,
        checks=checks,
    )


def safe_feature_defaults() -> Dict[str, bool]:
    return {
        "auto_apply_enabled": env_bool("RICO_ENABLE_AUTO_APPLY", False),
        "approval_required_for_applications": env_bool("RICO_REQUIRE_APPROVAL_FOR_APPLICATIONS", True),
        "telegram_enabled": env_bool("RICO_ENABLE_TELEGRAM", True),
        "learning_enabled": env_bool("RICO_ENABLE_LEARNING", True),
    }
