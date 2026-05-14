"""Tests for user isolation in application tracking."""
import os
import pytest
from src.applications import (
    mark_applied,
    is_applied,
    is_applied_batch,
    update_application_status,
    get_applied_jobs,
    get_application_stats,
    filter_unapplied_jobs,
    _require_user_id_for_production,
    get_job_id,
    APPLIED_JOBS_FILE,
    load_applied_jobs,
    save_applied_jobs,
)


@pytest.fixture(autouse=True)
def cleanup_applied_jobs():
    """Clean up applied_jobs.json before and after each test."""
    # Save existing data
    existing_data = load_applied_jobs()

    # Clear the file for the test
    save_applied_jobs([])

    yield

    # Restore original data
    save_applied_jobs(existing_data)


class TestProductionModeEnforcement:
    """Test that production mode requires user_id for sensitive operations."""

    def test_production_mode_rejects_mark_applied_without_user_id(self):
        """mark_applied raises RuntimeError in production without user_id."""
        # Save original env
        original_env = os.getenv("APP_ENV")
        try:
            os.environ["APP_ENV"] = "production"
            job = {"title": "Test Job", "company": "Test Co", "link": "https://example.com/job1"}
            with pytest.raises(RuntimeError) as exc_info:
                mark_applied(job)
            assert "mark_applied requires user_id in production" in str(exc_info.value)
        finally:
            if original_env is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = original_env

    def test_production_mode_rejects_is_applied_without_user_id(self):
        """is_applied raises RuntimeError in production without user_id."""
        original_env = os.getenv("APP_ENV")
        try:
            os.environ["APP_ENV"] = "production"
            job = {"title": "Test Job", "company": "Test Co", "link": "https://example.com/job1"}
            with pytest.raises(RuntimeError) as exc_info:
                is_applied(job)
            assert "is_applied requires user_id in production" in str(exc_info.value)
        finally:
            if original_env is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = original_env

    def test_production_mode_rejects_update_application_status_without_user_id(self):
        """update_application_status raises RuntimeError in production without user_id."""
        original_env = os.getenv("APP_ENV")
        try:
            os.environ["APP_ENV"] = "production"
            job = {"title": "Test Job", "company": "Test Co", "link": "https://example.com/job1"}
            with pytest.raises(RuntimeError) as exc_info:
                update_application_status(job, "interview")
            assert "update_application_status requires user_id in production" in str(exc_info.value)
        finally:
            if original_env is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = original_env

    def test_development_mode_allows_operations_without_user_id(self):
        """Development mode allows operations without user_id (with warning)."""
        original_env = os.getenv("APP_ENV")
        try:
            os.environ["APP_ENV"] = "development"
            job = {"title": "Test Job", "company": "Test Co", "link": "https://example.com/job1"}
            # Should not raise, may log warning
            mark_applied(job)
            is_applied(job)
            update_application_status(job, "applied")
        finally:
            if original_env is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = original_env


class TestUserIdIsolation:
    """Test that user_id properly isolates application data."""

    def test_mark_applied_allows_same_job_for_different_users(self):
        """Same job can be marked as applied by different users."""
        job = {"title": "Test Job", "company": "Test Co", "link": "https://example.com/job1"}

        # Mark for user1
        result1 = mark_applied(job, user_id="user1")
        assert result1 is True

        # Mark for user2 - should succeed (different user)
        result2 = mark_applied(job, user_id="user2")
        assert result2 is True

        # Both users should see the job as applied
        assert is_applied(job, user_id="user1") is True
        assert is_applied(job, user_id="user2") is True

    def test_is_applied_only_sees_current_user_jobs(self):
        """is_applied only returns True for jobs applied by the current user."""
        job1 = {"title": "Job 1", "company": "Co 1", "link": "https://example.com/job1"}
        job2 = {"title": "Job 2", "company": "Co 2", "link": "https://example.com/job2"}

        # Mark job1 for user1
        mark_applied(job1, user_id="user1")

        # Mark job2 for user2
        mark_applied(job2, user_id="user2")

        # user1 should only see job1 as applied
        assert is_applied(job1, user_id="user1") is True
        assert is_applied(job2, user_id="user1") is False

        # user2 should only see job2 as applied
        assert is_applied(job1, user_id="user2") is False
        assert is_applied(job2, user_id="user2") is True

    def test_is_applied_batch_filters_by_user_id(self):
        """is_applied_batch returns results filtered by user_id."""
        job1 = {"title": "Job 1", "company": "Co 1", "link": "https://example.com/job1"}
        job2 = {"title": "Job 2", "company": "Co 2", "link": "https://example.com/job2"}

        # Mark job1 for user1
        mark_applied(job1, user_id="user1")

        # Mark job2 for user2
        mark_applied(job2, user_id="user2")

        # user1 batch check - should see job1 as applied, job2 as not
        result1 = is_applied_batch([job1, job2], user_id="user1")
        job1_id = get_job_id(job1)
        job2_id = get_job_id(job2)
        assert result1.get(job1_id) is True
        assert result1.get(job2_id) is False

        # user2 batch check - should see job2 as applied, job1 as not
        result2 = is_applied_batch([job1, job2], user_id="user2")
        assert result2.get(job1_id) is False
        assert result2.get(job2_id) is True

    def test_update_application_status_only_updates_current_user_record(self):
        """update_application_status only updates the current user's record."""
        job = {"title": "Test Job", "company": "Test Co", "link": "https://example.com/job1"}

        # Mark as applied for both users
        mark_applied(job, user_id="user1")
        mark_applied(job, user_id="user2")

        # Update status for user1
        result = update_application_status(job, "interview", user_id="user1")
        assert result is True

        # user1 should see interview status
        jobs1 = get_applied_jobs(user_id="user1")
        assert len(jobs1) == 1
        assert jobs1[0]["status"] == "interview"

        # user2 should still have applied status
        jobs2 = get_applied_jobs(user_id="user2")
        assert len(jobs2) == 1
        assert jobs2[0]["status"] == "applied"

    def test_get_applied_jobs_filters_by_user_id(self):
        """get_applied_jobs returns only jobs for the specified user."""
        job1 = {"title": "Job 1", "company": "Co 1", "link": "https://example.com/job1"}
        job2 = {"title": "Job 2", "company": "Co 2", "link": "https://example.com/job2"}

        # Mark job1 for user1
        mark_applied(job1, user_id="user1")

        # Mark job2 for user2
        mark_applied(job2, user_id="user2")

        # user1 should only get job1
        jobs1 = get_applied_jobs(user_id="user1")
        assert len(jobs1) == 1
        assert jobs1[0]["title"] == "Job 1"

        # user2 should only get job2
        jobs2 = get_applied_jobs(user_id="user2")
        assert len(jobs2) == 1
        assert jobs2[0]["title"] == "Job 2"

    def test_get_application_stats_filters_by_user_id(self):
        """get_application_stats returns stats only for the specified user."""
        job1 = {"title": "Job 1", "company": "Co 1", "link": "https://example.com/job1"}
        job2 = {"title": "Job 2", "company": "Co 2", "link": "https://example.com/job2"}

        # Mark job1 for user1
        mark_applied(job1, user_id="user1")

        # Mark job2 for user2 with interview status
        mark_applied(job2, status="interview", user_id="user2")

        # user1 stats
        stats1 = get_application_stats(user_id="user1")
        assert stats1["total_applied"] == 1
        assert stats1["interviews_scheduled"] == 0

        # user2 stats
        stats2 = get_application_stats(user_id="user2")
        assert stats2["total_applied"] == 1
        assert stats2["interviews_scheduled"] == 1

    def test_filter_unapplied_jobs_filters_by_user_id(self):
        """filter_unapplied_jobs filters by user_id."""
        job1 = {"title": "Job 1", "company": "Co 1", "link": "https://example.com/job1"}
        job2 = {"title": "Job 2", "company": "Co 2", "link": "https://example.com/job2"}

        # Mark job1 for user1
        mark_applied(job1, user_id="user1")

        # Both jobs for user2
        pairs = [(job1, 75), (job2, 80)]

        # user2 should see both as unapplied (job1 was applied by user1, not user2)
        unapplied = filter_unapplied_jobs(pairs, user_id="user2")
        assert len(unapplied) == 2

        # user1 should see only job2 as unapplied
        unapplied1 = filter_unapplied_jobs(pairs, user_id="user1")
        assert len(unapplied1) == 1
        assert unapplied1[0][0]["title"] == "Job 2"
