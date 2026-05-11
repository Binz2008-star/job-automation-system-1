// ─────────────────────────────────────────────────────────────────────────────
// DTOs matching confirmed backend contracts.
// Do NOT add fields here unless the backend contract is confirmed.
// ─────────────────────────────────────────────────────────────────────────────

// ── GET /health ───────────────────────────────────────────────────────────────
export interface RicoStatus {
  ready_for_api?: boolean;
  ready_for_db?: boolean;
  ready_for_telegram?: boolean;
  ready_for_openai?: boolean;
  ready_for_jotform?: boolean;
  ready_for_hf?: boolean;
  ai_provider?: string;
}

export interface HealthResponse {
  status: "ok" | "healthy" | "degraded" | "error";
  service?: string;
  environment?: string;
  database?: string;
  db?: string;
  openai?: boolean;
  telegram?: boolean;
  version?: string;

  // AI provider status (top-level)
  ready_for_openai?: boolean;
  ready_for_hf?: boolean;
  ready_for_jotform?: boolean;
  ai_provider?: "openai" | "huggingface" | "fallback" | "none" | string;

  // Nested rico status
  rico?: RicoStatus;

  endpoints?: Record<string, string>;
}

// ── Jobs ──────────────────────────────────────────────────────────────────────
export interface Job {
  job_id: string;
  title: string;
  company: string;
  location: string;
  /** field name varies between endpoints — both accepted */
  salary?: string;
  salary_range?: string;
  score: number;
  reason: string;
  apply_url: string;
  tags: string[];
  posted_at?: string;
}

// GET /api/v1/jobs
export interface JobListResponse {
  jobs: Job[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

// POST /api/v1/jobs/{job_id}/apply | /skip | /block
export interface JobActionRequest {
  job: Record<string, unknown>;
}

export interface JobActionResponse {
  status: string;
  message: string;
  job_id?: string | null;
}

// ── Chat ──────────────────────────────────────────────────────────────────────
// POST /api/chat
export interface ChatRequest {
  user_id: string;
  message: string;
}

export interface ChatResponse {
  reply: string;
  jobs?: Job[];
  actions?: string[];
}

/** Client-side only — not sent to API */
export interface ChatMessage {
  id: string;
  role: "user" | "rico";
  content: string;
  jobs?: Job[];
  timestamp: Date;
}

// ── Profile ───────────────────────────────────────────────────────────────────
// GET /api/profile?user_id=
export interface UserProfile {
  user_id: string;
  name: string;
  email?: string;
  telegram_username?: string;
  dream_role?: string;
  preferred_city?: string;
  cv_uploaded?: boolean;
  created_at?: string;
}

// POST /api/profile
export interface ProfileUpdateRequest {
  user_id: string;
  name?: string;
  telegram_username?: string;
  dream_role?: string;
  preferred_city?: string;
  avoid_keywords?: string[];
}

// POST /api/upload-cv  (multipart/form-data)
export interface CVUploadResponse {
  success: boolean;
  message: string;
  skills_extracted?: string[];
  experience_years?: number;
}

// ── Applications ──────────────────────────────────────────────────────────────
export type ApplicationStatus =
  | "applied"
  | "interview_scheduled"
  | "offer_extended"
  | "rejected"
  | "saved";

export interface Application {
  application_id: string;
  job_id: string;
  title: string;
  company: string;
  location: string;
  status: ApplicationStatus;
  applied_at?: string;
  updated_at?: string;
  notes?: string;
  apply_url?: string;
}

// GET /api/v1/applications
export interface ApplicationsResponse {
  applications: Application[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

// PATCH /api/v1/applications/{job_id}
export interface ApplicationActionRequest {
  status: ApplicationStatus;
  notes?: string;
}

export interface ApplicationActionResponse {
  status: string;
  job_id: string;
  message: string;
}

// ── Settings ────────────────────────────────────────────────────────────────
// GET /api/v1/settings
export interface SettingsResponse {
  include_keywords: string[];
  exclude_keywords: string[];
  min_score: number;
  max_daily_applies: number;
  telegram_chat_id: string;
  score_threshold_apply: number;
  score_threshold_watch: number;
  [key: string]: unknown;
}

// PUT /api/v1/settings
export interface SettingsUpdateRequest {
  include_keywords?: string[];
  exclude_keywords?: string[];
  min_score?: number;
  max_daily_applies?: number;
  telegram_chat_id?: string;
  score_threshold_apply?: number;
  score_threshold_watch?: number;
}

// ── Shared ────────────────────────────────────────────────────────────────────
export interface ApiError {
  detail: string;
  status_code?: number;
}
