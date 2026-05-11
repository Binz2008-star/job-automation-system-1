# Issue #83 — Rico SaaS Web Audit

**Branch:** `feat/saas-web-recovery-issue-83`  
**Date:** 2026-05-11  
**Auditor:** Cascade (Senior Product Engineer)  
**Scope:** `apps/web` frontend + `src/api` backend contract verification

---

## 1. Executive Summary

The Rico web app is architecturally sound — the backend API and proxy routing are correctly designed. However, **five concrete bugs** cause the broken production experience:

1. **Chat infinite loading** — `chat/page.tsx` calls `sendChat()` from `lib/api.ts` which routes through `/proxy/api/v1/rico/chat`. The backend requires a valid session cookie (JWT). If the user is unauthenticated (cookie absent or expired), the backend returns **401**, but the frontend `catch` block only checks `err.message.includes("401")` — which never matches because `lib/api.ts` throws `new Error(\`Chat failed: ${res.status}\`)`, not a message containing "401". **Result: the 401 error falls through to the generic handler which re-renders "Something went wrong" but the session-expired gate never triggers.** Separate symptom: the `chat/page.tsx` imports `sendChat` from `@/lib/api` but the `services/chat.ts` module imports `api` (the Axios-compat client) and calls `/api/chat` which is PATH_MAP'd to `/api/v1/rico/chat`. These are two parallel implementations. The page uses `lib/api.ts` directly, which is correct. The `services/chat.ts` is dead code.

2. **Health check unreachable in `services/health.ts`** — `getHealth()` calls `api.get("/health")` through `lib/client.ts`. The client prepends `/proxy`, making the URL `/proxy/health`. The rewrite in `next.config.js` maps `/proxy/api/:path*` but has a **separate rule** `{ source: "/proxy/health", destination: \`${api}/health\` }`. So `/proxy/health` is correctly rewritten — this works. However, `lib/client.ts`'s PATH_MAP does NOT contain `/health`, so `resolve("/health")` returns `/health` unchanged, and `buildUrl` produces `/proxy/health` — which IS covered by the rewrite. **This one actually works.** Issue is lower priority.

3. **Auth 401 detection bug (chat + all pages)** — `lib/api.ts` `sendChat()` throws `new Error(\`Chat failed: ${res.status}\`)`. The `chat/page.tsx` checks `err.message.includes("401")` — the string `"401"` IS in `"Chat failed: 401"`, so this actually should work. However the backend `rico_chat.py` calls `get_current_user(request)` which raises `HTTPException(status_code=401)`. FastAPI returns `{"detail": "Not authenticated"}`. The proxy passes this through as a 401. The frontend sees `res.ok === false` for a 401, and throws `new Error("Chat failed: 401")` — the includes check matches. **The session-expired modal should render.** The real root cause is likely CORS: the backend `CORS_ORIGINS` defaults to `http://localhost:3000` — in **production on ricohunt.com**, if `CORS_ORIGINS` env var is not set to include the production domain, all credentialed cross-origin requests from the browser fail with a CORS preflight error, not a 401. A CORS failure does NOT return a readable HTTP status — the fetch throws a `TypeError: Failed to fetch`. This TypeError does NOT include "401", so `sessionExpired` never triggers and the generic error path shows "Something went wrong." **This is the primary root cause of chat appearing stuck.**

4. **Landing page primary CTA routes to Jotform externally** — `app/page.tsx` has two primary buttons (nav "Launch Rico" + hero "Start Your Job Agent") that both open `https://form.jotform.com/261278237812056` in a new tab. For a logged-out visitor, this is the only call to action. There is no `/login` or `/signup` link on the landing page except a secondary text link to `/dashboard` in the nav. **Users who click the primary CTA leave the product entirely with no return path explained.**

5. **Mock data leaks specific single-user profile data** — `services/applications.ts` MOCK_APPS hardcodes specific job titles ("Environmental & Sustainability Manager", "HSSE Manager-CCGT", "EHS Manager") that match a single known user profile. `services/jobs.ts` MOCK_JOBS similarly hardcodes HSE/ESG roles. These leak when `NEXT_PUBLIC_USE_MOCK=true` is set in production, or confuse devs about what the real system serves.

---

## 2. File-by-File Findings

### `apps/web/app/chat/page.tsx`
| # | Finding | Severity |
|---|---------|----------|
| C1 | 401 detection: `err.message.includes("401")` — correct pattern but **only fires if response is HTTP**. CORS TypeError bypasses it. | High |
| C2 | `sendChat` imported from `@/lib/api` — correct. `services/chat.ts` is unused dead code. | Low |
| C3 | No timeout — if the backend never responds (Render cold start), the spinner runs forever. Should add `AbortController` with ~30s timeout. | Medium |
| C4 | `USE_MOCK` env check is in `services/chat.ts` (unused file), not in the actual chat page — no mock fallback for devs. | Low |

### `apps/web/lib/api.ts`
| # | Finding | Severity |
|---|---------|----------|
| A1 | `sendChat` correctly calls `/proxy/api/v1/rico/chat` with `credentials: "include"`. Path is correct. | OK |
| A2 | Error thrown as `new Error(\`Chat failed: ${res.status}\`)` — readable status is embedded in message, 401 detection works for HTTP errors. | OK |
| A3 | `fetchHealth()` uses absolute `RICO_API` URL — server-side only function. Correct for SSR. | OK |
| A4 | `fetchMe()`, `fetchProfile()`, `fetchSavedSearches()` use `/proxy` — correct for client-side. | OK |

### `apps/web/next.config.js`
| # | Finding | Severity |
|---|---------|----------|
| N1 | Rewrite rules cover `/proxy/api/:path*` AND `/proxy/health` — correct. | OK |
| N2 | No `NEXT_PUBLIC_RICO_API` documented anywhere in `apps/web` — no `.env.local.example`. Devs must guess the env var name. | Low |

### `apps/web/lib/client.ts`
| # | Finding | Severity |
|---|---------|----------|
| L1 | PATH_MAP maps `/api/settings` → `/api/v1/settings`. Backend router is at `/api/v1/settings`. Correct. | OK |
| L2 | PATH_MAP maps `/api/chat` → `/api/v1/rico/chat`. But `services/chat.ts` (dead code) uses this. Live code uses `lib/api.ts` directly. | Low |
| L3 | `/health` not in PATH_MAP — `resolve("/health")` returns `/health` unchanged, URL becomes `/proxy/health`. The rewrite in next.config handles this. Works but implicit. | Low |

### `apps/web/services/applications.ts`
| # | Finding | Severity |
|---|---------|----------|
| S1 | MOCK_APPS contains ESG/HSE role names tied to a single-user profile. Should use generic placeholder roles. | Medium |
| S2 | `getApplicationStats()` — calls `/api/applications/stats`. Backend has `src/api/routers/stats.py` at `/api/v1/stats`. PATH_MAP only maps `/api/applications` → `/api/v1/applications`, not `/api/applications/stats` → `/api/v1/applications/stats`. **Correct via prefix match** in `resolve()`. | OK |

### `apps/web/services/jobs.ts`
| # | Finding | Severity |
|---|---------|----------|
| J1 | MOCK_JOBS contains ESG/HSE-specific content tied to a single user. | Medium |
| J2 | `applyJob`, `skipJob`, `blockJob` all call `/api/jobs/{id}/apply|skip|block`. Backend router `src/api/routers/jobs.py` would need to confirm these routes exist. | Medium |

### `apps/web/app/login/page.tsx`
| # | Finding | Severity |
|---|---------|----------|
| LG1 | Uses `bg-zinc-950`, `border-zinc-800`, `bg-indigo-600` — does NOT use Rico brand colors (`#06060f`, `#5b4fff`, `#13132a`). Visually inconsistent. | Medium |
| LG2 | No sign-up path explained. For a SaaS product, users need to understand how to get access. | Medium |

### `apps/web/app/page.tsx` (Landing)
| # | Finding | Severity |
|---|---------|----------|
| P1 | Primary CTA "Start Your Job Agent" and nav "Launch Rico" both go to `form.jotform.com` — no `/login` link on the page. | High |
| P2 | "Dashboard" nav link goes to `/dashboard` without auth check — will redirect to login. Inconsistent UX. | Low |
| P3 | Mock job cards in hero use ESG/HSE persona — acceptable for a marketing demo. | OK |
| P4 | `Space_Grotesk` and `JetBrains_Mono` fonts referenced in page but NOT loaded in `layout.tsx` (only `Cabinet_Grotesk` and `Instrument_Sans` are loaded). These font references silently fall back to system fonts. | High |

### `apps/web/app/layout.tsx`
| # | Finding | Severity |
|---|---------|----------|
| LY1 | Only loads `Cabinet_Grotesk` and `Instrument_Sans`. `Space_Grotesk` and `JetBrains_Mono` used in `page.tsx` are missing. | High |

### `apps/web/app/dashboard/page.tsx`
| # | Finding | Severity |
|---|---------|----------|
| D1 | Uses `force-dynamic` — correct for live data. | OK |
| D2 | `SystemStatus` does SSR fetch with `fetchHealth()` (absolute URL). Works in production. | OK |
| D3 | `DashboardStats` and `ProfileSummaryCard` are client components that call proxied endpoints. Both have correct auth redirect logic. | OK |

### `apps/web/app/profile/page.tsx`
| # | Finding | Severity |
|---|---------|----------|
| PR1 | `fetchProfile()` called without auth guard — if cookie is absent, backend returns 401, frontend shows generic error. Should redirect to `/login`. | Medium |
| PR2 | Jotform "Quick Start form" link is present but unlabeled — no explanation of what happens after form submission, no return path. | Medium |

### `apps/web/components/DashboardShell.tsx`
| # | Finding | Severity |
|---|---------|----------|
| DS1 | Nav includes "Saved Searches" — this is a legacy/low-value page, clutters navigation. | Low |
| DS2 | No icons in nav items — harder to scan quickly. | Low |
| DS3 | No user identity shown anywhere in the shell (no email/name display). | Medium |

### `apps/web/components/SavedSearchesList.tsx`
| # | Finding | Severity |
|---|---------|----------|
| SS1 | Uses `text-zinc-*`, `bg-zinc-*` — inconsistent with Rico brand palette used everywhere else. | Low |

### Backend — `src/api/routers/rico_chat.py`
| # | Finding | Severity |
|---|---------|----------|
| BC1 | `POST /api/v1/rico/chat` returns `Dict[str, Any]` from `chat_service.send_message()`. Response key is `response` (from `rico_openai_agent.py`). Frontend tries `res.response ?? res.reply ?? res.message ?? res.content ?? res.answer`. If backend key is `response`, this works. | OK |
| BC2 | `get_current_user(request)` reads from session cookie. Requires `session` or JWT cookie set by login. | OK |

### Backend — `src/api/app.py` (CORS)
| # | Finding | Severity |
|---|---------|----------|
| CO1 | `CORS_ORIGINS` defaults to `http://localhost:3000`. **In production, this must be set to `https://ricohunt.com` (or include it).** If not set, browser blocks credentialed requests from `ricohunt.com` to `rico-job-automation-api.onrender.com`. This is the **primary root cause of chat appearing stuck in production.** | Critical |

---

## 3. Root Cause Summary

| Priority | Root Cause | Fix |
|----------|-----------|-----|
| 🔴 Critical | `CORS_ORIGINS` not set to production domain on Render | Set `CORS_ORIGINS=https://ricohunt.com` in Render env vars |
| 🔴 High | Chat catches `TypeError: Failed to fetch` (CORS) as generic error, shows "Something went wrong" instead of actionable message | Improve error detection to distinguish CORS/network errors |
| 🟠 High | Landing page has no `/login` link — all CTAs go to Jotform externally | Add `Sign in` link to nav; change primary CTA to `/login` or explain Jotform handoff |
| 🟠 High | `Space_Grotesk` + `JetBrains_Mono` fonts not loaded in `layout.tsx` | Add font imports |
| 🟡 Medium | Login page uses `zinc/indigo` palette instead of Rico brand colors | Restyle to Rico brand |
| 🟡 Medium | Mock data contains single-user HSE/ESG profile data | Genericize mock data |
| 🟡 Medium | Profile page has no auth redirect — fails silently for unauthenticated users | Add auth guard |
| 🟡 Medium | Jotform link in profile page unexplained | Add branded explanation and return path |
| 🟢 Low | Nav includes "Saved Searches" — clutter | Remove from primary nav |
| 🟢 Low | `services/chat.ts` is dead code (not imported by any page) | Remove or annotate |
| 🟢 Low | No `apps/web/.env.local.example` | Add example file |

---

## 4. What Is Real Backend vs. Placeholder Frontend

| Feature | Status |
|---------|--------|
| `POST /api/v1/rico/chat` | ✅ Real backend — routes to `chat_service.send_message()` |
| `GET /api/v1/rico/profile` | ✅ Real backend — reads from `profile_repo` |
| `GET /api/v1/jobs` | ✅ Real backend router exists |
| `GET /api/v1/applications` | ✅ Real backend router exists |
| `GET /api/v1/settings` | ✅ Real backend router exists |
| `GET /health` | ✅ Real backend |
| `POST /api/v1/auth/login` | ✅ Real backend — sets session cookie |
| Mock data in `services/` | ⚠️ Dev-only when `NEXT_PUBLIC_USE_MOCK=true` |
| Jotform onboarding | ⚠️ External form — webhook exists on backend at `/api/v1/rico/webhooks/jotform` |
| CV upload | ⚠️ Backend endpoint exists but frontend has no upload UI |
| Telegram alerts | ✅ Real — backend automation; no frontend control needed |
| Gmail sync | ✅ Real — `run_daily.py`; no frontend control needed |
| Scoring engine | ✅ Real backend automation |

---

## 5. What Should Be Fixed Now vs. Later

### Fix Now (this PR)
1. **[CORS note in docs]** — Document that `CORS_ORIGINS` must include production domain on the backend. This is an infra config, not a code change.
2. **Chat error handling** — Distinguish CORS/network `TypeError` from HTTP errors. Show actionable message: "Could not reach Rico. Check your connection or try again."
3. **Chat request timeout** — Add `AbortController` with 30s timeout to prevent infinite spinner.
4. **Landing page CTAs** — Change primary "Launch Rico" / "Start Your Job Agent" to `/login`. Add brief explanation before Jotform as a secondary option.
5. **Login page branding** — Restyle with Rico brand palette (`#06060f`, `#5b4fff`, `#13132a`).
6. **Font loading** — Add `Space_Grotesk` + `JetBrains_Mono` to `layout.tsx`.
7. **Profile page auth guard** — Redirect to `/login` on 401 from `fetchProfile()`.
8. **Profile Jotform link** — Add branded explanation: "Complete your profile in 2 minutes via our Quick Start form. We'll sync it automatically."
9. **Generic mock data** — Remove ESG/HSE-specific role names from mock arrays.
10. **Nav cleanup** — Remove "Saved Searches" from primary nav.
11. **`services/chat.ts`** — Annotate as legacy/unused.

### Fix Later (follow-up issues)
- In-product onboarding form replacing Jotform entirely
- CV upload UI
- User identity display in sidebar (email/name from `/me`)
- Mobile nav hamburger menu
- Pagination on jobs/applications pages
- Real-time pipeline run status

---

## 6. Production Smoke-Test Checklist

### Auth
- [ ] Navigate to `https://ricohunt.com/login` — page loads with Rico brand styling
- [ ] Submit valid credentials — redirects to `/dashboard`
- [ ] Submit invalid credentials — shows error message, no redirect
- [ ] After login, refresh `/dashboard` — stays logged in (session cookie persists)
- [ ] Click "Sign out" — redirects to `/login`, session cleared
- [ ] Navigate to `/dashboard` without login — redirects to `/login`

### Chat
- [ ] Log in, go to `/chat`
- [ ] Type "hi" and press Enter — spinner appears
- [ ] Response appears within 30 seconds (or clear error shown, not infinite spinner)
- [ ] If API unavailable: message reads "Could not reach Rico. Check your connection."
- [ ] If session expired mid-session: session-expired UI shown with "Sign in" button
- [ ] Page refresh — chat history clears but page loads correctly

### Dashboard
- [ ] `/dashboard` — system status cards render (live or error state, not blank)
- [ ] Profile summary card shows real data or "No profile yet" prompt
- [ ] Stats cards show real job/application counts or honest "0" with empty state

### Jobs
- [ ] `/jobs` — loads without error
- [ ] With no jobs: shows empty state "No matches in this range"
- [ ] With jobs: cards render with score, title, company
- [ ] Score filter buttons work

### Applications
- [ ] `/applications` — loads without error
- [ ] With no applications: shows empty state
- [ ] Status summary strip renders (all 7 columns)

### Settings
- [ ] `/settings` — loads backend status section
- [ ] Sliders and inputs accept changes
- [ ] "Save settings" button completes without error

### Profile
- [ ] `/profile` — loads real profile or "No profile yet" state
- [ ] "Edit" links open Rico chat with pre-filled prompt
- [ ] "Quick Start form" link opens Jotform with explanation

### Network
- [ ] No requests fail with CORS error in browser console
- [ ] All `/proxy/*` requests return HTTP responses (not `TypeError: Failed to fetch`)
- [ ] No secrets appear in network responses (no API keys, tokens, passwords)

---

## 7. Backend CORS Configuration (Action Required)

The backend at `rico-job-automation-api.onrender.com` must have:

```
CORS_ORIGINS=https://ricohunt.com,http://localhost:3000
```

Set this in the Render dashboard under Environment Variables for the backend service. Without this, **all credentialed browser requests from production will be silently blocked**, causing the chat and all authenticated pages to fail with `TypeError: Failed to fetch` instead of a meaningful error.

This is an **infrastructure configuration change**, not a code change. It does not require a deployment.

---

*End of audit. All fixes tracked in branch `feat/saas-web-recovery-issue-83`.*
