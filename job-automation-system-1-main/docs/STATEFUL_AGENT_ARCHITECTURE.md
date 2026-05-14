# Stateful Agent Architecture

## Overview

Rico has been migrated from a stateless chat flow to a stateful agent architecture. The key principle is:

**The model should not be responsible for remembering everything. The database and backend should remember. The AI model should reason over the current profile context.**

Rico learns through stored profile updates, behavior signals, and job-action feedback.

## Request Flow

```
request
→ resolve identity
→ load profile and memory
→ hydrate context
→ normalize roles (NEW)
→ score CV fit (NEW)
→ recommend adjacent roles (NEW)
→ maintain active search context (NEW)
→ route intent
→ call AI provider if needed
→ execute safe workflow action
→ save learning signal
→ respond with structured next actions
```

## Core Components

### 1. AI Provider Router (`src/rico_openai_agent.py`, `src/rico_openai_runtime.py`)

**Status**: Already exists, no changes needed.

Handles AI provider selection and failover:
- **Primary**: DeepSeek (if `DEEPSEEK_API_KEY` is set)
- **Optional**: OpenAI (if `RICO_AI_PROVIDER=openai`)
- **Fallback**: Hugging Face (if HF keys are set)
- **Provider metadata**: Tracks availability, model names, rate limits

**Usage**:
```python
from src.rico_openai_agent import RicoOpenAIAgent

agent = RicoOpenAIAgent()
response = agent.respond(user_message, user_context=user_profile_dict)
```

### 2. Canonical Identity Resolver (`src/agent/identity/resolver.py`)

**New component**.

Resolves user identity from multiple sources into a single canonical user_id:
- **Guest public sessions**: `public:{session_id}` (lowest confidence)
- **Authenticated users**: Email from JWT (highest confidence)
- **Jotform identity**: Email or telegram_username from form submission
- **Telegram identity**: chat_id from webhook
- **CV-extracted identity**: Email parsed from CV

**Priority order**: Email > Telegram username > Telegram chat_id > Guest session

**Usage**:
```python
from src.agent.identity.resolver import resolve_canonical_user

resolution = resolve_canonical_user(
    email="user@example.com",
    telegram_username="@username",
    session_id="abc123",
)
# resolution.canonical_user_id = "user@example.com"
# resolution.identity_source = "authenticated"
# resolution.confidence = 0.95
```

**Identity merging**: When a guest session later authenticates, the system can merge the identities:
```python
from src.agent.coordinator import merge_identities

merge_identities(guest_session_id="public:abc123", email="user@example.com")
```

### 3. Profile Context Resolver (`src/agent/context/resolver.py`)

**New component**.

Loads user profile from DB and hydrates from multiple sources:
- **Database**: Canonical profile truth
- **CV extraction**: Skills, experience, roles from parsed CV
- **Jotform**: User-provided structured data
- **Chat history**: Natural language preference extraction
- **Action history**: Behavioral inference (deal breakers, preferences)

**Features**:
- Computes profile completeness score (0.0-1.0)
- Identifies missing required vs optional fields
- Prevents repeated questions (24h cooldown per field)
- Returns what should be asked about next

**Usage**:
```python
from src.agent.context.resolver import resolve_profile_context

context = resolve_profile_context(
    canonical_user_id="user@example.com",
    cv_data=extracted_cv_dict,
    jotform_data=normalized_jotform,
    chat_history=recent_messages,
)
# context.completeness_score = 0.75
# context.missing_required = ["salary_expectation_aed"]
# context.hydration_sources = ["cv", "jotform"]
```

### 4. Learning Signals Repository (`src/repositories/learning_repo.py`)

**New component**.

Stores behavioral learning signals extracted from user actions:
- **Role preferences**: From applied/saved jobs
- **Location preferences**: From saved jobs
- **Skill relevance**: From applied jobs
- **Company sentiment**: From blocked/applied companies (-1.0 to 1.0)
- **Feedback events**: Explicit positive/negative feedback

**Signal inference**:
```python
from src.repositories.learning_repo import infer_signals_from_job_action

infer_signals_from_job_action(
    canonical_user_id="user@example.com",
    action_type="apply",
    job={"title": "Senior Engineer", "company": "Google", "location": "Dubai"},
)
# Automatically learns:
# - role_preference: "Senior Engineer" +0.8
# - location_preference: "Dubai" +0.7
# - company_sentiment: "Google" +0.5
```

**Querying preferences**:
```python
from src.repositories.learning_repo import get_learning_profile, get_top_preferences

profile = get_learning_profile("user@example.com")
top_roles = get_top_preferences("user@example.com", "role_preference", limit=5)
# [("Senior Engineer", 0.85), ("Full Stack Developer", 0.72), ...]
```

### 5. Agent Workflow Layer (`src/agent/workflow/coordinator.py`)

**Enhanced existing orchestrator**.

Classifies intent, checks permissions, routes to tools:
- **Intent classification**: Keyword-based (from existing orchestrator)
- **Permission gates**: SAFE, REQUIRES_CONFIRMATION, AUTO_ONLY, PROHIBITED
- **Confirmation flow**: High-impact actions require user approval
- **Learning signal logging**: Automatic signal capture from actions

**Permission levels**:
- **SAFE**: search_jobs, save_job, skip_job, explain_match, draft_message, prepare_interview, update_preferences, get_stats, help
- **REQUIRES_CONFIRMATION**: apply_job, block_company, trigger_pipeline
- **AUTO_ONLY**: Reserved for future auto-apply mode

**Usage**:
```python
from src.agent.workflow.coordinator import execute_workflow

result = execute_workflow(
    message="Find me jobs in Dubai",
    profile=user_profile,
    canonical_user_id="user@example.com",
    autonomy_level="recommend_only",
)
# result.intent = IntentType.SEARCH_JOBS
# result.requires_confirmation = False
# result.data = {"matches": [...]}
```

**Confirmation flow**:
```python
result = execute_workflow(
    explicit_action="apply",
    job={"title": "Senior Engineer", ...},
    profile=user_profile,
    canonical_user_id="user@example.com",
)
# result.requires_confirmation = True
# result.confirmation_prompt = "Confirm application to Senior Engineer at Company?"
# result.confirmation_token = "uuid-..."

# User confirms:
confirmed_result = execute_workflow(
    confirmation_token=result.confirmation_token,
    canonical_user_id="user@example.com",
)
```

### 6. Audit/Event Log (`src/repositories/audit_repo.py`)

**Enhanced with new logging functions**.

Logs all important events with timestamps:
- **Action audit log**: Existing, tracks job actions
- **Learning signal audit**: NEW, tracks all learning signals
- **Profile hydration audit**: NEW, tracks when/how profiles are enriched
- **Permission check audit**: NEW, tracks permission gate evaluations

**No private data leaks into public responses** - all logs are stored securely in DB.

**Usage**:
```python
from src.repositories.audit_repo import (
    log_learning_signal,
    log_profile_hydration,
    log_permission_check,
)

log_learning_signal(
    canonical_user_id="user@example.com",
    signal_type="role_preference",
    signal_value="Senior Engineer",
    signal_weight=0.8,
    source="job_action",
)

log_profile_hydration(
    canonical_user_id="user@example.com",
    hydration_sources=["cv", "jotform"],
    completeness_before=0.3,
    completeness_after=0.85,
)

log_permission_check(
    canonical_user_id="user@example.com",
    intent="apply_job",
    permission_level="requires_confirmation",
    allowed=False,
    requires_confirmation=True,
)
```

### 7. Role Intelligence Layer (`src/agent/intelligence/`)

**NEW component**.

Provides career agent intelligence beyond simple chat:
- **Role normalization**: Maps variant titles to canonical forms (sales man → Sales Representative)
- **CV-fit scoring**: Scores how well profile matches target role (0.0-1.0)
- **Adjacent role recommendations**: Suggests similar roles based on skills

#### Role Normalizer (`src/agent/intelligence/normalizer.py`)

```python
from src.agent.intelligence.normalizer import normalize_role

canonical = normalize_role("senior sales man")
# Returns: "Sales Representative"
```

#### Profile Fit Scorer (`src/agent/intelligence/scorer.py`)

```python
from src.agent.intelligence.scorer import score_profile_fit

fit = score_profile_fit(profile, "Software Engineer", location="Dubai")
# fit.overall_score = 0.85
# fit.skills_score = 0.9
# fit.missing_required_skills = ["docker"]
```

#### Adjacent Role Recommender (`src/agent/intelligence/recommender.py`)

```python
from src.agent.intelligence.recommender import recommend_adjacent_roles

recommendations = recommend_adjacent_roles(profile, "Software Engineer", limit=5)
# Returns roles like "Data Scientist", "DevOps Engineer", "Machine Learning Engineer"
```

### 8. Active Search Context (`src/repositories/search_context_repo.py`)

**NEW component**.

Maintains user's active search state across sessions:
- Current search query and filters
- Jobs seen in current session
- Jobs saved/skipped/applied
- Last search timestamp

```python
from src.repositories.search_context_repo import update_search_context, get_unseen_jobs

context = update_search_context(
    canonical_user_id="user@example.com",
    query="software engineer",
    target_locations=["Dubai", "Remote"],
)

unseen = get_unseen_jobs("user@example.com", all_jobs)
# Returns only jobs not yet seen by user
```

### 9. Stateful Agent Coordinator (`src/agent/coordinator.py`)

**New component**.

Ties all components together into the complete request flow:

```python
from src.agent.coordinator import handle_agent_request, AgentRequest

request = AgentRequest(
    message="Find me jobs in Dubai",
    email="user@example.com",
)

response = handle_agent_request(request)
# response.success = True
# response.message = "Found 15 job matches"
# response.canonical_user_id = "user@example.com"
# response.profile_completeness = 0.85
# response.learning_signals_applied = True
```

**Get user state**:
```python
from src.agent.coordinator import get_user_state

state = get_user_state("user@example.com")
# Returns complete user state including:
# - Profile data
# - Learning signals
# - Behavior signals
# - Hydration sources
```

### 8. Migration Adapter (`src/services/stateful_chat_adapter.py`)

**New component**.

Provides backward-compatible adapter for gradual migration:

```python
from src.services.stateful_chat_adapter import send_message_stateful

# Drop-in replacement for chat_service.send_message()
response = send_message_stateful(
    user_id="user@example.com",
    message="Find me jobs",
    email="user@example.com",
)
```

This allows existing code to use the new architecture without breaking changes.

## Database Schema

### New Tables

#### `learning_signals`
Stores behavioral learning signals:
```sql
CREATE TABLE learning_signals (
    id SERIAL PRIMARY KEY,
    canonical_user_id VARCHAR(255) NOT NULL,
    signal_type VARCHAR(100) NOT NULL,
    signal_value TEXT NOT NULL,
    signal_weight FLOAT NOT NULL,
    source VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### `learning_signals_audit`
Audit log for learning signals (separate from operational storage):
```sql
CREATE TABLE learning_signals_audit (
    id SERIAL PRIMARY KEY,
    canonical_user_id VARCHAR(255) NOT NULL,
    signal_type VARCHAR(100) NOT NULL,
    signal_value TEXT NOT NULL,
    signal_weight FLOAT NOT NULL,
    source VARCHAR(50) NOT NULL,
    metadata JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### `profile_hydration_audit`
Tracks profile enrichment events:
```sql
CREATE TABLE profile_hydration_audit (
    id SERIAL PRIMARY KEY,
    canonical_user_id VARCHAR(255) NOT NULL,
    hydration_sources TEXT[] NOT NULL,
    completeness_before FLOAT NOT NULL,
    completeness_after FLOAT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### `permission_check_audit`
Tracks permission gate evaluations:
```sql
CREATE TABLE permission_check_audit (
    id SERIAL PRIMARY KEY,
    canonical_user_id VARCHAR(255) NOT NULL,
    intent VARCHAR(100) NOT NULL,
    permission_level VARCHAR(50) NOT NULL,
    allowed BOOLEAN NOT NULL,
    requires_confirmation BOOLEAN NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Migration Guide

### For Existing Chat API

**Option 1: Direct migration (recommended)**
```python
# Old code
from src.services.chat_service import send_message
response = send_message(user_id, message)

# New code
from src.services.stateful_chat_adapter import send_message_stateful
response = send_message_stateful(user_id, message, email=user_id)
```

**Option 2: Gradual migration**
Keep using `chat_service.send_message()` for now, gradually migrate endpoints one by one using the adapter.

### For New Features

Use the new coordinator directly:
```python
from src.agent.coordinator import handle_agent_request, AgentRequest

request = AgentRequest(
    message=user_message,
    email=user_email,
    job=job_dict,
)
response = handle_agent_request(request)
```

## Testing

### Unit Tests

Test individual components:
```python
# Test identity resolution
from src.agent.identity.resolver import resolve_canonical_user
resolution = resolve_canonical_user(email="test@example.com")
assert resolution.canonical_user_id == "test@example.com"

# Test profile hydration
from src.agent.context.resolver import resolve_profile_context
context = resolve_profile_context("test@example.com", cv_data=cv_dict)
assert context.completeness_score > 0

# Test learning signals
from src.repositories.learning_repo import record_learning_signal
record_learning_signal("test@example.com", "role_preference", "Engineer", 0.8)
```

### Integration Tests

Test the full flow:
```python
from src.agent.coordinator import handle_agent_request, AgentRequest

request = AgentRequest(
    message="Find jobs",
    email="test@example.com",
)
response = handle_agent_request(request)
assert response.success
assert "matches" in response.data
```

## Key Design Decisions

### 1. Database as Source of Truth

The database remembers everything. The AI model only reasons over the current profile context. This ensures:
- Persistence across sessions
- No data loss on model restart
- Audit trail of all learning
- Ability to revert changes

### 2. Identity Resolution Priority

Email > Telegram username > Telegram chat_id > Guest session

This ensures authenticated users get the highest quality experience while still supporting guest sessions.

### 3. Permission Gates

High-impact actions (apply, block, trigger_pipeline) require confirmation by default. This prevents accidental actions while allowing auto-apply mode for power users.

### 4. Learning Signal Decay

Learning signals use exponential moving average (EMA) with alpha=0.3. This means:
- New signals have more weight
- Old signals gradually decay
- System adapts to changing preferences

### 5. Question Cooldown

Fields are only asked about once every 24 hours. This prevents nagging while allowing for profile updates over time.

## Performance Considerations

- **Caching**: Profile context is cached for 1 hour
- **Database indexing**: All audit tables have user+timestamp indexes
- **Batch operations**: Learning signals are inferred in batches from actions
- **Async logging**: Audit logging is non-blocking

## Security Considerations

- **No private data in responses**: All logs are stored securely
- **Permission checks**: All high-impact actions gated
- **Identity verification**: JWT tokens for authenticated users
- **Webhook secrets**: Jotform and GitHub webhooks verified

## Future Enhancements

1. **Embedding-based intent classification**: Replace keyword matching with ML
2. **Reinforcement learning**: Optimize learning signal weights
3. **Cross-session memory**: Share learning signals across identity sources
4. **Real-time preference updates**: WebSocket-based profile updates
5. **Advanced permission policies**: Role-based, time-based, location-based

## Troubleshooting

### Profile not hydrating
- Check DB connection
- Verify CV parsing is working
- Check Jotform webhook is receiving data
- Review logs for hydration errors

### Learning signals not being recorded
- Check `learning_signals` table exists
- Verify DB write permissions
- Review audit logs for errors

### Permission checks failing
- Verify autonomy_level setting
- Check permission level mapping
- Review permission_check_audit for details

### Identity resolution issues
- Check email format validation
- Verify telegram_username extraction
- Review identity resolution logs
