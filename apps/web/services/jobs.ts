import api from "@/lib/client";
import type {
  Job,
  JobActionRequest,
  JobActionResponse,
  RecommendedJobsResponse,
} from "@/types";

// ── DEV MOCK — only active when NEXT_PUBLIC_USE_MOCK=true ────────────────────
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

const MOCK_JOBS: Job[] = [
  {
    job_id: "mock_001",
    title: "Environmental Manager — HSE",
    company: "ADNOC Group",
    location: "Abu Dhabi, UAE",
    salary_range: "AED 28-35k/mo",
    score: 96,
    reason: "Title + ISO 14001 + Gulf experience match",
    tags: ["ISO 14001", "Senior", "Environmental"],
    posted_at: new Date().toISOString(),
    apply_url: "#",
  },
  {
    job_id: "mock_002",
    title: "QHSE Manager",
    company: "Emaar Properties",
    location: "Dubai, UAE",
    salary_range: "AED 22-28k/mo",
    score: 88,
    reason: "QHSE + multi-site ops + MBA alignment",
    tags: ["QHSE", "Facilities", "MBA"],
    posted_at: new Date().toISOString(),
    apply_url: "#",
  },
  {
    job_id: "mock_003",
    title: "Sustainability & ESG Manager",
    company: "DP World",
    location: "Dubai, UAE",
    salary_range: "AED 20-26k/mo",
    score: 81,
    reason: "ESG + sustainability + UAE compliance experience",
    tags: ["ESG", "Sustainability", "Logistics"],
    posted_at: new Date().toISOString(),
    apply_url: "#",
  },
];

// ── GET /api/jobs/recommended?user_id= ───────────────────────────────────────
export async function getRecommendedJobs(
  userId: string
): Promise<RecommendedJobsResponse> {
  if (USE_MOCK) {
    return { user_id: userId, count: MOCK_JOBS.length, jobs: MOCK_JOBS };
  }
  const { data } = await api.get<RecommendedJobsResponse>(
    "/api/jobs/recommended",
    { params: { user_id: userId } }
  );
  return data;
}

// ── POST /api/jobs/action ─────────────────────────────────────────────────────
export async function submitJobAction(
  payload: JobActionRequest
): Promise<JobActionResponse> {
  if (USE_MOCK) {
    return { success: true, job_id: payload.job_id, action: payload.action };
  }
  const { data } = await api.post<JobActionResponse>(
    "/api/jobs/action",
    payload
  );
  return data;
}
