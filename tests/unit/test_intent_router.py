from __future__ import annotations

import pytest

from src.rico.intent.router import IntentRouter
from src.rico.intent.types import IntentSource


@pytest.fixture
def router() -> IntentRouter:
    return IntentRouter()


def test_open_ended_routes_to_ai(router: IntentRouter) -> None:
    decision = router.route(
        message="how can you help me",
        user_id="u1",
        profile_context_present=True,
    )
    assert decision.handler_name == "ConversationalAIHandler"
    assert decision.should_use_ai is True
    assert decision.source is IntentSource.RULE
    assert decision.intent == "conversational"
    assert decision.reason.startswith("gate:")


def test_bare_role_falls_through_to_legacy(router: IntentRouter) -> None:
    decision = router.route(
        message="HSE Manager",
        user_id="u1",
        profile_context_present=True,
    )
    assert decision.handler_name == "LegacyClassifier"
    assert decision.should_use_ai is False
    assert decision.source is IntentSource.LEGACY


def test_explicit_role_search_falls_through_to_legacy(router: IntentRouter) -> None:
    decision = router.route(
        message="find HSE Manager jobs",
        user_id="u1",
        profile_context_present=True,
    )
    assert decision.handler_name == "LegacyClassifier"
    assert decision.source is IntentSource.LEGACY


def test_log_dict_redacts_raw_message(router: IntentRouter) -> None:
    decision = router.route(
        message="my private cv content 12345",
        user_id="u1",
        profile_context_present=False,
    )
    log_dict = decision.to_log_dict()
    assert "raw_message" not in log_dict
    assert "my private" not in str(log_dict)
    assert len(log_dict["message_hash"]) == 16
