// ─────────────────────────────────────────────────────────────────────────────
// DTOs matching confirmed backend contracts.
// Do NOT add fields here unless the backend contract is confirmed.
// ─────────────────────────────────────────────────────────────────────────────

// ── GET /health ───────────────────────────────────────────────────────────────
export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  service: string;
  environment: string;
  database: string;
  openai: boolean;
  telegram: boolean;
  version: string;
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

// GET /api/jobs/recommended?user_id=
export interface RecommendedJobsResponse {
  user_id: string;
  count: number;
  jobs: Job[];
}

export type JobAction = "save" | "ignore" | "apply";

// POST /api/jobs/action
export interface JobActionRequest {
  user_id: string;
  job_id: string;
  action: JobAction;
}

export interface JobActionResponse {
  success: boolean;
  job_id: string;
  action: JobAction;
  message?: string;
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
  actions?: JobAction[];
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

// GET /api/applications?user_id=
export interface ApplicationsResponse {
  user_id: string;
  count: number;
  applications: Application[];
}

// POST /api/applications/update
export interface ApplicationActionRequest {
  user_id: string;
  application_id: string;
  status: ApplicationStatus;
  notes?: string;
}

// ── Shared ────────────────────────────────────────────────────────────────────
export interface ApiError {
  detail: string;
  status_code?: number;
}
