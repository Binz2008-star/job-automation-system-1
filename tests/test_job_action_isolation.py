"""Tests for API job action isolation - ensure server-side job validation."""
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.deps import get_current_user


@pytest.fixture
def client_with_auth():
    """Create a test client with authentication override."""
    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user", "email": "test@example.com"}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestServerSideJobValidation:
    """Test that job actions use server-side job validation, not client-supplied objects."""

    @pytest.fixture
    def mock_jobs_repo(self, monkeypatch):
        """Mock jobs_repo.get_job to return test job."""
        from src.services.jobs_service import get_job

        def mock_get_job(job_id: str):
            if job_id == "123":
                return {
                    "id": "123",
                    "title": "Test Job",
                    "company": "Test Co",
                    "link": "https://example.com/job",
                }
            return None

        monkeypatch.setattr("src.services.jobs_service.get_job", mock_get_job)

    def test_skip_job_returns_404_when_job_not_found(self, client_with_auth):
        """skip endpoint should return 404 when job_id does not exist."""
        response = client_with_auth.post(
            "/api/v1/jobs/999/skip",
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_save_job_returns_404_when_job_not_found(self, client_with_auth):
        """save endpoint should return 404 when job_id does not exist."""
        response = client_with_auth.post(
            "/api/v1/jobs/999/save",
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_block_job_returns_404_when_job_not_found(self, client_with_auth):
        """block endpoint should return 404 when job_id does not exist."""
        response = client_with_auth.post(
            "/api/v1/jobs/999/block",
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestApplyEndpointJobValidation:
    """Test that apply endpoint validates client-supplied job against server-side job_id."""

    @pytest.fixture
    def mock_jobs_repo(self, monkeypatch):
        """Mock jobs_repo.get_job to return test job."""
        def mock_get_job(job_id: str):
            if job_id == "123":
                return {
                    "id": "123",
                    "title": "Test Job",
                    "company": "Test Co",
                    "link": "https://example.com/job",
                }
            return None

        monkeypatch.setattr("src.api.routers.jobs.get_job", mock_get_job)

    def test_apply_returns_404_when_job_not_found(self, client_with_auth):
        """apply endpoint should return 404 when job_id does not exist."""
        response = client_with_auth.post(
            "/api/v1/jobs/999/apply",
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_apply_rejects_mismatched_job_id(self, client_with_auth, mock_jobs_repo):
        """apply endpoint should reject when client job_id doesn't match URL job_id."""
        response = client_with_auth.post(
            "/api/v1/jobs/123/apply",
            json={"job": {"id": "456", "title": "Different Job"}},  # Mismatch
        )

        assert response.status_code == 422
        assert "does not match job_id in URL" in response.json()["detail"]
