"""
Feedback Loop System
Implements the complete learning cycle: Apply → Track → Update → Learn → Re-score

This module orchestrates the continuous improvement of the job search system
by analyzing outcomes and updating the decision engine based on real-world feedback.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.db import get_top_jobs, get_application_stats, is_db_available
from src.applications import get_applied_jobs, update_application_status
from src.decision_engine_v2 import JobDecisionEngine, generate_decision_insights
from src.response_intelligence import ResponseIntelligenceEngine, create_engine

logger = logging.getLogger(__name__)


class FeedbackLoopSystem:
    """
    Complete feedback loop system for continuous improvement.

    Orchestrates the cycle:
    1. Apply - Submit applications
    2. Track - Monitor responses and outcomes
    3. Update - Record new data in database
    4. Learn - Analyze patterns and extract insights
    5. Re-score - Update decision engine with learnings
    """

    def __init__(
        self,
        decision_engine: JobDecisionEngine,
        response_engine: Optional[ResponseIntelligenceEngine] = None,
    ) -> None:
        self._decision_engine = decision_engine
        self._response_engine = response_engine or create_engine(decision_engine)
        self._last_learning_cycle = None
        self._learning_frequency = timedelta(days=7)  # Learn weekly

    def run_complete_cycle(self) -> Dict[str, Any]:
        """
        Run the complete feedback loop cycle.

        Returns comprehensive analysis and updates.
        """
        try:
            # Step 1: Load current data
            current_data = self._load_current_data()

            # Step 2: Track responses and outcomes
            response_analysis = self._track_responses(current_data)

            # Step 3: Update records with new information
            update_results = self._update_records(current_data, response_analysis)

            # Step 4: Learn from outcomes
            learning_results = self._learn_from_outcomes(current_data)

            # Step 5: Re-score based on learnings
            rescoring_results = self._rescore_based_on_learnings(learning_results)

            # Step 6: Generate follow-up actions
            follow_up_results = self._generate_follow_up_actions(current_data)

            # Update learning cycle timestamp
            self._last_learning_cycle = datetime.now()

            logger.info(
                "feedback_loop_cycle_completed",
                extra={
                    "applications_analyzed": len(current_data.get("applications", [])),
                    "jobs_analyzed": len(current_data.get("jobs", [])),
                    "learning_insights": len(learning_results.get("learning_insights", [])),
                    "follow_up_actions": len(follow_up_results.get("follow_up_actions", [])),
                },
            )

            return {
                "cycle_timestamp": self._last_learning_cycle.isoformat(),
                "data_loaded": current_data,
                "response_analysis": response_analysis,
                "update_results": update_results,
                "learning_results": learning_results,
                "rescoring_results": rescoring_results,
                "follow_up_results": follow_up_results,
                "cycle_summary": self._generate_cycle_summary(
                    response_analysis, learning_results, follow_up_results
                ),
            }

        except Exception as e:
            logger.error("feedback_loop_cycle_failed", extra={"error": str(e)})
            return {"error": f"Feedback loop cycle failed: {str(e)}"}

    def should_run_learning_cycle(self) -> bool:
        """Check if it's time to run a learning cycle."""
        if self._last_learning_cycle is None:
            return True

        return datetime.now() - self._last_learning_cycle >= self._learning_frequency

    def get_learning_status(self) -> Dict[str, Any]:
        """Get current learning status and recommendations."""
        return {
            "last_learning_cycle": self._last_learning_cycle.isoformat() if self._last_learning_cycle else None,
            "next_learning_cycle": (self._last_learning_cycle + self._learning_frequency).isoformat() if self._last_learning_cycle else None,
            "should_run_now": self.should_run_learning_cycle(),
            "learning_frequency_days": self._learning_frequency.days,
        }

    # ------------------------------------------------------------------
    # Private methods - implementing each step of the cycle
    # ------------------------------------------------------------------

    def _load_current_data(self) -> Dict[str, Any]:
        """Load current data from database and other sources."""
        try:
            if is_db_available():
                jobs = get_top_jobs(100)  # Get more jobs for analysis
                applications = get_applied_jobs()
                app_stats = get_application_stats()
                data_source = "database"
            else:
                jobs = []
                applications = []
                app_stats = {"total_applied": 0, "success_rate": 0}
                data_source = "fallback"

            return {
                "jobs": jobs,
                "applications": applications,
                "app_stats": app_stats,
                "data_source": data_source,
                "load_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("data_load_failed", extra={"error": str(e)})
            return {
                "jobs": [],
                "applications": [],
                "app_stats": {"total_applied": 0, "success_rate": 0},
                "data_source": "error",
                "error": str(e),
            }

    def _track_responses(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Track and analyze responses from employers."""
        applications = data.get("applications", [])

        if not applications:
            return {"error": "No application data to track"}

        # Use response intelligence engine
        response_analysis = self._response_engine.analyze_response_patterns(applications)

        # Add tracking metadata
        response_analysis["tracking_timestamp"] = datetime.now().isoformat()
        response_analysis["applications_tracked"] = len(applications)

        return response_analysis

    def _update_records(self, data: Dict[str, Any], response_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Update records with new information from response tracking."""
        applications = data.get("applications", [])
        updated_count = 0

        # Identify applications that need status updates
        for app in applications:
            # Check if application needs follow-up based on response analysis
            if self._should_update_application_status(app, response_analysis):
                # In a real implementation, this would update the database
                # For now, we'll just count the updates that would be made
                updated_count += 1

        return {
            "applications_reviewed": len(applications),
            "updates_needed": updated_count,
            "update_timestamp": datetime.now().isoformat(),
        }

    def _learn_from_outcomes(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Learn from application outcomes to improve future predictions."""
        jobs = data.get("jobs", [])
        applications = data.get("applications", [])

        if not applications or not jobs:
            return {"error": "Insufficient data for learning"}

        # Use response intelligence engine for learning
        learning_results = self._response_engine.learn_from_outcomes(applications, jobs)

        # Add learning metadata
        learning_results["learning_timestamp"] = datetime.now().isoformat()
        learning_results["data_points_analyzed"] = len(applications)

        return learning_results

    def _rescore_based_on_learnings(self, learning_results: Dict[str, Any]) -> Dict[str, Any]:
        """Update scoring model based on learning insights."""
        if "error" in learning_results:
            return {"error": "Cannot rescore without successful learning"}

        # Extract feedback data for scoring updates
        feedback_data = {
            "outcome_patterns": learning_results.get("success_factors", {}),
            "company_responses": {},  # Would be populated from actual response data
            "role_success_rates": {},  # Would be populated from actual role data
        }

        # Update scoring using response intelligence engine
        scoring_updates = self._response_engine.update_scoring_from_feedback(feedback_data)

        return {
            "scoring_updates": scoring_updates,
            "rescoring_timestamp": datetime.now().isoformat(),
        }

    def _generate_follow_up_actions(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate follow-up actions based on current state."""
        applications = data.get("applications", [])

        if not applications:
            return {"error": "No applications for follow-up"}

        # Use response intelligence engine for follow-up recommendations
        follow_up_results = self._response_engine.generate_follow_up_intelligence(applications)

        # Add follow-up metadata
        follow_up_results["follow_up_timestamp"] = datetime.now().isoformat()

        return follow_up_results

    def _should_update_application_status(self, application: Dict[str, Any], response_analysis: Dict[str, Any]) -> bool:
        """Determine if an application needs status update."""
        # Simple heuristic - in real implementation, this would be more sophisticated
        status = application.get("status", "unknown")
        applied_date = application.get("date_applied")

        if not applied_date:
            return False

        try:
            applied_dt = datetime.fromisoformat(applied_date.replace("Z", "+00:00"))
            days_since = (datetime.now() - applied_dt).days

            # Update needed if no response for 2+ weeks
            return status == "applied" and days_since >= 14

        except (ValueError, AttributeError):
            return False

    def _generate_cycle_summary(
        self,
        response_analysis: Dict[str, Any],
        learning_results: Dict[str, Any],
        follow_up_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate summary of the feedback loop cycle."""
        summary = {
            "cycle_success": True,
            "key_metrics": {},
            "recommendations": [],
            "next_steps": [],
        }

        # Extract key metrics
        if "success_rate" in response_analysis:
            summary["key_metrics"]["current_success_rate"] = response_analysis["success_rate"]

        if "learning_insights" in learning_results:
            summary["key_metrics"]["insights_generated"] = len(learning_results["learning_insights"])

        if "total_actions_needed" in follow_up_results:
            summary["key_metrics"]["follow_up_actions_needed"] = follow_up_results["total_actions_needed"]

        # Generate recommendations
        if response_analysis.get("success_rate", 0) < 10:
            summary["recommendations"].append("Consider improving application quality or targeting")

        if follow_up_results.get("total_actions_needed", 0) > 5:
            summary["recommendations"].append("Multiple follow-ups needed - consider prioritizing")

        # Next steps
        summary["next_steps"].append("Review and execute follow-up actions")
        summary["next_steps"].append("Monitor response patterns over next week")
        summary["next_steps"].append("Prepare for next learning cycle")

        return summary


# ---------------------------------------------------------------------------
# Convenience functions for external use
# ---------------------------------------------------------------------------

def create_feedback_loop_system(decision_engine: JobDecisionEngine) -> FeedbackLoopSystem:
    """Create and initialize feedback loop system."""
    return FeedbackLoopSystem(decision_engine)


def run_learning_cycle(feedback_system: FeedbackLoopSystem) -> Dict[str, Any]:
    """Convenience function to run a complete learning cycle."""
    return feedback_system.run_complete_cycle()


def should_run_learning_cycle(feedback_system: FeedbackLoopSystem) -> bool:
    """Check if learning cycle should run."""
    return feedback_system.should_run_learning_cycle()


# ---------------------------------------------------------------------------
# Integration functions for main pipeline
# ---------------------------------------------------------------------------

def integrate_feedback_loop_into_pipeline(
    decision_engine: JobDecisionEngine,
    run_frequency: str = "weekly",  # "daily", "weekly", "monthly"
) -> Dict[str, Any]:
    """
    Integrate feedback loop into the main job search pipeline.

    Returns configuration and status for integration.
    """
    feedback_system = create_feedback_loop_system(decision_engine)

    # Set learning frequency based on preference
    frequency_map = {
        "daily": timedelta(days=1),
        "weekly": timedelta(days=7),
        "monthly": timedelta(days=30),
    }

    if run_frequency in frequency_map:
        feedback_system._learning_frequency = frequency_map[run_frequency]

    return {
        "integration_status": "configured",
        "learning_frequency": run_frequency,
        "next_cycle_due": feedback_system.get_learning_status()["next_learning_cycle"],
        "integration_instructions": {
            "call_run_learning_cycle": "Execute this function to run the complete feedback loop",
            "check_should_run": "Use should_run_learning_cycle() to check if cycle is due",
            "get_status": "Use get_learning_status() to check current status",
        },
    }
