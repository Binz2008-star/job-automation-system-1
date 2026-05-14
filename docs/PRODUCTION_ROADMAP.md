# Rico AI — Production Architecture Transformation

**Version:** 2.0  
**Date:** May 15, 2026  
**Prepared for:** Base44  
**Status:** Production migration blueprint

---

## 1. Executive Summary

Rico AI is currently a **functional prototype** with a production-capable FastAPI backend, a scaffolded Next.js frontend, and a battle-tested daily automation pipeline. This document maps the exact path from prototype to a **multi-tenant SaaS platform** serving thousands of UAE job seekers.

**Core thesis:** Migrate incrementally. The legacy pipeline stays operational while we wrap it in a modern async, observable, and horizontally scalable architecture.

---

## 2. Architectural Weaknesses (Current State)

### 2.1 Critical Bottlenecks

| Weakness | Severity | Why It Hurts |
|----------|----------|-------------|
| **Synchronous pipeline** | High | `run_daily.py` runs everything in one thread. Job fetching blocks scoring. Scoring blocks notifications. 68s runtime will scale linearly with job volume. |
| **~1600ms DB latency** | High | Neon free-tier RTT. Every query pays 1.6s penalty. Profile lookups, chat history, audit logs all suffer. |
| **No connection pooling** | High | `psycopg2` creates fresh connections per request. Under concurrent load this collapses. |
| **JSON fallback as primary** | Medium | When DB is down, Rico falls back to JSON files. No ACID guarantees. Race conditions on concurrent writes. |
| **Single AI provider at a time** | Medium | OpenAI fails → DeepSeek → HF, but each check is synchronous and adds latency. No circuit breaker with backoff. |
| **No async workers** | High | Telegram notifications, email sends, dashboard generation, Gmail sync all run inline. One slow Gmail scan stalls the whole pipeline. |
| **No message queue** | High | Cannot retry failed jobs, cannot distribute work across processes, cannot scale horizontally. |
| **GitHub Actions as scheduler** | Medium | Tight coupling to GitHub. No visibility into queue depth, no retry logic, no worker autoscaling. |
| **No WebSocket streaming** | Medium | Chat responses are full REST round-trips. AI inference (1-3s) feels sluggish without streaming. |
| **Frontend is scaffold-only** | Medium | Next.js app exists but has minimal pages. No real-time chat UI, no dashboard, no profile editing. |
| **No vector search** | High | Job recommendations use keyword matching + HF embeddings. No semantic search. No memory retrieval via vectors. |
| **No caching layer** | Medium | Profile lookups, job scores, chat history all hit DB every time. No Redis caching for hot data. |
| **No structured logging** | Medium | Python `logging.basicConfig` with plain text. Cannot parse or query logs in production. |
| **No distributed tracing** | Medium | Cannot trace a single chat request through intent → profile → AI → response across modules. |
| **No API versioning strategy** | Low | All routes under `/api/v1/` but no migration path for v2. |
| **Secrets in env only** | Medium | `.env` is the only secret store. No secret rotation, no encryption at rest for sensitive fields. |

### 2.2 Technical Debt Inventory

| Debt | File(s) | Impact | Effort |
|------|---------|--------|--------|
| Monolithic `rico_chat_api.py` (1,576 LOC) | `src/rico_chat_api.py` | Cognitive overload, hard to test, brittle | 2-3 days refactor into handlers |
| Inline regex compilation | `src/rico_chat_api.py` | Re-compiled on every import | 30 min |
| `getattr`/`is_dataclass` branching | `src/rico_chat_api.py` | Profile normalization scattered across 3 methods | 2 hours |
| Mixed sync/async in FastAPI | `src/api/app.py` | Lifespan is async but DB init calls sync code | 1 hour |
| HF token whitespace bug | `src/llm_scorer.py` | Breaks scoring on GitHub Actions | Already fixed — verify |
| Broken email notifier | `src/notifier.py` | Dead code path | 2 hours to remove or fix |
| Multiple dashboard files | `dashboard*.py` (5 files) | Confusion about which is canonical | 1 hour to consolidate |
| Duplicate profile logic | `profile.py`, `rico_agent.py`, `profile_repo.py` | Three representations of the same entity | 1 day to unify |
| No type hints on dynamic data | `feedback_loop.py`, `decision_engine.py` | Runtime errors instead of static analysis | 1 day |

---

## 3. Production Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CDN / Edge (Cloudflare)                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────────────┐   │
│  │ Static     │  │ DDoS       │  │ Bot      │  │ WAF Rules            │   │
│  │ Assets     │  │ Protection │  │ Detection│  │ (Rate limit / Block) │   │
│  └────┬───────┘  └────┬───────┘  └────┬───────┘  └─────────┬──────────┘   │
└───────┼───────────────┼───────────────┼────────────────────┼──────────────┘
        │               │               │                    │
        └───────────────┴───────────────┴────────────────────┘
                              │
        ┌─────────────────────▼─────────────────────┐
        │         LOAD BALANCER (NGINX / ALB)       │
        │   • SSL termination                       │
        │   • Rate limiting (per IP)                │
        │   • Health check routing                  │
        └─────────────────────┬─────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
   │ API Pod │          │ API Pod │          │ API Pod │
   │  (x3)   │          │  (x3)   │          │  (x3)   │
   └────┬────┘          └────┬────┘          └────┬────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
        ┌────────────────────▼────────────────────┐
        │           REDIS (Valkey / ElastiCache) │
        │  ┌─────────────┐  ┌─────────────────┐  │
        │  │ Celery      │  │ Session Cache   │  │
        │  │ Broker      │  │ + Rate Limit    │  │
        │  │ + Results   │  │ + Hot Data      │  │
        │  └─────────────┘  └─────────────────┘  │
        └────────────────────┬────────────────────┘
                             │
        ┌────────────────────▼────────────────────┐
        │      WORKER POOL (Celery + Prefork)     │
        │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
        │  │ Pipeline │ │ Chat AI  │ │ Gmail    │ │
        │  │ Worker   │ │ Worker   │ │ Worker   │ │
        │  │ (x2)     │ │ (x3)     │ │ (x1)     │ │
        │  └──────────┘ └──────────┘ └──────────┘ │
        └─────────────────────────────────────────┘
                             │
        ┌────────────────────▼────────────────────┐
        │      NEON POSTGRESQL + PGVECTOR         │
        │  ┌─────────────┐  ┌─────────────────┐   │
        │  │ Primary     │  │ Vector Extension│   │
        │  │ (connection │  │ (semantic       │   │
        │  │  pooled)    │  │  search)        │   │
        │  └─────────────┘  └─────────────────┘   │
        └─────────────────────────────────────────┘
                             │
        ┌────────────────────▼────────────────────┐
        │              OBSERVABILITY              │
        │  ┌─────────┐ ┌─────────┐ ┌──────────┐  │
        │  │Grafana  │ │Prometheus│ │ Jaeger   │  │
        │  │Dashboard│ │Metrics  │ │Tracing  │  │
        │  └─────────┘ └─────────┘ └──────────┘  │
        └─────────────────────────────────────────┘
```

---

## 4. Scalability Improvements

### 4.1 Database Layer

**Current:** Direct `psycopg2` connections, ~1600ms latency, no pooling  
**Target:** Connection pooling + read replicas + query optimization

```python
# src/db_pool.py  (NEW)
import os
from contextlib import contextmanager
from typing import Generator
import psycopg2.pool

_DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None

def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=_DATABASE_URL,
            connect_timeout=10,
            options="-c statement_timeout=30000",
        )
    return _pool

@contextmanager
def get_db_connection() -> Generator:
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)
```

**Migrations needed:**
1. Add `pgvector` extension for semantic search
2. Add indexes on hot queries:
   ```sql
   CREATE INDEX idx_jobs_fetched_at ON jobs(fetched_at DESC);
   CREATE INDEX idx_chat_history_user_ts ON chat_history(user_id, timestamp DESC);
   CREATE INDEX idx_applications_user_status ON applications(user_id, status);
   CREATE INDEX idx_audit_log_user_ts ON action_audit_log(user_email, timestamp DESC);
   ```
3. Partition `action_audit_log` by month (it grows fastest)

### 4.2 Async Processing with Celery + Redis

**Current:** Everything synchronous in `run_daily.py`  
**Target:** Distributed task queue with retry, dead-letter, and monitoring

**Worker topology:**

| Queue | Workers | Tasks | Priority |
|-------|---------|-------|----------|
| `pipeline` | 2 | job_fetch, scoring, dashboard | Normal |
| `chat` | 3 | AI inference, memory update | High |
| `gmail` | 1 | sync_gmail, reply classification | Low |
| `notifications` | 2 | telegram, email, follow-up | High |
| `default` | 2 | onboarding, profile update | Normal |

### 4.3 Caching Strategy

**Hot data (Redis, 5-min TTL):**
- User profile (fetched on every chat)
- Job score cache (rarely changes)
- Chat history last 10 messages

**Warm data (Redis, 1-hour TTL):**
- Job listings (fetched daily, immutable after fetch)
- Role intelligence results
- Match explanations

**Cold data (DB only):**
- Full chat history
- Audit logs
- Learning signals

### 4.4 Horizontal Scaling

**API tier:** Stateless FastAPI pods behind a load balancer. Scale to N replicas.
**Worker tier:** Celery workers scale independently per queue.
**Database:** Neon Pro tier with read replicas. Connection pooling (PgBouncer) on the app side.

---

## 5. Deployment Architecture

### 5.1 Docker Strategy

**Multi-stage Dockerfile for API:**

```dockerfile
# Dockerfile.api
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpq5 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY src/ ./src/
COPY data/ ./data/
EXPOSE 8000
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Worker Dockerfile:**

```dockerfile
# Dockerfile.worker
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY src/ ./src/
COPY data/ ./data/
CMD ["celery", "-A", "src.workers.celery_app", "worker", "-Q", "pipeline,chat,gmail,notifications,default", "--concurrency", "4", "-l", "info"]
```

### 5.2 Kubernetes Manifests

See `k8s/` directory for full manifests. Key resources:

| Resource | Replicas | CPU | Memory | HPA Target |
|----------|----------|-----|--------|------------|
| Deployment/api | 3 | 500m | 512Mi | 70% CPU |
| Deployment/worker | 2-10 | 500m | 1Gi | Queue depth |
| StatefulSet/redis | 1 | 250m | 512Mi | N/A |
| CronJob/pipeline | 1 (per run) | 500m | 512Mi | N/A |

### 5.3 Local Development (docker-compose)

See `docker-compose.yml` at repo root. Spins up:
- API server (auto-reload)
- Redis
- PostgreSQL (local, not Neon)
- Celery worker (auto-reload)
- Flower (Celery monitoring UI)

---

## 6. Async Processing: Celery Worker Architecture

### 6.1 Celery App Configuration

```python
# src/workers/celery_app.py
from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "rico",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "src.workers.pipeline_tasks",
        "src.workers.chat_tasks",
        "src.workers.notification_tasks",
        "src.workers.gmail_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Dubai",
    enable_utc=True,
    task_routes={
        "src.workers.pipeline_tasks.*": {"queue": "pipeline"},
        "src.workers.chat_tasks.*": {"queue": "chat"},
        "src.workers.notification_tasks.*": {"queue": "notifications"},
        "src.workers.gmail_tasks.*": {"queue": "gmail"},
    },
    task_default_queue="default",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)
```

### 6.2 Task Definitions

```python
# src/workers/pipeline_tasks.py
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_and_score_jobs(self, user_id: str = None):
    """Fetch jobs and score them. Retry on transient failures."""
    try:
        from src.job_sources import get_jobs
        from src.llm_scorer import score_jobs_llm
        from src.filter import filter_new_jobs

        raw_jobs = get_jobs()
        new_jobs = filter_new_jobs(raw_jobs)
        scored = score_jobs_llm(new_jobs)
        return {"fetched": len(raw_jobs), "new": len(new_jobs), "scored": len(scored)}
    except Exception as exc:
        logger.exception("fetch_and_score_jobs failed")
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=2)
def generate_dashboard(self):
    """Build and deploy dashboard HTML."""
    try:
        from src.dashboard import build_dashboard
        build_dashboard()
        return {"status": "deployed"}
    except Exception as exc:
        raise self.retry(exc=exc)
```

```python
# src/workers/chat_tasks.py
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=2, default_retry_delay=30, time_limit=30)
def process_chat_message(self, user_id: str, message: str, session_id: str):
    """Process chat message async with timeout guard."""
    try:
        from src.rico_chat_api import RicoChatAPI
        api = RicoChatAPI()
        # Use existing chat flow
        response = api.chat(user_id=user_id, message=message)
        return response
    except Exception as exc:
        logger.exception("process_chat_message failed")
        raise self.retry(exc=exc)
```

```python
# src/workers/notification_tasks.py
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def send_telegram_alert(self, chat_id: str, message: str):
    try:
        from src.telegram_bot import send_telegram_message
        send_telegram_message(chat_id, message)
        return {"sent": True}
    except Exception as exc:
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=2)
def send_follow_up_reminder(self, user_id: str, job_id: str):
    try:
        from src.follow_up import check_and_notify
        check_and_notify(user_id, job_id)
        return {"reminded": True}
    except Exception as exc:
        raise self.retry(exc=exc)
```

### 6.3 Pipeline Orchestration (Replacing run_daily.py)

```python
# src/workers/orchestrator.py
from celery import chain, group
from src.workers.celery_app import celery_app
from src.workers.pipeline_tasks import fetch_and_score_jobs, generate_dashboard
from src.workers.gmail_tasks import sync_gmail
from src.workers.notification_tasks import send_telegram_alert
from src.workers.chat_tasks import run_feedback_loop

def run_daily_pipeline(user_id: str = None):
    """Replace the monolithic run_daily.py with a distributed workflow."""
    workflow = chain(
        fetch_and_score_jobs.s(user_id),
        group(
            sync_gmail.s(),
            run_feedback_loop.s(),
        ),
        generate_dashboard.s(),
        send_telegram_alert.s(
            chat_id="default",
            message="Daily pipeline complete. Check your dashboard."
        ),
    )
    return workflow.apply_async()
```

---

## 7. WebSocket Streaming Architecture

### 7.1 FastAPI WebSocket Endpoint

```python
# src/api/websocket.py
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info("ws_connect user=%s total=%d", user_id, len(self.active_connections))

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)
        logger.info("ws_disconnect user=%s total=%d", user_id, len(self.active_connections))

    async def send_text(self, user_id: str, message: str):
        ws = self.active_connections.get(user_id)
        if ws:
            await ws.send_text(message)

manager = ConnectionManager()

@router.websocket("/ws/chat/{user_id}")
async def chat_websocket(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            message = payload.get("message", "")

            # Stream AI response in chunks
            async for chunk in stream_chat_response(user_id, message):
                await manager.send_text(user_id, json.dumps({
                    "type": "chunk",
                    "content": chunk,
                }))

            await manager.send_text(user_id, json.dumps({
                "type": "done",
            }))
    except WebSocketDisconnect:
        manager.disconnect(user_id)
```

### 7.2 Streaming AI Response

```python
# src/workers/chat_tasks.py  (extension)
async def stream_chat_response(user_id: str, message: str):
    """Yield text chunks from OpenAI streaming API."""
    from src.rico_openai_agent import RicoOpenAIAgent
    agent = RicoOpenAIAgent()
    async for chunk in agent.stream_response(user_id, message):
        yield chunk
```

---

## 8. Microservice Migration Roadmap

**Phase 0: Monolith Hardening (Week 1-2)**
- Add connection pooling
- Add Redis caching
- Add structured logging + metrics
- Add Celery for the daily pipeline only

**Phase 1: Worker Extraction (Week 3-4)**
- Move `run_daily.py` to Celery tasks
- Move Gmail sync to dedicated worker
- Move dashboard generation to worker
- Keep chat inline (latency-sensitive)

**Phase 2: Chat Service Extraction (Week 5-6)**
- Extract chat logic from `rico_chat_api.py` into `src/services/chat_service.py`
- Add WebSocket streaming
- Add async AI inference with timeout

**Phase 3: API Gateway + Auth Service (Week 7-8)**
- Extract JWT auth to standalone service (or keep inline with shared library)
- Add API gateway (Kong or Nginx)
- Add request transformation / versioning

**Phase 4: Full Microservices (Month 3+)**
- Job scraper service (independent scaling)
- AI inference service (GPU-capable pods)
- Notification service (Telegram, Email, SMS)
- Analytics service (separate read DB)

**Decision gate:** Only proceed to Phase 4 when you have >1000 DAU. Before that, the monolith with async workers is cheaper and simpler.

---

## 9. Monitoring & Observability Stack

### 9.1 Metrics (Prometheus)

```python
# src/observability/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Info

# Pipeline metrics
pipeline_jobs_fetched = Counter("rico_jobs_fetched_total", "Jobs fetched", ["source"])
pipeline_jobs_scored = Counter("rico_jobs_scored_total", "Jobs scored", ["model"])
pipeline_duration = Histogram("rico_pipeline_duration_seconds", "Pipeline runtime")

# Chat metrics
chat_requests = Counter("rico_chat_requests_total", "Chat requests", ["intent"])
chat_latency = Histogram("rico_chat_latency_seconds", "Chat response time", ["provider"])
chat_tokens = Counter("rico_chat_tokens_total", "Tokens consumed", ["provider", "model"])

# System metrics
active_users = Gauge("rico_active_users", "Active users in last 5 min")
queue_depth = Gauge("rico_queue_depth", "Celery queue depth", ["queue"])
```

### 9.2 Structured Logging (JSON)

```python
# src/observability/logging_config.py
import logging
import json
import sys
from pythonjsonlogger import jsonlogger

def setup_logging():
    logHandler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(timestamp)s %(level)s %(name)s %(message)s %(correlation_id)s %(user_id)s %(duration_ms)s",
        rename_fields={"levelname": "level"},
    )
    logHandler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [logHandler]
```

### 9.3 Distributed Tracing (Jaeger / OpenTelemetry)

```python
# src/observability/tracing.py
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

def init_tracing(app):
    provider = TracerProvider()
    jaeger = JaegerExporter(agent_host_name="jaeger-agent", agent_port=6831)
    provider.add_span_processor(BatchSpanProcessor(jaeger))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    CeleryInstrumentor.instrument()
    Psycopg2Instrumentor.instrument()
```

### 9.4 Alerting Rules

```yaml
# alerting/prometheus-rules.yml
groups:
  - name: rico
    rules:
      - alert: HighChatLatency
        expr: histogram_quantile(0.95, rico_chat_latency_seconds_bucket) > 5
        for: 5m
        annotations:
          summary: "95th percentile chat latency > 5s"

      - alert: PipelineFailure
        expr: rico_pipeline_duration_seconds_count == 0
        for: 25h
        annotations:
          summary: "Daily pipeline has not run in 25 hours"

      - alert: QueueBacklog
        expr: rico_queue_depth > 100
        for: 10m
        annotations:
          summary: "Celery queue backlog > 100 tasks"
```

---

## 10. CI/CD Strategy

### 10.1 GitHub Actions Pipeline

```yaml
# .github/workflows/production-ci-cd.yml
name: Production CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        ports: ["5432:5432"]
      redis:
        image: redis:7
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest --cov=src --cov-report=xml
      - run: bandit -r src/ -f json -o bandit_report.json || true
      - run: safety check -r requirements.txt || true

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile.api
          push: true
          tags: ghcr.io/${{ github.repository }}/api:${{ github.sha }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Kubernetes
        run: |
          kubectl set image deployment/api api=ghcr.io/${{ github.repository }}/api:${{ github.sha }}
          kubectl set image deployment/worker worker=ghcr.io/${{ github.repository }}/api:${{ github.sha }}
          kubectl rollout status deployment/api
          kubectl rollout status deployment/worker
```

### 10.2 Environment Promotion

| Environment | Trigger | DB | AI Provider |
|-------------|---------|-----|-------------|
| Local | `docker-compose up` | Local PostgreSQL | OpenAI (dev key) |
| Staging | PR merge to `develop` | Neon staging | DeepSeek (cheaper) |
| Production | Push to `main` | Neon production | OpenAI (primary) |

---

## 11. Security Hardening

### 11.1 Immediate Actions (This Week)

| Action | File / Config | Effort |
|--------|-------------|--------|
| Add HMAC webhook verification | `src/rico_jotform_webhook.py`, `src/rico_telegram_webhook.py` | 2 hours |
| Add request size limits | `src/api/app.py` | 30 min |
| Add CORS strictness | `src/api/app.py` | 30 min |
| Remove broken email code | `src/notifier.py` | 1 hour |
| Add rate limiting to all public routes | `src/api/rate_limit.py` | 2 hours |
| Encrypt sensitive DB fields | `src/repositories/profile_repo.py` | 4 hours |
| Add CSP headers for dashboard | `dashboard.html` | 1 hour |

### 11.2 Medium-Term (Next Month)

| Action | Effort |
|--------|--------|
| Implement API key rotation | 1 day |
| Add OAuth2 provider (Google, LinkedIn) | 2 days |
| Add request signing for internal service calls | 1 day |
| Implement row-level security in DB | 2 days |
| Add DDoS protection (Cloudflare) | 2 hours |
| Penetration test (OWASP ZAP) | 1 day |

---

## 12. Best Tool Recommendations

### 12.1 Cloud Provider

**Recommendation: Render (now) → AWS/GCP (scale)**

| Stage | Provider | Why |
|-------|----------|-----|
| Now | Render | Zero-config deploy, auto-HTTPS, free tier fits current load. Postgres + Redis native. |
| 500+ users | AWS ECS Fargate | Container orchestration without managing K8s. Auto-scaling. |
| 5000+ users | AWS EKS or GCP GKE | Full Kubernetes for multi-service, GPU inference, complex networking. |

### 12.2 Vector Database

**Recommendation: pgvector (in Neon)**

Rico already uses Neon PostgreSQL. Adding `pgvector` extension requires zero new infrastructure.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE jobs ADD COLUMN embedding vector(384);
CREATE INDEX idx_jobs_embedding ON jobs USING ivfflat (embedding vector_cosine_ops);
```

**Alternative:** Pinecone or Weaviate if you need multi-tenant isolation at vector level.

### 12.3 Queue System

**Recommendation: Redis + Celery**

- Already in codebase (`REDIS_URL` env var)
- Celery is the most mature Python task queue
- Flower UI for monitoring out of the box
- Easy migration to SQS/RabbitMQ later if needed

### 12.4 Auth Architecture

**Recommendation: JWT + OAuth2 (incremental)**

**Phase 1 (now):** Keep current JWT in httpOnly cookies. Add refresh token rotation.
**Phase 2 (month 2):** Add OAuth2 providers (Google, LinkedIn) for one-click signup.
**Phase 3 (month 3):** Consider Auth0/Clerk if you need SSO, organization-level auth, or SAML.

### 12.5 Memory Architecture for AI Agents

**Recommendation: Tiered memory**

| Tier | Store | Use Case | TTL |
|------|-------|----------|-----|
| Working | Redis | Last 10 chat messages, current intent | 5 min |
| Short-term | PostgreSQL | Full chat history, recent actions | Permanent |
| Long-term | pgvector | Semantic memory (profile preferences, job patterns) | Permanent |
| Ephemeral | In-process | Tool context, current scoring params | Request lifetime |

**Implementation:**
```python
# src/agent/memory.py
class TieredMemory:
    def __init__(self, redis_client, db_pool):
        self.redis = redis_client
        self.db = db_pool

    async def get_context(self, user_id: str, query: str) -> dict:
        # 1. Working memory (Redis)
        working = await self.redis.get(f"chat:working:{user_id}")
        # 2. Short-term (DB last 50 messages)
        recent = await self.db.fetch("SELECT * FROM chat_history WHERE user_id=$1 ORDER BY timestamp DESC LIMIT 50", user_id)
        # 3. Long-term (pgvector semantic search)
        semantic = await self.db.fetch("SELECT * FROM memories WHERE user_id=$1 ORDER BY embedding <-> $2 LIMIT 10", user_id, embed(query))
        return {"working": working, "recent": recent, "semantic": semantic}
```

---

## 13. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Add connection pooling (`src/db_pool.py`)
- [ ] Add Redis caching to hot paths
- [ ] Add structured JSON logging
- [ ] Add Prometheus metrics to API
- [ ] Refactor `rico_chat_api.py` into handler modules
- [ ] Fix CORS and rate limiting gaps
- [ ] Add HMAC webhook verification

**Cost impact:** ~$0 (uses existing infra)
**Risk:** Low
**Team:** 1 backend engineer

### Phase 2: Async Workers (Weeks 3-4)
- [ ] Set up Celery + Redis
- [ ] Migrate `run_daily.py` to Celery tasks
- [ ] Add task retry + dead-letter queue
- [ ] Add Flower monitoring UI
- [ ] Move Gmail sync to background worker
- [ ] Move dashboard generation to worker

**Cost impact:** +$20-50/mo (Redis on Render)
**Risk:** Medium (changes core pipeline)
**Team:** 1 backend engineer

### Phase 3: Real-Time Chat (Weeks 5-6)
- [ ] Add WebSocket endpoint
- [ ] Implement streaming AI responses
- [ ] Add connection manager + heartbeat
- [ ] Frontend: real-time chat UI in Next.js
- [ ] Add Redis pub/sub for multi-instance chat

**Cost impact:** +$0 (same infra)
**Risk:** Medium (new protocol)
**Team:** 1 backend + 1 frontend

### Phase 4: SaaS Readiness (Weeks 7-10)
- [ ] Add row-level security in DB
- [ ] Implement multi-tenant data isolation
- [ ] Add subscription/plan management
- [ ] Add admin dashboard
- [ ] Implement API key auth for integrations
- [ ] Add OAuth2 (Google, LinkedIn)

**Cost impact:** +$50-100/mo (Neon Pro, Render Pro)
**Risk:** High (data model changes)
**Team:** 1 backend + 1 frontend

### Phase 5: Scale & Intelligence (Months 3-6)
- [ ] Add pgvector for semantic search
- [ ] Implement tiered memory architecture
- [ ] Add multi-agent orchestration
- [ ] GPU inference service for embeddings
- [ ] Recruiter copilot features
- [ ] Autonomous follow-up management

**Cost impact:** +$200-500/mo (GPU, vector DB, higher Neon tier)
**Risk:** High (new AI patterns)
**Team:** 2 backend + 1 ML + 1 frontend

---

## 14. Priority Matrix

| Priority | Task | Impact | Effort | Owner | Week |
|----------|------|--------|--------|-------|------|
| **P0** | Connection pooling | High | 4h | Backend | W1 |
| **P0** | Celery workers for pipeline | High | 2d | Backend | W2 |
| **P0** | Webhook HMAC verification | High | 2h | Backend | W1 |
| **P1** | Redis caching | Medium | 1d | Backend | W1 |
| **P1** | Structured logging | Medium | 4h | Backend | W1 |
| **P1** | WebSocket streaming | High | 3d | Backend + Frontend | W3 |
| **P1** | Frontend chat UI | High | 5d | Frontend | W3-4 |
| **P2** | Prometheus metrics | Medium | 1d | Backend | W2 |
| **P2** | CI/CD pipeline | Medium | 1d | DevOps | W2 |
| **P2** | Docker + docker-compose | Medium | 1d | DevOps | W1 |
| **P2** | DB indexes + pgvector | Medium | 1d | Backend | W2 |
| **P3** | Multi-tenant isolation | High | 1w | Backend | W5 |
| **P3** | OAuth2 integration | Medium | 3d | Backend | W6 |
| **P3** | Kubernetes manifests | Medium | 2d | DevOps | W4 |
| **P4** | GPU inference service | High | 2w | ML | M3 |
| **P4** | Multi-agent orchestration | High | 3w | ML + Backend | M4 |

---

## 15. Technical Debt Assessment

| Debt Item | Severity | Effort to Fix | Impact if Ignored |
|-----------|----------|---------------|-------------------|
| Monolithic `rico_chat_api.py` | High | 2-3 days | Cannot scale chat team, bug-prone |
| No connection pooling | Critical | 4 hours | System collapses under concurrent load |
| Synchronous pipeline | Critical | 2 days | 68s → 600s+ as jobs scale |
| No caching layer | High | 1 day | Wastes DB cycles, slow UX |
| Broken email notifier | Low | 1 hour | Dead code, confusion |
| Multiple dashboard files | Low | 1 hour | Developer confusion |
| Mixed sync/async | Medium | 2 hours | Runtime errors, blocked event loop |
| No type hints on dynamic data | Medium | 1 day | Runtime errors, harder to refactor |
| Inline regex compilation | Low | 30 min | Minor perf hit |

**Total debt payoff time:** ~2 weeks of focused refactoring

---

## 16. Estimated Scaling Limits

### Current Architecture (Monolith)

| Resource | Limit | Bottleneck |
|----------|-------|------------|
| Concurrent chat users | ~20 | Synchronous AI inference blocks event loop |
| Daily jobs processed | ~500 | Single-threaded pipeline runtime |
| DB queries/sec | ~10 | ~1600ms latency + no pooling |
| Active users (total) | ~200 | JSON fallback cannot handle concurrent writes |

### With Phase 1-2 Improvements (Workers + Pooling + Caching)

| Resource | Limit | Bottleneck |
|----------|-------|------------|
| Concurrent chat users | ~200 | Redis pub/sub for multi-instance sync |
| Daily jobs processed | ~5,000 | Celery worker concurrency |
| DB queries/sec | ~500 | Connection pool (20 conns) |
| Active users (total) | ~2,000 | Neon Pro tier capacity |

### With Phase 3-5 (Full SaaS)

| Resource | Limit | Bottleneck |
|----------|-------|------------|
| Concurrent chat users | ~5,000 | AI inference latency (need GPU workers) |
| Daily jobs processed | ~50,000 | Job scraper rate limits |
| DB queries/sec | ~5,000 | Read replicas + connection pooling |
| Active users (total) | ~50,000 | Requires horizontal scaling + microservices |

---

## 17. Security Hardening Checklist

### Immediate (This Week)

- [ ] Add `WEBHOOK_SECRET` env var and HMAC-SHA256 verification to Jotform webhook
- [ ] Add `TELEGRAM_WEBHOOK_SECRET` and verify incoming Telegram updates
- [ ] Limit request body size to 1MB on all routes
- [ ] Add `Strict-Transport-Security` header (`max-age=31536000; includeSubDomains`)
- [ ] Add `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`
- [ ] Sanitize all user inputs with Bleach or equivalent
- [ ] Add brute-force protection on login endpoint (5 attempts / 15 min / IP)
- [ ] Rotate all API keys that were ever exposed in logs
- [ ] Enable Neon row-level security (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`)
- [ ] Add `audit_log` table encryption for `failure_reason` and `result_message`

### Short-Term (Next 2 Weeks)

- [ ] Implement refresh token rotation (new refresh token on every access token use)
- [ ] Add OAuth2 state parameter validation
- [ ] Add request signing for internal service → service communication
- [ ] Implement API key scoping (read-only, write, admin)
- [ ] Add Content Security Policy headers to dashboard HTML
- [ ] Run OWASP ZAP scan and fix all High/Medium findings
- [ ] Add dependency vulnerability scanning in CI (`safety`, `pip-audit`)
- [ ] Implement secret scanning in CI (gitleaks or truffleHog)
- [ ] Add database backup automation (Neon already does this — verify retention)
- [ ] Document incident response playbook

### Medium-Term (Next Month)

- [ ] Implement RBAC at DB level (separate read-only roles for analytics)
- [ ] Add data retention policies (auto-delete chat history after 2 years)
- [ ] Implement GDPR/CCPA data export and deletion endpoints
- [ ] Add SIEM integration (Datadog Security or Splunk)
- [ ] Penetration test by external security firm
- [ ] Implement mutual TLS (mTLS) for internal service mesh
- [ ] Add DDoS protection (Cloudflare Pro or AWS Shield)

---

## 18. Evolution Paths

### 18.1 AI Recruiting Copilot

**What changes:** Rico flips from job-seeker assistant to recruiter assistant.

**New components:**
- Recruiter dashboard (job posting, candidate matching)
- Resume parser for inbound applications
- AI interview scheduling and scoring
- Automated candidate sourcing from LinkedIn

**Architecture impact:**
- New `recruiter` tenant type in DB
- New `candidate_pool` vector index
- New `interview` module with video/audio processing
- New compliance layer (GDPR for candidate data)

### 18.2 Autonomous Job Agent

**What changes:** Rico applies to jobs on behalf of the user without explicit per-job approval.

**Requirements:**
- Cover letter generation quality > 90% human-equivalent
- Application form auto-fill (name, email, CV upload)
- Human-in-the-loop for high-value roles only
- Legal framework for automated application consent

**Architecture impact:**
- New `autonomous_apply` worker queue
- Form-filling service (Playwright/Selenium)
- Application tracking with recruiter reply monitoring
- Compliance audit trail for every auto-apply

### 18.3 SaaS Platform

**What changes:** Multi-tenant, subscription-based, white-label ready.

**Requirements:**
- Organization-level accounts (companies subscribe for their employees)
- White-label theming (colors, logo, domain)
- API for integrations (HRIS, ATS)
- Billing and usage metering

**Architecture impact:**
- `organizations` table + `organization_id` on all tenant data
- Stripe integration for billing
- Usage tracking (jobs processed, AI tokens consumed)
- API key management per organization

### 18.4 Multi-Agent Ecosystem

**What changes:** Rico becomes an orchestrator for specialized agents.

**Agents:**
- `ResumeAgent` — CV optimization, keyword matching, ATS scoring
- `InterviewAgent` — Mock interviews, feedback, coaching
- `NetworkAgent` — LinkedIn outreach, referral generation
- `SalaryAgent` — Market research, negotiation scripts
- `VisaAgent` — UAE visa guidance, document checklists

**Architecture impact:**
- Agent registry (like tool registry but for agents)
- Inter-agent communication bus (Redis pub/sub or message queue)
- Shared memory layer (all agents read/write same user context)
- Agent marketplace (3rd party agents)

---

## 19. Cost Estimates

### Current (Prototype)

| Service | Monthly Cost |
|---------|-------------|
| Neon PostgreSQL (Free) | $0 |
| GitHub Actions (Free) | $0 |
| GitHub Pages (Free) | $0 |
| Telegram Bot (Free) | $0 |
| OpenAI API | $5-20 |
| HuggingFace Inference | $0 |
| **Total** | **$5-20** |

### Phase 1-2 (Production Foundation)

| Service | Monthly Cost |
|---------|-------------|
| Neon PostgreSQL (Pro) | $19 |
| Render (API + Worker) | $25-50 |
| Redis (Render or Upstash) | $10-20 |
| OpenAI API | $50-100 |
| Cloudflare (Pro) | $20 |
| **Total** | **$124-209** |

### Phase 3-5 (Full SaaS)

| Service | Monthly Cost |
|---------|-------------|
| Neon PostgreSQL (Scale) | $100-300 |
| AWS ECS / EKS | $200-500 |
| Redis (ElastiCache) | $50-100 |
| OpenAI API | $500-2000 |
| GPU Inference (AWS/GCP) | $200-500 |
| Cloudflare (Enterprise) | $200 |
| Monitoring (Datadog/Grafana Cloud) | $100-300 |
| **Total** | **$1350-3900** |

---

*End of Production Architecture Transformation Document*
