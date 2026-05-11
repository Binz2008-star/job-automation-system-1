// Absolute backend URL — used only for server-side (SSR) fetches such as fetchHealth().
const RICO_API =
  process.env.NEXT_PUBLIC_RICO_API ??
  "https://rico-job-automation-api.onrender.com";

// All client-side fetches route through /proxy so the session cookie is set and
// sent as a first-party (same-origin) cookie, bypassing Chrome's cross-site
// cookie blocking. Next.js rewrites /proxy/* → RICO_API/* server-side.
const PROXY = "/proxy";

// ── Health ────────────────────────────────────────────────────────────────────

export interface RicoStatus {
  ready_for_api: boolean;
  ready_for_db: boolean;
  ready_for_telegram: boolean;
  ready_for_openai: boolean;
  ready_for_jotform: boolean;
  ready_for_hf: boolean;
  ai_provider: string;
}

export interface HealthResponse {
  status: string;
  db: string;
  version: string;
  rico: RicoStatus;
}

// Server-side only — uses absolute URL (relative URLs don't resolve in Node.js).
export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${RICO_API}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json() as Promise<HealthResponse>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface MeResponse {
  email: string;
  role: string;
  authenticated: boolean;
}

export async function fetchMe(): Promise<MeResponse> {
  const res = await fetch(`${PROXY}/api/v1/me`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`/me failed: ${res.status}`);
  return res.json() as Promise<MeResponse>;
}

export interface LoginResponse {
  message: string;
  email: string;
}

export async function login(
  email: string,
  password: string
): Promise<LoginResponse> {
  const res = await fetch(`${PROXY}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? "Login failed");
  }
  return res.json() as Promise<LoginResponse>;
}

export async function logout(): Promise<void> {
  await fetch(`${PROXY}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

// ── Profile ───────────────────────────────────────────────────────────────────

export interface ProfileResponse {
  profile_exists: boolean;
  email?: string;
  user_id?: string;
  name?: string | null;
  phone?: string | null;
  telegram_username?: string | null;
  target_roles?: string[];
  preferred_cities?: string[];
  salary_expectation_aed?: number | null;
  minimum_salary_aed?: number | null;
  skills?: string[];
  industries?: string[];
  visa_status?: string | null;
  notice_period?: string | null;
  years_experience?: number | null;
  current_role?: string | null;
  current_company?: string | null;
  linkedin_url?: string | null;
  settings?: Record<string, unknown>;
}

export async function fetchProfile(): Promise<ProfileResponse> {
  const res = await fetch(`${PROXY}/api/v1/rico/profile`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Profile fetch failed: ${res.status}`);
  return res.json() as Promise<ProfileResponse>;
}

// ── Saved searches ────────────────────────────────────────────────────────────

export interface SavedSearch {
  id: number;
  query: string;
  filters: Record<string, unknown>;
  created_at: string;
}

export interface SavedSearchesResponse {
  searches: SavedSearch[];
  total: number;
}

export async function fetchSavedSearches(): Promise<SavedSearchesResponse> {
  const res = await fetch(`${PROXY}/api/v1/rico/settings/saved-searches`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Saved searches fetch failed: ${res.status}`);
  return res.json() as Promise<SavedSearchesResponse>;
}

export async function createSavedSearch(
  query: string,
  filters?: Record<string, unknown>
): Promise<{ status: string; query: string }> {
  const res = await fetch(`${PROXY}/api/v1/rico/settings/saved-searches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ query, filters: filters ?? {} }),
  });
  if (!res.ok) throw new Error(`Save search failed: ${res.status}`);
  return res.json() as Promise<{ status: string; query: string }>;
}

// ── Password reset ────────────────────────────────────────────────────────────

export async function forgotPassword(email: string): Promise<{ message: string }> {
  const res = await fetch(`${PROXY}/api/v1/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json() as Promise<{ message: string }>;
}

export async function resetPassword(
  token: string,
  new_password: string
): Promise<{ message: string }> {
  const res = await fetch(`${PROXY}/api/v1/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password }),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Reset failed: ${res.status}`);
  }
  return res.json() as Promise<{ message: string }>;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export interface JobMatch {
  title: string;
  company: string;
  location?: string;
  score?: number;
  why?: string;
  actions?: string[];
}

export interface RicoOption {
  action: string;
  label: string;
}

export interface ChatApiResponse {
  response?: string;
  reply?: string;
  message?: string;
  content?: string;
  answer?: string;
  type?: string;
  matches?: JobMatch[];
  options?: RicoOption[];
  next_action?: string;
  response_source?: string;
  provider?: string;
  provider_state?: string;
  openai_available?: boolean;
  hf_available?: boolean;
  data?: {
    response?: string;
    reply?: string;
    message?: string;
    content?: string;
  };
}

// ── CV upload ─────────────────────────────────────────────────────────────────

export interface ParsedCV {
  text: string;
  skills: string[];
  emails: string[];
  phones: string[];
  years_experience_hint: number | null;
  certifications: string[];
  languages: string[];
}

export interface UploadCVResponse {
  user_id: string;
  filename: string;
  parsed: ParsedCV;
}

function extractDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; message?: string };
    return first.msg ?? first.message ?? fallback;
  }
  return fallback;
}

export async function uploadCV(file: File): Promise<UploadCVResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${PROXY}/api/v1/rico/upload-cv`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(extractDetail(body.detail, `Upload failed: ${res.status}`));
  }
  return res.json() as Promise<UploadCVResponse>;
}

// ── Onboarding ────────────────────────────────────────────────────────────────

export interface OnboardingPayload {
  target_roles?: string[];
  preferred_cities?: string[];
  salary_expectation_aed?: number;
  years_experience?: number;
  current_role?: string;
  skills?: string[];
}

export async function submitOnboarding(
  payload: OnboardingPayload
): Promise<{ status: string; updated_fields: string[] }> {
  const res = await fetch(`${PROXY}/api/v1/onboarding/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(extractDetail(body.detail, `Onboarding submit failed: ${res.status}`));
  }
  return res.json() as Promise<{ status: string; updated_fields: string[] }>;
}

// No user_id field — identity comes exclusively from the session cookie.
export async function sendChat(
  message: string,
  signal?: AbortSignal
): Promise<ChatApiResponse> {
  const res = await fetch(`${PROXY}/api/v1/rico/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    signal,
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
  return res.json() as Promise<ChatApiResponse>;
}
