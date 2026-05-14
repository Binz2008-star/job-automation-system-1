#!/usr/bin/env python3
"""Test Jotform webhook security fix for production environment."""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.rico_jotform_webhook import (
    _is_production,
    _validate_webhook_secret,
    handle_jotform_submission,
)


class TestJotformWebhookSecurity:
    """Test security fixes for Jotform webhook."""

    def test_is_production_development_default(self):
        """Test that default environment is development."""
        with patch.dict(os.environ, {}, clear=True):
            assert not _is_production()

    def test_is_production_development_explicit(self):
        """Test that explicit development environment is detected."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            assert not _is_production()

    def test_is_production_development_mixed_case(self):
        """Test that mixed case development environment is detected."""
        with patch.dict(os.environ, {"ENVIRONMENT": "DEVELOPMENT"}):
            assert not _is_production()

    def test_is_production_true(self):
        """Test that production environment is detected."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            assert _is_production()

    def test_is_production_mixed_case(self):
        """Test that mixed case production environment is detected."""
        with patch.dict(os.environ, {"ENVIRONMENT": "PRODUCTION"}):
            assert _is_production()

    def test_validate_webhook_secret_development_missing(self):
        """Test that missing webhook secret is allowed in development."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            assert _validate_webhook_secret()

    def test_validate_webhook_secret_development_present(self):
        """Test that present webhook secret works in development."""
        with patch.dict(os.environ, {
            "ENVIRONMENT": "development",
            "JOTFORM_WEBHOOK_SECRET": "test_secret"
        }):
            assert _validate_webhook_secret()

    def test_validate_webhook_secret_production_missing(self):
        """Test that missing webhook secret fails in production."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            assert not _validate_webhook_secret()

    def test_validate_webhook_secret_production_present(self):
        """Test that present webhook secret works in production."""
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "JOTFORM_WEBHOOK_SECRET": "test_secret"
        }):
            assert _validate_webhook_secret()

    def test_handle_jotform_submission_development_no_secret(self):
        """Test that webhook works in development without secret."""
        payload = {
            "formID": "test_form",
            "submissionID": "test_submission",
            "email": "test@example.com"
        }

        # Mock the database operations to avoid DB connection issues
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True), \
             patch('src.rico_jotform_webhook.RicoDB') as mock_db:

            # Mock successful database operations
            mock_db_instance = MagicMock()
            mock_db.return_value = mock_db_instance
            mock_db_instance.upsert_user.return_value = {"id": 1}
            mock_db_instance.upsert_settings.return_value = {"id": 1}
            mock_db_instance.mark_onboarding_complete.return_value = True

            result = handle_jotform_submission(payload)
            assert result["status"] == "ok"

    def test_handle_jotform_submission_production_missing_secret(self):
        """Test that webhook fails in production without secret."""
        payload = {
            "formID": "test_form",
            "submissionID": "test_submission",
            "email": "test@example.com"
        }

        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            result = handle_jotform_submission(payload)
            assert result["status"] == "rejected"
            assert result["reason"] == "missing_webhook_secret"

    def test_handle_jotform_submission_production_with_secret(self):
        """Test that webhook works in production with secret."""
        payload = {
            "formID": "test_form",
            "submissionID": "test_submission",
            "email": "test@example.com"
        }

        # Mock the database operations to avoid DB connection issues
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "JOTFORM_WEBHOOK_SECRET": "test_secret",
            "JOTFORM_FORM_ID": "test_form"  # Set form ID to pass validation
        }), patch('src.rico_jotform_webhook.RicoDB') as mock_db:

            # Mock successful database operations
            mock_db_instance = MagicMock()
            mock_db.return_value = mock_db_instance
            mock_db_instance.upsert_user.return_value = {"id": 1}
            mock_db_instance.upsert_settings.return_value = {"id": 1}
            mock_db_instance.mark_onboarding_complete.return_value = True

            result = handle_jotform_submission(payload)
            # Should get past secret validation and form ID validation
            assert result["status"] == "ok"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
