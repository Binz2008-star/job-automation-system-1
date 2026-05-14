# Rico AI — Cloud Setup & Integration Guide

## Purpose

This document explains exactly how to finish, deploy, and scale Rico AI using the existing `job-automation-system-1` repository and Neon database.

Rico already contains:

- agent orchestration
- multilingual NLU
- safety layer
- memory layer
- repo adapter
- recommendation logic
- Telegram hooks
- quality gates
- onboarding form

This guide focuses on what cloud/devops/backend work still needs to be completed.

---

# Current Rico Files

## Added Agent Files

```text
src/rico_agent.py
src/rico_repo_adapter.py
src/rico_chat_api.py
src/rico_memory.py
src/rico_nlu.py
src/rico_safety.py
src/rico_identity.py
src/rico_quality.py
src/rico_db.py
```

---

# Existing System Reused by Rico

Rico already consumes:

```text
src/run_daily.py
src/scoring.py
src/llm_scorer.py
src/job_agent.py
src/applications.py
src/telegram_bot.py
src/gmail_importer.py
src/dashboard.py
src/filter.py
src/job_sources.py
src/feedback_loop.py
```

---

# Required Environment Variables

```env
# Existing
DATABASE_URL=
OPENAI_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMAIL_USER=
EMAIL_PASS=

# Rico-specific
RICO_ENV=production
RICO_DEFAULT_LANGUAGE=en
RICO_ENABLE_AUTO_APPLY=false
RICO_ENABLE_LEARNING=true
RICO_ENABLE_TELEGRAM=true
RICO_ENABLE_GMAIL_SYNC=true

# Jotform (active onboarding form)
JOTFORM_API_KEY=
JOTFORM_FORM_ID=261277622782059
JOTFORM_WEBHOOK_SECRET=

# Frontend
NEXT_PUBLIC_API_URL=

# Redis / queues
REDIS_URL=
```

---

# Env contract — which key powers which subsystem

| Env var | Canonical name | Used by | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ | `src/rico_openai_agent.py` | Conversational reply for open-ended chat messages. When unset, Rico falls back to a safe templated reply. |
| `OPEN_AI_API` | ⚠️ legacy fallback | `src/rico_openai_agent.py` | Read only if `OPENAI_API_KEY` is missing. Standardize on `OPENAI_API_KEY` in production. |
| `RICO_OPENAI_MODEL` | ✅ optional | `src/rico_openai_agent.py` | Override the OpenAI model. Default: `gpt-4.1-mini`. |
| `HF_TOKEN` | ✅ | `src/llm_scorer.py`, `src/job_agent.py` | Embedding-based job scoring and HF text generation. NOT used in the chat reply path. |
| `JOTFORM_FORM_ID` | ✅ | `src/api/routers/rico_chat.py` | Active onboarding form ID (comma-separated list supported). |
| `JOTFORM_WEBHOOK_SECRET` | ✅ | `src/api/routers/rico_chat.py` | Fail-closed webhook verification. When set, missing/wrong secret returns 403. |
| `JOTFORM_API_KEY` | optional | declared in `src/rico_env.py` | Reserved for CV/file retrieval from Jotform submissions. |
| `JOTFORM_RICO_FORM_ID` | ❌ unused | nothing | Declared in some `.env` files but no code reads it. Use `JOTFORM_FORM_ID` only. |

---

# Database Setup

Rico uses the SAME Neon PostgreSQL database.

Run:

```python
from src.rico_db import init_rico_db
init_rico_db()
```

This creates:

```text
rico_users
rico_profiles
rico_agent_settings
rico_chat_history
rico_learning_signals
rico_job_recommendations
rico_alerts
```

without affecting the existing system tables.

---

# FastAPI Server (Required)

## Create

```text
src/rico_server.py
```

Recommended stack:

- FastAPI
- uvicorn
- pydantic
- WebSockets

---

# Required Endpoints

## Chat

```http
POST /api/chat
```

Request:

```json
{
  "user_id": "123",
  "message": "Find HSE jobs in Dubai"
}
```

Response:

```json
{
  "message": "I found 5 strong matches",
  "matches": []
}
```

---

## Onboarding Webhook

```http
POST /api/webhooks/jotform
```

Tasks:

- validate webhook
- map fields
- create user
- save profile
- download CV
- trigger first search
- send Telegram welcome

---

## Telegram Webhook

```http
POST /api/telegram/webhook
```

Support:

- Apply button
- Save button
- Ignore button
- See Details
- Cover Letter
- Interview Prep

---

# CV Parsing Layer

## Create

```text
src/cv_parser.py
```

Use:

- pdfplumber
- PyMuPDF
- python-docx

Extract:

- skills
- companies
- experience
- certifications
- education
- tools
- languages

Then enrich Rico profile automatically.

---

# OpenAI Tool Calling

## Required

Rico should become a real tool-calling agent.

Recommended tools:

```text
search_jobs
score_jobs
save_job
ignore_job
apply_job
write_cover_letter
prepare_interview
update_preferences
send_telegram_alert
```

---

# Frontend

## Recommended

```text
Next.js
Tailwind
shadcn/ui
```

## UX Principle

The user should feel:

```text
I just talk to Rico.
```

NOT:

```text
I operate a job board.
```

---

# Recommended Frontend Pages

```text
/
/chat
/dashboard
/profile
/applications
/settings
```

---

# Chat UI Requirements

## Required Features

- streaming responses
- upload CV
- message history
- Telegram-style bubbles
- action buttons
- mobile responsive
- typing indicator
- recommendation cards

---

# Real-Time Infrastructure

Recommended:

```text
Redis
Celery or RQ
WebSockets
```

Background jobs:

- daily job search
- Telegram alerts
- Gmail sync
- follow-up reminders
- weekly reports
- recommendation refresh

---

# Telegram Experience

Rico should behave like a real assistant inside Telegram.

Example:

```text
Rico:
I found 3 strong matches today.
```

Buttons:

```text
[Apply]
[Save]
[Ignore]
[Interview Prep]
```

---

# Safety Rules

Rico must NEVER:

- fake experience
- forge documents
- share passwords
- expose OTPs
- mass-spam recruiters
- discriminate illegally
- auto-submit without consent

---

# Production Deployment

## Recommended Infrastructure

```text
Frontend: Vercel
Backend: Railway / Render / Fly.io
Database: Neon
Queues: Redis Cloud
Storage: S3 or Cloudinary
Monitoring: Better Stack / Sentry
```

---

# Docker

Recommended files:

```text
Dockerfile
compose.yml
```

Services:

```text
api
worker
redis
scheduler
```

---

# CI/CD

Recommended:

```text
GitHub Actions
```

Pipelines:

- lint
- tests
- build
- deploy

---

# High Priority Next Build Order

## Phase 1

1. FastAPI server
2. Jotform webhook
3. Telegram webhook
4. PostgreSQL integration
5. CV parser
6. Chat endpoint

## Phase 2

7. OpenAI tool-calling
8. Frontend chat UI
9. Vector memory
10. Real-time streaming

## Phase 3

11. Multi-user scaling
12. Billing
13. Admin dashboard
14. AI analytics
15. Voice assistant

---

# Final Product Vision

Rico should feel like:

```text
AI recruiter
+
career advisor
+
autonomous assistant
+
hiring partner
```

working continuously toward helping users land stronger UAE jobs.
