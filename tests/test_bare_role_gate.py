import pytest

from src.rico_chat_api import RicoChatAPI


@pytest.mark.parametrize("msg", [
    "Software Engineer", "Senior Backend Developer", "Data Scientist",
    "UX/UI Designer", "C++ Developer", "DevOps Lead", "QA Engineer",
    "Doctor", "Registered Nurse", "Cardiologist", "Surgeon",
    "Médico", "Physician Assistant",
    "Accountant", "Chief Financial Officer", "Investment Analyst",
    "Tax Consultant", "Auditor",
    "Chef", "Pastry Chef", "Chef de Cuisine", "Electrician",
    "Photographer", "Graphic Designer", "Pilot", "Architect",
    "HSE Manager", "QHSE Officer", "Environmental Engineer",
    "CEO", "CTO", "CFO",
    "Senior Vice President of Global Marketing",
])
def test_accepts_real_role_titles(msg: str) -> None:
    assert RicoChatAPI._looks_like_bare_target_role(msg) is True


@pytest.mark.parametrize("msg", [
    "what is my status", "What is my status?",
    "how are you", "why do I get no matches",
    "where are the jobs", "when will you reply",
    "which one is best", "is there anything new",
    "qué jobs hay?", "状态怎么样？",
    "tell me jobs", "show me openings", "find me a role",
    "give me matches", "list my applications", "help me please",
    "explain this", "describe the position",
    "hi", "hello there", "hey", "thanks", "ok cool", "yes please",
    "no thanks", "great",
    "my status", "I want jobs", "I'm looking", "we need help",
    "the manager position", "any new jobs", "some openings",
    "manager 5 years", "engineer level 2",
    "a really specific senior staff principal software engineer position",
    "Hello. Find jobs.",
    "", "   ",
])
def test_rejects_non_role_messages(msg: str) -> None:
    assert RicoChatAPI._looks_like_bare_target_role(msg) is False
