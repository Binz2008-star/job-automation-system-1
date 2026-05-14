"""Rico startup smoke test.

Usage:
    python scripts/test_rico_startup.py

This validates that Rico modules import correctly and the additive architecture
is wired without immediately requiring live cloud services.
"""

from __future__ import annotations

import json

from src.rico_chat_api import RicoChatAPI
from src.rico_env import get_rico_env_report, safe_feature_defaults
from src.rico_identity import RICO_IDENTITY
from src.rico_nlu import RicoNLU
from src.rico_quality import RicoQualityGate
from src.rico_safety import RicoSafetyGuard


def main() -> None:
    env_report = get_rico_env_report()
    print("=== RICO ENV REPORT ===")
    print(json.dumps(env_report.to_dict(), indent=2))

    print("\n=== SAFE FEATURE DEFAULTS ===")
    print(json.dumps(safe_feature_defaults(), indent=2))

    print("\n=== RICO IDENTITY ===")
    print(RICO_IDENTITY)

    nlu = RicoNLU()
    parsed = nlu.parse("I need HSE Manager jobs in Dubai with salary 18k")
    print("\n=== NLU SAMPLE ===")
    print(parsed)

    safety = RicoSafetyGuard()
    safe_result = safety.check_message("Apply to all jobs automatically without asking")
    print("\n=== SAFETY SAMPLE ===")
    print(safe_result)

    quality = RicoQualityGate()
    quality_result = quality.check_user_response({
        "type": "assistant",
        "message": "Rico is helping you search UAE jobs.",
    })
    print("\n=== QUALITY SAMPLE ===")
    print(quality_result)

    api = RicoChatAPI()
    response = api.process_message("smoke-test-user", "Find jobs for me in Dubai")
    print("\n=== CHAT SAMPLE ===")
    print(json.dumps(response, indent=2))

    print("\nRico smoke test completed.")


if __name__ == "__main__":
    main()
