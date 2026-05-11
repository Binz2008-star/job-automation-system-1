#!/usr/bin/env python3
"""Test Rico free AI provider mode functionality."""

import os
import pytest
from unittest.mock import patch, Mock
from starlette.requests import Request

from src.rico_env import get_ai_provider
from src.services.chat_service import send_message
from src.api.routers.rico_chat import rico_openai_smoke

_AI_ENV_VARS = [
    "OPENAI_API_KEY",
    "OPEN_AI_API",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_FALLBACK_MODEL",
    "HF_API_TOKEN",
    "HF_TOKEN",
    "HF_API_KEY",
    "HUGGINGFACE_API_KEY",
    "RICO_AI_PROVIDER",
]


@pytest.fixture(autouse=True)
def clear_ai_env():
    saved = {name: os.environ.get(name) for name in _AI_ENV_VARS}
    for name in _AI_ENV_VARS:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class TestFreeProviderMode:
    """Test free AI provider mode functionality."""

    def test_get_ai_provider_default(self):
        """Test that default provider is 'none' when env var is not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_ai_provider() == "none"

    def test_get_ai_provider_none(self):
        """Test that provider='none' is respected."""
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "none"}):
            assert get_ai_provider() == "none"

    def test_get_ai_provider_openai(self):
        """Test that provider='openai' is respected."""
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "openai"}):
            assert get_ai_provider() == "openai"

    def test_get_ai_provider_huggingface(self):
        """Test that provider='huggingface' is respected."""
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "huggingface"}):
            assert get_ai_provider() == "huggingface"

    def test_get_ai_provider_deepseek(self):
        """Test that provider='deepseek' is respected."""
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "deepseek"}):
            assert get_ai_provider() == "deepseek"

    def test_get_ai_provider_invalid(self):
        """Test that invalid provider defaults to auto-detect (none when no keys)."""
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "invalid"}, clear=True):
            assert get_ai_provider() == "none"

    def test_get_ai_provider_auto_detects_hf(self):
        """Test that HF key auto-detects huggingface provider."""
        with patch.dict(os.environ, {"HF_TOKEN": "hf_test_token"}, clear=True):
            assert get_ai_provider() == "huggingface"

    def test_get_ai_provider_auto_detects_hf_api_token_alias(self):
        """Test that HF_API_TOKEN is treated as a valid HF key alias."""
        with patch.dict(os.environ, {"HF_API_TOKEN": "hf_test_token"}, clear=True):
            assert get_ai_provider() == "huggingface"

    def test_get_ai_provider_deepseek_priority_over_hf(self):
        """Test that DeepSeek wins auto-detect when both DeepSeek and HF keys are present."""
        with patch.dict(
            os.environ,
            {"HF_TOKEN": "hf_test", "DEEPSEEK_API_KEY": "dsk-test"},
            clear=True,
        ):
            assert get_ai_provider() == "deepseek"

    def test_get_ai_provider_auto_detects_deepseek(self):
        """Test that a DeepSeek key auto-detects DeepSeek."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "dsk-test-token"}, clear=True):
            assert get_ai_provider() == "deepseek"

    def test_get_ai_provider_case_insensitive(self):
        """Test that provider is case insensitive."""
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "none"}):
            assert get_ai_provider() == "none"
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "openai"}):
            assert get_ai_provider() == "openai"
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "DeepSeek"}):
            assert get_ai_provider() == "deepseek"

    def test_get_ai_provider_hf_alias(self):
        """Test that 'hf' shorthand resolves to 'huggingface'."""
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "hf"}):
            assert get_ai_provider() == "huggingface"
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "HF"}):
            assert get_ai_provider() == "huggingface"

    @patch('src.rico_chat_api.RicoChatAPI')
    def test_send_message_delegates_to_chat_api(self, mock_chat_api):
        """send_message always delegates to RicoChatAPI.process_message."""
        mock_api_instance = mock_chat_api.return_value
        mock_api_instance.process_message.return_value = {
            "message": "AI response",
            "response_source": "openai",
            "provider": "openai",
            "openai_available": True,
            "hf_available": False,
        }

        result = send_message(user_id="test@example.com", message="Hello")

        mock_api_instance.process_message.assert_called_once_with(
            user_id="test@example.com", message="Hello"
        )
        assert result["message"] == "AI response"
        assert result["response_source"] == "openai"
        assert result["provider"] == "openai"
        assert result["openai_available"] is True

    def test_openai_smoke_provider_none(self):
        """Test that smoke endpoint returns disabled response when provider=none."""
        mock_request = Mock(spec=Request)

        with patch('src.rico_env.get_ai_provider', return_value="none"), \
             patch('src.api.routers.rico_chat.get_current_user', return_value={"email": "test@example.com"}):
            result = rico_openai_smoke(mock_request)

        assert result["success"] is False
        assert result["provider"] == "none"
        assert result["openai_available"] is False
        assert result["error"] == "OpenAIProviderDisabled"
        assert result["model"] is None
        assert result["fallback_model"] is None
        assert "disabled" in result["response"].lower()

    def test_openai_smoke_provider_openai(self):
        """Test that smoke endpoint calls OpenAI when provider=openai."""
        mock_request = Mock(spec=Request)

        with patch('src.rico_env.get_ai_provider', return_value="openai"), \
             patch('src.api.routers.rico_chat.get_current_user', return_value={"email": "test@example.com"}), \
             patch('src.rico_openai_runtime.call_openai_minimal', return_value={
                 "success": True,
                 "model": "gpt-4o-mini",
                 "fallback_model": "gpt-4.1-mini",
                 "text": "OK",
                 "error": None,
                 "error_detail": None,
                 "openai_available": True
             }) as mock_call_openai:
            result = rico_openai_smoke(mock_request)

        mock_call_openai.assert_called_once_with("Say OK", smoke=True)
        assert result["success"] is True
        assert result["model"] == "gpt-4o-mini"
        assert result["response"] == "OK"

    def test_openai_smoke_provider_huggingface(self):
        """Test that smoke endpoint returns HF status when provider=huggingface."""
        mock_request = Mock(spec=Request)

        with patch.dict(os.environ, {"HF_TOKEN": "hf_test_token"}), \
             patch('src.rico_env.get_ai_provider', return_value="huggingface"), \
             patch('src.api.routers.rico_chat.get_current_user', return_value={"email": "test@example.com"}):
            result = rico_openai_smoke(mock_request)

        assert result["success"] is False
        assert result["provider"] == "huggingface"
        assert result["openai_available"] is False
        assert result["hf_available"] is True
        assert result["error"] == "OpenAIProviderDisabled"

    def test_openai_smoke_provider_deepseek(self):
        """Test that smoke endpoint calls the shared runtime when provider=deepseek."""
        mock_request = Mock(spec=Request)

        with patch('src.rico_env.get_ai_provider', return_value="deepseek"), \
             patch('src.api.routers.rico_chat.get_current_user', return_value={"email": "test@example.com"}), \
             patch('src.rico_openai_runtime.call_openai_minimal', return_value={
                 "success": True,
                 "provider": "deepseek",
                 "provider_available": True,
                 "model": "deepseek-v4-flash",
                 "fallback_model": "deepseek-v4-pro",
                 "text": "OK",
                 "error": None,
                 "error_detail": None,
                 "openai_available": False,
                 "deepseek_available": True,
             }) as mock_call_openai:
            result = rico_openai_smoke(mock_request)

        mock_call_openai.assert_called_once_with("Say OK", smoke=True, provider="deepseek")
        assert result["success"] is True
        assert result["provider"] == "deepseek"
        assert result["model"] == "deepseek-v4-flash"
        assert result["deepseek_available"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
