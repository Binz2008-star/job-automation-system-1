"""src/agent/workflow

Enhanced agent workflow layer with permission gates.

Classifies intent, checks permissions before high-impact actions,
routes to tools, logs learning signals, and returns structured responses.
"""
from __future__ import annotations

from src.agent.workflow.coordinator import WorkflowCoordinator, execute_workflow

__all__ = ["WorkflowCoordinator", "execute_workflow"]
