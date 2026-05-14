"""src/repositories/search_context_repo.py

Active search context persistence for Rico Agent OS.

Maintains user's active search state across sessions:
- Current search query
- Applied filters (location, role, salary, etc.)
- Jobs seen in current session
- Jobs saved/skipped/applied
- Last search timestamp
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.db import get_db_connection, is_db_available

logger = logging.getLogger(__name__)
_UTC = timezone.utc


@dataclass
class SearchContext:
    """Active search context for a user."""
    canonical_user_id: str
    query: Optional[str] = None
    target_role: Optional[str] = None
    target_locations: List[str] = field(default_factory=list)
    salary_range: Optional[Dict[str, int]] = None  # {"min": 10000, "max": 50000}
    visa_status: Optional[str] = None
    remote_only: bool = False
    jobs_seen: Set[str] = field(default_factory=set)  # Job IDs seen in this session
    jobs_saved: Set[str] = field(default_factory=set)
    jobs_skipped: Set[str] = field(default_factory=set)
    jobs_applied: Set[str] = field(default_factory=set)
    last_search_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(_UTC))
    metadata: Dict[str, Any] = field(default_factory=dict)


class SearchContextRepository:
    """
    Repository for persisting active search context.

    Allows users to maintain search state across sessions:
    - Resume where they left off
    - Avoid showing already-seen jobs
    - Track applied/saved/skipped jobs
    """

    def __init__(self):
        self._cache: Dict[str, SearchContext] = {}

    def get(self, canonical_user_id: str) -> Optional[SearchContext]:
        """Get active search context for a user."""
        # Check cache first
        if canonical_user_id in self._cache:
            return self._cache[canonical_user_id]

        # Load from database
        if is_db_available():
            context = self._db_load(canonical_user_id)
            if context:
                self._cache[canonical_user_id] = context
                return context

        return None

    def save(self, context: SearchContext) -> bool:
        """Save search context to database and cache."""
        context.last_search_at = datetime.now(_UTC)
        self._cache[context.canonical_user_id] = context

        if is_db_available():
            return self._db_save(context)
        else:
            logger.info("search_context_saved user=%s (cache only, DB unavailable)", context.canonical_user_id)
            return True

    def update(
        self,
        canonical_user_id: str,
        *,
        query: Optional[str] = None,
        target_role: Optional[str] = None,
        target_locations: Optional[List[str]] = None,
        salary_range: Optional[Dict[str, int]] = None,
        visa_status: Optional[str] = None,
        remote_only: Optional[bool] = None,
    ) -> SearchContext:
        """
        Update search context with new search parameters.

        Creates new context if none exists.
        """
        context = self.get(canonical_user_id) or SearchContext(
            canonical_user_id=canonical_user_id,
        )

        if query is not None:
            context.query = query
        if target_role is not None:
            context.target_role = target_role
        if target_locations is not None:
            context.target_locations = target_locations
        if salary_range is not None:
            context.salary_range = salary_range
        if visa_status is not None:
            context.visa_status = visa_status
        if remote_only is not None:
            context.remote_only = remote_only

        self.save(context)
        return context

    def mark_job_seen(self, canonical_user_id: str, job_id: str) -> SearchContext:
        """Mark a job as seen by the user."""
        context = self.get(canonical_user_id) or SearchContext(
            canonical_user_id=canonical_user_id,
        )
        context.jobs_seen.add(job_id)
        self.save(context)
        return context

    def mark_job_saved(self, canonical_user_id: str, job_id: str) -> SearchContext:
        """Mark a job as saved by the user."""
        context = self.get(canonical_user_id) or SearchContext(
            canonical_user_id=canonical_user_id,
        )
        context.jobs_saved.add(job_id)
        self.save(context)
        return context

    def mark_job_skipped(self, canonical_user_id: str, job_id: str) -> SearchContext:
        """Mark a job as skipped by the user."""
        context = self.get(canonical_user_id) or SearchContext(
            canonical_user_id=canonical_user_id,
        )
        context.jobs_skipped.add(job_id)
        self.save(context)
        return context

    def mark_job_applied(self, canonical_user_id: str, job_id: str) -> SearchContext:
        """Mark a job as applied by the user."""
        context = self.get(canonical_user_id) or SearchContext(
            canonical_user_id=canonical_user_id,
        )
        context.jobs_applied.add(job_id)
        self.save(context)
        return context

    def get_unseen_jobs(
        self,
        canonical_user_id: str,
        all_jobs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Filter jobs to only show unseen jobs.

        Args:
            canonical_user_id: User ID
            all_jobs: List of all available jobs

        Returns:
            List of jobs not yet seen by the user
        """
        context = self.get(canonical_user_id)
        if not context:
            return all_jobs

        unseen = []
        for job in all_jobs:
            job_id = job.get("id") or job.get("_key")
            if job_id and job_id not in context.jobs_seen:
                unseen.append(job)

        return unseen

    def clear(self, canonical_user_id: str) -> bool:
        """Clear search context for a user."""
        if canonical_user_id in self._cache:
            del self._cache[canonical_user_id]

        if is_db_available():
            return self._db_delete(canonical_user_id)
        return True

    def _db_load(self, canonical_user_id: str) -> Optional[SearchContext]:
        """Load search context from database."""
        conn = get_db_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Check if table exists
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = 'search_context'
                    )
                    """
                )
                table_exists = cur.fetchone()[0]

                if not table_exists:
                    return None

                # Load context
                cur.execute(
                    """
                    SELECT query, target_role, target_locations, salary_range,
                           visa_status, remote_only, jobs_seen, jobs_saved,
                           jobs_skipped, jobs_applied, last_search_at, created_at, metadata
                    FROM search_context
                    WHERE canonical_user_id = %s
                    """,
                    (canonical_user_id,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                import json
                return SearchContext(
                    canonical_user_id=canonical_user_id,
                    query=row[0],
                    target_role=row[1],
                    target_locations=row[2] or [],
                    salary_range=row[3],
                    visa_status=row[4],
                    remote_only=row[5] or False,
                    jobs_seen=set(row[6] or []),
                    jobs_saved=set(row[7] or []),
                    jobs_skipped=set(row[8] or []),
                    jobs_applied=set(row[9] or []),
                    last_search_at=row[10],
                    created_at=row[11] or datetime.now(_UTC),
                    metadata=row[12] or {},
                )
        except Exception:
            logger.exception("search_context_db_load_failed user=%s", canonical_user_id)
            return None
        finally:
            conn.close()

    def _db_save(self, context: SearchContext) -> bool:
        """Save search context to database."""
        conn = get_db_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                # Check if table exists
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = 'search_context'
                    )
                    """
                )
                table_exists = cur.fetchone()[0]

                if not table_exists:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS search_context (
                            id SERIAL PRIMARY KEY,
                            canonical_user_id VARCHAR(255) UNIQUE NOT NULL,
                            query TEXT,
                            target_role VARCHAR(255),
                            target_locations TEXT[],
                            salary_range JSONB,
                            visa_status VARCHAR(100),
                            remote_only BOOLEAN DEFAULT FALSE,
                            jobs_seen TEXT[],
                            jobs_saved TEXT[],
                            jobs_skipped TEXT[],
                            jobs_applied TEXT[],
                            last_search_at TIMESTAMP WITH TIME ZONE,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            metadata JSONB,
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_search_context_user
                        ON search_context(canonical_user_id)
                        """
                    )
                    conn.commit()

                # Upsert context
                import json
                cur.execute(
                    """
                    INSERT INTO search_context
                    (canonical_user_id, query, target_role, target_locations, salary_range,
                     visa_status, remote_only, jobs_seen, jobs_saved, jobs_skipped,
                     jobs_applied, last_search_at, created_at, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (canonical_user_id)
                    DO UPDATE SET
                        query = EXCLUDED.query,
                        target_role = EXCLUDED.target_role,
                        target_locations = EXCLUDED.target_locations,
                        salary_range = EXCLUDED.salary_range,
                        visa_status = EXCLUDED.visa_status,
                        remote_only = EXCLUDED.remote_only,
                        jobs_seen = EXCLUDED.jobs_seen,
                        jobs_saved = EXCLUDED.jobs_saved,
                        jobs_skipped = EXCLUDED.jobs_skipped,
                        jobs_applied = EXCLUDED.jobs_applied,
                        last_search_at = EXCLUDED.last_search_at,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    """,
                    (
                        context.canonical_user_id,
                        context.query,
                        context.target_role,
                        context.target_locations,
                        json.dumps(context.salary_range) if context.salary_range else None,
                        context.visa_status,
                        context.remote_only,
                        list(context.jobs_seen),
                        list(context.jobs_saved),
                        list(context.jobs_skipped),
                        list(context.jobs_applied),
                        context.last_search_at,
                        context.created_at,
                        json.dumps(context.metadata) if context.metadata else None,
                    ),
                )
                conn.commit()

        except Exception:
            logger.exception("search_context_db_save_failed user=%s", context.canonical_user_id)
            return False
        finally:
            conn.close()

        return True

    def _db_delete(self, canonical_user_id: str) -> bool:
        """Delete search context from database."""
        conn = get_db_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM search_context WHERE canonical_user_id = %s",
                    (canonical_user_id,),
                )
                conn.commit()
        except Exception:
            logger.exception("search_context_db_delete_failed user=%s", canonical_user_id)
            return False
        finally:
            conn.close()

        return True


# Module-level singleton
_search_context_repo = SearchContextRepository()


def get_search_context(canonical_user_id: str) -> Optional[SearchContext]:
    """Convenience function to get search context."""
    return _search_context_repo.get(canonical_user_id)


def save_search_context(context: SearchContext) -> bool:
    """Convenience function to save search context."""
    return _search_context_repo.save(context)


def update_search_context(
    canonical_user_id: str,
    **kwargs,
) -> SearchContext:
    """Convenience function to update search context."""
    return _search_context_repo.update(canonical_user_id, **kwargs)
