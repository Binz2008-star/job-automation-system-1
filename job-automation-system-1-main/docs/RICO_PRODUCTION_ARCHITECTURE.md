# Rico AI — Production Architecture and Design

## 1. Backend stack

- Hosting: Render web service, worker, and Redis
- Database: Neon PostgreSQL
- Queue: Redis + Celery for background jobs
- Language: Python 3.11 with FastAPI
- Authentication: JWT tokens through httpOnly cookie or Bearer header
- AI: Hugging Face free inference API for intent parsing, plus local sentence-transformers for embeddings
- Webhook: Jotform incoming POST handled with DB-backed idempotency

## 2. Frontend stack

- Hosting: Vercel
- Framework: Next.js with TypeScript and Tailwind CSS
- State: React Query for server state, Zustand for UI state
- Chat: Vercel AI SDK for streaming responses
- API client: generated from FastAPI OpenAPI spec

## 3. Core flows

### Onboarding flow

User starts chat on web or Telegram. Backend loads onboarding state from Neon. If status is `not_started`, Rico starts onboarding. All answers are persisted to DB after each step.

When consent is true, the webhook calls onboarding completion logic, setting status to `completed` and storing `completed_at`. Chat must never ask a completed user for first-name onboarding again.

### Job search flow

User asks for a role and location, for example: `find me operations manager jobs in Dubai`.

Backend parses intent, extracts role, location, and optional salary preferences, then returns immediately with a queued/searching response. A Celery task fetches jobs from production-safe sources, computes match scores, stores results, and notifies the user.

Production should avoid live LinkedIn scraping. Use Indeed RSS, approved APIs, or curated company feeds.

### Auto-apply flow

User approves a job match. Backend generates a pre-filled application message or email draft. User manually reviews and submits. Backend tracks application status.

Do not directly submit external applications without explicit user approval.

## 4. Database schema direction

### users

- `user_id` or UUID primary key
- `telegram_username` unique where available
- `email`
- `created_at`

### onboarding_state

- `user_id`
- `status`
- `profile_completed`
- `completed_at`
- profile/onboarding fields such as first name, target role, preferred city, avoid list, CV URL, and consent

### job_matches

- `id`
- `user_id`
- `job_id`
- `score`
- `explanation`
- `status`
- `created_at`

### webhook_events

- `id`
- `provider`
- `submission_id`
- `processed_at`
- `metadata`
- unique constraint on `(provider, submission_id)`

### applications

- `id`
- `user_id`
- `job_id`
- `applied_at`
- `cover_letter`
- `status`

All user-scoped queries must include `WHERE user_id = current_user_id` or equivalent repository-layer scoping.

## 5. User isolation enforcement

Every authenticated endpoint must derive the current user from a trusted JWT/session dependency. Request-body `user_id` must not be trusted for authenticated user data access.

Webhook routes are the exception because they do not have a user JWT. They must derive a stable user identifier from verified payload fields and store a mapping to the canonical user record.

Required tests:

- User A cannot read User B profile
- User A cannot read User B jobs
- User A cannot update User B applications
- resource mismatch returns 403 or 404

## 6. AI mode

Intent parsing may use Hugging Face free inference for MVP, but rate limits must be treated as normal operating conditions.

Embeddings can use `sentence-transformers/all-MiniLM-L6-v2` locally for matching. Explanation generation should be limited to top matches to avoid unnecessary API calls.

When provider rate limits occur, Rico must return explicit provider-state metadata, such as:

```json
{
  "response_source": "rate_limited",
  "provider_state": "rate_limited"
}
```

## 7. Webhook idempotency

Jotform posts to the Rico webhook endpoint. Handler extracts `submission_id` and registers it through PostgreSQL:

```sql
INSERT INTO webhook_events (provider, submission_id)
VALUES ('jotform', :submission_id)
ON CONFLICT DO NOTHING
RETURNING id;
```

If no row is returned, the webhook is a duplicate and must return success/ignored without reprocessing. File-based webhook duplicate tracking is not production-safe.

## 8. Deployment pipeline

Run migrations before app startup. Recommended production startup pattern:

```bash
alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port $PORT
```

For zero-downtime deployment, use at least two web instances and rolling updates.

## 9. Health checks

Health endpoint should verify critical dependencies instead of returning static OK.

Target shape:

```json
{
  "status": "healthy",
  "database": "ok",
  "redis": "ok",
  "openai": "ok",
  "timestamp": "2026-05-11T12:00:00Z"
}
```

## 10. Logging and monitoring

Use structured JSON logs with request IDs. Request ID must be generated at ingress and passed to background tasks.

Do not log secrets, raw provider headers, full user CV contents, or full webhook payloads.

## 11. Cost direction

MVP can run mostly on free tiers, but production stability improves with paid Render instances and better queue/worker separation.

## 12. Not included in phase 1

- Team accounts
- Recruiter portal
- Automated LinkedIn scraping
- Direct external form filling
- Billing and subscriptions
- Full kanban dashboard

## 13. Rico identity

Rico is an AI job-search assistant for users seeking better job matches, application support, and application tracking. Product behavior should be professional, concise, proactive, and transparent about system limitations.

## 14. Testing coverage target

- onboarding state machine tests
- webhook idempotency tests, including concurrent duplicates
- chat flow tests with mocked provider responses
- user-isolation tests
- rate-limit simulation tests

## 15. Current implementation status

Merged:

- OpenAI rate-limit provider-state preservation

In progress:

- DB-backed Jotform webhook idempotency

Critical blocker:

- rotate exposed secrets before additional feature merges

Next engineering priority:

- strict JWT-derived user isolation across authenticated endpoints
