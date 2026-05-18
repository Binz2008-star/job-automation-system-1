"""Phase 1 gate-level tests for open-ended question routing."""
from __future__ import annotations

import pytest

from src.rico.intent.gates import is_open_ended_question


@pytest.mark.parametrize("msg", [
    "how can you help me",
    "what can you do",
    "what is my name",
    "can you improve my CV",
    "tell me what you know about me",
    "why is this job a match",
    "anything?",
    "qué hay?",
    "结果如何？",
    "how do I apply",
    "what is the salary",
    "why no matches",
    "when will I hear back",
    "where are the jobs",
    "who is hiring",
    "can I get more",
    "could you check",
    "should I apply",
    "would you save this",
    "explain the match score",
    "do you have new jobs",
    "tell me about this role",
    "show me more",
    "",
    "   ",
])
def test_gate_rejects_open_ended(msg: str) -> None:
    is_open, reason = is_open_ended_question(msg)
    assert is_open is True, (msg, reason)
    assert reason != "ok"


@pytest.mark.parametrize("msg", [
    "HSE Manager",
    "Safety Officer",
    "Operations Manager",
    "ESG Specialist",
    "Software Engineer",
    "Chef",
    "Cardiologist",
    "find HSE Manager jobs",
    "show me jobs",
    "keep all",
    "both please",
    "asdf qwer zxcv",
])
def test_gate_lets_through_non_questions(msg: str) -> None:
    is_open, reason = is_open_ended_question(msg)
    assert is_open is False, (msg, reason)
    assert reason == "ok"


def test_show_me_routes_to_ai_by_phrase_opener() -> None:
    is_open, reason = is_open_ended_question("show me more details")
    assert is_open is True
    assert reason.startswith("phrase:")
