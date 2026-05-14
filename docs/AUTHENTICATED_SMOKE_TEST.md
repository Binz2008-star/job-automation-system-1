# Authenticated Smoke Test Documentation

## Purpose

This document outlines the process for performing authenticated smoke tests on the Job Automation Platform API. These tests verify that protected endpoints work correctly with valid authentication tokens.

## Required Test Account Setup

Before performing authenticated smoke tests, you need a test account:

1. **Create a test user** via the registration endpoint:
   ```
   POST /api/v1/auth/register
   ```
   with a test email and password (e.g., `smoke-test@example.com`).

2. **Or use an existing test account** if one already exists in the database.

3. **Environment variables** (for fallback auth):
   - `ADMIN_EMAIL` - default admin email
   - `ADMIN_PASSWORD_HASH` - bcrypt hash of admin password (recommended)
   - `ADMIN_PASSWORD` - plaintext fallback (dev only, not recommended for production)

## Login Request Example

### Using curl

```bash
curl -X POST https://rico-job-automation-api.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your-test-email@example.com",
    "password": "your-test-password"
  }' \
  -c cookies.txt
```

The `-c cookies.txt` flag saves the authentication cookie to a file for subsequent requests.

### Using Postman

1. Create a new POST request to `https://rico-job-automation-api.onrender.com/api/v1/auth/login`
2. Set headers:
   - `Content-Type: application/json`
3. Set body (raw JSON):
   ```json
   {
     "email": "your-test-email@example.com",
     "password": "your-test-password"
   }
   ```
4. Send the request - the response will include an `access_token` cookie (httpOnly)
5. Postman automatically stores this cookie for subsequent requests

## How to Store Cookie/Token Temporarily

### Using curl with cookies

After login, use the saved cookie file for authenticated requests:

```bash
curl -X GET https://rico-job-automation-api.onrender.com/api/v1/settings \
  -b cookies.txt
```

### Using Postman

1. After successful login, Postman automatically stores the httpOnly cookie
2. All subsequent requests to the same domain will include the cookie
3. You can view cookies in:
   - Postman: Cookies icon (cookie jar) in the request panel
   - Browser: DevTools → Application → Cookies

### Manual token extraction (if needed)

If you need to extract the JWT token manually (not recommended for production):

```bash
curl -X POST https://rico-job-automation-api.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}' \
  -i | grep Set-Cookie
```

## Endpoints to Test

### 1. GET /api/v1/settings

**Purpose:** Retrieve user settings

**Expected status codes:**
- `200 OK` - Success with settings data
- `401 Unauthorized` - Invalid or missing authentication

**Example:**
```bash
curl -X GET https://rico-job-automation-api.onrender.com/api/v1/settings \
  -b cookies.txt
```

### 2. GET /api/v1/jobs?page=1&limit=1&min_score=0

**Purpose:** Retrieve job listings with pagination and filtering

**Expected status codes:**
- `200 OK` - Success with jobs data
- `401 Unauthorized` - Invalid or missing authentication

**Example:**
```bash
curl -X GET "https://rico-job-automation-api.onrender.com/api/v1/jobs?page=1&limit=1&min_score=0" \
  -b cookies.txt
```

### 3. GET /api/v1/applications/stats

**Purpose:** Retrieve application statistics

**Expected status codes:**
- `200 OK` - Success with statistics data
- `401 Unauthorized` - Invalid or missing authentication

**Example:**
```bash
curl -X GET https://rico-job-automation-api.onrender.com/api/v1/applications/stats \
  -b cookies.txt
```

### 4. GET /api/v1/rico/settings/saved-searches

**Purpose:** Retrieve saved search queries

**Expected status codes:**
- `200 OK` - Success with saved searches data
- `401 Unauthorized` - Invalid or missing authentication

**Example:**
```bash
curl -X GET https://rico-job-automation-api.onrender.com/api/v1/rico/settings/saved-searches \
  -b cookies.txt
```

### 5. POST /api/v1/rico/chat

**Purpose:** Send a chat message to the Rico AI

**Expected status codes:**
- `200 OK` - Success with AI response
- `401 Unauthorized` - Invalid or missing authentication
- `405 Method Not Allowed` - Wrong HTTP method (GET instead of POST)

**Example:**
```bash
curl -X POST https://rico-job-automation-api.onrender.com/api/v1/rico/chat \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"message":"Hello"}'
```

## Expected Status Codes Summary

| Endpoint | Method | Expected Success | Expected Auth Failure |
|----------|--------|------------------|----------------------|
| /api/v1/settings | GET | 200 OK | 401 Unauthorized |
| /api/v1/jobs | GET | 200 OK | 401 Unauthorized |
| /api/v1/applications/stats | GET | 200 OK | 401 Unauthorized |
| /api/v1/rico/settings/saved-searches | GET | 200 OK | 401 Unauthorized |
| /api/v1/rico/chat | POST | 200 OK | 401 Unauthorized |

## Cleanup Steps

After completing smoke tests:

1. **Delete temporary cookie file:**
   ```bash
   rm cookies.txt
   ```

2. **Clear Postman cookies:**
   - Open Postman cookie jar
   - Delete cookies for the test domain

3. **Delete test account (if created):**
   - Use the delete user endpoint if available, or
   - Manually delete from the database

4. **Verify cleanup:**
   - Try accessing an authenticated endpoint without credentials
   - Should receive `401 Unauthorized`

## Security Note

**Never use production personal credentials for smoke tests.**

- Use dedicated test accounts only
- Test accounts should have limited permissions
- Never commit credentials to version control
- Rotate test credentials regularly
- Use environment-specific test accounts (dev, staging, production)
- Consider using test account creation/automation for CI/CD

## Troubleshooting

### 401 Unauthorized despite valid login

- Check cookie domain and path
- Verify cookie is being sent (check browser DevTools or curl verbose output)
- Ensure token hasn't expired (default TTL: 24 hours)
- Check `COOKIE_SECURE` environment variable (must match HTTP/HTTPS)

### 405 Method Not Allowed

- Ensure correct HTTP method (GET vs POST)
- Check endpoint documentation in `/api/docs`

### CORS errors

- Check frontend origin is allowed
- Verify `CORS_ORIGINS` environment variable
- Note: SameSite cookie settings may affect cross-origin requests

## Automation

For CI/CD pipelines, consider:

1. Creating a dedicated test user during pipeline setup
2. Storing test credentials in CI/CD secrets (not in code)
3. Running smoke tests after each deployment
4. Cleaning up test data after pipeline completion
