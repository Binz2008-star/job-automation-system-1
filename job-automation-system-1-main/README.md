# Rico AI — AI-Native UAE Career Companion

Rico AI is evolving this repository from a job automation pipeline into an **AI-native UAE career companion**.

Rico is designed to feel like:

```text
career friend + hiring partner + AI operator
```

not like:

```text
job board + long form + generic chatbot
```

Rico learns from the user through chat and actions, scans UAE jobs in the background, scores matches, explains the best opportunities, helps with applications, tracks progress, and reminds the user what to do next.

---

## Public Quick Start

Primary public onboarding form:

**Rico AI Quick Start**  
https://form.jotform.com/261278237812056

Users should start with only:

- first name
- Telegram username
- dream job
- preferred UAE city
- anything Rico should avoid
- optional CV
- consent

Everything else should be learned progressively through chat, CV parsing, job actions, and outcomes.

---

## Existing System Foundation

The original repository already includes a UAE-focused job automation system with:

- job fetching
- filtering
- scoring
- Telegram notifications
- application tracking
- Gmail sync
- database fallback
- dashboard generation
- follow-up reminders
- feedback loop

Rico AI now sits on top of that system as the agent-first product layer.

---

## Rico Product Promise

Rico helps the user feel:

> I am not doing this job search alone anymore.

Rico should:

- understand the user's career goal
- remember preferences
- learn from chat and behavior
- scan UAE jobs in the background
- show only strong matches
- explain why a job fits
- help draft honest applications
- prepare interview notes
- track application progress
- send useful Telegram alerts
- stay safe and permission-based

---

## Architecture

```text
Rico Quick Start Form
        ↓
Jotform Webhook
        ↓
FastAPI Rico Server
        ↓
Rico Safety + NLU + Memory
        ↓
OpenAI Tool-Calling Agent
        ↓
Rico Tool Registry
        ↓
Existing Job Automation System
        ↓
Neon Database + Telegram + Dashboard
```

Legacy pipeline remains available:

```text
JobSpy
  ↓
Filter
  ↓
Scoring
  ↓
Applications Tracking
  ↓
Telegram Notifications
  ↓
Dashboard
  ↓
Follow-up Reminders
  ↓
Feedback Loop
```

---

## Rico Modules

```text
src/rico_agent.py              # Agent orchestration and profile model
src/rico_repo_adapter.py       # Bridge to existing job automation system
src/rico_chat_api.py           # Chat-first controller
src/rico_memory.py             # Lightweight JSON memory fallback
src/rico_db.py                 # Neon/PostgreSQL Rico tables
src/rico_nlu.py                # English/Arabic/mixed language understanding
src/rico_safety.py             # Guardrails and high-impact action checks
src/rico_identity.py           # Canonical Rico identity and system prompt
src/rico_quality.py            # Recommendation and response quality checks
src/rico_env.py                # Environment readiness validation
src/rico_server.py             # FastAPI server and webhook routes
src/rico_jotform_webhook.py    # Jotform onboarding handler
src/rico_telegram_webhook.py   # Telegram webhook handler
src/rico_telegram_ui.py        # Telegram buttons and job card helpers
src/rico_openai_agent.py       # OpenAI reasoning/tool-calling layer
src/rico_tool_registry.py      # Tools exposed to Rico's AI agent
src/cv_parser.py               # CV parsing and profile extraction
```

---

## Environment Variables

```env
DATABASE_URL=postgresql://user:password@host:port/database
OPENAI_API_KEY=your_openai_key
RICO_OPENAI_MODEL=gpt-4.1-mini
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_MODEL=deepseek-v4-flash
RICO_AI_PROVIDER=deepseek

TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_default_chat_id

JOTFORM_API_KEY=your_jotform_key
JOTFORM_FORM_ID=261278237812056
JOTFORM_WEBHOOK_SECRET=your_webhook_secret

EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_app_password
EMAIL_TO=your_email@gmail.com

REDIS_URL=redis://localhost:6379
RICO_ENABLE_AUTO_APPLY=false
RICO_REQUIRE_APPROVAL_FOR_APPLICATIONS=true
RICO_ENABLE_TELEGRAM=true
RICO_ENABLE_LEARNING=true
RICO_MATCH_STRICTNESS=balanced
RICO_DEFAULT_LANGUAGE=mixed
```

Never commit API keys or secrets to GitHub.

---

## Setup

### Prerequisites

- Python 3.11+
- Neon/PostgreSQL database
- Telegram bot
- OpenAI API key
- Jotform form/webhook
- Gmail app password, if using Gmail sync

### Install

```bash
git clone https://github.com/Binz2008-star/job-automation-system-1.git
cd job-automation-system-1
pip install -r requirements.txt
```

---

## Run Rico API Server

```bash
uvicorn src.rico_server:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Chat endpoint:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo","message":"Find HSE Manager jobs in Dubai"}'
```

---

## Webhooks

### Jotform

```http
POST /api/webhooks/jotform
```

Use this endpoint for the Rico AI Quick Start form:

```env
JOTFORM_FORM_ID=261278237812056
```

### Telegram

```http
POST /api/telegram/webhook
```

Rico uses Telegram as the main habit loop for:

- job alerts
- match explanations
- save/ignore/apply actions
- reminders
- interview preparation

---

## Run Legacy Daily Pipeline

The existing automation system still works independently:

```bash
python -m src.run_daily
```

This remains useful for scheduled job discovery, scoring, reports, Gmail sync, dashboard generation, and follow-up reminders.

---

## Smoke Test

```bash
python scripts/test_rico_startup.py
```

This checks:

- Rico env readiness
- identity
- NLU
- safety
- quality gate
- chat flow

without requiring every external service to be live.

---

## Safety Rules

Rico must never:

- fake experience
- forge documents
- lie on behalf of the user
- share private data without permission
- send applications without approval
- spam recruiters
- discriminate using protected traits

Rico must always:

- stay honest
- protect user data
- ask before high-impact actions
- keep the user in control
- allow preferences to change anytime

---

## Product Standards

Rico should be:

- chat-first
- Telegram-first
- low-friction
- emotionally supportive
- background-working
- intelligent
- safe
- habit-forming

Every recommendation should include:

- match score
- simple explanation
- next action
- user control

---

## Important Project Docs

```text
RICO_PRODUCT_MANIFESTO.md       # Product identity and philosophy
RICO_HARDENING_CHECKLIST.md     # Production and safety checklist
RICO_CLOUD_SETUP.md             # Cloud deployment and integration guide
ARCHITECTURE_RICO_AI.md         # Production architecture blueprint
```

---

## Current Status

Rico currently has:

- Quick Start onboarding form
- FastAPI server scaffold
- Jotform webhook route
- Telegram webhook route
- CV parser
- Neon DB layer
- memory fallback
- multilingual NLU
- safety layer
- quality layer
- OpenAI agent scaffold
- tool registry
- existing pipeline adapter

Still required for full production:

- live cloud deployment
- webhook verification
- Telegram inline callback execution
- Redis workers
- WebSocket streaming
- frontend chat UI
- auth and rate limiting
- secure CV storage
- full OpenAI tool execution loop

---

## License

MIT
