"""src/agent/coordinator.py

Stateful agent coordinator that ties all components together.

Implements the complete request flow:
request → resolve identity → load profile and memory → hydrate context
→ route intent → call AI provider if needed → execute safe workflow action
→ save learning signal → respond

The model does NOT remember everything.
The database and backend remember.
The AI model reasons over the current profile context.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.agent.identity.resolver import IdentityResolver, resolve_canonical_user, IdentityResolution
from src.agent.context.resolver import ProfileContextResolver, resolve_profile_context, ProfileContext
from src.agent.workflow.coordinator import WorkflowCoordinator, execute_workflow, WorkflowResult, IntentType
from src.rico_agent import RicoProfile
from src.repositories.audit_repo import log_permission_check, log_profile_hydration
from src.repositories.learning_repo import record_learning_signal, LearningProfile

logger = logging.getLogger(__name__)
_UTC = timezone.utc


@dataclass
class AgentRequest:
    """Incoming request to the stateful agent."""
    message: Optional[str] = None
    explicit_action: Optional[str] = None
    job: Optional[Dict[str, Any]] = None
    email: Optional[str] = None
    telegram_username: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    session_id: Optional[str] = None
    jotform_submission: Optional[Dict[str, Any]] = None
    cv_data: Optional[Dict[str, Any]] = None
    cv_extracted_email: Optional[str] = None
    chat_history: Optional[List[Dict[str, Any]]] = None
    confirmation_token: Optional[str] = None
    autonomy_level: str = "recommend_only"


@dataclass
class AgentResponse:
    """Response from the stateful agent."""
    success: bool
    message: str
    intent: Optional[IntentType] = None
    data: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
    confirmation_token: Optional[str] = None
    canonical_user_id: str = "anonymous"
    profile_completeness: float = 0.0
    missing_fields: List[str] = field(default_factory=list)
    learning_signals_applied: bool = False
    execution_time_ms: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Role intelligence fields
    normalized_role: Optional[str] = None
    profile_fit_score: Optional[float] = None
    adjacent_roles: List[Dict[str, Any]] = field(default_factory=list)
    search_context: Optional[Dict[str, Any]] = None


class StatefulAgentCoordinator:
    """
    Main coordinator for the stateful agent architecture.

    Orchestrates the complete request flow:
    1. Resolve identity (guest, authenticated, Jotform, Telegram, CV)
    2. Load and hydrate profile context
    3. Route intent and check permissions
    4. Execute workflow action
    5. Save learning signals
    6. Return structured response
    """

    def __init__(self):
        self.identity_resolver = IdentityResolver()
        self.profile_resolver = ProfileContextResolver()
        self.workflow_coordinator = WorkflowCoordinator()

    def handle_request(self, request: AgentRequest) -> AgentResponse:
        """
        Handle a complete agent request through the stateful flow.

        Args:
            request: AgentRequest with all available context

        Returns:
            AgentResponse with execution result
        """
        wall_start = time.monotonic()

        try:
            # Step 1: Resolve identity
            identity = self.identity_resolver.resolve(
                email=request.email,
                telegram_username=request.telegram_username,
                telegram_chat_id=request.telegram_chat_id,
                session_id=request.session_id,
                jotform_submission=request.jotform_submission,
                cv_extracted_email=request.cv_extracted_email,
            )

            canonical_user_id = identity.canonical_user_id

            # Step 2: Load and hydrate profile context
            profile_context = self.profile_resolver.resolve(
                canonical_user_id=canonical_user_id,
                cv_data=request.cv_data,
                jotform_data=request.jotform_submission,
                chat_history=request.chat_history,
            )

            # Log profile hydration
            if profile_context.hydration_sources:
                log_profile_hydration(
                    canonical_user_id=canonical_user_id,
                    hydration_sources=profile_context.hydration_sources,
                    completeness_before=0.0,  # Could track previous completeness
                    completeness_after=profile_context.completeness_score,
                )

            profile = profile_context.profile

            # Step 3: Execute workflow
            workflow_result = self.workflow_coordinator.execute(
                message=request.message,
                explicit_action=request.explicit_action,
                job=request.job,
                profile=profile,
                canonical_user_id=canonical_user_id,
                autonomy_level=request.autonomy_level or (profile.settings.autonomy_level if profile else "recommend_only"),
                confirmation_token=request.confirmation_token,
            )

            # Step 4: Log permission check if applicable
            if workflow_result.permission_level.value != "safe":
                log_permission_check(
                    canonical_user_id=canonical_user_id,
                    intent=workflow_result.intent.value,
                    permission_level=workflow_result.permission_level.value,
                    allowed=workflow_result.success,
                    requires_confirmation=workflow_result.requires_confirmation,
                )

            # Step 5: Build response
            # Extract role intelligence from workflow data
            role_intelligence = workflow_result.data.get("role_intelligence", {}) if workflow_result.data else {}

            response = AgentResponse(
                success=workflow_result.success,
                message=workflow_result.message,
                intent=workflow_result.intent,
                data=workflow_result.data,
                requires_confirmation=workflow_result.requires_confirmation,
                confirmation_prompt=workflow_result.confirmation_prompt,
                confirmation_token=workflow_result.confirmation_token,
                canonical_user_id=canonical_user_id,
                profile_completeness=profile_context.completeness_score,
                missing_fields=profile_context.missing_required,
                learning_signals_applied=workflow_result.learning_signals_logged,
                execution_time_ms=workflow_result.execution_time_ms,
                error=workflow_result.error,
                metadata={
                    "identity_source": identity.identity_source,
                    "identity_confidence": identity.confidence,
                    "hydration_sources": profile_context.hydration_sources,
                    "permission_level": workflow_result.permission_level.value,
                },
                # Role intelligence fields
                normalized_role=role_intelligence.get("normalized_role"),
                profile_fit_score=role_intelligence.get("fit_score"),
                adjacent_roles=role_intelligence.get("adjacent_roles", []),
            )

            logger.info(
                "agent_request_completed user=%s intent=%s success=%s completeness=%.2f duration_ms=%d",
                canonical_user_id,
                workflow_result.intent.value if workflow_result.intent else "none",
                workflow_result.success,
                profile_context.completeness_score,
                response.execution_time_ms,
            )

            return response

        except Exception as exc:
            logger.exception("agent_request_failed")
            return AgentResponse(
                success=False,
                message=f"Agent request failed: {str(exc)}",
                error=str(exc),
                execution_time_ms=int((time.monotonic() - wall_start) * 1000),
            )

    def get_user_state(self, canonical_user_id: str) -> Dict[str, Any]:
        """
        Get the complete state of a user.

        Returns identity, profile, learning signals, and recent activity.
        """
        try:
            # Load profile context
            profile_context = self.profile_resolver.resolve(
                canonical_user_id=canonical_user_id,
                force_refresh=True,
            )

            # Load learning profile
            from src.repositories.learning_repo import get_learning_profile
            learning_profile = get_learning_profile(canonical_user_id)

            return {
                "canonical_user_id": canonical_user_id,
                "profile": profile_context.profile.__dict__ if profile_context.profile else None,
                "profile_completeness": profile_context.completeness_score,
                "missing_required": profile_context.missing_required,
                "missing_optional": profile_context.missing_optional,
                "hydration_sources": profile_context.hydration_sources,
                "learning_signals": {
                    "role_preferences": learning_profile.role_preferences,
                    "location_preferences": learning_profile.location_preferences,
                    "skill_relevance": learning_profile.skill_relevance,
                    "company_sentiment": learning_profile.company_sentiment,
                    "feedback_events": learning_profile.feedback_events,
                },
                "behavior_signals": profile_context.behavior_signals,
                "last_hydrated": profile_context.last_hydrated_at.isoformat() if profile_context.last_hydrated_at else None,
            }
        except Exception as exc:
            logger.exception("get_user_state_failed user=%s", canonical_user_id)
            return {"error": str(exc), "canonical_user_id": canonical_user_id}

    def merge_identities(
        self,
        guest_session_id: str,
        email: str,
    ) -> bool:
        """
        Merge a guest session with an authenticated user.

        Called when a guest user later authenticates with email.
        """
        try:
            # Resolve both identities
            guest_identity = self.identity_resolver.resolve(session_id=guest_session_id)
            authenticated_identity = self.identity_resolver.resolve(email=email)

            # Link the guest session to the authenticated user
            success = self.identity_resolver.link_identity(
                canonical_user_id=authenticated_identity.canonical_user_id,
                link_email=email,
            )

            if success:
                logger.info(
                    "identity_merge_success guest=%s authenticated=%s",
                    guest_identity.canonical_user_id,
                    authenticated_identity.canonical_user_id,
                )

            return success
        except Exception:
            logger.exception("identity_merge_failed guest=%s email=%s", guest_session_id, email)
            return False


# Module-level singleton
_stateful_agent_coordinator = StatefulAgentCoordinator()


def handle_agent_request(request: AgentRequest) -> AgentResponse:
    """
    Convenience function to handle an agent request.

    Uses the singleton StatefulAgentCoordinator instance.
    """
    return _stateful_agent_coordinator.handle_request(request)


def get_user_state(canonical_user_id: str) -> Dict[str, Any]:
    """
    Convenience function to get user state.

    Uses the singleton StatefulAgentCoordinator instance.
    """
    return _stateful_agent_coordinator.get_user_state(canonical_user_id)


def merge_identities(guest_session_id: str, email: str) -> bool:
    """
    Convenience function to merge identities.

    Uses the singleton StatefulAgentCoordinator instance.
    """
    return _stateful_agent_coordinator.merge_identities(guest_session_id, email)
