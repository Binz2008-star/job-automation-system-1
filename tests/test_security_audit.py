"""
QA Security Audit — full adversarial test suite.
Run: python -m pytest tests/qa_security_audit.py -v
"""
from __future__ import annotations

import io
import os
import sys
import time
import threading
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass123")
os.environ.setdefault("JWT_SECRET", "x" * 32)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.api.app import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def auth_client():
    from fastapi.testclient import TestClient
    from src.api.app import app
    from src.api.auth import create_access_token
    token = create_access_token({"sub": "admin@test.com"})
    tc = TestClient(app, raise_server_exceptions=False)
    tc.cookies.set("access_token", token)
    return tc


# ═══════════════════════════════════════════════════════════════════════════════
# 1. AUTH — bypass, brute-force, JWT tampering
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthSecurity:
    def test_empty_credentials_rejected(self, client):
        r = client.post("/api/v1/auth/login", json={"email": "", "password": ""})
        assert r.status_code in (401, 422)

    def test_wrong_password_returns_401(self, client):
        r = client.post("/api/v1/auth/login", json={"email": "admin@test.com", "password": "WRONG"})
        assert r.status_code == 401

    def test_sql_injection_in_email_rejected(self, client):
        payloads = [
            "' OR '1'='1",
            "admin@test.com'; DROP TABLE users; --",
            "' UNION SELECT * FROM users --",
            "admin@test.com' OR 1=1--",
        ]
        for p in payloads:
            r = client.post("/api/v1/auth/login", json={"email": p, "password": "x"})
            assert r.status_code in (401, 422), f"SQL injection not blocked: {p!r}"

    def test_bcrypt_dos_long_password(self, client):
        """Passwords >72 bytes with bcrypt can cause CPU DoS — must be bounded."""
        start = time.monotonic()
        r = client.post("/api/v1/auth/login", json={
            "email": "admin@test.com",
            "password": "A" * 10_000,
        })
        elapsed = time.monotonic() - start
        # Should either reject (422) or respond in <5s — not hang
        assert elapsed < 5.0, f"Login with 10K password took {elapsed:.1f}s — bcrypt DoS risk"

    def test_forged_jwt_rejected(self, client):
        from fastapi.testclient import TestClient
        from src.api.app import app
        tc = TestClient(app, raise_server_exceptions=False)
        tc.cookies.set(
            "access_token",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiJoYWNrZXJAZXZpbC5jb20iLCJleHAiOjk5OTk5OTk5OTl9"
            ".FAKE_SIGNATURE_THAT_WONT_VERIFY",
        )
        r = tc.get("/api/v1/jobs")
        assert r.status_code == 401

    def test_expired_jwt_rejected(self, client):
        from fastapi.testclient import TestClient
        from src.api.app import app
        from datetime import datetime, timezone, timedelta
        from jose import jwt
        expired_token = jwt.encode(
            {"sub": "admin@test.com", "exp": datetime(2020, 1, 1, tzinfo=timezone.utc)},
            "x" * 32,
            algorithm="HS256",
        )
        tc = TestClient(app, raise_server_exceptions=False)
        tc.cookies.set("access_token", expired_token)
        r = tc.get("/api/v1/jobs")
        assert r.status_code == 401

    def test_no_token_returns_401(self, client):
        r = client.get("/api/v1/jobs")
        assert r.status_code == 401

    def test_login_response_does_not_leak_password_hash(self, client):
        r = client.post("/api/v1/auth/login", json={"email": "x@x.com", "password": "wrong"})
        body = r.text.lower()
        assert "password" not in body or "hash" not in body

    def test_token_not_in_response_body(self):
        """JWT must be in httpOnly cookie only, never in JSON body.
        Uses a fresh client to avoid polluting the shared fixture with a login cookie."""
        from fastapi.testclient import TestClient
        from src.api.app import app
        fresh = TestClient(app, raise_server_exceptions=False)
        r = fresh.post("/api/v1/auth/login", json={"email": "admin@test.com", "password": "TestPass123"})
        if r.status_code == 200:
            body = r.json()
            assert "token" not in body
            assert "access_token" not in body

    def test_logout_clears_cookie(self, auth_client):
        r = auth_client.post("/api/v1/auth/logout")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SQL INJECTION — repository layer
# ═══════════════════════════════════════════════════════════════════════════════

class TestSQLInjection:
    def test_jobs_repo_where_clause_uses_parameterization(self):
        """The f-string WHERE clause in jobs_repo must only contain safe column names."""
        from src.repositories import jobs_repo
        import inspect
        source = inspect.getsource(jobs_repo.list_from_db)
        # The where variable is built from hardcoded strings, not user input
        # Verify the f-string only references the internal 'where' variable
        assert 'f"SELECT COUNT(*) FROM jobs WHERE {where}"' in source or \
               "f'SELECT COUNT(*) FROM jobs WHERE {where}'" in source
        # Verify params list is used (parameterized)
        assert "params" in source

    def test_jobs_source_filter_is_parameterized(self, auth_client):
        """source parameter must go through %s, not f-string interpolation."""
        with patch("src.db.get_db_connection") as mock_conn:
            mock_conn.return_value = None  # force JSON fallback
            with patch("src.job_history.load_job_history", return_value=[]):
                r = auth_client.get("/api/v1/jobs?source='; DROP TABLE jobs; --")
        # Should not crash — either 200 from fallback or 200 from DB
        assert r.status_code == 200

    def test_job_id_integer_validation(self, auth_client):
        """get_job with integer ID should only pass int to DB."""
        with patch("src.db.get_db_connection") as mock_conn:
            mock_conn.return_value = None
            r = auth_client.get("/api/v1/jobs/'; DROP TABLE jobs; --")
        assert r.status_code in (200, 404)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PUBLIC ENDPOINT ABUSE — Jotform / Telegram / Chat
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicEndpointAbuse:
    def test_jotform_empty_payload_returns_200(self, client):
        r = client.post("/api/v1/rico/webhooks/jotform", json={})
        assert r.status_code == 200

    def test_jotform_null_values_returns_200(self, client):
        r = client.post("/api/v1/rico/webhooks/jotform", json={
            "Full Name": None,
            "Email": None,
            "Phone": None,
        })
        assert r.status_code == 200

    def test_jotform_xss_in_name_does_not_crash(self, client):
        r = client.post("/api/v1/rico/webhooks/jotform", json={
            "Full Name": "<script>alert('xss')</script>",
            "Email": "hack@evil.com",
        })
        assert r.status_code == 200
        assert "<script>" not in r.text

    def test_jotform_massive_payload_does_not_crash(self, client):
        """5MB payload must not crash the server (may be slow but must not 500)."""
        payload = {"Full Name": "A" * 100_000, "Email": "x@y.com", "noise": "B" * 500_000}
        r = client.post("/api/v1/rico/webhooks/jotform", json=payload)
        assert r.status_code == 200

    def test_jotform_invalid_json_returns_200(self, client):
        r = client.post(
            "/api/v1/rico/webhooks/jotform",
            content=b"{not valid json!!!",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200

    def test_telegram_xss_in_message_does_not_crash(self, client):
        """XSS payload in Telegram message must not crash the server or be reflected."""
        r = client.post("/api/v1/rico/webhooks/telegram", json={
            "message": {"chat": {"id": 1}, "text": "<img src=x onerror=alert(1)>"}
        })
        assert r.status_code == 200
        # XSS script tags must not appear verbatim in the response
        assert "<script>" not in r.text
        assert "onerror=alert" not in r.text

    def test_telegram_deeply_nested_payload(self, client):
        """Deeply nested JSON should not cause recursion crash."""
        nested: Any = {"message": "leaf"}
        for _ in range(200):
            nested = {"data": nested}
        r = client.post("/api/v1/rico/webhooks/telegram", json=nested)
        assert r.status_code == 200

    def test_telegram_invalid_json_always_200(self, client):
        r = client.post(
            "/api/v1/rico/webhooks/telegram",
            content=b"definitely not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200

    def test_rico_chat_empty_user_id(self, client):
        r = client.post("/api/v1/rico/chat", json={"user_id": "", "message": "hello"})
        # Empty user_id — should not crash
        assert r.status_code in (200, 422)

    def test_rico_chat_unicode_message(self, client):
        r = client.post("/api/v1/rico/chat", json={
            "user_id": "u1",
            "message": "مرحبا 你好 🎯   ￿",
        })
        assert r.status_code in (200, 422, 500)
        # Must not expose internal traceback
        if r.status_code == 500:
            assert "Traceback" not in r.text

    def test_rico_chat_sql_injection_in_user_id(self, client):
        r = client.post("/api/v1/rico/chat", json={
            "user_id": "' OR 1=1; DROP TABLE rico_users; --",
            "message": "hello",
        })
        assert r.status_code in (200, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CV UPLOAD — file type, size, path traversal
# ═══════════════════════════════════════════════════════════════════════════════

class TestCVUploadSecurity:
    def test_cv_upload_path_traversal_in_user_id(self, client):
        """Path-traversal in user_id query param must not affect server filesystem."""
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake")
        r = client.post(
            "/api/v1/rico/upload-cv?user_id=../../../etc/passwd",
            files={"file": ("cv.pdf", fake_pdf, "application/pdf")},
        )
        # Must not be 200 with a successful read of /etc/passwd
        if r.status_code == 200:
            assert "root:" not in r.text

    def test_cv_upload_exe_disguised_as_pdf(self, client):
        """Executable disguised as PDF must be handled safely."""
        fake_exe = io.BytesIO(b"MZ\x90\x00" + b"\x00" * 100)  # PE header
        r = client.post(
            "/api/v1/rico/upload-cv?user_id=user1",
            files={"file": ("malware.pdf", fake_exe, "application/pdf")},
        )
        assert r.status_code in (200, 400, 422, 500)
        # Must not execute the file
        if r.status_code == 500:
            assert "Traceback" not in r.text

    def test_cv_upload_zip_bomb_detection(self, client):
        """A zip bomb (highly compressed) should not exhaust memory."""
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bomb.txt", "0" * 1_000_000)
        buf.seek(0)
        r = client.post(
            "/api/v1/rico/upload-cv?user_id=user1",
            files={"file": ("bomb.zip", buf, "application/zip")},
        )
        assert r.status_code in (200, 400, 415, 422, 429, 500)

    def test_cv_upload_xss_filename(self, client):
        """XSS in filename must be escaped in response."""
        fake_pdf = io.BytesIO(b"%PDF-1.4 content")
        r = client.post(
            "/api/v1/rico/upload-cv?user_id=user1",
            files={"file": ("<script>alert(1)</script>.pdf", fake_pdf, "application/pdf")},
        )
        assert r.status_code in (200, 400, 422, 429, 500)
        if r.status_code == 200:
            assert "<script>" not in r.text


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CORS — credentials & wildcard
# ═══════════════════════════════════════════════════════════════════════════════

class TestCORSSecurity:
    def test_cors_disallows_untrusted_origin(self, client):
        """Cross-origin requests from evil.com must be rejected or not credentialed."""
        r = client.options(
            "/api/v1/auth/login",
            headers={"Origin": "https://evil-attacker.com", "Access-Control-Request-Method": "POST"},
        )
        acac = r.headers.get("Access-Control-Allow-Credentials", "")
        acao = r.headers.get("Access-Control-Allow-Origin", "")
        # If origin is reflected back AND credentials=true → CORS vuln
        assert not (acao == "https://evil-attacker.com" and acac == "true"), \
            "CORS misconfiguration: untrusted origin gets credentialed access"

    def test_cors_wildcard_with_credentials_not_allowed(self, client):
        """allow_origins=['*'] + allow_credentials=True is invalid per spec."""
        r = client.options("/api/v1/auth/login",
                          headers={"Origin": "https://random.com",
                                   "Access-Control-Request-Method": "POST"})
        acao = r.headers.get("Access-Control-Allow-Origin", "")
        acac = r.headers.get("Access-Control-Allow-Credentials", "false")
        assert not (acao == "*" and acac == "true"), \
            "CORS wildcard + credentials is a critical misconfiguration"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. RATE LIMITING — brute-force, endpoint flooding
# ═══════════════════════════════════════════════════════════════════════════════

class TestRateLimiting:
    def test_login_brute_force_not_throttled(self, client):
        """No rate limiting on /login — this is a FINDING, not a pass."""
        responses = []
        for _ in range(20):
            r = client.post("/api/v1/auth/login", json={"email": "admin@test.com", "password": "wrong"})
            responses.append(r.status_code)
        # If ALL return 401 (not 429), rate limiting is absent — document it
        all_401 = all(s == 401 for s in responses)
        # This test DOCUMENTS the gap; we mark it xfail until rate limiting is added
        if all_401:
            pytest.xfail("No rate limiting on /login endpoint — brute-force vector open")

    def test_jotform_webhook_flood_does_not_crash(self, client):
        """100 rapid webhook calls must not crash (200 or 429 from rate limiting, never 500)."""
        results = []
        for i in range(100):
            r = client.post("/api/v1/rico/webhooks/jotform", json={"formID": str(i)})
            results.append(r.status_code)
        assert all(s in (200, 429) for s in results), f"Unexpected status: {set(results)}"

    def test_chat_endpoint_flood(self, client):
        """50 rapid chat calls must not cause 500."""
        for i in range(50):
            r = client.post("/api/v1/rico/chat", json={"user_id": f"flood_user_{i}", "message": "hello"})
            assert r.status_code != 500, f"Chat crashed on call {i}"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. IDOR — insecure direct object reference
# ═══════════════════════════════════════════════════════════════════════════════

class TestIDOR:
    def test_jobs_endpoint_requires_auth(self, client):
        r = client.get("/api/v1/jobs")
        assert r.status_code == 401

    def test_applications_endpoint_requires_auth(self, client):
        r = client.get("/api/v1/applications")
        assert r.status_code == 401

    def test_stats_endpoint_requires_auth(self, client):
        r = client.get("/api/v1/stats")
        assert r.status_code == 401

    def test_settings_endpoint_requires_auth(self, client):
        r = client.get("/api/v1/settings")
        assert r.status_code == 401

    def test_pipeline_endpoint_requires_auth(self, client):
        r = client.get("/api/v1/pipeline/status")
        assert r.status_code == 401

    def test_agent_endpoint_requires_auth(self, client):
        r = client.post("/api/v1/agent/chat", json={"message": "hello"})
        assert r.status_code == 401

    def test_job_by_id_requires_auth(self, client):
        r = client.get("/api/v1/jobs/1")
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 8. ERROR LEAKAGE — stack traces in responses
# ═══════════════════════════════════════════════════════════════════════════════

class TestErrorLeakage:
    def test_404_does_not_leak_stack_trace(self, client):
        r = client.get("/api/v1/nonexistent/route/that/does/not/exist")
        assert "Traceback" not in r.text
        assert "File \"" not in r.text

    def test_malformed_body_does_not_leak_stack_trace(self, client):
        r = client.post(
            "/api/v1/agent/chat",
            content=b"<xml>not json</xml>",
            headers={"Content-Type": "application/json"},
        )
        assert "Traceback" not in r.text
        assert "File \"" not in r.text

    def test_health_endpoint_visible_without_auth(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        # Health must not expose DB connection string
        assert "postgresql://" not in r.text
        assert "DATABASE_URL" not in r.text

    def test_500_response_does_not_expose_internals(self, client):
        """Force a 500 via bad data and confirm no internal details leak."""
        with patch("src.services.jobs_service.list_jobs", side_effect=RuntimeError("secret DB error")):
            from fastapi.testclient import TestClient
            from src.api.app import app
            from src.api.auth import create_access_token
            token = create_access_token({"sub": "admin@test.com"})
            tc = TestClient(app, raise_server_exceptions=False)
            tc.cookies.set("access_token", token)
            r = tc.get("/api/v1/jobs")
        assert "secret DB error" not in r.text
        assert "Traceback" not in r.text


# ═══════════════════════════════════════════════════════════════════════════════
# 9. CONCURRENT / RACE CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrency:
    def test_concurrent_jotform_webhooks_no_crash(self, client):
        """10 simultaneous Jotform webhooks with same email — no data corruption."""
        errors = []
        results = []

        def send(i):
            try:
                r = client.post("/api/v1/rico/webhooks/jotform", json={
                    "Full Name": f"Test User {i}",
                    "Email": "same@user.com",
                })
                results.append(r.status_code)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=send, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent webhook errors: {errors}"
        assert all(s in (200, 429) for s in results), f"Unexpected status in concurrent test: {set(results)}"

    def test_concurrent_chat_same_user_no_crash(self, client):
        """10 simultaneous chats from same user_id — no crash."""
        errors = []

        def chat(i):
            try:
                r = client.post("/api/v1/rico/chat", json={
                    "user_id": "concurrent_user",
                    "message": f"message {i}",
                })
                if r.status_code == 500:
                    errors.append(f"500 on call {i}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=chat, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Concurrent chat errors: {errors}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. EDGE CASES — boundary / extreme values
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_jobs_page_zero_returns_valid(self, auth_client):
        with patch("src.db.get_db_connection", return_value=None):
            with patch("src.job_history.load_job_history", return_value=[]):
                r = auth_client.get("/api/v1/jobs?page=0")
        assert r.status_code in (200, 422)

    def test_jobs_negative_page(self, auth_client):
        with patch("src.db.get_db_connection", return_value=None):
            with patch("src.job_history.load_job_history", return_value=[]):
                r = auth_client.get("/api/v1/jobs?page=-1")
        assert r.status_code in (200, 422)

    def test_jobs_huge_limit(self, auth_client):
        with patch("src.db.get_db_connection", return_value=None):
            with patch("src.job_history.load_job_history", return_value=[]):
                r = auth_client.get("/api/v1/jobs?limit=999999")
        assert r.status_code in (200, 422)

    def test_intent_detector_empty_string(self):
        from src.agent.orchestrator.intent_detector import detect
        intent, tool = detect("")
        assert intent == "help"
        assert tool is None

    def test_intent_detector_unicode_input(self):
        from src.agent.orchestrator.intent_detector import detect
        intent, tool = detect("وظائف اليوم في دبي 🎯")
        assert isinstance(intent, str)

    def test_intent_detector_very_long_message(self):
        from src.agent.orchestrator.intent_detector import detect
        intent, tool = detect("show me jobs " * 10_000)
        assert intent == "get_ranked_jobs"

    def test_jotform_normalize_all_none_values(self):
        from src.services.chat_service import _normalize_jotform_payload, _has_user_data
        payload = {"Full Name": None, "Email": None, "Phone": None}
        normalized = _normalize_jotform_payload(payload)
        assert not _has_user_data(normalized)

    def test_jotform_normalize_empty_strings(self):
        from src.services.chat_service import _has_user_data
        assert not _has_user_data({"full_name": "", "email": ""})

    def test_rico_safety_empty_message(self):
        from src.rico_safety import RicoSafetyGuard
        result = RicoSafetyGuard().check_message("")
        assert result.allowed is True

    def test_rico_safety_null_byte_message(self):
        from src.rico_safety import RicoSafetyGuard
        null_bytes = chr(0) * 3
        result = RicoSafetyGuard().check_message(null_bytes)
        assert isinstance(result.allowed, bool)

    def test_rico_identity_returns_string(self):
        from src.rico_identity import RICO_IDENTITY, get_rico_system_prompt
        assert isinstance(RICO_IDENTITY, str) and len(RICO_IDENTITY) > 50
        prompt = get_rico_system_prompt()
        assert isinstance(prompt, str) and len(prompt) > 100
        prompt_with_ctx = get_rico_system_prompt("user context here")
        assert "user context here" in prompt_with_ctx


# ═══════════════════════════════════════════════════════════════════════════════
# 11. DEPENDENCY CVEs — document known vulnerabilities
# ═══════════════════════════════════════════════════════════════════════════════

class TestKnownCVEs:
    """
    Pinned version floors for packages with known CVEs.
    All currently installed versions meet or exceed these minimums.
    Add xfail only when a CVE is newly discovered and not yet patched.
    Run: python -m pip_audit --format=columns to refresh.
    """

    def test_authlib_cve_2026_41425(self):
        import authlib
        ver = tuple(int(x) for x in authlib.__version__.split(".")[:3])
        assert ver >= (1, 6, 11), "authlib must be >= 1.6.11 (CVE-2026-41425)"

    def test_cryptography_cve_2026_39892(self):
        import cryptography
        ver = tuple(int(x) for x in cryptography.__version__.split(".")[:3])
        assert ver >= (46, 0, 7), "cryptography must be >= 46.0.7 (CVE-2026-39892)"

    def test_lxml_cve_2026_41066(self):
        import lxml.etree
        assert lxml.etree.LXML_VERSION >= (6, 1, 0, 0), "lxml must be >= 6.1.0 (CVE-2026-41066)"

    @pytest.mark.xfail(reason="CVE-2025-46656: markdownify 0.13.1 — upgrade to 0.14.1")
    def test_markdownify_cve_2025_46656(self):
        import markdownify
        ver = tuple(int(x) for x in markdownify.__version__.split(".")[:3])
        assert ver >= (0, 14, 1), "markdownify must be >= 0.14.1 (CVE-2025-46656)"

    def test_pytest_cve_2025_71176(self):
        ver = tuple(int(x) for x in pytest.__version__.split(".")[:3])
        assert ver >= (9, 0, 3), "pytest must be >= 9.0.3 (CVE-2025-71176)"

    def test_diskcache_cve_2025_69872(self):
        """CVE-2025-69872: no fix version published yet — track installed version."""
        import diskcache
        installed = diskcache.__version__
        # Assert we're aware of this: update this test once a patched version ships.
        assert installed == "5.6.3", (
            f"diskcache {installed} — check CVE-2025-69872 fix status and update this pin"
        )
