"""
tests/test_telegram_inline.py
Tests for Telegram inline keyboards, callback dispatch, job cache, and ack.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass123")
os.environ.setdefault("JWT_SECRET", "x" * 32)

_SAMPLE_JOB = {
    "id": "job-001",
    "title": "ESG Manager",
    "company": "Acme Corp",
    "location": "Dubai, UAE",
    "link": "https://example.com/job/001",
    "score": 87,
    "match_reason": "Strong HSE background",
}


# ── Keyboard builder ──────────────────────────────────────────────────────────

class TestBuildJobKeyboard:
    def test_returns_inline_keyboard(self):
        from src.telegram_actions import build_job_keyboard
        kb = build_job_keyboard(_SAMPLE_JOB)
        assert "inline_keyboard" in kb
        assert isinstance(kb["inline_keyboard"], list)

    def test_open_apply_row_has_url(self):
        from src.telegram_actions import build_job_keyboard
        kb = build_job_keyboard(_SAMPLE_JOB)
        first_row = kb["inline_keyboard"][0]
        assert any("url" in btn for btn in first_row)

    def test_action_buttons_use_rico_namespace(self):
        from src.telegram_actions import build_job_keyboard
        kb = build_job_keyboard(_SAMPLE_JOB)
        all_callbacks = [
            btn["callback_data"]
            for row in kb["inline_keyboard"]
            for btn in row
            if "callback_data" in btn
        ]
        assert all(cb.startswith("rico:") for cb in all_callbacks), \
            f"Non-rico callbacks found: {all_callbacks}"

    def test_action_buttons_include_all_required_actions(self):
        from src.telegram_actions import build_job_keyboard
        kb = build_job_keyboard(_SAMPLE_JOB)
        actions = {
            btn["callback_data"].split(":")[1]
            for row in kb["inline_keyboard"]
            for btn in row
            if "callback_data" in btn
        }
        assert "apply" in actions
        assert "save" in actions
        assert "skip" in actions
        assert "why" in actions
        assert "draft" in actions
        assert "not_relevant" in actions

    def test_no_url_button_when_link_missing(self):
        from src.telegram_actions import build_job_keyboard
        job = {**_SAMPLE_JOB, "link": ""}
        kb = build_job_keyboard(job)
        all_buttons = [btn for row in kb["inline_keyboard"] for btn in row]
        assert not any("url" in btn for btn in all_buttons)

    def test_callback_data_contains_job_key(self):
        from src.telegram_actions import build_job_keyboard
        from src.applications import get_job_id
        kb = build_job_keyboard(_SAMPLE_JOB)
        expected_key = get_job_id(_SAMPLE_JOB)
        all_callbacks = [
            btn["callback_data"]
            for row in kb["inline_keyboard"]
            for btn in row
            if "callback_data" in btn
        ]
        assert all(cb.endswith(expected_key) for cb in all_callbacks)


# ── Recommendation message ────────────────────────────────────────────────────

class TestRecommendationMessage:
    def test_contains_title_and_company(self):
        from src.rico_telegram_ui import recommendation_message
        msg = recommendation_message(_SAMPLE_JOB)
        assert "ESG Manager" in msg
        assert "Acme Corp" in msg

    def test_contains_score(self):
        from src.rico_telegram_ui import recommendation_message
        msg = recommendation_message(_SAMPLE_JOB)
        assert "87" in msg

    def test_fallback_for_missing_fields(self):
        from src.rico_telegram_ui import recommendation_message
        msg = recommendation_message({})
        assert "Role" in msg or "Company" in msg  # fallback strings present


# ── Parse callback ────────────────────────────────────────────────────────────

class TestParseCallback:
    def test_valid_rico_callback(self):
        from src.rico_telegram_ui import parse_callback
        result = parse_callback("rico:apply:abc123")
        assert result["namespace"] == "rico"
        assert result["action"] == "apply"
        assert result["job_key"] == "abc123"

    def test_invalid_format_returns_unknown(self):
        from src.rico_telegram_ui import parse_callback
        result = parse_callback("applied|job-001")
        assert result["namespace"] == "unknown"

    def test_empty_string(self):
        from src.rico_telegram_ui import parse_callback
        result = parse_callback("")
        assert result["action"] == "unknown"

    def test_job_key_with_colons_preserved(self):
        from src.rico_telegram_ui import parse_callback
        result = parse_callback("rico:save:key:with:colons")
        assert result["job_key"] == "key:with:colons"


# ── Job cache ─────────────────────────────────────────────────────────────────

class TestJobCache:
    def test_cache_and_lookup(self, tmp_path):
        from src.applications import get_job_id
        import src.rico_telegram_ui as ui

        # Redirect cache to tmp dir
        original = ui.TELEGRAM_JOB_CACHE_FILE
        original_lock = ui.TELEGRAM_JOB_CACHE_LOCK
        ui.TELEGRAM_JOB_CACHE_FILE = tmp_path / "cache.json"
        ui.TELEGRAM_JOB_CACHE_LOCK = str(ui.TELEGRAM_JOB_CACHE_FILE) + ".lock"
        try:
            ui.cache_job(_SAMPLE_JOB)
            result = ui.lookup_job(get_job_id(_SAMPLE_JOB))
            assert result is not None
            assert result["title"] == "ESG Manager"
        finally:
            ui.TELEGRAM_JOB_CACHE_FILE = original
            ui.TELEGRAM_JOB_CACHE_LOCK = original_lock

    def test_lookup_missing_key_returns_none(self, tmp_path):
        import src.rico_telegram_ui as ui
        original = ui.TELEGRAM_JOB_CACHE_FILE
        original_lock = ui.TELEGRAM_JOB_CACHE_LOCK
        ui.TELEGRAM_JOB_CACHE_FILE = tmp_path / "cache.json"
        ui.TELEGRAM_JOB_CACHE_LOCK = str(ui.TELEGRAM_JOB_CACHE_FILE) + ".lock"
        try:
            result = ui.lookup_job("nonexistent-key")
            assert result is None
        finally:
            ui.TELEGRAM_JOB_CACHE_FILE = original
            ui.TELEGRAM_JOB_CACHE_LOCK = original_lock

    def test_cache_handles_corrupt_file(self, tmp_path):
        import src.rico_telegram_ui as ui
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("NOT JSON {{{{", encoding="utf-8")
        original = ui.TELEGRAM_JOB_CACHE_FILE
        original_lock = ui.TELEGRAM_JOB_CACHE_LOCK
        ui.TELEGRAM_JOB_CACHE_FILE = cache_file
        ui.TELEGRAM_JOB_CACHE_LOCK = str(cache_file) + ".lock"
        try:
            result = ui.lookup_job("any-key")
            assert result is None
        finally:
            ui.TELEGRAM_JOB_CACHE_FILE = original
            ui.TELEGRAM_JOB_CACHE_LOCK = original_lock


# ── handle_callback_only ──────────────────────────────────────────────────────

def _make_callback_update(action: str, job_key: str, callback_id: str = "cb-001") -> Dict[str, Any]:
    return {
        "callback_query": {
            "id": callback_id,
            "from": {"id": 99999},
            "data": f"rico:{action}:{job_key}",
        }
    }


class TestHandleCallbackOnly:
    def test_valid_apply_callback_returns_ok(self, tmp_path):
        import src.rico_telegram_ui as ui
        from src.applications import get_job_id
        from src.agent.runtime import agent_runtime
        original_cache = ui.TELEGRAM_JOB_CACHE_FILE
        original_cache_lock = ui.TELEGRAM_JOB_CACHE_LOCK
        original_log = ui.TELEGRAM_ACTIONS_FILE
        original_log_lock = ui.TELEGRAM_ACTIONS_LOCK
        ui.TELEGRAM_JOB_CACHE_FILE = tmp_path / "cache.json"
        ui.TELEGRAM_JOB_CACHE_LOCK = str(ui.TELEGRAM_JOB_CACHE_FILE) + ".lock"
        ui.TELEGRAM_ACTIONS_FILE = tmp_path / "actions.json"
        ui.TELEGRAM_ACTIONS_LOCK = str(ui.TELEGRAM_ACTIONS_FILE) + ".lock"
        try:
            ui.cache_job(_SAMPLE_JOB)
            job_key = get_job_id(_SAMPLE_JOB)
            update = _make_callback_update("apply", job_key)
            with patch.object(agent_runtime, "handle_action",
                              return_value=MagicMock(ok=True, message="Apply noted.")) as mock_runtime:
                result = ui.handle_callback_only(update)
            assert result["ok"] is True
            assert result["callback_id"] == "cb-001"
            assert result["action"] == "apply"
            mock_runtime.assert_called_once()
            assert mock_runtime.call_args.kwargs["action"] == "apply"
        finally:
            ui.TELEGRAM_JOB_CACHE_FILE = original_cache
            ui.TELEGRAM_JOB_CACHE_LOCK = original_cache_lock
            ui.TELEGRAM_ACTIONS_FILE = original_log
            ui.TELEGRAM_ACTIONS_LOCK = original_log_lock

    def test_unsupported_namespace_returns_not_ok(self):
        from src.rico_telegram_ui import handle_callback_only
        update = {"callback_query": {"id": "cb-x", "from": {"id": 1}, "data": "other:action:key"}}
        result = handle_callback_only(update)
        assert result["ok"] is False

    def test_empty_update_returns_not_ok(self):
        from src.rico_telegram_ui import handle_callback_only
        result = handle_callback_only({})
        assert result["ok"] is False

    def test_callback_id_always_in_result(self):
        from src.rico_telegram_ui import handle_callback_only
        update = _make_callback_update("skip", "somekey", callback_id="cb-999")
        with patch("src.rico_telegram_ui.record_callback_action", return_value=True):
            result = handle_callback_only(update)
        assert result.get("callback_id") == "cb-999"

    @pytest.mark.parametrize("action", ["apply", "save", "skip", "why", "draft", "remind", "not_relevant"])
    def test_all_supported_actions_return_ok(self, action, tmp_path):
        import src.rico_telegram_ui as ui
        from src.agent.runtime import agent_runtime
        original_log = ui.TELEGRAM_ACTIONS_FILE
        original_log_lock = ui.TELEGRAM_ACTIONS_LOCK
        ui.TELEGRAM_ACTIONS_FILE = tmp_path / f"actions_{action}.json"
        ui.TELEGRAM_ACTIONS_LOCK = str(ui.TELEGRAM_ACTIONS_FILE) + ".lock"
        try:
            update = _make_callback_update(action, "test-key-001")
            with patch.object(agent_runtime, "handle_action",
                              return_value=MagicMock(ok=True, message="Action done.")):
                result = ui.handle_callback_only(update)
            assert result["ok"] is True, f"action={action} returned ok=False"
        finally:
            ui.TELEGRAM_ACTIONS_FILE = original_log
            ui.TELEGRAM_ACTIONS_LOCK = original_log_lock


# ── answerCallbackQuery ───────────────────────────────────────────────────────

class TestAnswerCallbackQuery:
    def test_calls_telegram_api(self):
        from src.telegram_actions import answer_callback_query
        mock_resp = MagicMock()
        mock_resp.ok = True
        with patch("src.telegram_actions.requests.post", return_value=mock_resp) as mock_post, \
             patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake-token"}):
            result = answer_callback_query("cb-123", text="Saved!")
        assert result is True
        call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert call_json["callback_query_id"] == "cb-123"
        assert call_json["text"] == "Saved!"

    def test_returns_false_without_token(self):
        from src.telegram_actions import answer_callback_query
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": ""}):
            result = answer_callback_query("cb-123")
        assert result is False

    def test_returns_false_with_empty_callback_id(self):
        from src.telegram_actions import answer_callback_query
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake-token"}):
            result = answer_callback_query("")
        assert result is False

    def test_long_text_truncated_to_200(self):
        from src.telegram_actions import answer_callback_query
        mock_resp = MagicMock()
        mock_resp.ok = True
        with patch("src.telegram_actions.requests.post", return_value=mock_resp) as mock_post, \
             patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake-token"}):
            answer_callback_query("cb-x", text="A" * 500)
        call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert len(call_json["text"]) <= 200

    def test_network_failure_returns_false(self):
        from src.telegram_actions import answer_callback_query
        with patch("src.telegram_actions.requests.post", side_effect=Exception("network down")), \
             patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake-token"}):
            result = answer_callback_query("cb-xyz")
        assert result is False


# ── Webhook end-to-end ────────────────────────────────────────────────────────

class TestWebhookCallbackFlow:
    def test_process_telegram_update_handles_callback(self):
        from src.rico_telegram_webhook import process_telegram_update
        from src.applications import get_job_id

        update = _make_callback_update("save", get_job_id(_SAMPLE_JOB), "cb-e2e")

        from src.agent.runtime import agent_runtime
        with patch.object(agent_runtime, "handle_action",
                          return_value=MagicMock(ok=True, message="Saved.")), \
             patch("src.rico_telegram_webhook.answer_callback_query", return_value=True) as mock_ack:
            result = process_telegram_update(update)

        assert result["ok"] is True
        mock_ack.assert_called_once()
        call_args = mock_ack.call_args
        assert call_args[0][0] == "cb-e2e"  # callback_id passed through

    def test_process_telegram_update_routes_text_messages(self):
        from src.rico_telegram_webhook import process_telegram_update
        update = {"message": {"chat": {"id": 12345}, "from": {"id": 12345}, "text": "hi"}}
        with patch("src.rico_telegram_webhook.chat_api") as mock_api:
            mock_api.process_message.return_value = {"message": "Hello!"}
            result = process_telegram_update(update)
        assert result["chat_id"] == "12345"
        assert "reply" in result


# ── send_job_card_with_buttons ────────────────────────────────────────────────

class TestSendJobCardWithButtons:
    def test_sends_message_with_reply_markup(self):
        from src.telegram_bot import send_job_card_with_buttons
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.raise_for_status = MagicMock()

        with patch("src.telegram_bot.requests.post", return_value=mock_resp) as mock_post, \
             patch("src.rico_telegram_ui.cache_job"), \
             patch.dict(os.environ, {
                 "TELEGRAM_BOT_TOKEN": "fake-token",
                 "TELEGRAM_CHAT_ID": "chat-123",
             }):
            result = send_job_card_with_buttons(_SAMPLE_JOB)

        assert result is True
        call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert "reply_markup" in call_json
        assert call_json["parse_mode"] == "HTML"

    def test_caches_job_before_sending(self):
        from src.telegram_bot import send_job_card_with_buttons
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.raise_for_status = MagicMock()

        with patch("src.telegram_bot.requests.post", return_value=mock_resp), \
             patch("src.rico_telegram_ui.cache_job") as mock_cache, \
             patch.dict(os.environ, {
                 "TELEGRAM_BOT_TOKEN": "fake-token",
                 "TELEGRAM_CHAT_ID": "chat-123",
             }):
            send_job_card_with_buttons(_SAMPLE_JOB)

        mock_cache.assert_called_once_with(_SAMPLE_JOB)

    def test_returns_false_when_no_token(self):
        from src.telegram_bot import send_job_card_with_buttons
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
            result = send_job_card_with_buttons(_SAMPLE_JOB)
        assert result is False

    def test_returns_false_on_network_error(self):
        from src.telegram_bot import send_job_card_with_buttons
        with patch("src.telegram_bot.requests.post", side_effect=Exception("timeout")), \
             patch("src.rico_telegram_ui.cache_job"), \
             patch.dict(os.environ, {
                 "TELEGRAM_BOT_TOKEN": "fake-token",
                 "TELEGRAM_CHAT_ID": "chat-123",
             }):
            result = send_job_card_with_buttons(_SAMPLE_JOB)
        assert result is False
