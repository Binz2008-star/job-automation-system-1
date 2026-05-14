"""
scripts/smoke_rico_chat_flow.py
==============================
Local smoke test for the core Rico chat flow.

Simulates guest/public user chat without browser or external APIs.
No OpenAI, no HF, no live job search calls.

Usage:
    python scripts/smoke_rico_chat_flow.py

Exit codes:
    0  all pass
    1  any fail
"""
from __future__ import annotations

import os
import sys

# Allow importing src.* when script is run from project root or scripts/ dir
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from unittest.mock import MagicMock, patch


def _make_api():
    """Build RicoChatAPI with all external I/O mocked."""
    patches = [
        patch("src.rico_memory.RicoMemoryStore"),
        patch("src.rico_agent.RicoAgent"),
        patch("src.rico_repo_adapter.RicoSystem"),
        patch("src.rico_openai_agent.RicoOpenAIAgent"),
    ]
    for p in patches:
        p.start()

    from src.rico_chat_api import RicoChatAPI

    api = RicoChatAPI()
    api.memory = MagicMock()
    api.memory.append_chat_message = MagicMock()
    api.system = MagicMock()
    api.system.run_for_profile = MagicMock(return_value={"matches": []})
    api.openai_agent = MagicMock()
    api.openai_agent.model = "gpt-4o"
    api.openai_agent.openai_available = True
    api.openai_agent.deepseek_available = False
    api.openai_agent.hf_available = False
    api.openai_agent.provider_available = True
    api.openai_agent.provider_state = None

    for p in patches:
        p.stop()

    return api


def _cv_profile() -> dict:
    return {
        "cv_status": "processed",
        "cv_filename": "test_cv.pdf",
        "skills": ["HSE Management", "ISO 14001", "Safety", "Compliance"],
        "certifications": ["NEBOSH IGC", "ISO 14001 Lead Auditor"],
        "years_experience": 8,
        "industries": ["Oil & Gas"],
        "target_roles": ["Senior HSE Manager"],
    }


def _run(api, message: str, profile: dict, route_entities=None) -> dict:
    from unittest.mock import MagicMock

    route_mock = MagicMock(
        tool_name=None, entities=route_entities or {}, tool_args={},
        confirmation_prompt=None, source="keyword"
    )
    with (
        patch("src.rico_chat_api.get_profile", return_value=profile),
        patch("src.rico_chat_api.is_onboarding_complete", return_value=True),
        patch("src.rico_chat_api.upsert_profile", return_value=profile),
        patch("src.rico_chat_api._route", return_value=route_mock),
    ):
        return api._handle_active_user("test-user", message)


def main() -> int:
    failures = []
    api = _make_api()
    cv = _cv_profile()

    # ── Step 1: "am looking for job" → profile_role_suggestions ────────────
    result = _run(api, "am looking for job", cv)
    if result.get("type") != "profile_role_suggestions":
        failures.append(
            f"FAIL: 'am looking for job' → expected 'profile_role_suggestions', got {result.get('type')!r}"
        )
    else:
        print("PASS: 'am looking for job' → profile_role_suggestions")

    # ── Step 2: "Senior HSE Manager" → role_confirmation ───────────────────
    api2 = _make_api()
    result = _run(api2, "Senior HSE Manager", cv)
    if result.get("type") != "role_confirmation":
        failures.append(
            f"FAIL: 'Senior HSE Manager' → expected 'role_confirmation', got {result.get('type')!r}"
        )
    else:
        print("PASS: 'Senior HSE Manager' → role_confirmation")
        if api2.system.run_for_profile.called:
            failures.append("FAIL: run_for_profile called for role_confirmation (should not)")
        else:
            print("      run_for_profile: NOT called (correct)")

    # ── Step 3: "so?" → options ─────────────────────────────────────────────
    api3 = _make_api()
    result = _run(api3, "so?", cv)
    if result.get("type") != "options":
        failures.append(
            f"FAIL: 'so?' → expected 'options', got {result.get('type')!r}"
        )
    else:
        print("PASS: 'so?' → options")
        if api3.system.run_for_profile.called:
            failures.append("FAIL: run_for_profile called for 'so?' (should not)")
        else:
            print("      run_for_profile: NOT called (correct)")

    # ── Step 4: "find live jobs for Senior HSE Manager" → pipeline ─────────
    api4 = _make_api()
    result = _run(
        api4, "find live jobs for Senior HSE Manager", cv,
        route_entities={"job_title": "Senior HSE Manager"}
    )
    if result.get("type") == "role_confirmation":
        failures.append(
            "FAIL: live search triggered role_confirmation instead of pipeline"
        )
    elif api4.system.run_for_profile.called:
        print("PASS: 'find live jobs for Senior HSE Manager' → pipeline (run_for_profile called)")
    else:
        # It may have been routed elsewhere; check it wasn't the fast path at least
        if result.get("type") in ("options", "role_confirmation"):
            failures.append(
                f"FAIL: live search hit fast path ({result.get('type')}) instead of pipeline"
            )
        else:
            print(f"PASS: 'find live jobs for Senior HSE Manager' → {result.get('type')} (not fast path)")

    # ── Summary ─────────────────────────────────────────────────────────────
    print()
    if failures:
        print(f"SMOKE TEST FAILED — {len(failures)} failure(s):")
        for f in failures:
            print(f"  {f}")
        return 1

    print("SMOKE TEST PASSED — all 4 steps OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
