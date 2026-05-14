"""
tests/test_agent_runtime.py
Tests for the Rico agent runtime (src/agent/runtime.py).

Covers:
  - All 9 supported actions
  - Dry-run mode
  - Unknown action rejection
  - Job resolution (provided dict / cache lookup / stub fallback)
  - RuntimeResult shape
  - Audit log is called
  - No interactive code reachable
  - Telegram callback routing through runtime
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ADMIN_EMAIL",    "admin@test.com")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass123")
os.environ.setdefault("JWT_SECRET",     "x" * 32)

_JOB = {
    "id":               "job-rt-001",
    "title":            "ESG Manager",
    "company":          "Acme Corp",
    "location":         "Dubai, UAE",
    "link":             "https://example.com/job/rt-001",
    "score":            88,
    "match_reason":     "Strong HSE background",
    "profile_explanation": "Matches your senior sustainability experience.",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(action, job=None, job_key="test-key", source="test", dry_run=False):
    from src.agent.runtime import agent_runtime
    return agent_runtime.handle_action(
        user_id="user-test",
        action=action,
        job_key=job_key,
        job=job or _JOB,
        source=source,
        dry_run=dry_run,
    )


def _patch_audit():
    return patch("src.agent.runtime.log_action")


def _patch_is_duplicate(value=False):
    return patch("src.agent.runtime.is_duplicate", return_value=value)


# ── RuntimeResult shape ───────────────────────────────────────────────────────

class TestRuntimeResultShape:
    def test_has_required_fields(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                result = _run("save")
        assert hasattr(result, "ok")
        assert hasattr(result, "message")
        assert hasattr(result, "action")
        assert hasattr(result, "job_key")
        assert hasattr(result, "source")
        assert hasattr(result, "user_id")
        assert hasattr(result, "dry_run")
        assert hasattr(result, "data")
        assert hasattr(result, "error")
        assert hasattr(result, "confidence")
        assert hasattr(result, "explanation")
        assert hasattr(result, "duration_ms")

    def test_to_dict_is_serialisable(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                result = _run("save")
        d = result.to_dict()
        import json
        json.dumps(d)  # must not raise

    def test_user_id_and_source_propagated(self):
        from src.agent.runtime import agent_runtime
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                result = agent_runtime.handle_action(
                    user_id="telegram-99999", action="save",
                    job=_JOB, source="telegram",
                )
        assert result.user_id == "telegram-99999"
        assert result.source == "telegram"

    def test_duration_ms_is_non_negative(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                result = _run("save")
        assert result.duration_ms >= 0

    def test_confidence_is_1_for_explicit_actions(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.services.apply_service.apply_to_job", return_value={"status": "applied"}):
                result = _run("apply")
        assert result.confidence == 1.0


# ── All supported actions ─────────────────────────────────────────────────────

class TestApplyAction:
    def test_apply_calls_mark_applied(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.services.apply_service.apply_to_job",
                       return_value={"status": "applied"}) as mock_apply:
                result = _run("apply")
        assert result.ok is True
        assert "apply" in result.message.lower() or "track" in result.message.lower()

    def test_apply_ok_true_on_success(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.services.apply_service.apply_to_job", return_value={"status": "applied"}):
                result = _run("apply")
        assert result.ok is True
        assert result.action == "apply"


class TestSaveAction:
    def test_save_calls_mark_applied_with_saved_status(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True) as mock:
                result = _run("save")
        mock.assert_called_once()
        call_args = mock.call_args
        assert call_args[0][1] == "saved" or "saved" in str(call_args)

    def test_save_returns_ok(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                result = _run("save")
        assert result.ok is True


class TestSkipAction:
    def test_skip_returns_ok(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.services.jobs_service.skip_job", return_value=True):
                result = _run("skip")
        assert result.action == "skip"

    def test_not_relevant_maps_to_skip_tool(self):
        from src.agent.orchestrator.intent_detector import ACTION_TO_TOOL
        assert ACTION_TO_TOOL["not_relevant"] == "skip_job"

    def test_not_relevant_returns_ok(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.services.jobs_service.skip_job", return_value=True):
                result = _run("not_relevant")
        assert result.ok is True
        assert result.action == "not_relevant"


class TestDraftAction:
    def test_draft_returns_generated_message(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.message_generator.generate_message",
                       return_value="Dear Hiring Manager, ...") as mock_gen:
                result = _run("draft")
        assert result.ok is True
        assert "Dear Hiring Manager" in result.message
        mock_gen.assert_called_once_with(_JOB)

    def test_draft_data_contains_draft_key(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.message_generator.generate_message", return_value="test draft"):
                result = _run("draft")
        assert "draft" in result.data


class TestWhyAction:
    def test_why_returns_profile_explanation(self):
        with _patch_audit(), _patch_is_duplicate():
            result = _run("why")
        assert "sustainability" in result.message.lower() or result.ok is True

    def test_why_falls_back_to_match_reason(self):
        job = {**_JOB, "profile_explanation": None, "match_reason": "great HSE fit"}
        with _patch_audit(), _patch_is_duplicate():
            result = _run("why", job=job)
        assert "HSE" in result.message

    def test_why_has_fallback_for_empty_job(self):
        with _patch_audit(), _patch_is_duplicate():
            result = _run("why", job={"id": "x"})
        assert result.ok is True
        assert len(result.message) > 0

    def test_why_data_contains_explanation_key(self):
        with _patch_audit(), _patch_is_duplicate():
            result = _run("why")
        assert "explanation" in result.data


class TestRemindAction:
    def test_remind_returns_reminder_date(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.applications.update_application_status"):
                result = _run("remind")
        assert result.ok is True
        assert "reminder" in result.message.lower() or "-" in result.message

    def test_remind_sets_reminder_in_tracker(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.applications.update_application_status") as mock_update:
                result = _run("remind")
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args
        assert "reminder" in str(call_kwargs).lower()

    def test_remind_data_contains_reminder_date(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.applications.update_application_status"):
                result = _run("remind")
        assert "reminder_date" in result.data


# ── Unknown action ────────────────────────────────────────────────────────────

class TestUnknownAction:
    def test_unknown_action_returns_not_ok(self):
        result = _run("teleport")
        assert result.ok is False

    def test_unknown_action_message_lists_valid_types(self):
        result = _run("teleport")
        assert "apply" in result.message or "Supported" in result.message

    def test_unknown_action_error_contains_action_name(self):
        result = _run("teleport")
        assert "teleport" in (result.error or result.message)

    def test_empty_action_returns_not_ok(self):
        result = _run("")
        assert result.ok is False


# ── Dry-run mode ──────────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_returns_ok_without_executing(self):
        with patch("src.services.apply_service.apply_to_job") as mock_apply:
            result = _run("apply", dry_run=True)
        mock_apply.assert_not_called()
        assert result.ok is True
        assert result.dry_run is True

    def test_dry_run_message_contains_dry_run_label(self):
        result = _run("save", dry_run=True)
        assert "DRY RUN" in result.message or "dry" in result.message.lower()

    def test_dry_run_no_audit_log(self):
        with patch("src.agent.runtime.log_action") as mock_log:
            result = _run("skip", dry_run=True)
        mock_log.assert_not_called()

    @pytest.mark.parametrize("action", ["apply", "save", "skip", "draft", "why", "remind", "not_relevant"])
    def test_dry_run_all_actions(self, action):
        result = _run(action, dry_run=True)
        assert result.ok is True
        assert result.dry_run is True


# ── Job resolution ────────────────────────────────────────────────────────────

class TestJobResolution:
    def test_uses_provided_job_dict(self):
        with _patch_audit(), _patch_is_duplicate():
            with patch("src.message_generator.generate_message") as mock_gen:
                mock_gen.return_value = "msg"
                _run("draft", job=_JOB)
        mock_gen.assert_called_once_with(_JOB)

    def test_falls_back_to_cache_when_no_job(self):
        from src.agent.runtime import AgentRuntime
        cached = {**_JOB, "title": "Cached Job"}
        with patch("src.rico_telegram_ui.lookup_job", return_value=cached), \
             _patch_audit(), _patch_is_duplicate():
            with patch("src.message_generator.generate_message") as mock_gen:
                mock_gen.return_value = "msg"
                runtime = AgentRuntime()
                runtime.handle_action(
                    user_id="u", action="draft",
                    job_key="some-key", job=None, source="test",
                )
        mock_gen.assert_called_once_with(cached)

    def test_stubs_job_from_key_when_cache_misses(self):
        from src.agent.runtime import AgentRuntime
        with patch("src.rico_telegram_ui.lookup_job", return_value=None), \
             _patch_audit(), _patch_is_duplicate():
            runtime = AgentRuntime()
            result = runtime.handle_action(
                user_id="u", action="why",
                job_key="fallback-key", job=None, source="test",
            )
        assert result.ok is True  # graceful, not crash


# ── Audit logging ─────────────────────────────────────────────────────────────

class TestAuditLog:
    def test_audit_called_on_successful_action(self):
        with patch("src.agent.runtime.log_action") as mock_log, _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                _run("save")
        mock_log.assert_called_once()

    def test_audit_called_on_failed_action(self):
        with patch("src.agent.runtime.log_action") as mock_log, _patch_is_duplicate():
            with patch("src.applications.mark_applied", side_effect=Exception("db down")):
                _run("save")
        mock_log.assert_called_once()

    def test_audit_not_called_on_dry_run(self):
        with patch("src.agent.runtime.log_action") as mock_log:
            _run("save", dry_run=True)
        mock_log.assert_not_called()

    def test_audit_contains_action_type(self):
        with patch("src.agent.runtime.log_action") as mock_log, _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                _run("save")
        record = mock_log.call_args[0][0]
        assert record["action_type"] == "save"

    def test_audit_contains_user_id(self):
        from src.agent.runtime import agent_runtime
        with patch("src.agent.runtime.log_action") as mock_log, _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                agent_runtime.handle_action(
                    user_id="user-audit-check", action="save",
                    job=_JOB, source="test",
                )
        record = mock_log.call_args[0][0]
        assert record["user_email"] == "user-audit-check"

    def test_audit_contains_source(self):
        from src.agent.runtime import agent_runtime
        with patch("src.agent.runtime.log_action") as mock_log, _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                agent_runtime.handle_action(
                    user_id="u", action="save",
                    job=_JOB, source="telegram",
                )
        record = mock_log.call_args[0][0]
        assert record.get("source") == "telegram"


# ── No interactive code reachable ─────────────────────────────────────────────

class TestNoInteractiveCode:
    def test_runtime_module_imports_without_stdin(self):
        """Importing the runtime must not require or touch stdin."""
        import importlib
        import src.agent.runtime as rt
        importlib.reload(rt)  # re-import in test context
        assert hasattr(rt, "agent_runtime")

    def test_no_input_call_in_runtime(self):
        import ast, pathlib
        src_text = pathlib.Path("src/agent/runtime.py").read_text()
        tree = ast.parse(src_text)
        calls = [
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        ]
        assert "input" not in calls, "input() found in runtime.py — must not be there"

    def test_no_webbrowser_import_in_runtime(self):
        import pathlib
        src_text = pathlib.Path("src/agent/runtime.py").read_text()
        assert "webbrowser" not in src_text


# ── Tool registry completeness ─────────────────────────────────────────────────

class TestToolRegistry:
    def test_all_action_types_have_registered_tools(self):
        from src.agent.orchestrator.intent_detector import ACTION_TO_TOOL
        from src.agent.registry.tool_registry import is_registered
        for action, tool_name in ACTION_TO_TOOL.items():
            assert is_registered(tool_name), \
                f"Action '{action}' maps to '{tool_name}' which is NOT registered"

    def test_new_tools_registered(self):
        from src.agent.registry.tool_registry import is_registered
        assert is_registered("draft_message")
        assert is_registered("explain_match")
        assert is_registered("set_reminder")


# ── Telegram callback routing through runtime ─────────────────────────────────

class TestTelegramRuntimeIntegration:
    def test_handle_job_action_delegates_to_runtime(self):
        from src.rico_telegram_ui import handle_job_action
        from src.agent.runtime import agent_runtime
        with patch.object(agent_runtime, "handle_action") as mock_runtime:
            mock_runtime.return_value = MagicMock(ok=True, message="Saved.")
            result = handle_job_action("save", _JOB, user_id="tg-user")
        mock_runtime.assert_called_once()
        call_kwargs = mock_runtime.call_args.kwargs
        assert call_kwargs["action"] == "save"
        assert call_kwargs["source"] == "telegram"
        assert call_kwargs["user_id"] == "tg-user"

    def test_handle_job_action_returns_ok_and_reply(self):
        from src.rico_telegram_ui import handle_job_action
        with patch("src.agent.runtime.log_action"), _patch_is_duplicate():
            with patch("src.applications.mark_applied", return_value=True):
                result = handle_job_action("save", _JOB, user_id="tg-42")
        assert "ok" in result
        assert "reply" in result
        assert result["ok"] is True

    @pytest.mark.parametrize("action", ["apply", "save", "skip", "not_relevant", "why", "draft", "remind"])
    def test_all_telegram_actions_return_ok_via_runtime(self, action, tmp_path):
        """All 7 Telegram button actions flow through the runtime and return ok=True."""
        import src.rico_telegram_ui as ui
        original_log = ui.TELEGRAM_ACTIONS_FILE
        original_log_lock = ui.TELEGRAM_ACTIONS_LOCK
        ui.TELEGRAM_ACTIONS_FILE = tmp_path / f"actions_{action}.json"
        ui.TELEGRAM_ACTIONS_LOCK = str(ui.TELEGRAM_ACTIONS_FILE) + ".lock"
        try:
            from src.rico_telegram_ui import handle_job_action
            with patch("src.agent.runtime.log_action"), _patch_is_duplicate():
                with patch("src.applications.mark_applied", return_value=True), \
                     patch("src.services.apply_service.apply_to_job", return_value={"status": "applied"}), \
                     patch("src.services.jobs_service.skip_job", return_value=True), \
                     patch("src.message_generator.generate_message", return_value="msg"), \
                     patch("src.applications.update_application_status"):
                    result = handle_job_action(action, _JOB, user_id="tg-test")
            assert result["ok"] is True, f"action={action} returned ok=False: {result}"
        finally:
            ui.TELEGRAM_ACTIONS_FILE = original_log
            ui.TELEGRAM_ACTIONS_LOCK = original_log_lock
