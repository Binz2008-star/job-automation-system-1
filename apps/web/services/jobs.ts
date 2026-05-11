import api from "@/lib/client";
import type {
  Job,
  JobActionRequest,
  JobActionResponse,
  JobListResponse,
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

// ── GET /api/v1/jobs ───────────────────────────────────────────────────────────
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
  const { data } = await api.get<JobListResponse>("/api/jobs", {
    params: { page, limit, min_score: minScore, source },
  });
  // Backend returns raw dicts — normalize to frontend Job shape with safe defaults
  const rawJobs = Array.isArray(data?.jobs) ? (data.jobs as unknown[]) : [];
  const jobs: Job[] = rawJobs.map((j) => {
    const item = j as Record<string, any>;
    return {
      job_id: (item.job_id ?? item.id ?? item._id ?? "") as string,
      title: (item.title ?? "Untitled role") as string,
      company: (item.company ?? "Unknown company") as string,
      location: (item.location ?? "Remote / unspecified") as string,
      salary_range: (item.salary_range ?? item.salary ?? "") as string,
      score: typeof item.score === "number" ? item.score : 0,
      reason: (item.reason ?? item.match_reason ?? "") as string,
      tags: Array.isArray(item.tags) ? (item.tags as string[]) : [],
      posted_at: (item.posted_at ?? item.date_found ?? "") as string,
      apply_url: (item.apply_url ?? item.link ?? "") as string,
    };
  });
  return {
    jobs,
    total: typeof data.total === "number" ? data.total : jobs.length,
    page: typeof data.page === "number" ? data.page : page,
    limit: typeof data.limit === "number" ? data.limit : limit,
    pages: typeof data.pages === "number" ? data.pages : 1,
  };
}

// ── GET /api/v1/jobs/{job_id} ──────────────────────────────────────────────────
export async function getJobById(jobId: string): Promise<Job> {
  if (USE_MOCK) {
    const job = MOCK_JOBS.find((j) => j.job_id === jobId);
    if (!job) throw new Error("Job not found");
    return job;
  }
  const { data } = await api.get<Job>(`/api/jobs/${jobId}`);
  return data;
}

// ── POST /api/v1/jobs/{job_id}/apply ───────────────────────────────────────────
export async function applyJob(
  jobId: string,
  payload: JobActionRequest
): Promise<JobActionResponse> {
  if (USE_MOCK) {
    return { status: "applied", message: "Application submitted", job_id: jobId };
  }
  const { data } = await api.post<JobActionResponse>(
    `/api/jobs/${jobId}/apply`,
    payload
  );
  return data;
}

// ── POST /api/v1/jobs/{job_id}/skip ────────────────────────────────────────────
export async function skipJob(
  jobId: string,
  payload: JobActionRequest
): Promise<JobActionResponse> {
  if (USE_MOCK) {
    return { status: "skipped", message: "Job skipped", job_id: jobId };
  }
  const { data } = await api.post<JobActionResponse>(
    `/api/jobs/${jobId}/skip`,
    payload
  );
  return data;
}

// ── POST /api/v1/jobs/{job_id}/block ───────────────────────────────────────────
export async function blockJob(
  jobId: string,
  payload: JobActionRequest
): Promise<JobActionResponse> {
  if (USE_MOCK) {
    return { status: "blocked", message: "Company blocked", job_id: jobId };
  }
  const { data } = await api.post<JobActionResponse>(
    `/api/jobs/${jobId}/block`,
    payload
  );
  return data;
}
