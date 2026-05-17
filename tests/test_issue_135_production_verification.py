"""Integration test for issue #135: Verify DeepSeek, HF fallback, and Jotform onboarding in production.

This test validates:
1. /api/v1/rico/health/ai-provider endpoint returns correct provider state
2. HF fallback readiness is properly detected
3. Jotform metadata is returned in chat responses
4. Provider cascade fallback logic

Follow-up intent routing (issue #133) is covered by tests/test_follow_up_intent.py
"""

import os
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.rico_env import get_rico_env_report, get_ai_provider
from src.rico_openai_agent import RicoOpenAIAgent
from src.rico_hf_client import is_available
from src.rico_chat_api import RicoChatAPI


class TestAIProviderHealthEndpoint:
    """Verify AI provider health endpoint behavior."""

    def test_health_endpoint_data_structure(self):
        """Health endpoint should return all required fields."""
        report = get_rico_env_report()

        # Verify all required fields exist
        assert hasattr(report, "openai_key_present")
        assert hasattr(report, "deepseek_key_present")
        assert hasattr(report, "hf_key_present")
        assert hasattr(report, "ready_for_deepseek")
        assert hasattr(report, "ready_for_hf")
        assert hasattr(report, "hf_available")
        assert hasattr(report, "ready_for_jotform")
        assert hasattr(report, "ai_provider")
        assert hasattr(report, "ready_for_openai")

        # Verify to_dict works
        report_dict = report.to_dict()
        assert "openai_key_present" in report_dict
        assert "deepseek_key_present" in report_dict
        assert "hf_key_present" in report_dict
        assert "ready_for_deepseek" in report_dict
        assert "ready_for_hf" in report_dict
        assert "hf_available" in report_dict
        assert "ready_for_jotform" in report_dict
        assert "ai_provider" in report_dict
        assert "ready_for_openai" in report_dict

    def test_health_http_response_exposes_key_presence_fields(self):
        """The public /health payload should surface key presence separately."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/health")
        assert response.status_code == 200

        payload = response.json()
        assert "openai_key_present" in payload
        assert "deepseek_key_present" in payload
        assert "hf_key_present" in payload
        assert "rico" in payload
        assert "openai_key_present" in payload["rico"]
        assert "deepseek_key_present" in payload["rico"]
        assert "hf_key_present" in payload["rico"]

    def test_deepseek_readiness_detection(self):
        """DeepSeek readiness should be detected when DEEPSEEK_API_KEY is set."""
        # Save original value
        original_key = os.getenv("DEEPSEEK_API_KEY")

        try:
            # Test with key set
            os.environ["DEEPSEEK_API_KEY"] = "test_key"
            os.environ["RICO_AI_PROVIDER"] = "deepseek"

            report = get_rico_env_report()
            provider = get_ai_provider()

            assert provider == "deepseek"
            assert report.deepseek_key_present == True
            assert report.ready_for_deepseek == True

        finally:
            # Restore original value
            if original_key is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = original_key
            os.environ.pop("RICO_AI_PROVIDER", None)

    def test_hf_readiness_detection(self):
        """HF readiness should be detected when HF key is set."""
        # Save original values
        original_hf = os.getenv("HF_API_TOKEN")
        original_provider = os.getenv("RICO_AI_PROVIDER")

        try:
            # Test with HF key set
            os.environ["HF_API_TOKEN"] = "test_hf_key"
            os.environ["RICO_AI_PROVIDER"] = "huggingface"

            report = get_rico_env_report()
            provider = get_ai_provider()

            assert provider == "huggingface"
            assert report.hf_key_present == True
            assert report.ready_for_hf == True
            assert report.hf_available == True

        finally:
            # Restore original values
            if original_hf is None:
                os.environ.pop("HF_API_TOKEN", None)
            else:
                os.environ["HF_API_TOKEN"] = original_hf
            if original_provider is None:
                os.environ.pop("RICO_AI_PROVIDER", None)
            else:
                os.environ["RICO_AI_PROVIDER"] = original_provider

    def test_hf_available_separate_from_ready_for_hf(self):
        """hf_available should report HF key presence regardless of active provider."""
        # Save original values
        original_hf = os.getenv("HF_API_TOKEN")
        original_provider = os.getenv("RICO_AI_PROVIDER")
        original_deepseek = os.getenv("DEEPSEEK_API_KEY")
        original_openai = os.getenv("OPENAI_API_KEY")
        original_openai_legacy = os.getenv("OPEN_AI_API")

        try:
            # Test with DeepSeek as active provider but HF key present
            os.environ["DEEPSEEK_API_KEY"] = "test_deepseek"
            os.environ["HF_API_TOKEN"] = "test_hf_key"
            os.environ["RICO_AI_PROVIDER"] = "deepseek"
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("OPEN_AI_API", None)

            report = get_rico_env_report()
            provider = get_ai_provider()

            assert provider == "deepseek"
            assert report.deepseek_key_present == True
            assert report.hf_key_present == True
            assert report.openai_key_present == False
            assert report.ready_for_deepseek == True
            assert report.ready_for_hf == False  # HF is not the active provider
            assert report.hf_available == True  # HF key is present for fallback

        finally:
            # Restore original values
            if original_hf is None:
                os.environ.pop("HF_API_TOKEN", None)
            else:
                os.environ["HF_API_TOKEN"] = original_hf
            if original_provider is None:
                os.environ.pop("RICO_AI_PROVIDER", None)
            else:
                os.environ["RICO_AI_PROVIDER"] = original_provider
            if original_deepseek is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = original_deepseek
            if original_openai is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original_openai
            if original_openai_legacy is None:
                os.environ.pop("OPEN_AI_API", None)
            else:
                os.environ["OPEN_AI_API"] = original_openai_legacy

    def test_key_presence_fields_are_independent_of_selected_provider(self):
        """Key presence fields should report config regardless of active provider."""
        original_env = {
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
            "OPEN_AI_API": os.getenv("OPEN_AI_API"),
            "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
            "HF_API_TOKEN": os.getenv("HF_API_TOKEN"),
            "RICO_AI_PROVIDER": os.getenv("RICO_AI_PROVIDER"),
        }

        try:
            os.environ["OPENAI_API_KEY"] = "test_openai_key"
            os.environ["DEEPSEEK_API_KEY"] = "test_deepseek_key"
            os.environ["HF_API_TOKEN"] = "test_hf_key"
            os.environ["RICO_AI_PROVIDER"] = "deepseek"

            report = get_rico_env_report()

            assert report.openai_key_present == True
            assert report.deepseek_key_present == True
            assert report.hf_key_present == True
            assert report.ready_for_openai == False
            assert report.ready_for_deepseek == True
            assert report.ready_for_hf == False
            assert report.hf_available == True

        finally:
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_jotform_readiness_detection(self):
        """Jotform readiness should be detected when form ID is set."""
        # Save original values
        original_form_id = os.getenv("JOTFORM_FORM_ID")
        original_alias = os.getenv("JOTFORM_RICO_FORM_ID")

        try:
            # Test with form ID set
            os.environ["JOTFORM_FORM_ID"] = "test_form_123"

            report = get_rico_env_report()
            assert report.ready_for_jotform == True

            # Test with alias
            os.environ.pop("JOTFORM_FORM_ID")
            os.environ["JOTFORM_RICO_FORM_ID"] = "test_form_456"

            report = get_rico_env_report()
            assert report.ready_for_jotform == True

        finally:
            # Restore original values
            if original_form_id is None:
                os.environ.pop("JOTFORM_FORM_ID", None)
            else:
                os.environ["JOTFORM_FORM_ID"] = original_form_id
            if original_alias is None:
                os.environ.pop("JOTFORM_RICO_FORM_ID", None)
            else:
                os.environ["JOTFORM_RICO_FORM_ID"] = original_alias


class TestHFFallbackReadiness:
    """Verify HF fallback is properly configured."""

    def test_hf_client_availability(self):
        """HF client should report availability correctly."""
        # Save all HF token aliases
        original_tokens = {
            "HF_API_TOKEN": os.getenv("HF_API_TOKEN"),
            "HF_API_KEY": os.getenv("HF_API_KEY"),
            "HF_TOKEN": os.getenv("HF_TOKEN"),
            "HUGGINGFACE_API_KEY": os.getenv("HUGGINGFACE_API_KEY"),
        }

        try:
            # Test with token
            os.environ["HF_API_TOKEN"] = "test_token"
            assert is_available() == True

            # Test without any HF tokens
            for key in original_tokens:
                os.environ.pop(key, None)
            assert is_available() == False

        finally:
            # Restore original values
            for key, value in original_tokens.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_openai_agent_hf_available(self):
        """RicoOpenAIAgent should report HF availability correctly."""
        agent = RicoOpenAIAgent()

        # The property checks for any HF key alias
        # This test verifies the property exists and returns a boolean
        assert isinstance(agent.hf_available, bool)

        # Verify it checks multiple env var aliases
        original_tokens = {
            "HF_API_TOKEN": os.getenv("HF_API_TOKEN"),
            "HF_API_KEY": os.getenv("HF_API_KEY"),
            "HF_TOKEN": os.getenv("HF_TOKEN"),
            "HUGGINGFACE_API_KEY": os.getenv("HUGGINGFACE_API_KEY"),
        }

        try:
            # Test with one alias
            os.environ["HF_API_TOKEN"] = "test"
            agent2 = RicoOpenAIAgent()
            assert agent2.hf_available == True

            # Test without any
            for key in original_tokens:
                os.environ.pop(key, None)
            agent3 = RicoOpenAIAgent()
            assert agent3.hf_available == False

        finally:
            # Restore original values
            for key, value in original_tokens.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class TestJotformMetadataInChatResponses:
    """Verify Jotform metadata is returned in chat responses."""

    def test_jotform_metadata_in_finalize(self):
        """Chat API should include Jotform form ID in finalized responses."""
        api = RicoChatAPI()

        # Save original values
        original_form_id = os.getenv("JOTFORM_FORM_ID")
        original_alias = os.getenv("JOTFORM_RICO_FORM_ID")

        try:
            # Test with form ID set
            os.environ["JOTFORM_FORM_ID"] = "test_form_123"

            # Create a minimal response
            test_response = {"type": "test", "message": "test"}
            finalized = api._finalize(test_response, "keyword", profile=None)

            assert "jotform_form_id" in finalized
            assert finalized["jotform_form_id"] == "test_form_123"

            # Test with alias
            os.environ.pop("JOTFORM_FORM_ID")
            os.environ["JOTFORM_RICO_FORM_ID"] = "test_form_456"

            finalized2 = api._finalize(test_response, "keyword", profile=None)
            assert "jotform_form_id" in finalized2
            assert finalized2["jotform_form_id"] == "test_form_456"

            # Test without form ID
            os.environ.pop("JOTFORM_RICO_FORM_ID")
            finalized3 = api._finalize(test_response, "keyword", profile=None)
            assert "jotform_form_id" in finalized3
            assert finalized3["jotform_form_id"] is None

        finally:
            # Restore original values
            if original_form_id is None:
                os.environ.pop("JOTFORM_FORM_ID", None)
            else:
                os.environ["JOTFORM_FORM_ID"] = original_form_id
            if original_alias is None:
                os.environ.pop("JOTFORM_RICO_FORM_ID", None)
            else:
                os.environ["JOTFORM_RICO_FORM_ID"] = original_alias


class TestProviderCascadeFallback:
    """Verify provider cascade fallback logic."""

    def test_agent_provider_available_property(self):
        """Agent should report provider availability based on configured provider."""
        # Save original values for all provider keys
        original_values = {
            "RICO_AI_PROVIDER": os.getenv("RICO_AI_PROVIDER"),
            "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
            "OPEN_AI_API": os.getenv("OPEN_AI_API"),
            "HF_API_TOKEN": os.getenv("HF_API_TOKEN"),
            "HF_API_KEY": os.getenv("HF_API_KEY"),
            "HF_TOKEN": os.getenv("HF_TOKEN"),
            "HUGGINGFACE_API_KEY": os.getenv("HUGGINGFACE_API_KEY"),
        }

        try:
            # Test DeepSeek provider
            os.environ["RICO_AI_PROVIDER"] = "deepseek"
            os.environ["DEEPSEEK_API_KEY"] = "test"
            # Clear other provider keys
            for key in ["OPENAI_API_KEY", "OPEN_AI_API", "HF_API_TOKEN", "HF_API_KEY", "HF_TOKEN", "HUGGINGFACE_API_KEY"]:
                os.environ.pop(key, None)
            agent1 = RicoOpenAIAgent()
            assert agent1.provider_available == True

            # Test HF provider
            os.environ.pop("DEEPSEEK_API_KEY")
            os.environ["RICO_AI_PROVIDER"] = "huggingface"
            os.environ["HF_API_TOKEN"] = "test"
            agent2 = RicoOpenAIAgent()
            assert agent2.provider_available == True

            # Test no provider (clear all)
            for key in original_values:
                os.environ.pop(key, None)
            agent3 = RicoOpenAIAgent()
            assert agent3.provider_available == False

        finally:
            # Restore original values
            for key, value in original_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
