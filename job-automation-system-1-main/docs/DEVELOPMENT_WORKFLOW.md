# Rico Development Workflow

## A. Start every feature from fresh main

```bash
git checkout main
git pull origin main
git checkout -b feat/<short-name>
```

## B. One product objective per PR

Keep scope tight. If a bug fix and a feature are separate objectives, open separate PRs.

## C. Every chat behavior bug must include

- exact failed phrase
- expected response type
- test proving heavy pipeline called / not called

## D. Rico response order

1. session/profile fast path
2. deterministic intent
3. cached result if available
4. external job search only after explicit request
5. AI/provider fallback last

## E. Frontend buttons must send

```typescript
option.message ?? option.label
```

Never send `option.label` alone when a `message` field exists.

## F. Do not trust production test until `/api/v1/version` confirms deployed commit

```bash
curl https://ricohunt.com/api/v1/version
```

## Local verification

Run before every push:

```bash
pytest tests/unit/test_role_confirmation.py -q
pytest tests/unit/test_profile_role_suggestions.py -q
pytest tests/unit/test_cv_persistence_chat.py -q
python scripts/smoke_rico_chat_flow.py
cd apps/web && npm run build
```

Or use the shortcut:

```bash
python scripts/smoke_rico_chat_flow.py
```
