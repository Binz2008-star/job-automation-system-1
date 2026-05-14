"""Backward-compatibility shim for Rico AI server.

DEPRECATED: Use `src.api.app:app` as the single production entry point.

    uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

This file re-exports `app` from `src.api.app` so old startup commands
and Render configs that reference `src.rico_server:app` continue to work.
"""
from __future__ import annotations

# Re-export the canonical FastAPI application
from src.api.app import app  # noqa: F401
