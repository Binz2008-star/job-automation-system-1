import type {
    Application,
    ApplicationActionRequest,
    ApplicationActionResponse,
    ApplicationStatus,
    ApplicationsResponse,
    HealthResponse as ClientHealthResponse,
    Job,
    JobActionRequest,
    JobActionResponse,
    JobListResponse,
    SettingsResponse,
    SettingsUpdateRequest,
} from "@/types";

// Absolute backend URL — used only for server-side (SSR) fetches such as fetchHealth().
const RICO_API =
    process.env.NEXT_PUBLIC_RICO_API ??
    "https://rico-job-automation-api.onrender.com";

// All client-side fetches route through /proxy so the session cookie is set and
// sent as a first-party (same-origin) cookie, bypassing Chrome's cross-site
// cookie blocking. Next.js rewrites /proxy/* → RICO_API/* server-side.
const PROXY = "/proxy";
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

export class ApiError extends Error {
    statusCode: number;
    data?: unknown;

    constructor(message: string, statusCode: number, data?: unknown) {
        super(message);
        this.statusCode = statusCode;
        this.data = data;
        this.name = "ApiError";
    }
}

function buildProxyUrl(path: string, params?: Record<string, unknown>): string {
    const url = `${PROXY}${path}`;
    if (!params) return url;

    const qs = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value != null) qs.append(key, String(value));
    });

    const query = qs.toString();
    return query ? `${url}?${query}` : url;
}

async function requestJson<T>(
    path: string,
    init: RequestInit = {},
    params?: Record<string, unknown>
): Promise<T> {
    const headers = new Headers(init.headers);
    const isForm = init.body instanceof FormData;
    const hasBody = init.body !== undefined && init.body !== null;

    if (!isForm && hasBody && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }

    const res = await fetch(buildProxyUrl(path, params), {
        ...init,
        headers,
        credentials: init.credentials ?? "include",
    });

    if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
            detail?: unknown;
            message?: string;
        };
        const fallback = `${res.status} ${path}`;
        const message =
            extractDetail(body.detail, body.message ?? fallback) ?? fallback;
        throw new ApiError(message, res.status, body);
    }

    if (res.status === 204) return {} as T;
    return (await res.json()) as T;
}

// ── Health ────────────────────────────────────────────────────────────────────

export interface RicoStatus {
    ready_for_api: boolean;
    ready_for_db: boolean;
    ready_for_telegram: boolean;
    ready_for_openai: boolean;
    ready_for_deepseek: boolean;
    ready_for_jotform: boolean;
    ready_for_hf: boolean;
    ai_provider: string;
}

export interface HealthResponse {
    status: string;
    db: string;
    version: string;
    ready_for_openai?: boolean;
    ready_for_deepseek?: boolean;
    ready_for_hf?: boolean;
    ready_for_jotform?: boolean;
    ai_provider?: string;
    rico: RicoStatus;
}

// Server-side only — uses absolute URL (relative URLs don't resolve in Node.js).
export async function fetchHealth(): Promise<HealthResponse> {
    const res = await fetch(`${RICO_API}/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
    return res.json() as Promise<HealthResponse>;
}

// Client-side health check via the same-origin proxy.
export async function getHealth(): Promise<ClientHealthResponse> {
    return requestJson<ClientHealthResponse>("/health", { method: "GET" });
}

// ── Version (debug only, non-user-facing) ──────────────────────────────────────

export interface VersionResponse {
    app: string;
    commit: string;
    environment: string;
    deployed_at: string;
}

export async function getVersion(): Promise<VersionResponse> {
    return requestJson<VersionResponse>("/api/v1/version", { method: "GET" });
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface MeResponse {
    email: string | null;
    role: string;
    authenticated: boolean;
    guest?: boolean;
}

export async function fetchMe(signal?: AbortSignal): Promise<MeResponse> {
    const res = await fetch(`${PROXY}/api/v1/me`, {
        credentials: "include",
        signal,
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
    password: string,
    publicUserIdToMerge?: string | null
): Promise<LoginResponse> {
    const body: Record<string, unknown> = { email, password };
    if (publicUserIdToMerge) {
        body.public_user_id_to_merge = publicUserIdToMerge;
    }
    const res = await fetch(`${PROXY}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
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

export async function deleteSavedSearch(id: string): Promise<void> {
    const res = await fetch(`${PROXY}/api/v1/rico/settings/saved-searches/${id}`, {
        method: "DELETE",
        credentials: "include",
    });
    if (!res.ok) throw new Error(`Delete search failed: ${res.status}`);
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

const MOCK_JOBS: Job[] = [
    {
        job_id: "mock_001",
        title: "Senior Manager - [Your Field]",
        company: "Example Corp",
        location: "Dubai, UAE",
        salary_range: "AED 25-35k/mo",
        score: 94,
        reason: "Profile keyword match + seniority level + location",
        tags: ["Senior", "Management", "UAE"],
        posted_at: new Date().toISOString(),
        apply_url: "#",
    },
    {
        job_id: "mock_002",
        title: "Department Lead - Operations",
        company: "Regional Holdings",
        location: "Abu Dhabi, UAE",
        salary_range: "AED 20-28k/mo",
        score: 87,
        reason: "Role title + experience range + salary band alignment",
        tags: ["Operations", "Leadership", "Full-time"],
        posted_at: new Date().toISOString(),
        apply_url: "#",
    },
    {
        job_id: "mock_003",
        title: "Specialist - Compliance & Governance",
        company: "Acme Group",
        location: "Dubai, UAE",
        salary_range: "AED 18-24k/mo",
        score: 79,
        reason: "Compliance keywords + UAE market match",
        tags: ["Compliance", "Governance", "Mid-level"],
        posted_at: new Date().toISOString(),
        apply_url: "#",
    },
];

function normalizeJob(raw: unknown): Job {
    const item = raw as Record<string, unknown>;
    return {
        job_id: String(item.job_id ?? item.id ?? item._id ?? ""),
        title: String(item.title ?? "Untitled role"),
        company: String(item.company ?? "Unknown company"),
        location: String(item.location ?? "Remote / unspecified"),
        salary_range: String(item.salary_range ?? item.salary ?? ""),
        score: typeof item.score === "number" ? item.score : 0,
        reason: String(item.reason ?? item.match_reason ?? ""),
        tags: Array.isArray(item.tags) ? (item.tags as string[]) : [],
        posted_at: String(item.posted_at ?? item.date_found ?? ""),
        apply_url: String(item.apply_url ?? item.link ?? ""),
    };
}

export async function getJobs(
    page = 1,
    limit = 20,
    minScore = 0,
    source?: string
): Promise<JobListResponse> {
    if (USE_MOCK) {
        return {
            jobs: MOCK_JOBS,
            total: MOCK_JOBS.length,
            page: 1,
            limit: 20,
            pages: 1,
        };
    }

    const data = await requestJson<JobListResponse>(
        "/api/v1/jobs",
        { method: "GET" },
        { page, limit, min_score: minScore, source }
    );
    const rawJobs = Array.isArray(data?.jobs) ? (data.jobs as unknown[]) : [];
    const jobs = rawJobs.map(normalizeJob);

    return {
        jobs,
        total: typeof data.total === "number" ? data.total : jobs.length,
        page: typeof data.page === "number" ? data.page : page,
        limit: typeof data.limit === "number" ? data.limit : limit,
        pages: typeof data.pages === "number" ? data.pages : 1,
    };
}

export async function getJobById(jobId: string): Promise<Job> {
    if (USE_MOCK) {
        const job = MOCK_JOBS.find((item) => item.job_id === jobId);
        if (!job) throw new Error("Job not found");
        return job;
    }

    const data = await requestJson<Job>(`/api/v1/jobs/${jobId}`, { method: "GET" });
    return normalizeJob(data);
}

export async function applyJob(
    jobId: string,
    payload: JobActionRequest
): Promise<JobActionResponse> {
    if (USE_MOCK) {
        return { status: "applied", message: "Application submitted", job_id: jobId };
    }

    return requestJson<JobActionResponse>(`/api/v1/jobs/${jobId}/apply`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function saveJob(
    jobId: string,
    payload: JobActionRequest
): Promise<JobActionResponse> {
    if (USE_MOCK) {
        return { status: "saved", message: "Job saved", job_id: jobId };
    }

    return requestJson<JobActionResponse>(`/api/v1/jobs/${jobId}/save`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function skipJob(
    jobId: string,
    payload: JobActionRequest
): Promise<JobActionResponse> {
    if (USE_MOCK) {
        return { status: "skipped", message: "Job skipped", job_id: jobId };
    }

    return requestJson<JobActionResponse>(`/api/v1/jobs/${jobId}/skip`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function blockJob(
    jobId: string,
    payload: JobActionRequest
): Promise<JobActionResponse> {
    if (USE_MOCK) {
        return { status: "blocked", message: "Company blocked", job_id: jobId };
    }

    return requestJson<JobActionResponse>(`/api/v1/jobs/${jobId}/block`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

// ── Applications ──────────────────────────────────────────────────────────────

const APPLICATION_STATUS_ALIASES: Record<string, ApplicationStatus> = {
    interview_scheduled: "interview",
    offer_extended: "offer",
};

const MOCK_APPLICATIONS: Application[] = [
    {
        application_id: "app_001",
        job_id: "job_001",
        title: "Senior Manager - Operations",
        company: "Acme Corporation",
        location: "Dubai, UAE",
        status: "applied",
        applied_at: "2026-04-20T09:00:00Z",
        apply_url: "#",
    },
    {
        application_id: "app_002",
        job_id: "job_002",
        title: "Team Lead - Projects",
        company: "Global Industries",
        location: "Abu Dhabi, UAE",
        status: "interview",
        applied_at: "2026-04-15T08:00:00Z",
        apply_url: "#",
    },
    {
        application_id: "app_003",
        job_id: "job_003",
        title: "Specialist - Compliance",
        company: "Regional Group",
        location: "Dubai, UAE",
        status: "applied",
        applied_at: "2026-04-18T11:00:00Z",
        apply_url: "#",
    },
    {
        application_id: "app_004",
        job_id: "job_004",
        title: "Manager - Quality Assurance",
        company: "Horizon Enterprises",
        location: "Abu Dhabi, UAE",
        status: "rejected",
        applied_at: "2026-04-10T10:00:00Z",
        apply_url: "#",
    },
];

function normalizeApplicationStatus(raw: string): ApplicationStatus {
    return APPLICATION_STATUS_ALIASES[raw] ?? (raw as ApplicationStatus);
}

function normalizeApplication(raw: unknown): Application {
    const item = raw as Record<string, unknown>;
    const applicationId = String(item.application_id ?? item.job_id ?? item.id ?? "");
    const jobId = String(item.job_id ?? item.id ?? applicationId);

    return {
        application_id: applicationId,
        job_id: jobId,
        title: String(item.title ?? "Untitled role"),
        company: String(item.company ?? "Unknown company"),
        location: String(item.location ?? "Remote / unspecified"),
        status: normalizeApplicationStatus(String(item.status ?? "applied")),
        applied_at: String(item.applied_at ?? item.date_applied ?? ""),
        updated_at: String(item.updated_at ?? item.date_updated ?? ""),
        notes: String(item.notes ?? ""),
        apply_url: String(item.apply_url ?? item.link ?? ""),
    };
}

export async function getApplications(
    status?: string,
    page = 1,
    limit = 50
): Promise<ApplicationsResponse> {
    if (USE_MOCK) {
        return {
            applications: MOCK_APPLICATIONS,
            total: MOCK_APPLICATIONS.length,
            page: 1,
            limit: 50,
            pages: 1,
        };
    }

    const data = await requestJson<ApplicationsResponse>(
        "/api/v1/applications",
        { method: "GET" },
        { status, page, limit }
    );
    const rawApplications = Array.isArray(data?.applications)
        ? (data.applications as unknown[])
        : [];
    const applications = rawApplications.map(normalizeApplication);

    return {
        applications,
        total: typeof data.total === "number" ? data.total : applications.length,
        page: typeof data.page === "number" ? data.page : page,
        limit: typeof data.limit === "number" ? data.limit : limit,
        pages: typeof data.pages === "number" ? data.pages : 1,
    };
}

export async function updateApplicationStatus(
    jobId: string,
    payload: ApplicationActionRequest
): Promise<ApplicationActionResponse> {
    if (USE_MOCK) {
        return {
            status: payload.status,
            job_id: jobId,
            message: "Status updated",
        };
    }

    return requestJson<ApplicationActionResponse>(`/api/v1/applications/${jobId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

export async function getApplicationStats(): Promise<Record<string, number>> {
    if (USE_MOCK) {
        return {
            applied: 2,
            interview: 1,
            offer: 0,
            rejected: 1,
            saved: 0,
        };
    }

    const data = await requestJson<Record<string, number>>("/api/v1/applications/stats", {
        method: "GET",
    });
    const normalized: Record<string, number> = {};

    for (const [key, value] of Object.entries(data)) {
        const normalizedKey = APPLICATION_STATUS_ALIASES[key] ?? key;
        normalized[normalizedKey] = (normalized[normalizedKey] ?? 0) + value;
    }

    return normalized;
}

// ── Settings ──────────────────────────────────────────────────────────────────

const MOCK_SETTINGS: SettingsResponse = {
    include_keywords: ["Environmental", "HSE", "ESG", "Sustainability"],
    exclude_keywords: ["Sales", "Marketing", "Retail"],
    min_score: 65,
    max_daily_applies: 5,
    telegram_chat_id: "",
    score_threshold_apply: 80,
    score_threshold_watch: 60,
};

export async function getSettings(): Promise<SettingsResponse> {
    if (USE_MOCK) return MOCK_SETTINGS;
    return requestJson<SettingsResponse>("/api/v1/settings", { method: "GET" });
}

export async function updateSettings(
    payload: SettingsUpdateRequest
): Promise<SettingsResponse> {
    if (USE_MOCK) {
        return { ...MOCK_SETTINGS, ...payload };
    }

    return requestJson<SettingsResponse>("/api/v1/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
    });
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
    confidence?: "high" | "medium" | "low";
    match_reasons?: string[];
    match_concerns?: string[];
    missing_facts?: string[];
    recommended_action?: string;
}

export interface RicoOption {
    action: string;
    label: string;
    message?: string;
    role?: string;
}

export interface NextAction {
    action: string;
    label: string;
    message: string;
    role: string;
}

export interface NextAction {
    action: string;
    label: string;
    message: string;
    role: string;
}

export interface ChatApiResponse {
    response?: string;
    reply?: string;
    message?: string;
    content?: string;
    answer?: string;
    text?: string;
    data?: {
        response?: string;
        reply?: string;
        message?: string;
        content?: string;
        text?: string;
    };
    type?: string;
    matches?: JobMatch[];
    options?: RicoOption[];
    next_action?: string;
    response_source?: string;
    role?: string;
    reasons?: string[];
    next_actions?: NextAction[];
}

export interface ParsedCV {
    text: string;
    emails: string[];
    phones: string[];
    skills: string[];
    certifications: string[];
    languages: string[];
    years_experience_hint?: number | null;
    years_experience?: number | null;
    extraction_quality?: string;
    extracted_chars?: number;
}

export interface ProfilePreview {
    name: string | null;
    email: string | null;
    phone: string | null;
    current_role: string | null;
    experience_years: number | null;
    target_roles: string[];
    skills_detected: string[];
    existing_skills: string[];
    skills: string[];
    certifications: string[];
    languages: string[];
}

export interface UploadCVResponse {
    ok: boolean;
    status: string;
    document_type?: string;
    extraction_quality?: string;
    extracted_chars?: number;
    filename?: string;
    preview?: ProfilePreview;
    parsed?: ParsedCV;
    message?: string;
    user_id?: string;
}

export interface ConfirmCVProfileRequest {
    preview: ProfilePreview;
    filename: string;
}

export interface ConfirmCVProfileResponse {
    ok: boolean;
    status: string;
    message: string;
    profile: Record<string, unknown>;
}

export async function confirmCVProfile(
    payload: ConfirmCVProfileRequest,
    userId?: string
): Promise<ConfirmCVProfileResponse> {
    const url = new URL(`${PROXY}/api/v1/rico/confirm-cv-profile`);
    if (userId) {
        url.searchParams.set("user_id", userId);
    }
    const res = await fetch(url.toString(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(extractDetail(body.detail, `Confirm profile failed: ${res.status}`));
    }
    return res.json() as Promise<ConfirmCVProfileResponse>;
}

function extractDetail(detail: unknown, fallback: string): string {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: string; message?: string };
        return first.msg ?? first.message ?? fallback;
    }
    return fallback;
}

export async function uploadCV(
    file: File,
    userId?: string
): Promise<UploadCVResponse> {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(buildProxyUrl("/api/v1/rico/upload-cv", userId ? { user_id: userId } : undefined), {
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

// ── Applications Tracking ───────────────────────────────────────────────────────

export interface ApplicationCreatePayload {
    job_id: string;
    title: string;
    company: string;
    location?: string;
    url?: string;
    status?: string;
    source?: string;
}

export interface ApplicationUpdatePayload {
    status: string;
    notes?: string;
}

export async function createApplication(
    payload: ApplicationCreatePayload
): Promise<{ status: string; job_id: string; message: string }> {
    const res = await fetch(`${PROXY}/api/v1/applications`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(extractDetail(body.detail, `Create application failed: ${res.status}`));
    }
    return res.json() as Promise<{ status: string; job_id: string; message: string }>;
}

export async function updateApplication(
    jobId: string,
    payload: ApplicationUpdatePayload
): Promise<{ status: string; job_id: string; message: string }> {
    const res = await fetch(`${PROXY}/api/v1/applications/${jobId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(extractDetail(body.detail, `Update application failed: ${res.status}`));
    }
    return res.json() as Promise<{ status: string; job_id: string; message: string }>;
}

// ── Profile Updates ───────────────────────────────────────────────────────────

export interface ProfileUpdatePayload {
    target_roles?: string[];
    preferred_cities?: string[];
    salary_expectation_aed?: number;
    years_experience?: number;
    current_role?: string;
    skills?: string[];
}

export async function updateProfile(
    payload: ProfileUpdatePayload
): Promise<{ status: string; updated_fields: string[] }> {
    const res = await fetch(`${PROXY}/api/v1/rico/profile`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(extractDetail(body.detail, `Profile update failed: ${res.status}`));
    }
    return res.json() as Promise<{ status: string; updated_fields: string[] }>;
}

// ── Auth Register ───────────────────────────────────────────────────────────────

export async function register(
    email: string,
    password: string,
    publicUserIdToMerge?: string | null
): Promise<{ email: string; role: string }> {
    const body: Record<string, unknown> = { email, password };
    if (publicUserIdToMerge) {
        body.public_user_id_to_merge = publicUserIdToMerge;
    }
    const res = await fetch(`${PROXY}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(err.detail ?? `Registration failed: ${res.status}`);
    }
    return res.json() as Promise<{ email: string; role: string }>;
}

// Public chat — no auth required. Uses session_id stored in localStorage.
export async function sendChatPublic(
    message: string,
    sessionId: string,
    signal?: AbortSignal
): Promise<ChatApiResponse> {
    const res = await fetch(`${PROXY}/api/v1/rico/chat/public`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal,
        body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
    return res.json() as Promise<ChatApiResponse>;
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
