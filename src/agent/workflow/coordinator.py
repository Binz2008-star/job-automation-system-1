"""src/agent/workflow/coordinator.py

Enhanced workflow coordinator with permission gates.

Classifies intent, checks permissions before high-impact actions,
routes to tools, logs learning signals, and returns structured responses.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.agent.orchestrator.intent_detector import detect, ACTION_TO_TOOL, VALID_ACTION_TYPES
from src.agent.registry import tool_registry
from src.agent.runtime import agent_runtime
from src.rico_agent import RicoProfile
from src.repositories.audit_repo import log_action
from src.repositories.learning_repo import infer_signals_from_job_action
from src.agent.intelligence.normalizer import normalize_role
from src.agent.intelligence.scorer import score_profile_fit
from src.agent.intelligence.recommender import recommend_adjacent_roles

logger = logging.getLogger(__name__)
_UTC = timezone.utc


class IntentType(Enum):
    """Canonical intent types."""
    SEARCH_JOBS = "search_jobs"
    APPLY_JOB = "apply_job"
    SAVE_JOB = "save_job"
    SKIP_JOB = "skip_job"
    BLOCK_COMPANY = "block_company"
    DRAFT_MESSAGE = "draft_message"
    EXPLAIN_MATCH = "explain_match"
    PREPARE_INTERVIEW = "prepare_interview"
    UPDATE_PREFERENCES = "update_preferences"
    GET_STATS = "get_stats"
    TRIGGER_PIPELINE = "trigger_pipeline"
    HELP = "help"
    UNKNOWN = "unknown"


class PermissionLevel(Enum):
    """Permission levels for actions."""
    SAFE = "safe"  # Can execute without confirmation
    REQUIRES_CONFIRMATION = "requires_confirmation"  # Must ask user first
    AUTO_ONLY = "auto_only"  # Only allowed in auto-apply mode
    PROHIBITED = "prohibited"  # Never allowed


@dataclass
class WorkflowResult:
    """Result of workflow execution."""
    success: bool
    intent: IntentType
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
    permission_level: PermissionLevel = PermissionLevel.SAFE
    execution_time_ms: int = 0
    learning_signals_logged: bool = False
    error: Optional[str] = None


class WorkflowCoordinator:
    """
    Coordinates agent workflows with permission gates.

    Workflow:
    1. Classify intent from message or explicit action
    2. Check permission level for the intent
    3. If requires_confirmation, return confirmation request
    4. If safe or auto mode, execute the action
    5. Log learning signals from the action
    6. Return structured result
    """

    # Permission levels for each intent
    _PERMISSION_MAP: Dict[IntentType, PermissionLevel] = {
        IntentType.SEARCH_JOBS: PermissionLevel.SAFE,
        IntentType.SAVE_JOB: PermissionLevel.SAFE,
        IntentType.SKIP_JOB: PermissionLevel.SAFE,
        IntentType.EXPLAIN_MATCH: PermissionLevel.SAFE,
        IntentType.DRAFT_MESSAGE: PermissionLevel.SAFE,
        IntentType.PREPARE_INTERVIEW: PermissionLevel.SAFE,
        IntentType.UPDATE_PREFERENCES: PermissionLevel.SAFE,
        IntentType.GET_STATS: PermissionLevel.SAFE,
        IntentType.HELP: PermissionLevel.SAFE,
        IntentType.APPLY_JOB: PermissionLevel.REQUIRES_CONFIRMATION,
        IntentType.BLOCK_COMPANY: PermissionLevel.REQUIRES_CONFIRMATION,
        IntentType.TRIGGER_PIPELINE: PermissionLevel.REQUIRES_CONFIRMATION,
        IntentType.UNKNOWN: PermissionLevel.SAFE,
    }

    def __init__(self):
        self._pending_confirmations: Dict[str, Dict[str, Any]] = {}

    def execute(
        self,
        message: Optional[str] = None,
        explicit_action: Optional[str] = None,
        job: Optional[Dict[str, Any]] = None,
        profile: Optional[RicoProfile] = None,
        canonical_user_id: str = "anonymous",
        autonomy_level: str = "recommend_only",
        confirmation_token: Optional[str] = None,
    ) -> WorkflowResult:
        """
        Execute a workflow.

        Args:
            message: User message for intent classification
            explicit_action: Explicit action type (bypasses classification)
            job: Job dict for job-specific actions
            profile: User profile for context
            canonical_user_id: Resolved user ID
            autonomy_level: User's autonomy setting (recommend_only, auto, manual)
            confirmation_token: Token if user confirmed a pending action

        Returns:
            WorkflowResult with execution outcome
        """
        wall_start = time.monotonic()

        # Check for confirmation token (user confirmed a pending action)
        if confirmation_token and confirmation_token in self._pending_confirmations:
            return self._execute_confirmed_action(
                confirmation_token,
                canonical_user_id,
                profile,
                autonomy_level,
            )

        # Determine intent
        if explicit_action:
            intent = self._action_to_intent(explicit_action)
        elif message:
            intent = self._classify_intent(message)
        else:
            intent = IntentType.HELP

        # Check permission level
        permission_level = self._PERMISSION_MAP.get(intent, PermissionLevel.SAFE)

        # Auto-apply mode bypasses confirmation for apply actions
        if autonomy_level == "auto" and intent == IntentType.APPLY_JOB:
            permission_level = PermissionLevel.SAFE

        # If requires confirmation and not in auto mode
        if permission_level == PermissionLevel.REQUIRES_CONFIRMATION and autonomy_level != "auto":
            return self._request_confirmation(
                intent,
                job,
                canonical_user_id,
                profile,
            )

        # Execute the workflow
        result = self._execute_workflow(
            intent,
            message,
            job,
            profile,
            canonical_user_id,
        )

        result.execution_time_ms = int((time.monotonic() - wall_start) * 1000)
        result.permission_level = permission_level

        # Log learning signals for job actions
        if job and result.success and intent in (IntentType.APPLY_JOB, IntentType.SAVE_JOB, IntentType.SKIP_JOB, IntentType.BLOCK_COMPANY):
            try:
                action_type = intent.value.replace("_job", "")
                infer_signals_from_job_action(canonical_user_id, action_type, job)
                result.learning_signals_logged = True
            except Exception:
                logger.exception("learning_signals_inference_failed intent=%s user=%s", intent, canonical_user_id)

        return result

    def _classify_intent(self, message: str) -> IntentType:
        """Classify intent from user message."""
        intent_name, tool_name = detect(message)

        # Map intent detector output to IntentType
        intent_map = {
            "get_ranked_jobs": IntentType.SEARCH_JOBS,
            "apply": IntentType.APPLY_JOB,
            "save": IntentType.SAVE_JOB,
            "skip": IntentType.SKIP_JOB,
            "block": IntentType.BLOCK_COMPANY,
            "draft": IntentType.DRAFT_MESSAGE,
            "why": IntentType.EXPLAIN_MATCH,
            "get_application_stats": IntentType.GET_STATS,
            "trigger_pipeline": IntentType.TRIGGER_PIPELINE,
            "help": IntentType.HELP,
        }

        return intent_map.get(intent_name, IntentType.UNKNOWN)

    def _action_to_intent(self, action: str) -> IntentType:
        """Convert action string to IntentType."""
        action_map = {
            "apply": IntentType.APPLY_JOB,
            "save": IntentType.SAVE_JOB,
            "skip": IntentType.SKIP_JOB,
            "not_relevant": IntentType.SKIP_JOB,
            "block": IntentType.BLOCK_COMPANY,
            "draft": IntentType.DRAFT_MESSAGE,
            "why": IntentType.EXPLAIN_MATCH,
            "remind": IntentType.PREPARE_INTERVIEW,
            "trigger_pipeline": IntentType.TRIGGER_PIPELINE,
        }
        return action_map.get(action, IntentType.UNKNOWN)

    def _request_confirmation(
        self,
        intent: IntentType,
        job: Optional[Dict[str, Any]],
        canonical_user_id: str,
        profile: Optional[RicoProfile],
    ) -> WorkflowResult:
        """Generate a confirmation request for a high-impact action."""
        import uuid
        confirmation_token = str(uuid.uuid4())

        # Store pending action
        self._pending_confirmations[confirmation_token] = {
            "intent": intent,
            "job": job,
            "canonical_user_id": canonical_user_id,
            "profile": profile,
            "timestamp": datetime.now(_UTC).isoformat(),
        }

        # Generate confirmation prompt
        if intent == IntentType.APPLY_JOB and job:
            confirmation_prompt = (
                f"Confirm application to {job.get('title', 'this job')} at {job.get('company', 'this company')}? "
                f"Reply YES to confirm or CANCEL to abort."
            )
        elif intent == IntentType.BLOCK_COMPANY and job:
            confirmation_prompt = (
                f"Confirm blocking {job.get('company', 'this company')} from future results? "
                f"Reply YES to confirm or CANCEL to abort."
            )
        elif intent == IntentType.TRIGGER_PIPELINE:
            confirmation_prompt = (
                "Confirm running the full job search pipeline now? "
                "This will search, score, and potentially send notifications. "
                "Reply YES to confirm or CANCEL to abort."
            )
        else:
            confirmation_prompt = f"Confirm this action? Reply YES to confirm or CANCEL to abort."

        return WorkflowResult(
            success=True,
            intent=intent,
            message="Confirmation required",
            requires_confirmation=True,
            confirmation_prompt=confirmation_prompt,
            confirmation_token=confirmation_token,
            permission_level=PermissionLevel.REQUIRES_CONFIRMATION,
            data={"pending_action": intent.value},
        )

    def _execute_confirmed_action(
        self,
        confirmation_token: str,
        canonical_user_id: str,
        profile: Optional[RicoProfile],
        autonomy_level: str,
    ) -> WorkflowResult:
        """Execute a previously confirmed action."""
        if confirmation_token not in self._pending_confirmations:
            return WorkflowResult(
                success=False,
                intent=IntentType.UNKNOWN,
                message="Confirmation token not found or expired",
                error="invalid_confirmation_token",
            )

        pending = self._pending_confirmations.pop(confirmation_token)
        intent = pending["intent"]
        job = pending["job"]

        return self._execute_workflow(
            intent,
            None,  # No message for confirmed actions
            job,
            profile,
            canonical_user_id,
        )

    def _execute_workflow(
        self,
        intent: IntentType,
        message: Optional[str],
        job: Optional[Dict[str, Any]],
        profile: Optional[RicoProfile],
        canonical_user_id: str,
    ) -> WorkflowResult:
        """Execute the workflow for a given intent."""
        try:
            if intent == IntentType.SEARCH_JOBS:
                return self._execute_search_jobs(message, profile, canonical_user_id)
            elif intent in (IntentType.APPLY_JOB, IntentType.SAVE_JOB, IntentType.SKIP_JOB, IntentType.BLOCK_COMPANY):
                return self._execute_job_action(intent, job, canonical_user_id)
            elif intent == IntentType.DRAFT_MESSAGE:
                return self._execute_draft_message(job, profile, canonical_user_id)
            elif intent == IntentType.EXPLAIN_MATCH:
                return self._execute_explain_match(job, profile, canonical_user_id)
            elif intent == IntentType.PREPARE_INTERVIEW:
                return self._execute_prepare_interview(job, profile, canonical_user_id)
            elif intent == IntentType.UPDATE_PREFERENCES:
                return self._execute_update_preferences(message, profile, canonical_user_id)
            elif intent == IntentType.GET_STATS:
                return self._execute_get_stats(canonical_user_id)
            elif intent == IntentType.TRIGGER_PIPELINE:
                return self._execute_trigger_pipeline(canonical_user_id)
            elif intent == IntentType.HELP:
                return self._execute_help()
            else:
                return WorkflowResult(
                    success=False,
                    intent=intent,
                    message=f"Intent {intent.value} not implemented",
                    error="intent_not_implemented",
                )
        except Exception as exc:
            logger.exception("workflow_execution_failed intent=%s user=%s", intent, canonical_user_id)
            return WorkflowResult(
                success=False,
                intent=intent,
                message=f"Workflow execution failed: {str(exc)}",
                error=str(exc),
            )

    def _execute_search_jobs(
        self,
        message: Optional[str],
        profile: Optional[RicoProfile],
        canonical_user_id: str,
    ) -> WorkflowResult:
        """Execute job search workflow with role intelligence."""
        from src.rico_repo_adapter import RicoSystem
        system = RicoSystem()

        try:
            workflow_result = system.run_for_profile(profile)
            matches = workflow_result.get("matches", [])[:5]

            # Role intelligence
            role_intelligence = {}
            if profile and profile.target_roles:
                target_role = profile.target_roles[0]
                normalized_role = normalize_role(target_role)
                fit_score = score_profile_fit(profile, normalized_role)
                adjacent_roles = recommend_adjacent_roles(profile, normalized_role, limit=3)

                role_intelligence = {
                    "normalized_role": normalized_role,
                    "fit_score": fit_score.overall_score,
                    "fit_details": {
                        "skills_score": fit_score.skills_score,
                        "experience_score": fit_score.experience_score,
                        "industry_score": fit_score.industry_score,
                        "missing_required_skills": fit_score.missing_required_skills,
                    },
                    "adjacent_roles": [
                        {
                            "role": r.canonical_role,
                            "similarity": r.similarity_score,
                            "reason": r.reason,
                            "fit_score": r.fit_score,
                        }
                        for r in adjacent_roles
                    ],
                }

            return WorkflowResult(
                success=True,
                intent=IntentType.SEARCH_JOBS,
                message=f"Found {len(matches)} job matches",
                data={
                    "matches": matches,
                    "total": len(workflow_result.get("matches", [])),
                    "role_intelligence": role_intelligence,
                },
            )
        except Exception as exc:
            logger.exception("search_jobs_failed user=%s", canonical_user_id)
            return WorkflowResult(
                success=False,
                intent=IntentType.SEARCH_JOBS,
                message=f"Job search failed: {str(exc)}",
                error=str(exc),
            )

    def _execute_job_action(
        self,
        intent: IntentType,
        job: Optional[Dict[str, Any]],
        canonical_user_id: str,
    ) -> WorkflowResult:
        """Execute job action (apply, save, skip, block)."""
        if not job:
            return WorkflowResult(
                success=False,
                intent=intent,
                message="No job provided for this action",
                error="missing_job",
            )

        action = intent.value.replace("_job", "").replace("_company", "")
        job_key = job.get("id") or job.get("_key", "")

        result = agent_runtime.handle_action(
            user_id=canonical_user_id,
            action=action,
            job_key=job_key,
            job=job,
            source="workflow",
        )

        return WorkflowResult(
            success=result.ok,
            intent=intent,
            message=result.message,
            data=result.data or {},
            error=result.error,
        )

    def _execute_draft_message(
        self,
        job: Optional[Dict[str, Any]],
        profile: Optional[RicoProfile],
        canonical_user_id: str,
    ) -> WorkflowResult:
        """Execute message drafting workflow."""
        if not job:
            return WorkflowResult(
                success=False,
                intent=IntentType.DRAFT_MESSAGE,
                message="No job provided for drafting",
                error="missing_job",
            )

        # Use existing tool
        try:
            tool_def = tool_registry.get("draft_message")
            tool_result = tool_def.fn(job)

            return WorkflowResult(
                success=tool_result.success,
                intent=IntentType.DRAFT_MESSAGE,
                message=tool_result.data.get("draft", "") if tool_result.data else "Draft generated",
                data=tool_result.data or {},
                error=tool_result.error if not tool_result.success else None,
            )
        except Exception as exc:
            logger.exception("draft_message_failed user=%s", canonical_user_id)
            return WorkflowResult(
                success=False,
                intent=IntentType.DRAFT_MESSAGE,
                message=f"Draft failed: {str(exc)}",
                error=str(exc),
            )

    def _execute_explain_match(
        self,
        job: Optional[Dict[str, Any]],
        profile: Optional[RicoProfile],
        canonical_user_id: str,
    ) -> WorkflowResult:
        """Execute match explanation workflow."""
        if not job:
            return WorkflowResult(
                success=False,
                intent=IntentType.EXPLAIN_MATCH,
                message="No job provided for explanation",
                error="missing_job",
            )

        try:
            from src.rico_match_explainer import build_match_explanation
            explanation = build_match_explanation(job, profile)

            return WorkflowResult(
                success=True,
                intent=IntentType.EXPLAIN_MATCH,
                message=explanation.get("why", "Match explanation generated"),
                data=explanation,
            )
        except Exception as exc:
            logger.exception("explain_match_failed user=%s", canonical_user_id)
            return WorkflowResult(
                success=False,
                intent=IntentType.EXPLAIN_MATCH,
                message=f"Explanation failed: {str(exc)}",
                error=str(exc),
            )

    def _execute_prepare_interview(
        self,
        job: Optional[Dict[str, Any]],
        profile: Optional[RicoProfile],
        canonical_user_id: str,
    ) -> WorkflowResult:
        """Execute interview preparation workflow."""
        # Use HF for interview prep
        try:
            from src.rico_hf_client import generate_text, is_available

            if not is_available():
                return WorkflowResult(
                    success=False,
                    intent=IntentType.PREPARE_INTERVIEW,
                    message="AI provider unavailable for interview prep",
                    error="provider_unavailable",
                )

            job_title = job.get("title", "this role") if job else "this role"
            company = job.get("company", "this company") if job else "this company"

            system_prompt = (
                "You are Rico, a UAE career coach. "
                "Provide concise, practical interview preparation tips "
                "including likely questions and answer frameworks."
            )

            prompt = f"Prepare for an interview for {job_title} at {company}."
            text = generate_text(prompt, system=system_prompt, max_new_tokens=400)

            return WorkflowResult(
                success=True,
                intent=IntentType.PREPARE_INTERVIEW,
                message=text or "Interview preparation notes generated",
                data={"notes": text},
            )
        except Exception as exc:
            logger.exception("prepare_interview_failed user=%s", canonical_user_id)
            return WorkflowResult(
                success=False,
                intent=IntentType.PREPARE_INTERVIEW,
                message=f"Interview prep failed: {str(exc)}",
                error=str(exc),
            )

    def _execute_update_preferences(
        self,
        message: Optional[str],
        profile: Optional[RicoProfile],
        canonical_user_id: str,
    ) -> WorkflowResult:
        """Execute preference update workflow."""
        # This would extract preferences from message and update profile
        # For now, return a placeholder
        return WorkflowResult(
            success=True,
            intent=IntentType.UPDATE_PREFERENCES,
            message="Preferences update not yet implemented - please use profile update endpoint",
            data={},
        )

    def _execute_get_stats(self, canonical_user_id: str) -> WorkflowResult:
        """Execute stats retrieval workflow."""
        try:
            tool_def = tool_registry.get("get_application_stats")
            tool_result = tool_def.fn(user_id=canonical_user_id)

            return WorkflowResult(
                success=tool_result.success,
                intent=IntentType.GET_STATS,
                data=tool_result.data,
                message=tool_result.error if not tool_result.success else None,
                execution_time_ms=tool_result.execution_time_ms,
            )
        except Exception as exc:
            logger.exception("get_stats_failed user=%s", canonical_user_id)
            return WorkflowResult(
                success=False,
                intent=IntentType.GET_STATS,
                error=str(exc),
            )

    def _execute_trigger_pipeline(self, canonical_user_id: str) -> WorkflowResult:
        """Execute pipeline trigger workflow."""
        try:
            tool_def = tool_registry.get("trigger_pipeline")
            tool_result = tool_def.fn()

            return WorkflowResult(
                success=tool_result.success,
                intent=IntentType.TRIGGER_PIPELINE,
                message=tool_result.data.get("message", "Pipeline triggered") if tool_result.data else "Pipeline triggered",
                data=tool_result.data or {},
                error=tool_result.error if not tool_result.success else None,
            )
        except Exception as exc:
            logger.exception("trigger_pipeline_failed user=%s", canonical_user_id)
            return WorkflowResult(
                success=False,
                intent=IntentType.TRIGGER_PIPELINE,
                message=f"Pipeline trigger failed: {str(exc)}",
                error=str(exc),
            )

    def _execute_help(self) -> WorkflowResult:
        """Execute help workflow."""
        help_text = (
            "I can help you with:\n"
            "- Search for jobs in the UAE\n"
            "- Save, skip, or apply to jobs\n"
            "- Draft messages to recruiters\n"
            "- Explain why a job matches your profile\n"
            "- Prepare for interviews\n"
            "- Get application statistics\n"
            "- Update your preferences\n\n"
            "Just tell me what you need help with."
        )

        return WorkflowResult(
            success=True,
            intent=IntentType.HELP,
            message=help_text,
            data={"options": ["search_jobs", "apply", "save", "draft", "explain", "interview", "stats"]},
        )


# Module-level singleton
_workflow_coordinator = WorkflowCoordinator()


def execute_workflow(
    message: Optional[str] = None,
    explicit_action: Optional[str] = None,
    job: Optional[Dict[str, Any]] = None,
    profile: Optional[RicoProfile] = None,
    canonical_user_id: str = "anonymous",
    autonomy_level: str = "recommend_only",
    confirmation_token: Optional[str] = None,
) -> WorkflowResult:
    """
    Convenience function to execute a workflow.

    Uses the singleton WorkflowCoordinator instance.
    """
    return _workflow_coordinator.execute(
        message=message,
        explicit_action=explicit_action,
        job=job,
        profile=profile,
        canonical_user_id=canonical_user_id,
        autonomy_level=autonomy_level,
        confirmation_token=confirmation_token,
    )
