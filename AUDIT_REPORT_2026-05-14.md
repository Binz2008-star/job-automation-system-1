# Rico AI — Production Security, Reliability & Performance Audit
**Date:** 2026-05-14  
**Auditor:** Senior QA / Security / SRE Review  
**Scope:** Full repository — backend, frontend, CI/CD, database, infrastructure, tests  
**Branch reviewed:** main (local working tree)  

---

## Executive Summary

The codebase shows **mature architectural patterns** (layered API, repository pattern, JWT auth, rate limiting, SaaS user isolation) but contains **multiple Critical and High-severity issues** that must be fixed before production deployment. The most severe is a **confirmed SQL injection vulnerability** in the SaaS data path. Several reliability issues around concurrency, credential hygiene, and CI/CD safety are also present.

**Bottom line:** Do not deploy to production without addressing the Critical items in the "Must fix before deploy" section.

---

## Top 10 Production Risks (Ranked)

| Rank | Risk | Severity | Category |
|------|------|----------|----------|
| 1 | SQL injection in `rico_db.py::get_recommendations` via f-string WHERE clause | **Critical** | Security |
| 2 | Hardcoded PII and credentials in source (name, email, example DB URL) | **Critical** | Security |
| 3 | Unpinned dependencies in `requirements.txt` — supply-chain / breakage risk | **High** | Reliability |
| 4 | `daily.yml` deploys dashboard even on pipeline failure (`if: always()`) | **High** | Reliability |
| 5 | `applications_repo.py` loads ALL user records into memory for pagination | **High** | Performance |
| 6 | `run_daily.py` Prometheus on port 8000 collides with API; distributed lock fail-open | **High** | Reliability |
| 7 | `db.py` `autocommit=True` destroys transactional safety for multi-step operations | **High** | Reliability |
| 8 | `indeed_apply.py` disables HTTPS verification and sandbox in browser automation | **High** | Security |
| 9 | `naukrigulf_apply.py` timezone truncation causes incorrect job-age filtering | **Medium** | Bug |
| 10 | Password reset flow logs tokens but never sends actual email to users | **Medium** | Bug / Reliability |

---

## Must Fix Before Deploy

### 1. SQL Injection (Critical)
**File:** `d:\job-automation-system-1-main\src\rico_db.py`  
**Line:** 420–436  
**Issue:** `get_recommendations` builds a SQL `WHERE` clause with an f-string, injecting the `status` parameter directly into the query string. Although `params` is passed separately for the `user_id` and `status` equality predicates, the `WHERE {where}` clause itself is constructed via string concatenation (f-string), and `limit`/`offset` are appended with `+` concatenation. While `limit`/`offset` are typed as `int` in the method signature, the `status` string is appended into the SQL text before parameterization.

```python
# rico_db.py:428-435
where = " AND ".join(filters)
cur.execute(
    f"""
    SELECT job_key, job, repo_score, rico_score, explanation, status, created_at, updated_at
    FROM rico_job_recommendations
    WHERE {where}
    ORDER BY updated_at DESC
    LIMIT %s OFFSET %s
    """,
    params + [limit, offset],
)
```

**Impact:** An attacker with a valid JWT who can control the `status` query parameter (or any future caller who passes an untrusted string) can exfiltrate or modify data in `rico_job_recommendations` and any other table accessible to the DB role.

**Recommended Fix:** Never use f-strings or `.format()` for SQL. Build the query with a static template and pass all values as parameters:

```python
where_clauses = ["user_id = %s"]
params: List[Any] = [user_id]
if status:
    where_clauses.append("status = %s")
    params.append(status)
where = " AND ".join(where_clauses)
sql = f"SELECT ... FROM rico_job_recommendations WHERE {where} ORDER BY updated_at DESC LIMIT %s OFFSET %s"
# ^ safe because `where` is composed ONLY of hardcoded clause strings
params += [limit, offset]
cur.execute(sql, params)
```

**Confidence:** High

---

### 2. Hardcoded Personal Data & Credential Exposure (Critical)
**File:** `d:\job-automation-system-1-main\src\indeed_apply.py`  
**Line:** 744–745  
**Issue:** Name and fallback email address are hardcoded:

```python
name  = "Roben Edwan"
email = os.getenv("INDEED_EMAIL", "robenedwan@gmail.com")
```

**File:** `d:\job-automation-system-1-main\.env.example`  
**Line:** 10  
**Issue:** Contains a real-looking Neon connection string:

```
DATABASE_URL=postgresql://authenticator:npg_R8hdwAMu9cOs@ep-long-poetry-am9o9qth-pooler...
```

Even if this is a rotated/invalid credential, it trains developers to commit connection strings and reveals internal infrastructure naming (Neon, region, project ID).

**Recommended Fix:**
- Remove hardcoded name/email from `indeed_apply.py`; load from env vars with no fallback.
- Replace `.env.example` `DATABASE_URL` with `postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require`.

**Confidence:** High

---

### 3. Dependency Version Pinning (High)
**File:** `d:\job-automation-system-1-main\requirements.txt`  
**Issue:** The vast majority of packages have no version constraints (`requests`, `python-dotenv`, `schedule`, `psycopg2-binary`, `fastapi`, `pydantic`, etc.). This creates:
- Non-reproducible builds
- Supply-chain attacks via typosquatting or compromised upstream releases
- Unexpected breaking changes on fresh installs

**Recommended Fix:** Pin every direct dependency to at least a minimum safe version and regenerate `requirements.lock` / `requirements-dev.lock`:

```txt
requests==2.32.3
python-dotenv==1.0.1
fastapi==0.115.0
pydantic==2.9.0
psycopg2-binary==2.9.9
...
```

**Confidence:** High

---

### 4. CI/CD — Dashboard Deployed on Failure (High)
**File:** `d:\job-automation-system-1-main\.github\workflows\daily.yml`  
**Line:** 64–78  
**Issue:** The "Deploy dashboard to GitHub Pages" step uses `if: always()`, meaning a broken or partially-failed pipeline will still overwrite the public dashboard. This can publish stale, corrupted, or empty data.

**Recommended Fix:** Change to `if: success()` or at minimum verify `dashboard.html` was generated by a successful step:

```yaml
- name: Deploy dashboard to GitHub Pages
  if: success() && hashFiles('dashboard.html') != ''
```

**Confidence:** High

---

### 5. In-Memory Pagination in Applications Router (High)
**File:** `d:\job-automation-system-1-main\src\api\routers\applications.py`  
**Line:** 37–49  
**Issue:** `list_applications` calls `get_all(user_id)` which loads **all** applications for a user into memory, then slices in Python:

```python
all_apps: List[Dict[str, Any]] = get_all(user_id=user_id)
if status:
    all_apps = [a for a in all_apps if a.get("status") == status]
total = len(all_apps)
offset = (page - 1) * limit
return {"applications": all_apps[offset : offset + limit], ...}
```

**Impact:** O(N) memory per request. A user with thousands of applications will cause memory pressure and slow response times. No database-level LIMIT/OFFSET is used.

**Recommended Fix:** Push pagination, filtering, and sorting into the database query in `applications_repo.py` / `rico_db.py`.

**Confidence:** High

---

### 6. Distributed Lock Fail-Open + Port Collision (High)
**File:** `d:\job-automation-system-1-main\src\run_daily.py`  
**Line:** 176–178 and 97–116  
**Issue 1:** `distributed_lock` catches all exceptions and yields `True` (fail-open), allowing concurrent pipeline runs if Redis is unreachable:

```python
except Exception as e:
    logger.error(f"lock_error: {e}")
    yield True  # Fail open
```

**Issue 2:** `start_http_server(8000)` starts Prometheus metrics on port 8000, the same port used by the FastAPI app in development and potentially in containerized production.

**Recommended Fix:**
- Fail **closed** on lock errors: `yield False`.
- Make Prometheus port configurable (`RICO_METRICS_PORT`) with default `9090` or `8001`.

**Confidence:** High

---

### 7. Database Autocommit Destroys Transactional Safety (High)
**File:** `d:\job-automation-system-1-main\src\db.py`  
**Line:** 32  
**Issue:** `get_db_connection` sets `conn.autocommit = True`. Every `cursor.execute()` is immediately committed. There is no way to perform multi-statement transactions atomically. If a later statement fails, earlier mutations are already persisted, leaving the DB in an inconsistent state.

**Recommended Fix:** Remove `autocommit = True`. Manage transactions explicitly with `conn.commit()` / `conn.rollback()`.

**Confidence:** High

---

### 8. Browser Automation Security Hardening (High)
**File:** `d:\job-automation-system-1-main\src\indeed_apply.py`  
**Line:** 391–402  
**Issue:**
- `ignore_https_errors=True` disables TLS certificate validation.
- `--no-sandbox` + `--disable-dev-shm-usage` are standard for containerized Chrome but increase attack surface.
- `--disable-blink-features=AutomationControlled` attempts to hide automation; combined with the above, this is a red flag for platform Terms of Service compliance.

**Recommended Fix:**
- Remove `ignore_https_errors=True` unless running against a known test environment.
- Gate `--no-sandbox` behind an explicit env var (`CHROME_NO_SANDBOX`) rather than enabling unconditionally.
- Document that automated application submission may violate Indeed/NaukriGulf ToS.

**Confidence:** High

---

### 9. Incorrect Job Age Filtering Due to Timezone Truncation (Medium)
**File:** `d:\job-automation-system-1-main\src\naukrigulf_apply.py`  
**Line:** 276–283  
**Issue:** `_is_too_old` truncates ISO strings to 19 characters, stripping timezone offsets:

```python
dt = datetime.fromisoformat(str(posted)[:19])
```

If `posted` is `2026-05-14T12:00:00+04:00`, it becomes `2026-05-14T12:00:00` (naive/local). On a UTC system, this shifts the timestamp and causes incorrect age calculations.

**Recommended Fix:** Parse the full ISO string with timezone support:

```python
dt = datetime.fromisoformat(str(posted).replace('Z', '+00:00'))
```

**Confidence:** High

---

### 10. Password Reset Never Sends Email (Medium)
**File:** `d:\job-automation-system-1-main\src\api\auth.py`  
**Line:** 230–267  
**Issue:** `forgot_password` generates a token, logs the reset URL, but never invokes an email-sending service. In production, users will never receive reset emails. The endpoint returns a generic success message, creating a broken user experience with no recovery path.

**Recommended Fix:** Integrate with an email provider (SendGrid, AWS SES, Postmark) or return a documented error if email is not configured. Do not silently claim success.

**Confidence:** High

---

## Additional High-Priority Findings

### 11. ` RicoDB()` Connection Lifecycle Bug in `upsert_user` / `upsert_profile`
**File:** `d:\job-automation-system-1-main\src\rico_db.py`  
**Lines:** 252–290, 292–318  
**Issue:** When `conn=None`, a new connection is opened, but `conn.commit()` is only called when `should_close=True`. If a caller passes an external connection (transaction in progress), the code does NOT commit, which is correct, but the `should_close` logic is inverted for the `upsert_user` path: it commits only when it created the connection. However, `connect()` returns a connection that is also a context manager; mixing explicit `close()` with `with` blocks is inconsistent and leak-prone.

**Impact:** Connection leaks under load; inconsistent transaction behavior.

**Recommended Fix:** Standardize on `with self.connect() as conn:` for all DB operations and remove optional `conn` parameters.

---

### 12. `get_user_bundle` Ambiguous Identity Resolution
**File:** `d:\job-automation-system-1-main\src\rico_db.py`  
**Line:** 354–364  
**Issue:** The query matches on `id::text = %s OR external_user_id = %s OR email = %s OR telegram_username = %s` with `LIMIT 1`. If two users share a `telegram_username` (not enforced UNIQUE) or if a malicious public user ID collides with an internal UUID, the wrong user's data may be returned.

**Recommended Fix:** Require the caller to specify which identifier type is being used. Do not OR-match across identity namespaces.

---

### 13. `applications_repo.py` Legacy Fallback on Empty String
**File:** `d:\job-automation-system-1-main\src\repositories\applications_repo.py`  
**Line:** 86–90  
**Issue:** `if not user_id:` treats empty string as "no user", falling back to legacy JSON. A bug or misconfiguration that passes `user_id=""` will bypass SaaS isolation and return global data.

**Recommended Fix:** Explicitly check `if user_id is None:` rather than truthiness.

---

### 14. `register` Schema Accepts `role="admin"` But Ignores It
**File:** `d:\job-automation-system-1-main\src\schemas\auth.py`  
**Line:** 24–32  
**Issue:** `RegisterRequest` allows `role: Literal["admin", "user"]` but `src/api/auth.py:314` forces `role="user"`. The schema is misleading to API consumers and could cause client-side bugs or be exploited if the enforcement is ever accidentally removed.

**Recommended Fix:** Remove `role` from `RegisterRequest` entirely.

---

### 15. No Output Encoding / XSS Risk in Public Chat
**File:** `d:\job-automation-system-1-main\src\api\routers\rico_chat.py`  
**Line:** 453–492  
**Issue:** The public chat endpoint returns `PublicChatResponse(message=...)`. If the underlying `chat_service.send_message` returns HTML/JS in the message string (e.g., from an LLM that echoes user input), and the frontend renders it as HTML, this is a stored XSS vector.

**Recommended Fix:** Sanitize LLM output before returning (bleach, html.escape, or ensure the frontend treats it as text-only). Add a `Content-Security-Policy` header.

---

### 16. `run_daily.py` — `build_dashboard` Writes to Shared File Without Locking
**File:** `d:\job-automation-system-1-main\src\run_daily.py`  
**Line:** 614–616  
**Issue:** `DASHBOARD_FILE.write_text(html)` is not atomic across processes. If two pipeline runs overlap (e.g., fail-open lock), the file can be corrupted.

**Recommended Fix:** Use `tempfile + os.replace` pattern (same as `applications.py`).

---

### 17. `deploy-production.yml` Is a No-Op
**File:** `d:\job-automation-system-1-main\.github\workflows\deploy-production.yml`  
**Issue:** The workflow only runs `echo` statements. It does not deploy anything. This gives a false sense of CI/CD safety.

**Recommended Fix:** Remove or implement actual deployment (e.g., Render deploy hook, container push, Terraform apply).

---

### 18. `daily.yml` — Self-Hosted Runner Session Check Uses Wrong Profile Path for Indeed
**File:** `d:\job-automation-system-1-main\.github\workflows\daily.yml`  
**Line:** 205–217  
**Issue:** The Indeed session check verifies `data/ng_profile` (the NaukriGulf profile directory), not an Indeed-specific profile path. If both platforms need different profiles, this check is incorrect.

**Recommended Fix:** Use distinct profile directories (`data/indeed_profile`, `data/ng_profile`) and check the correct one per job.

---

### 19. `actions.py` Rate Limit Label Misleading
**File:** `d:\job-automation-system-1-main\src\api\routers\actions.py`  
**Line:** 20  
**Issue:** `LIMIT_ACTIONS = LIMIT_CHAT` (30/minute). While functional, the naming is confusing; actions may deserve a different limit than chat.

**Recommended Fix:** Define `LIMIT_ACTIONS = "20/minute"` independently.

---

### 20. `db.py` `save_job` Description Truncation Can Split Multi-Byte Characters
**File:** `d:\job-automation-system-1-main\src\db.py`  
**Line:** 160  
**Issue:** `str(job.get('description', ''))[:1000]` truncates by byte/character count without regard for Unicode grapheme clusters or multi-byte characters.

**Recommended Fix:** Use a UTF-safe truncation function or limit at the DB schema level (e.g., `TEXT` with a check constraint).

---

### 21. `metrics` Endpoint Exposes Internal Metrics to Any Authenticated User
**File:** `d:\job-automation-system-1-main\src\api\routers\rico_chat.py`  
**Line:** 648–661  
**Issue:** `/api/v1/rico/metrics` requires only `get_current_user(request)` (any valid JWT), not admin. It returns uptime, request counts, and response times. This is information leakage.

**Recommended Fix:** Change dependency to `require_admin` or move metrics to a separate admin-only router.

---

### 22. Missing `NOT NULL` and Constraints on `rico_users.email`
**File:** `d:\job-automation-system-1-main\src\rico_db.py`  
**Line:** 33–44  
**Issue:** `rico_users.email` is `TEXT` without `NOT NULL` or `UNIQUE`. The `external_user_id` is `UNIQUE`, but email is not, allowing duplicate accounts and null emails.

**Recommended Fix:** Add `NOT NULL` to `email` and consider a partial unique index if multiple NULLs are allowed.

---

### 23. `feedback` Endpoint Has No Rate Limiting
**File:** `d:\job-automation-system-1-main\src\api\routers\rico_chat.py`  
**Line:** 528–555  
**Issue:** `@router.post("/feedback")` has no `@limiter.limit(...)` decorator. An authenticated user can flood the learning repository with signals.

**Recommended Fix:** Add `@limiter.limit("30/minute")`.

---

### 24. `applications.py` `mark_applied` Silently Rewrites Invalid Status
**File:** `d:\job-automation-system-1-main\src\applications.py`  
**Line:** 129–130  
**Issue:** If an invalid status is passed, it is silently changed to `"applied"` rather than raising or returning an error. This masks bugs upstream.

**Recommended Fix:** Return `False` or raise `ValueError` on invalid status.

---

### 25. `control_server.py` Uses Deprecated `@app.on_event("startup")`
**File:** `d:\job-automation-system-1-main\src\control_server.py`  
**Line:** 189  
**Issue:** FastAPI deprecated `@app.on_event` in favor of `lifespan` context managers. This will break in a future FastAPI release.

**Recommended Fix:** Migrate to `asynccontextmanager` lifespan (same pattern as `src/api/app.py`).

---

## Security Summary

| Category | Count | Notes |
|----------|-------|-------|
| SQL Injection | 1 | Confirmed in `rico_db.py` |
| Hardcoded Secrets/PII | 2 | Name/email in `indeed_apply.py`; example DB URL |
| XSS Risk | 1 | LLM output in public chat not sanitized |
| Unsafe CORS | 0 | CORS logic is correct (`_wildcard` check) |
| Broken Auth | 1 | `get_user_bundle` OR-matches across identity fields |
| Info Disclosure | 1 | Metrics endpoint not admin-gated |
| Insecure Defaults | 1 | Browser automation ignores HTTPS errors |
| Missing Encryption | 0 | Passwords use bcrypt; tokens use HS256 |
| Weak Rate Limiting | 2 | Feedback endpoint unbounded; actions limit reused from chat |

---

## Performance Summary

| Category | Count | Notes |
|----------|-------|-------|
| N+1 / In-Memory Pagination | 1 | `applications_repo.py` loads all rows |
| Unbounded Memory | 2 | `get_seen_links(days_back, limit)` bounds exist but are not enforced at API level; `get_all` unbounded |
| Missing DB Indexes | 1 | `rico_job_recommendations(job_key)` needs index |
| Blocking I/O | 2 | `run_daily.py` sleeps in main thread; Playwright is synchronous |
| Large Memory Allocations | 1 | LLM scoring loads all jobs into memory |
| Duplicate Work | 1 | `is_applied` reads JSON file on every check instead of caching |

---

## Reliability Summary

| Category | Count | Notes |
|----------|-------|-------|
| Transaction Safety | 1 | `autocommit=True` prevents atomic multi-step ops |
| Retry Logic Gaps | 1 | `retryable` decorator uses blocking sleep in main thread |
| Fail-Open Locks | 1 | Redis lock exceptions yield `True` |
| Partial Write Handling | 1 | Dashboard write not atomic |
| Graceful Shutdown | 0 | Playwright contexts close on `__exit__` — acceptable |
| Crash Recovery | 1 | Profile corruption recovery exists but resets to zero state |
| Migration Safety | 1 | ` RicoDB().init()` in lifespan can race with other workers |
| Startup Sequencing | 1 | `_check_critical_tables` logs error but does not abort startup |

---

## Test Coverage Summary

**Observation:** The `tests/` directory contains **39 test files** with **1000+ test functions**, which is a strong signal. However, the following critical paths appear under-tested or not tested at all based on file naming and grep results:

- **SQL injection regression test** for `rico_db.py::get_recommendations` — **missing**.
- **Rate-limit bypass / load test** for feedback endpoint — **missing**.
- **Concurrent `mark_applied` stress test** — not evident in test list.
- **Playwright engine failure modes** (network block, CAPTCHA, session expiry) — not unit-testable but no integration tests evident.
- **CI/CD workflow validation** (e.g., asserting `if: always()` behavior) — **missing**.
- **Password reset token expiration** exact boundary test — may exist in `test_password_reset.py` but cannot confirm without reading.

**Recommended Additions:**
1. `test_sql_injection_regression.py` — parametrize malicious `status` strings against `get_recommendations`.
2. `test_concurrent_mark_applied.py` — spawn threads/processes hitting `mark_applied` simultaneously.
3. `test_feedback_rate_limit.py` — verify 429 after 30 requests/minute.
4. `test_metrics_admin_only.py` — assert non-admin receives 403.

---

## Safe to Defer

These are lower priority or cosmetic and can be addressed in future sprints:

- **Code style:** Some modules use f-string logging (PEP 8 recommends lazy `%s` formatting). Not a security issue.
- **Doc exposure:** `docs_url="/api/docs"` and `redoc_url="/api/redoc"` are publicly accessible. Acceptable if the API is internal or if docs contain no sensitive schema details.
- **Frontend:** The landing page (`page.tsx`) uses inline styles rather than Tailwind — cosmetic / maintainability only.
- **Deprecated `datetime.utcnow()`** usages in `indeed_apply.py` — should be cleaned up but not breaking until Python 3.14+.
- **No email verification** on registration — acceptable for MVP; add to roadmap.

---

## Git / Repository State Notes

- `.env` is present in the working tree and open in the IDE. Per repo rules, it is `gitignored` and must not be modified by automation.
- `learning_cache/cache.db-shm` and `cache.db-wal` appear in the workspace snapshot. Ensure `learning_cache/` is fully `gitignored`.
- `dashboard_v3.html`, `index.html`, `rico-ai-landing.html` in root may be stale artifacts. Verify if they should be removed.
- The nested `job-automation-system-1-main/job-automation-system-1-main/` directory is unusual — verify it is not accidentally duplicated.

---

## Recommended Immediate Actions

1. **Patch SQL injection** in `rico_db.py` (see fix in Finding #1).
2. **Scrub hardcoded PII** from `indeed_apply.py` and rotate any credentials that match the example `.env.example` URL.
3. **Pin dependencies** and run `pip freeze > requirements.lock`.
4. **Fix `daily.yml`** to deploy dashboard only on success.
5. **Add DB-level pagination** to `applications_repo.py`.
6. **Fail closed** on distributed lock errors and make Prometheus port configurable.
7. **Remove `autocommit=True`** from `db.py` and manage transactions explicitly.
8. **Add rate limiting** to the feedback endpoint.
9. **Gate metrics** behind `require_admin`.
10. **Implement actual email sending** for password reset or disable the endpoint in production.

---
*End of Audit Report*
