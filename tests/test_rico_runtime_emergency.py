from __future__ import annotations

import os
from unittest.mock import patch


def test_jotform_active_form_ids_accepts_aliases(monkeypatch):
    monkeypatch.setenv("JOTFORM_FORM_ID", "261277622782059")
    monkeypatch.setenv("JOTFORM_RICO_FORM_ID", "261277705943060")
    from src.rico_jotform_webhook import _active_form_ids

    ids = _active_form_ids()
    assert "261277622782059" in ids
    assert "261277705943060" in ids


def test_telegram_format_dedupes_jobs(monkeypatch):
    from src.telegram_bot import format_telegram_jobs

    job = {
        "title": "HSE OFFICER",
        "company": "NMDC Group",
        "location": "Abu Dhabi, AZ, AE",
        "link": "https://example.com/apply",
    }
    message = format_telegram_jobs([(job, 100), (dict(job), 100), (dict(job), 100)])

    assert message.count("HSE OFFICER") == 1
    assert "Found 1" in message


def test_telegram_public_alerts_kill_switch(monkeypatch):
    from src.telegram_bot import send_telegram_message

    monkeypatch.setenv("RICO_TELEGRAM_PUBLIC_ALERTS", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

    with patch("requests.post") as post:
        assert send_telegram_message("hello") is False
        post.assert_not_called()
