"""
src/repositories/jobs_repo.py
All data access for the jobs table.
Services call these functions — never reach into the DB directly.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.db import get_db_connection

logger = logging.getLogger(__name__)


def list_from_db(
    offset: int,
    limit: int,
    min_score: int,
    source: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Paginated job query from Postgres.
    Returns None on any DB error so callers can fall back to JSON.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        filters = ["score >= %s"]
        params: list = [min_score]

        if source:
            filters.append("source = %s")
            params.append(source)

        where = " AND ".join(filters)

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM jobs WHERE {where}", params)  # nosec B608
            total = cur.fetchone()[0]

            query = (
                "SELECT id, title, company, location, link, score,"  # nosec B608
                " match_reason, source, date_found, seen"
                " FROM jobs WHERE " + where +
                " ORDER BY score DESC, date_found DESC LIMIT %s OFFSET %s"
            )
            cur.execute(query, params + [limit, offset])
            rows = cur.fetchall()

        jobs = [_row_to_job(r) for r in rows]
        return {
            "jobs": jobs,
            "total": total,
            "page": offset // limit + 1,
            "limit": limit,
            "pages": max(1, -(-total // limit)),
        }
    except Exception:
        logger.exception("jobs_repo_list_failed")
        return None
    finally:
        conn.close()


def get_by_db_id(db_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single job by its integer primary key."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, company, location, link, score,
                          match_reason, source, date_found, seen
                   FROM jobs WHERE id = %s""",
                (db_id,),
            )
            row = cur.fetchone()
        return _row_to_job(row) if row else None
    except Exception:
        logger.exception("jobs_repo_get_failed id=%s", db_id)
        return None
    finally:
        conn.close()


def _row_to_job(row: tuple) -> Dict[str, Any]:
    return {
        "id": str(row[0]),
        "title": row[1] or "",
        "company": row[2] or "",
        "location": row[3] or "",
        "link": row[4] or "",
        "score": row[5] or 0,
        "match_reason": row[6] or "",
        "source": row[7] or "",
        "date_found": row[8].isoformat() if row[8] else None,
        "seen": bool(row[9]),
    }
