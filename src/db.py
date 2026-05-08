"""
Neon Postgres Database Integration
Provides database functions with JSON fallback for reliability.
"""

import os
import psycopg2
from psycopg2 import sql, OperationalError
from dotenv import load_dotenv
from datetime import datetime
from typing import List, Dict, Any, Optional
import json

load_dotenv()

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")
DB_ENABLED = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql://"))

# Fallback to JSON if DB fails
JSON_FALLBACK = True

def get_db_connection():
    """Get database connection with error handling."""
    if not DB_ENABLED:
        return None

    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        return conn
    except OperationalError as e:
        print(f"⚠️ Database connection failed: {e}")
        print("🔄 Falling back to JSON storage")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected database error: {e}")
        return None


def init_db():
    """Initialize database tables if they don't exist."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            # Create jobs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT,
                    location TEXT,
                    link TEXT UNIQUE NOT NULL,
                    description TEXT,
                    score INTEGER DEFAULT 0,
                    match_reason TEXT,
                    source TEXT DEFAULT 'jobspy',
                    date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    seen BOOLEAN DEFAULT FALSE
                )
            """)

            # Create applications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id SERIAL PRIMARY KEY,
                    job_link TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'saved',
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    follow_up_date TIMESTAMP,
                    FOREIGN KEY (job_link) REFERENCES jobs(link) ON DELETE CASCADE
                )
            """)

            # Create auto_apply_attempts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_apply_attempts (
                    id SERIAL PRIMARY KEY,
                    job_id VARCHAR(500) UNIQUE NOT NULL,
                    title VARCHAR(500),
                    company VARCHAR(500),
                    status VARCHAR(50) NOT NULL,
                    error TEXT,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_link ON jobs(link)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_date_found ON jobs(date_found DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_applications_job_link ON applications(job_link)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auto_apply_job_id ON auto_apply_attempts(job_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auto_apply_status ON auto_apply_attempts(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auto_apply_timestamp ON auto_apply_attempts(timestamp DESC)")

        print("✅ Database initialized successfully")
        return True

    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    finally:
        if conn:
            conn.close()


def save_job(job: Dict[str, Any], score: int) -> bool:
    """Save a job to the database."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO jobs (title, company, location, link, description, score, match_reason, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (link) DO UPDATE SET
                    score = EXCLUDED.score,
                    match_reason = EXCLUDED.match_reason,
                    date_found = CURRENT_TIMESTAMP
            """, (
                job.get('title', '') or '',
                job.get('company', '') or '',
                job.get('location', '') or '',
                job.get('link', '') or '',
                str(job.get('description', ''))[:1000] if job.get('description') else '',  # Limit description length
                score,
                job.get('profile_explanation', '') or '',
                job.get('source', 'jobspy') or 'jobspy'
            ))

        return True

    except Exception as e:
        print(f"❌ Failed to save job: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_seen_links(days_back: int = 90, limit: int = 8000) -> List[str]:
    """
    Get seen job links from the past `days_back` days.
    Bounded by `limit` to prevent loading unbounded rows into memory.
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT link FROM jobs
                WHERE date_found > NOW() - (%s * INTERVAL '1 day')
                ORDER BY date_found DESC
                LIMIT %s
                """,
                (days_back, limit),
            )
            return [row[0] for row in cursor.fetchall()]

    except Exception as e:
        print(f"❌ Failed to get seen links: {e}")
        return []
    finally:
        if conn:
            conn.close()


def mark_applied(job_link: str, notes: str = None) -> bool:
    """Mark a job as applied."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            # Update job as seen
            cursor.execute("UPDATE jobs SET seen = TRUE WHERE link = %s", (job_link,))

            # Add or update application record
            cursor.execute("""
                INSERT INTO applications (job_link, status, notes)
                VALUES (%s, 'applied', %s)
                ON CONFLICT (job_link) DO UPDATE SET
                    status = EXCLUDED.status,
                    applied_at = CURRENT_TIMESTAMP,
                    notes = COALESCE(applications.notes, '') || ' | ' || COALESCE(%s, '')
            """, (job_link, notes or '', notes or ''))

        return True

    except Exception as e:
        print(f"❌ Failed to mark job as applied: {e}")
        return False
    finally:
        if conn:
            conn.close()


def update_application_status(job_link: str, status: str, notes: str = None) -> bool:
    """Update application status."""
    conn = get_db_connection()
    if not conn:
        return False

    valid_statuses = ['saved', 'opened', 'applied', 'interview', 'rejected', 'offer']
    if status not in valid_statuses:
        print(f"❌ Invalid status: {status}")
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE applications
                SET status = %s,
                    notes = COALESCE(notes, '') || CASE WHEN %s IS NOT NULL THEN ' | ' || %s ELSE '' END,
                    follow_up_date = CASE WHEN %s = 'interview' THEN CURRENT_TIMESTAMP ELSE follow_up_date END
                WHERE job_link = %s
            """, (status, notes, notes, status, job_link))
            # rowcount MUST be read inside the with-block; psycopg2 resets it on cursor close
            affected = cursor.rowcount

        return affected > 0

    except Exception as e:
        print(f"❌ Failed to update application status: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_top_jobs(limit: int = 10) -> List[Dict[str, Any]]:
    """Get top scored jobs."""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT title, company, location, link, score, match_reason, date_found
                FROM jobs
                WHERE score >= 40
                ORDER BY score DESC, date_found DESC
                LIMIT %s
            """, (limit,))

            jobs = []
            for row in cursor.fetchall():
                jobs.append({
                    'title': row[0],
                    'company': row[1],
                    'location': row[2],
                    'link': row[3],
                    'score': row[4],
                    'match_reason': row[5],
                    'date_found': row[6].isoformat() if row[6] else None
                })

            return jobs

    except Exception as e:
        print(f"❌ Failed to get top jobs: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_application_stats() -> Dict[str, Any]:
    """Get application statistics."""
    conn = get_db_connection()
    if not conn:
        return {}

    try:
        with conn.cursor() as cursor:
            # Get status counts
            cursor.execute("""
                SELECT status, COUNT(*)
                FROM applications
                GROUP BY status
            """)
            status_counts = dict(cursor.fetchall())

            # Calculate success rate
            total_applied = status_counts.get('applied', 0) + status_counts.get('interview', 0)
            interviews = status_counts.get('interview', 0)
            success_rate = (interviews / total_applied * 100) if total_applied > 0 else 0

            return {
                'total_applied': total_applied,
                'status_breakdown': status_counts,
                'interviews_scheduled': interviews,
                'rejections': status_counts.get('rejected', 0),
                'pending': status_counts.get('applied', 0),
                'success_rate': round(success_rate, 1)
            }

    except Exception as e:
        print(f"❌ Failed to get application stats: {e}")
        return {}
    finally:
        if conn:
            conn.close()


def is_db_available() -> bool:
    """Check if database is available."""
    return DB_ENABLED


def main():
    """Test database functions."""
    print("🧪 Testing Database Integration")

    if not DB_ENABLED:
        print("❌ DATABASE_URL not set or invalid")
        return

    # Test initialization
    print("\n1. Testing init_db():")
    if init_db():
        print("✅ Database initialized")
    else:
        print("❌ Database initialization failed")
        return

    # Test saving a job
    print("\n2. Testing save_job():")
    sample_job = {
        'title': 'Test Executive Assistant',
        'company': 'Test Company',
        'location': 'Dubai, UAE',
        'link': 'https://example.com/test',
        'description': 'Test job description',
        'profile_explanation': 'Test match reason'
    }

    if save_job(sample_job, 75):
        print("✅ Job saved successfully")
    else:
        print("❌ Failed to save job")

    # Test getting seen links
    print("\n3. Testing get_seen_links():")
    seen_links = get_seen_links()
    print(f"Seen links: {len(seen_links)}")

    # Test marking as applied
    print("\n4. Testing mark_applied():")
    if mark_applied('https://example.com/test', 'Test notes'):
        print("✅ Job marked as applied")
    else:
        print("❌ Failed to mark job as applied")

    # Test getting top jobs
    print("\n5. Testing get_top_jobs():")
    top_jobs = get_top_jobs(5)
    print(f"Top jobs: {len(top_jobs)}")

    # Test application stats
    print("\n6. Testing get_application_stats():")
    stats = get_application_stats()
    print(f"Stats: {stats}")


if __name__ == "__main__":
    main()
