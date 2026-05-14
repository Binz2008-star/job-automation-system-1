"""
tests/unit/conftest.py
======================
Auto-mocks all external dependencies for RicoChatAPI so tests can
construct RicoChatAPI() without DB connections, API keys, or network.

This file is picked up automatically by pytest for all tests in tests/unit/.
"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def mock_rico_dependencies(monkeypatch):
    """
    Patch all external I/O that RicoChatAPI.__init__ and its methods touch.
    Applied automatically to every test in tests/unit/.
    """
    mock_memory  = MagicMock()
    mock_agent   = MagicMock()
    mock_system  = MagicMock()
    mock_openai  = MagicMock()

    mock_openai.model               = "gpt-4o"
    mock_openai.openai_available    = True
    mock_openai.deepseek_available  = False
    mock_openai.hf_available        = False
    mock_openai.provider_available  = True
    mock_openai.provider_state      = None
    mock_openai.respond             = MagicMock(return_value={
        "type": "openai_response", "message": "mock AI reply"
    })

    mock_system.run_for_profile = MagicMock(return_value={"matches": []})

    # _route return value must look like a RouteResult:
    # tool_name, entities, tool_args, confirmation_prompt, source
    mock_route_result = MagicMock()
    mock_route_result.tool_name          = None
    mock_route_result.entities           = {}
    mock_route_result.tool_args          = {}
    mock_route_result.confirmation_prompt = None
    mock_route_result.source             = "keyword"

    with (
        patch("src.rico_memory.RicoMemoryStore",       return_value=mock_memory),
        patch("src.rico_agent.RicoAgent",              return_value=mock_agent),
        patch("src.rico_repo_adapter.RicoSystem",      return_value=mock_system),
        patch("src.rico_openai_agent.RicoOpenAIAgent", return_value=mock_openai),
        # DB / onboarding repos
        patch("src.rico_chat_api.is_onboarding_complete", return_value=True),
        patch("src.rico_chat_api.mark_onboarding_complete"),
        patch("src.rico_chat_api.set_onboarding_status"),
        patch("src.rico_chat_api.upsert_profile",
              side_effect=lambda user_id, updates: updates),
        # Intent router — must not make real calls
        patch("src.rico_chat_api._route", return_value=mock_route_result),
        # HF client
        patch("src.rico_chat_api.hf_ok", return_value=False),
    ):
        yield {
            "memory":  mock_memory,
            "agent":   mock_agent,
            "system":  mock_system,
            "openai":  mock_openai,
            "route":   mock_route_result,
        }
