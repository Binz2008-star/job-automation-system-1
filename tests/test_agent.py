"""
tests/test_agent.py
Adversarial test suite for the Agent Interaction Layer.

Coverage:
  - ToolRegistry: registration, lookup, unknown-tool handling
  - Tool execution: success paths, error paths, missing-field guards
  - IntentDetector: all intents + fallback
  - ResponseBuilder: shape, actions, error UI, fallback text
  - AgentChatEndpoint: auth, valid workflows, malformed payloads, invalid actions
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# ── Ensure project root is on path ────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Set required env vars before any import ───────────────────────────────────
os.environ.setdefault("ADMIN_EMAIL", "agent-test@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "agentpass123")
os.environ.setdefault("JWT_SECRET", "agentsecret" + "x" * 21)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Tool Registry
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolRegistry:
    def test_all_required_tools_registered(self):
        from src.agent.registry.tool_registry import is_registered

        required = [
            "search_jobs", "get_ranked_jobs", "apply_job", "skip_job",
            "save_job", "block_company", "get_pipeline_status",
            "trigger_pipeline", "get_application_stats",
        ]
        for name in required:
            assert is_registered(name), f"Tool {name!r} is not registered"

    def test_tool_lookup_returns_definition(self):
        from src.agent.registry.tool_registry import get
        tool = get("get_ranked_jobs")
        assert tool.name == "get_ranked_jobs"
        assert callable(tool.fn)
        assert isinstance(tool.description, str) and tool.description

    def test_unknown_tool_raises_key_error(self):
        from src.agent.registry.tool_registry import get
        with pytest.raises(KeyError, match="Unknown tool"):
            get("this_tool_does_not_exist")

    def test_all_tools_snapshot_is_non_empty(self):
        from src.agent.registry.tool_registry import all_tools
        tools = all_tools()
        assert len(tools) >= 9

    def test_is_registered_false_for_unknown(self):
        from src.agent.registry.tool_registry import is_registered
        assert not is_registered("not_a_real_tool")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Tool execution — success and error paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestJobTools:
    def test_get_ranked_jobs_returns_success_result(self):
        from src.agent.tools.job_tools import get_ranked_jobs
        with patch("src.services.jobs_service.list_jobs", return_value={"jobs": [], "total": 0, "page": 1, "limit": 10, "pages": 1}):
            result = get_ranked_jobs()
        assert result.success is True
        assert result.tool_name == "get_ranked_jobs"
        assert result.data is not None
        assert "jobs" in result.data

    def test_get_ranked_jobs_service_exception_returns_failure(self):
        from src.agent.tools.job_tools import get_ranked_jobs
        with patch("src.services.jobs_service.list_jobs", side_effect=RuntimeError("DB down")):
            result = get_ranked_jobs()
        assert result.success is False
        assert "DB down" in (result.error or "")

    def test_apply_job_missing_link_returns_failure(self):
        from src.agent.tools.job_tools import apply_job
        result = apply_job({"title": "HSE Manager", "company": "ACME"})
        assert result.success is False
        assert "link" in (result.error or "").lower()

    def test_apply_job_delegates_to_service(self):
        from src.agent.tools.job_tools import apply_job
        mock_result = {"status": "applied", "message": "Done"}
        with patch("src.services.apply_service.apply_to_job", return_value=mock_result):
            result = apply_job({"link": "https://example.com/job1", "title": "HSE"})
        assert result.success is True
        assert result.data == mock_result

    def test_skip_job_returns_normalised_dict(self):
        from src.agent.tools.job_tools import skip_job
        job = {"title": "HSE Mgr", "link": "https://naukrigulf.com/j1", "company": "Corp"}
        with patch("src.services.jobs_service.skip_job", return_value=True):
            result = skip_job(job)
        assert result.success is True
        assert result.tool_name == "skip_job"

    def test_save_job_calls_mark_applied(self):
        from src.agent.tools.job_tools import save_job as tool_save_job
        job = {"title": "Env Mgr", "link": "https://example.com/j2", "company": "Green Co"}
        with patch("src.applications.mark_applied", return_value=True) as mock_ma:
            result = tool_save_job(job)
        mock_ma.assert_called_once_with(job, "saved", "Saved via agent")
        assert result.success is True

    def test_apply_job_records_execution_time(self):
        from src.agent.tools.job_tools import apply_job
        with patch("src.services.apply_service.apply_to_job", return_value={"status": "applied", "message": ""}):
            result = apply_job({"link": "https://example.com/j3"})
        assert isinstance(result.execution_time_ms, int)
        assert result.execution_time_ms >= 0


class TestStatsTools:
    def test_get_stats_returns_success(self):
        from src.agent.tools.stats_tools import get_application_stats
        mock_stats = {"total_applied": 10, "interviews_scheduled": 2, "success_rate": 20.0}
        with patch("src.repositories.applications_repo.get_stats", return_value=mock_stats):
            result = get_application_stats()
        assert result.success is True
        assert result.data == mock_stats

    def test_get_stats_service_exception_returns_failure(self):
        from src.agent.tools.stats_tools import get_application_stats
        with patch("src.repositories.applications_repo.get_stats", side_effect=OSError("file locked")):
            result = get_application_stats()
        assert result.success is False
        assert "file locked" in (result.error or "")


class TestPipelineTools:
    def test_get_pipeline_status_returns_success(self):
        from src.agent.tools.pipeline_tools import get_pipeline_status
        with patch("src.services.pipeline_service.get_status", return_value={"status": "idle"}):
            result = get_pipeline_status()
        assert result.success is True
        assert result.data == {"status": "idle"}

    def test_trigger_pipeline_already_running_returns_failure(self):
        from src.agent.tools.pipeline_tools import trigger_pipeline
        with patch("src.services.pipeline_service.trigger", side_effect=RuntimeError("already running")):
            result = trigger_pipeline()
        assert result.success is False
        assert "already running" in (result.error or "")

    def test_trigger_pipeline_success(self):
        from src.agent.tools.pipeline_tools import trigger_pipeline
        with patch("src.services.pipeline_service.trigger", return_value=None):
            result = trigger_pipeline()
        assert result.success is True
        assert result.data == {"status": "triggered"}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Intent detector
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentDetector:
    def _detect(self, msg: str):
        from src.agent.orchestrator.intent_detector import detect
        return detect(msg)

    def test_show_jobs_intent(self):
        intent, tool = self._detect("Show me the best jobs today")
        assert intent == "get_ranked_jobs"
        assert tool == "get_ranked_jobs"

    def test_stats_intent(self):
        intent, tool = self._detect("What are my application stats?")
        assert intent == "get_application_stats"
        assert tool == "get_application_stats"

    def test_pipeline_status_intent(self):
        intent, tool = self._detect("What is the pipeline status?")
        assert intent == "get_pipeline_status"
        assert tool == "get_pipeline_status"

    def test_trigger_intent(self):
        intent, tool = self._detect("Run pipeline now")
        assert intent == "trigger_pipeline"
        assert tool == "trigger_pipeline"

    def test_unknown_falls_back_to_help(self):
        intent, tool = self._detect("How do I cook pasta?")
        assert intent == "help"
        assert tool is None

    def test_case_insensitive(self):
        intent, _ = self._detect("SHOW ME TOP JOBS")
        assert intent == "get_ranked_jobs"

    def test_partial_keyword_match(self):
        intent, _ = self._detect("Any new jobs in Dubai?")
        assert intent == "get_ranked_jobs"

    def test_stats_keyword_progress(self):
        intent, _ = self._detect("Show me my progress")
        assert intent == "get_application_stats"

    @pytest.mark.parametrize("msg,expected_intent", [
        ("top jobs please",         "get_ranked_jobs"),
        ("my interview stats",      "get_application_stats"),
        ("when did the pipeline run", "get_pipeline_status"),
        ("trigger the pipeline",    "trigger_pipeline"),
    ])
    def test_parametrized_intents(self, msg, expected_intent):
        intent, _ = self._detect(msg)
        assert intent == expected_intent


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Response builder
# ═══════════════════════════════════════════════════════════════════════════════

class TestResponseBuilder:
    def _make_result(self, tool: str, data=None, success=True, error=None):
        from src.schemas.agent import ToolExecutionResult
        return ToolExecutionResult(success=success, tool_name=tool, data=data, error=error)

    def test_job_list_response_has_job_list_ui_type(self):
        from src.agent.response_builder.response_builder import build_response
        from src.schemas.agent import AgentUIType
        jobs = [{"id": "1", "title": "HSE Mgr", "company": "ACME", "link": "https://ex.com/1", "score": 80}]
        result = self._make_result("get_ranked_jobs", {"jobs": jobs, "total": 1})
        resp = build_response(result)
        assert resp.ui is not None
        assert resp.ui.type == AgentUIType.JOB_LIST

    def test_each_job_has_apply_skip_save_actions(self):
        from src.agent.response_builder.response_builder import build_response
        jobs = [
            {"id": "1", "title": "HSE", "company": "A", "link": "https://ex.com/1", "score": 80},
            {"id": "2", "title": "QHSE", "company": "B", "link": "https://ex.com/2", "score": 70},
        ]
        result = self._make_result("get_ranked_jobs", {"jobs": jobs, "total": 2})
        resp = build_response(result)
        # 3 actions per job
        assert len(resp.actions) == 6
        action_types = {a.type for a in resp.actions}
        assert "apply" in action_types
        assert "skip" in action_types
        assert "save" in action_types

    def test_apply_action_carries_full_job_payload(self):
        from src.agent.response_builder.response_builder import build_response
        job = {"id": "99", "title": "HSE", "company": "ACME", "link": "https://ex.com/99", "score": 88}
        result = self._make_result("get_ranked_jobs", {"jobs": [job], "total": 1})
        resp = build_response(result)
        apply_actions = [a for a in resp.actions if a.type == "apply"]
        assert len(apply_actions) == 1
        assert apply_actions[0].job is not None
        assert apply_actions[0].job["link"] == "https://ex.com/99"

    def test_empty_job_list_returns_no_results_text(self):
        from src.agent.response_builder.response_builder import build_response
        from src.schemas.agent import AgentUIType
        result = self._make_result("get_ranked_jobs", {"jobs": [], "total": 0})
        resp = build_response(result)
        assert resp.ui.type == AgentUIType.TEXT
        assert "no" in resp.message.lower() or "filter" in resp.message.lower()

    def test_error_result_returns_error_ui(self):
        from src.agent.response_builder.response_builder import build_response
        from src.schemas.agent import AgentUIType
        result = self._make_result("apply_job", success=False, error="Connection timeout")
        resp = build_response(result)
        assert resp.success is False
        assert resp.ui.type == AgentUIType.ERROR
        assert "Connection timeout" in resp.message

    def test_stats_response_has_pipeline_action(self):
        from src.agent.response_builder.response_builder import build_response
        data = {"total_applied": 5, "interviews_scheduled": 1, "success_rate": 20.0, "rejections": 0, "pending": 4, "status_breakdown": {}}
        result = self._make_result("get_application_stats", data)
        resp = build_response(result)
        assert any(a.type == "trigger_pipeline" for a in resp.actions)

    def test_pipeline_running_has_no_trigger_action(self):
        from src.agent.response_builder.response_builder import build_response
        result = self._make_result("get_pipeline_status", {"status": "running", "started_at": "2026-05-09T10:00:00"})
        resp = build_response(result)
        assert not any(a.type == "trigger_pipeline" for a in resp.actions)

    def test_pipeline_idle_has_trigger_action(self):
        from src.agent.response_builder.response_builder import build_response
        result = self._make_result("get_pipeline_status", {"status": "idle"})
        resp = build_response(result)
        assert any(a.type == "trigger_pipeline" for a in resp.actions)

    def test_help_response_lists_commands(self):
        from src.agent.response_builder.response_builder import build_response
        from src.schemas.agent import AgentUIType
        result = self._make_result("help", {"intent": "help"})
        resp = build_response(result)
        assert resp.ui.type == AgentUIType.TEXT
        assert "commands" in resp.ui.data

    def test_apply_result_success_message(self):
        from src.agent.response_builder.response_builder import build_response
        from src.schemas.agent import AgentAction
        action = AgentAction(type="apply", label="Apply", job={"title": "HSE Manager", "link": "https://x.com/j"})
        result = self._make_result("apply_job", {"status": "applied", "message": "Submitted."})
        resp = build_response(result, original_action=action)
        assert "HSE Manager" in resp.message
        assert resp.success is True

    def test_action_ids_are_unique(self):
        from src.agent.response_builder.response_builder import build_response
        jobs = [{"id": str(i), "title": f"Job {i}", "company": "X", "link": f"https://ex.com/{i}", "score": 70 + i}
                for i in range(5)]
        result = self._make_result("get_ranked_jobs", {"jobs": jobs, "total": 5})
        resp = build_response(result)
        ids = [a.action_id for a in resp.actions]
        assert len(ids) == len(set(ids)), "Action IDs must be unique"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Agent chat endpoint (HTTP integration)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def client():
    """Authenticated test client with valid JWT cookie."""
    from fastapi.testclient import TestClient
    from src.api.app import app
    from src.api.auth import create_access_token

    token = create_access_token({"sub": "agent-test@example.com"})
    tc = TestClient(app, raise_server_exceptions=False)
    tc.cookies.set("access_token", token)
    return tc


class TestAgentChatEndpoint:
    def test_unauthenticated_returns_401(self):
        from fastapi.testclient import TestClient
        from src.api.app import app
        tc = TestClient(app, raise_server_exceptions=False)
        r = tc.post("/api/v1/agent/chat", json={"message": "hello"})
        assert r.status_code == 401

    def test_empty_message_returns_422(self, client):
        r = client.post("/api/v1/agent/chat", json={"message": ""})
        assert r.status_code == 422

    def test_missing_message_returns_422(self, client):
        r = client.post("/api/v1/agent/chat", json={})
        assert r.status_code == 422

    def test_message_too_long_returns_422(self, client):
        r = client.post("/api/v1/agent/chat", json={"message": "x" * 1001})
        assert r.status_code == 422

    def test_help_message_returns_200(self, client):
        r = client.post("/api/v1/agent/chat", json={"message": "hello there"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["message"]
        assert "tool_used" in body

    def test_show_jobs_message_returns_job_list_ui(self, client):
        mock_jobs = {"jobs": [{"id": "1", "title": "HSE Mgr", "company": "A", "link": "https://naukrigulf.com/j1", "score": 80}], "total": 1, "page": 1, "limit": 10, "pages": 1}
        with patch("src.services.jobs_service.list_jobs", return_value=mock_jobs):
            r = client.post("/api/v1/agent/chat", json={"message": "Show me today's best jobs"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["ui"]["type"] == "job_list"
        assert len(body["actions"]) >= 3  # at least apply+skip+save for 1 job

    def test_stats_message_returns_stats_ui(self, client):
        mock_stats = {"total_applied": 3, "interviews_scheduled": 1, "success_rate": 33.3, "rejections": 0, "pending": 2, "status_breakdown": {}}
        with patch("src.repositories.applications_repo.get_stats", return_value=mock_stats):
            r = client.post("/api/v1/agent/chat", json={"message": "Show me my application stats"})
        assert r.status_code == 200
        body = r.json()
        assert body["ui"]["type"] == "stats"

    def test_pipeline_status_message_returns_pipeline_ui(self, client):
        with patch("src.services.pipeline_service.get_status", return_value={"status": "idle"}):
            r = client.post("/api/v1/agent/chat", json={"message": "What is the pipeline status?"})
        assert r.status_code == 200
        body = r.json()
        assert body["ui"]["type"] == "pipeline_status"

    def test_apply_action_executes_apply_service(self, client):
        job = {"title": "HSE Manager", "company": "ACME", "link": "https://naukrigulf.com/j99", "score": 85}
        with patch("src.services.apply_service.apply_to_job", return_value={"status": "applied", "message": "Done"}):
            r = client.post("/api/v1/agent/chat", json={
                "message": "Apply to this job",
                "action": {"type": "apply", "label": "Apply", "job": job},
            })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "ACME" in body["message"] or "HSE Manager" in body["message"]

    def test_skip_action_marks_job_skipped(self, client):
        job = {"title": "QA Engineer", "company": "TechCo", "link": "https://indeed.com/jk=abc123", "score": 40}
        with patch("src.services.jobs_service.skip_job", return_value=True):
            r = client.post("/api/v1/agent/chat", json={
                "message": "Skip",
                "action": {"type": "skip", "label": "Skip", "job": job},
            })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True

    def test_invalid_action_type_returns_error_response(self, client):
        r = client.post("/api/v1/agent/chat", json={
            "message": "do something weird",
            "action": {"type": "hack_the_planet", "label": "Hack"},
        })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "hack_the_planet" in body["message"].lower() or "unknown" in body["message"].lower()

    def test_apply_action_missing_link_returns_error(self, client):
        job = {"title": "Intern", "company": "Corp"}  # no link
        r = client.post("/api/v1/agent/chat", json={
            "message": "Apply",
            "action": {"type": "apply", "label": "Apply", "job": job},
        })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False

    def test_malformed_json_returns_422(self, client):
        import json
        r = client.post(
            "/api/v1/agent/chat",
            content=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422

    def test_response_has_required_fields(self, client):
        r = client.post("/api/v1/agent/chat", json={"message": "help"})
        assert r.status_code == 200
        body = r.json()
        required = {"message", "ui", "actions", "tool_used", "execution_time_ms", "success"}
        assert required.issubset(body.keys()), f"Missing fields: {required - body.keys()}"

    def test_execution_time_is_non_negative_int(self, client):
        r = client.post("/api/v1/agent/chat", json={"message": "help"})
        body = r.json()
        assert isinstance(body["execution_time_ms"], int)
        assert body["execution_time_ms"] >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Schema validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentSchemas:
    def test_agent_action_default_action_id_is_hex(self):
        from src.schemas.agent import AgentAction
        a = AgentAction(type="apply", label="Apply")
        assert len(a.action_id) == 8
        assert a.action_id.isalnum()

    def test_agent_ui_type_values(self):
        from src.schemas.agent import AgentUIType
        assert AgentUIType.JOB_LIST == "job_list"
        assert AgentUIType.ERROR == "error"

    def test_agent_ui_response_defaults(self):
        from src.schemas.agent import AgentUIResponse
        r = AgentUIResponse(message="hello")
        assert r.actions == []
        assert r.ui is None
        assert r.success is True
        assert r.execution_time_ms == 0

    def test_tool_execution_result_defaults(self):
        from src.schemas.agent import ToolExecutionResult
        r = ToolExecutionResult(success=True, tool_name="test_tool")
        assert r.data is None
        assert r.error is None
        assert r.execution_time_ms == 0

    def test_agent_chat_request_rejects_empty_message(self):
        from pydantic import ValidationError
        from src.schemas.agent import AgentChatRequest
        with pytest.raises(ValidationError):
            AgentChatRequest(message="")

    def test_agent_chat_request_rejects_oversized_message(self):
        from pydantic import ValidationError
        from src.schemas.agent import AgentChatRequest
        with pytest.raises(ValidationError):
            AgentChatRequest(message="x" * 1001)

    def test_action_style_enum(self):
        from src.schemas.agent import ActionStyle, AgentAction
        a = AgentAction(type="apply", label="Apply", style=ActionStyle.PRIMARY)
        assert a.style == "primary"
