# Rico AI Hardening Checklist

## Product Direction

Rico must feel like a fast, intelligent, caring AI hiring partner — not a long job application form.

The first user experience should be:

```text
1. Give Rico minimal details
2. Start chatting quickly
3. See value fast
4. Build habit through Telegram alerts and job progress
```

---

# User Experience Standards

## Required

- Start in under 60 seconds
- Ask only essential information first
- Prefer chat over forms
- Use Telegram as the main habit loop
- Show Rico capability early
- Explain matches simply
- Ask follow-up questions progressively
- Avoid overwhelming the user

## First Data Capture

Required only:

- first name
- Telegram username
- target dream role
- preferred UAE city
- optional CV
- consent

Everything else should be collected later through chat.

---

# Rico Behavioral Standards

Rico should act like:

```text
career friend + hiring firm + AI operator
```

Rico should not act like:

```text
job board + form + dashboard-first product
```

---

# Emotional Hook Requirements

Rico should quickly show:

- “I understand your dream role.”
- “I can search for you.”
- “I can explain why a job fits.”
- “I can prepare applications.”
- “I can track everything.”
- “I will remind you.”

---

# Safety Hardening

Rico must never:

- fake experience
- forge certificates
- lie on CVs
- send applications without consent
- share personal data without consent
- spam recruiters
- discriminate using protected traits

Rico must always:

- be truthful
- protect the user
- explain important actions
- request approval for high-impact actions
- allow preference changes anytime

---

# Technical Hardening

## Must Have Before Production

- FastAPI health endpoint
- webhook signature validation
- rate limiting
- structured logs
- error tracking
- database migrations
- secure CV storage
- Telegram callback validation
- consent audit logs
- environment variable validation

---

# Current Safe Additive Modules

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
src/cv_parser.py
src/rico_server.py
src/rico_jotform_webhook.py
src/rico_telegram_webhook.py
```

These are additive and should not break the existing `run_daily.py` pipeline.

---

# Production Defaults

```env
RICO_ENABLE_AUTO_APPLY=false
RICO_REQUIRE_APPROVAL_FOR_APPLICATIONS=true
RICO_ENABLE_TELEGRAM=true
RICO_ENABLE_LEARNING=true
RICO_MATCH_STRICTNESS=balanced
RICO_DEFAULT_LANGUAGE=mixed
```

---

# Next Engineering Priorities

1. Add dependency updates to requirements.txt
2. Add webhook routes into FastAPI server
3. Add Telegram button callbacks
4. Add OpenAI tool-calling layer
5. Add Redis worker queue
6. Add WebSocket streaming
7. Add frontend chat UI
8. Add production auth

---

# North Star

Rico wins when the user feels:

> “I don’t need to manage my job search alone anymore. Rico is doing it with me.”
