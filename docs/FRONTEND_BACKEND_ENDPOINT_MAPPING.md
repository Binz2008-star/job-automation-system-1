# Frontend-Backend Endpoint Mapping

Current route-by-route audit for the deployed Rico frontend in `apps/web` against the FastAPI backend under `src/api`.

## Audit Scope

- Frontend target: `apps/web`
- Backend target: `src/api`
- Canonical command route: `/command`
- Compatibility redirects:
  - `/chat` -> `/command`
  - `/orchestrate` -> `/command`

## Frontend Route Mapping

| Frontend route | Primary frontend helper(s) | Backend endpoint(s) | Status |
| --- | --- | --- | --- |
| `/` | landing only | none required | aligned |
| `/login` | `login()` | `POST /api/v1/auth/login` | aligned |
| `/signup` | `register()` | `POST /api/v1/auth/register` | aligned |
| `/upload` | `uploadCV()` | `POST /api/v1/rico/upload-cv` | aligned |
| `/command` | `fetchMe()`, `sendChat()`, `sendChatPublic()`, `uploadCV()`, `confirmCVProfile()` | `GET /api/v1/me`, `POST /api/v1/rico/chat`, `POST /api/v1/rico/chat/public`, `POST /api/v1/rico/upload-cv`, `POST /api/v1/rico/confirm-cv-profile` | aligned |
| `/dashboard` | `fetchHealth()`, `fetchProfile()`, `getJobs()`, `getApplications()`, `getApplicationStats()`, `getSettings()` | `GET /health`, `GET /api/v1/rico/profile`, `GET /api/v1/jobs`, `GET /api/v1/applications`, `GET /api/v1/applications/stats`, `GET /api/v1/settings` | aligned |
| `/jobs` | `getJobs()`, `saveJob()`, `skipJob()`, `createApplication()`, `updateApplication()` | `GET /api/v1/jobs`, `POST /api/v1/jobs/{job_id}/save`, `POST /api/v1/jobs/{job_id}/skip`, `POST /api/v1/applications/manual`, `PATCH /api/v1/applications/{job_id}` | aligned |
| `/applications` | `getApplications()`, `updateApplicationStatus()` | `GET /api/v1/applications`, `PATCH /api/v1/applications/{job_id}` | aligned |
| `/profile` | `fetchProfile()` | `GET /api/v1/rico/profile` | aligned |
| `/settings` | `getHealth()`, `getSettings()`, `updateSettings()` | `GET /health`, `GET /api/v1/settings`, `PUT /api/v1/settings` | aligned |
| `/saved-searches` | `fetchSavedSearches()` | `GET /api/v1/rico/settings/saved-searches` | aligned |
| `/signals` | `useOrchestration()` -> `getSignals()` | `GET /api/v1/jobs` | aligned to live jobs feed |
| `/flow` | `getApplications()` | `GET /api/v1/applications` | aligned |
| `/archive` | `fetchChatHistory()` | `GET /api/v1/rico/chat/history` | aligned |

## Auth and Session Contract

- Browser-authenticated frontend requests use the same-origin `/proxy` path.
- Authenticated identity is derived from the `access_token` cookie.
- `GET /api/v1/me` is strict:
  - authenticated -> `200`
  - anonymous -> `401` by design
- Public or guest identity can be read from `GET /api/v1/auth/me` if needed, but the current frontend public-state handling already treats `/api/v1/me` `401` as expected guest state.

## Rico Surface Mapping

| Feature | Frontend helper | Backend endpoint | Notes |
| --- | --- | --- | --- |
| Authenticated Rico chat | `sendChat()` | `POST /api/v1/rico/chat` | Zod-validated response path |
| Public Rico chat | `sendChatPublic()` | `POST /api/v1/rico/chat/public` | Zod-validated response path |
| CV upload | `uploadCV()` | `POST /api/v1/rico/upload-cv` | Zod-validated response path |
| Confirm CV profile | `confirmCVProfile()` | `POST /api/v1/rico/confirm-cv-profile` | Zod-validated response path |
| Profile fetch | `fetchProfile()` | `GET /api/v1/rico/profile` | Zod-validated response path |
| Profile patch | `updateProfile()` | `PATCH /api/v1/rico/profile` | fixed by backend commit `b2cd2ae` |
| Chat history | `fetchChatHistory()` | `GET /api/v1/rico/chat/history` | Zod-validated response path |
| Feedback | `ricoChatApi.submitFeedback()` | `POST /api/v1/rico/feedback` | aligned to `feedback_type`, `rating`, optional `comment` |

## Intelligence Layer Status

There are still no dedicated backend endpoints for:

- trajectory forecasts
- opportunity signals
- temporal orchestration timelines

Current frontend intelligence surfaces are therefore wired to live backend data that already exists:

- `/signals` -> live jobs feed
- `/flow` -> live applications pipeline
- `/archive` -> live Rico chat history
- `orchestrationApi.getTrajectory()` -> live profile, applications, and chat history
- `orchestrationApi.getSignals()` -> live jobs feed

This is intentional. The frontend is no longer using fake empty placeholders for these surfaces, but it also is not claiming dedicated backend intelligence APIs that do not exist yet.

## Verified Non-Targets

The following are not valid current frontend targets and should not be treated as canonical:

- `/chat` as a primary product route
- `/orchestrate` as a primary product route
- `/api/v1/auth/refresh`
- `/api/v1/agent/stream`

## Current Limitations

- Lint debt may still exist outside strict build/typecheck correctness unless explicitly resolved in the active branch.
- Intelligence views are live-data-backed, but they remain derived client-side because the backend does not yet expose first-class trajectory/signals APIs.
