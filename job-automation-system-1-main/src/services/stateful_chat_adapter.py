"""src/services/stateful_chat_adapter.py

Adapter layer to migrate existing chat API to use new stateful architecture.

This adapter bridges the legacy RicoChatAPI interface with the new
StatefulAgentCoordinator, allowing gradual migration without breaking
existing functionality.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.agent.coordinator import AgentRequest, AgentResponse, handle_agent_request
from src.rico_memory import RicoMemoryStore

logger = logging.getLogger(__name__)


class StatefulChatAdapter:
    """
    Adapter for migrating chat API to stateful architecture.

    Provides backward-compatible interface while using new stateful coordinator
    under the hood.
    """

    def __init__(self):
        self.memory = RicoMemoryStore()

    def send_message(
        self,
        user_id: str,
        message: str,
        *,
        email: Optional[str] = None,
        telegram_username: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        session_id: Optional[str] = None,
        job: Optional[Dict[str, Any]] = None,
        confirmation_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message through the stateful agent.

        Args:
            user_id: Legacy user ID (email or session ID)
            message: User message
            email: Email for identity resolution
            telegram_username: Telegram username for identity resolution
            telegram_chat_id: Telegram chat ID for identity resolution
            session_id: Guest session ID
            job: Job dict for job-specific actions
            confirmation_token: Token if user confirmed a pending action

        Returns:
            Response dict compatible with existing chat API
        """
        # Determine identity parameters
        # If user_id looks like email, use it as email
        # If user_id looks like public:*, use it as session_id
        if user_id.startswith("public:"):
            session_id = session_id or user_id.replace("public:", "")
        elif "@" in user_id:
            email = email or user_id
        else:
            # Assume it's an email or legacy ID
            email = email or user_id

        # Build request
        request = AgentRequest(
            message=message,
            job=job,
            email=email,
            telegram_username=telegram_username,
            telegram_chat_id=telegram_chat_id,
            session_id=session_id,
            confirmation_token=confirmation_token,
        )

        # Handle through stateful coordinator
        response = handle_agent_request(request)

        # Convert to legacy format
        return self._to_legacy_response(response, user_id)

    def handle_action(
        self,
        user_id: str,
        action: str,
        job: Optional[Dict[str, Any]] = None,
        *,
        email: Optional[str] = None,
        confirmation_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle an explicit action through the stateful agent.

        Args:
            user_id: Legacy user ID
            action: Action type (apply, save, skip, block, etc.)
            job: Job dict
            email: Email for identity resolution
            confirmation_token: Token if user confirmed

        Returns:
            Response dict compatible with existing API
        """
        if user_id.startswith("public:"):
            session_id = user_id.replace("public:", "")
        elif "@" in user_id:
            email = email or user_id
        else:
            email = email or user_id

        request = AgentRequest(
            explicit_action=action,
            job=job,
            email=email,
            session_id=session_id if user_id.startswith("public:") else None,
            confirmation_token=confirmation_token,
        )

        response = handle_agent_request(request)
        return self._to_legacy_response(response, user_id)

    def handle_jotform_submission(
        self,
        jotform_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle a Jotform submission through the stateful agent.

        Args:
            jotform_data: Normalized Jotform submission payload

        Returns:
            Response dict compatible with existing API
        """
        # Extract identity from Jotform
        email = self._extract_email_from_jotform(jotform_data)
        telegram_username = self._extract_telegram_from_jotform(jotform_data)

        request = AgentRequest(
            jotform_submission=jotform_data,
            email=email,
            telegram_username=telegram_username,
        )

        response = handle_agent_request(request)
        return self._to_legacy_response(response, email or telegram_username or "unknown")

    def handle_cv_upload(
        self,
        user_id: str,
        cv_data: Dict[str, Any],
        *,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle a CV upload through the stateful agent.

        Args:
            user_id: Legacy user ID
            cv_data: Parsed CV data
            email: Email for identity resolution

        Returns:
            Response dict compatible with existing API
        """
        if user_id.startswith("public:"):
            session_id = user_id.replace("public:", "")
        elif "@" in user_id:
            email = email or user_id
        else:
            email = email or user_id

        cv_extracted_email = cv_data.get("emails", [None])[0] if cv_data.get("emails") else None

        request = AgentRequest(
            cv_data=cv_data,
            cv_extracted_email=cv_extracted_email,
            email=email,
            session_id=session_id if user_id.startswith("public:") else None,
        )

        response = handle_agent_request(request)
        return self._to_legacy_response(response, user_id)

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get user profile through the stateful agent.

        Args:
            user_id: Legacy user ID

        Returns:
            Profile dict compatible with existing API
        """
        from src.agent.coordinator import get_user_state

        if user_id.startswith("public:"):
            canonical_user_id = user_id
        elif "@" in user_id:
            canonical_user_id = user_id.lower()
        else:
            canonical_user_id = user_id

        state = get_user_state(canonical_user_id)
        return state

    def _to_legacy_response(self, response: AgentResponse, legacy_user_id: str) -> Dict[str, Any]:
        """Convert AgentResponse to legacy chat API format."""
        result: Dict[str, Any] = {
            "message": response.message,
            "type": response.intent.value if response.intent else "response",
            "success": response.success,
            "user_id": legacy_user_id,
            "canonical_user_id": response.canonical_user_id,
        }

        if response.requires_confirmation:
            result["requires_confirmation"] = True
            result["confirmation_prompt"] = response.confirmation_prompt
            result["confirmation_token"] = response.confirmation_token

        if response.data:
            result["data"] = response.data

        if response.profile_completeness > 0:
            result["profile_completeness"] = response.profile_completeness
            result["missing_fields"] = response.missing_fields

        if response.learning_signals_applied:
            result["learning_signals_applied"] = True

        if response.error:
            result["error"] = response.error

        if response.metadata:
            result["metadata"] = response.metadata

        return result

    def _extract_email_from_jotform(self, jotform_data: Dict[str, Any]) -> Optional[str]:
        """Extract email from Jotform submission."""
        answers = jotform_data.get("pretty", jotform_data)
        email = answers.get("email") or answers.get("Email Address") or answers.get("Email")
        return email

    def _extract_telegram_from_jotform(self, jotform_data: Dict[str, Any]) -> Optional[str]:
        """Extract Telegram username from Jotform submission."""
        answers = jotform_data.get("pretty", jotform_data)
        telegram = answers.get("telegram_username") or answers.get("Telegram Username")
        return telegram


# Module-level singleton for backward compatibility
_stateful_chat_adapter = StatefulChatAdapter()


def send_message_stateful(
    user_id: str,
    message: str,
    *,
    email: Optional[str] = None,
    telegram_username: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    session_id: Optional[str] = None,
    job: Optional[Dict[str, Any]] = None,
    confirmation_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to send message through stateful adapter.

    This can be used as a drop-in replacement for chat_service.send_message()
    when migrating to the stateful architecture.
    """
    return _stateful_chat_adapter.send_message(
        user_id=user_id,
        message=message,
        email=email,
        telegram_username=telegram_username,
        telegram_chat_id=telegram_chat_id,
        session_id=session_id,
        job=job,
        confirmation_token=confirmation_token,
    )
