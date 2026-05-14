# Job Automation System — Full Overview
**Roben Edwan | ESG/HSE Job Hunter | UAE**
*Last updated: May 5, 2026*

---

## What This System Does

An autonomous job hunting pipeline that runs twice daily, finds relevant ESG/HSE/Environmental jobs in the UAE, scores them using AI, notifies via Telegram, tracks applications, and monitors Gmail for responses — automatically.

---

## System Architecture

```
Data Sources (Indeed · Bayt · NaukriGulf · GulfTalent)
        ↓
job_sources.py      — Fetch · Deduplicate · Filter
        ↓
llm_scorer.py       — HF Embedding + Keyword Hybrid Score
        ↓
run_daily.py        — Orchestrator (main pipeline)
    ├── notifier.py          → Email (broken) + Telegram ✅
    ├── gmail_importer.py    → Monitor replies · Auto-update status
    ├── feedback_loop.py     → Learn from outcomes
    ├── dashboard.py         → Build HTML dashboard
    └── follow_up.py         → 14-day no-reply reminders
        ↓
GitHub Actions      — Runs 08:00 + 18:00 UAE (04:00 + 14:00 UTC)
        ↓
GitHub Pages        — Live dashboard auto-deployed
```

---

## Current System Status

### What Is Working ✅

| Component | Status | Detail |
|-----------|--------|--------|
| Job fetch | Live | 43 jobs/run from Indeed |
| HF scoring (local) | Live | hf=43 keyword=0 |
| HF scoring (GitHub) | Partial | hf=0 keyword=43 — token whitespace issue |
| High quality jobs | Live | 21 jobs/run (threshold 45) |
| Telegram | Live | Instant daily report |
| Email | Broken | App Password auth fails |
| Gmail sync | Live | 22 emails/run · scam filter active |
| Application tracker | Live | 14 apps · auto-updated from Gmail |
| PostgreSQL (Neon) | Live | Connected · ~1600ms latency |
| GitHub Actions | Live | 68s runtime · 2x daily |
| Dashboard | Live | GitHub Pages · auto-updated |
| Follow-up reminder | Live | 14-day Telegram alert |
| Feedback loop | Partial | Needs 5 matched outcomes · 1 so far |

### What Needs Fixing ⚠️

| Issue | Priority | Fix |
|-------|----------|-----|
| HF_TOKEN whitespace on GitHub | High | Strip fix deployed — verify next run |
| Email auth failed | Low | Skip — Telegram works |
| Feedback loop inactive | Low | Will activate with more replies |

---

## Applications Tracked

| Company | Position | Status |
|---------|----------|--------|
| Parsons Corporation | Environmental & Sustainability Manager | Applied |
| Al Jomaih Energy | HSSE Manager-CCGT | Applied (reply received) |
| Amazon | WHS Manager UAE FC | Applied |
| Strabag | Project Manager | Applied |
| EGA | Senior Associate - ESG Compliance | Applied |
| Larsen & Toubro | EHS Manager | Applied |
| Penta Global Engineering | Project HSE Manager | Applied |
| Talents Tide | Project HSE Manager | Applied |
| LOBA GROUP | ESG Manager | Applied |
| KAYALI | Sustainability Manager | Applied |
| Confidential Dubai | HSE Manager | Applied |
| Snoonu | Head of Operations | Applied |

---

## File Structure

```
job-automation-system-1/
├── src/
│   ├── run_daily.py              — Main pipeline orchestrator
│   ├── job_sources.py            — Indeed scraper (5 ESG/HSE queries)
│   ├── llm_scorer.py             — HF embedding + keyword hybrid
│   ├── scoring.py                — Keyword fallback scorer
│   ├── profile.py                — Roben's CV-aware candidate profile
│   ├── filter.py                 — Job deduplication
│   ├── gmail_importer.py         — Gmail monitor + scam filter
│   ├── feedback_loop.py          — Learning from outcomes
│   ├── response_intelligence.py  — Application status intelligence
│   ├── decision_engine.py        — Job decision scoring
│   ├── applications.py           — Application tracking
│   ├── job_history.py            — Job history management
│   ├── db.py                     — PostgreSQL + JSON fallback
│   ├── dashboard.py              — HTML dashboard generator
│   ├── notifier.py               — Email notifications
│   ├── telegram_bot.py           — Telegram alerts
│   ├── follow_up.py              — 14-day follow-up reminders
│   ├── weekly_report.py          — Weekly Telegram summary
│   ├── linkedin_importer.py      — LinkedIn CSV import tool
│   └── update_application_response.py — CLI application tracker
├── tests/
│   └── unit/test_feedback_loop.py — 35 tests passing
├── data/
│   ├── seen_jobs.json            — Deduplication cache
│   ├── applied_jobs.json         — Application tracker
│   ├── llm_score_cache.json      — HF score cache
│   └── gmail_review_queue.json   — Gmail review queue
├── .github/
│   └── workflows/
│       └── daily-job-bot.yml     — GitHub Actions scheduler
├── docs/
│   └── index.html                — GitHub Pages dashboard
├── .env                          — Local secrets (not committed)
├── requirements.txt              — Python dependencies
└── dashboard.html                — Generated dashboard
```

---

## Candidate Profile

**Name:** Roben Edwan
**Location:** Ajman, UAE
**Experience:** 10+ years
**Visa:** Dependent (renewal needed)

**Target Roles:**
- ESG Manager / Environmental Manager / Sustainability Manager
- HSE Manager / QHSE Manager / EHS Manager / HSSE Manager
- Environmental Compliance Manager / Compliance Manager
- Operations Manager (environmental/industrial context)
- General Manager (environmental services)

**Key Skills:**
- Environmental compliance, ISO 14001, UAE municipalities
- HSE/QHSE management systems
- Waste management, FOG control, wastewater
- Multi-site operations (80+ locations, 15+ staff)
- ESG reporting and sustainability strategy

**Disqualifiers (auto-filtered):**
- UAE National Only
- Junior / Entry Level / Intern
- Site Engineer / Quantity Surveyor / Civil Engineer
- Software Engineer / IT roles
- Medical / Healthcare / Sales

---

## Scoring System

**Method:** Hybrid (50% HF embedding + 50% keyword)

**HF Model:** `sentence-transformers/all-MiniLM-L6-v2`
**API:** `router.huggingface.co/hf-inference/models/...`
**Cache:** `data/llm_score_cache.json`

**Thresholds:**
- Score ≥ 45 → high_quality (shown in Telegram)
- Score < 45 → filtered out

**Fallback:** keyword scoring if HF unavailable

---

## Gmail Intelligence

**What it detects:**
- Application confirmations → status: `applied`
- Interview requests → status: `interview_scheduled`
- Rejections → status: `rejected`
- Offers → status: `offer_extended`

**Scam filter blocks:**
- `theuaejobs.com` and similar
- "You may be eligible" patterns
- LinkedIn notification emails

**Matching method:** Semantic company name matching (not URL-based)

---

## Infrastructure

| Component | Service | Detail |
|-----------|---------|--------|
| Database | Neon PostgreSQL | Cloud · always on |
| CI/CD | GitHub Actions | Free tier · 2x daily |
| Dashboard | GitHub Pages | Free · auto-deploy |
| Job Scraping | JobSpy + Indeed | No API key |
| AI Scoring | HuggingFace Inference API | Free tier · HF_TOKEN |
| Notifications | Telegram Bot | Free · instant |
| Gmail API | Google OAuth2 | credentials.json |

**GitHub Secrets required:**
- `EMAIL_USER` / `EMAIL_PASS` / `EMAIL_TO`
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
- `DATABASE_URL`
- `HF_TOKEN`
- `GMAIL_CREDENTIALS_JSON` / `GMAIL_TOKEN_JSON`

---

## What To Build Next — Agent Layer

| File | Purpose | Priority |
|------|---------|----------|
| `src/job_agent.py` | AI decides apply/watch/skip · writes cover letter | High |
| `src/telegram_actions.py` | One-tap Apply button per job | High |
| `src/followup_writer.py` | Auto-draft follow-up after 14 days | Medium |
| Bayt.com scraper | Add Gulf's biggest job board | Medium |

---

## Daily Pipeline Execution Order

```
1. init_db()                 — Connect PostgreSQL
2. build_orchestrator()      — Init feedback loop engine
3. fetch_and_score()         — Get jobs + score with HF
4. persist_history()         — Save to DB + JSON
5. notify()                  — Email (broken) + Telegram
6. apply_assistant()         — Disabled (interactive input)
7. sync_gmail()              — Read + classify replies
8. run_feedback_loop()       — Learn (needs 5 outcomes)
9. regenerate_dashboard()    — Build HTML
10. deploy_dashboard()       — Push to GitHub Pages
11. follow_up()              — Check 14-day reminders
```

---

## Key Commands

```bash
# Run pipeline manually
python -m src.run_daily

# Health check (10/10 expected)
python -m src.health_check

# Gmail dry run
python -m src.gmail_importer --dry-run --days 30

# Track an application
python -m src.update_application_response \
    --link "https://..." --status applied --notes "Applied via LinkedIn"

# Update application status
python -m src.update_application_response \
    --link "https://..." --status interview_scheduled

# Weekly report
python -m src.weekly_report

# Follow-up check
python -m src.follow_up

# LinkedIn import (when export arrives)
python -m src.linkedin_importer --zip export.zip --dry-run
```

---

## Links

- **Repo:** https://github.com/Binz2008-star/job-automation-system-1
- **Dashboard:** https://binz2008-star.github.io/job-automation-system-1/
- **Neon DB:** https://console.neon.tech
- **GitHub Actions:** https://github.com/Binz2008-star/job-automation-system-1/actions

---

*System runs autonomously. Check Telegram for daily updates.*
*If a company replies — update status immediately using the CLI command above.*
