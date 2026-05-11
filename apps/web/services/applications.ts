import api from "@/lib/client";
import type {
  Application,
  ApplicationActionRequest,
  ApplicationActionResponse,
  ApplicationStatus,
  ApplicationsResponse,
} from "@/types";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

const MOCK_APPS: Application[] = [
  {
    application_id: "app_001",
    job_id: "job_001",
    title: "Environmental & Sustainability Manager",
    company: "Parsons Corporation",
    location: "Dubai, UAE",
    status: "applied",
    applied_at: "2026-04-20T09:00:00Z",
    apply_url: "#",
  },
  {
    application_id: "app_002",
    job_id: "job_002",
    title: "HSSE Manager-CCGT",
    company: "Al Jomaih Energy",
    location: "Abu Dhabi, UAE",
    status: "interview_scheduled",
    applied_at: "2026-04-15T08:00:00Z",
    apply_url: "#",
  },
  {
    application_id: "app_003",
    job_id: "job_003",
    title: "Senior Associate - ESG Compliance",
    company: "EGA",
    location: "Dubai, UAE",
    status: "applied",
    applied_at: "2026-04-18T11:00:00Z",
    apply_url: "#",
  },
  {
    application_id: "app_004",
    job_id: "job_004",
    title: "EHS Manager",
    company: "Larsen & Toubro",
    location: "Abu Dhabi, UAE",
    status: "rejected",
    applied_at: "2026-04-10T10:00:00Z",
    apply_url: "#",
  },
];

// ── GET /api/v1/applications ─────────────────────────────────────────────────
export async function getApplications(
  status?: string,
  page = 1,
  limit = 50
): Promise<ApplicationsResponse> {
  if (USE_MOCK) {
    return {
      applications: MOCK_APPS,
      total: MOCK_APPS.length,
      page: 1,
      limit: 50,
      pages: 1,
    };
  }
  const { data } = await api.get<ApplicationsResponse>("/api/applications", {
    params: { status, page, limit },
  });
  // Backend returns raw dicts — normalize to frontend Application shape
  const rawApps = Array.isArray(data?.applications) ? (data.applications as unknown[]) : [];
  const applications: Application[] = rawApps.map((a) => {
    const item = a as Record<string, any>;
    const jobId = (item.job_id ?? item.id ?? "") as string;
    return {
      application_id: jobId,
      job_id: jobId,
      title: (item.title ?? "Untitled role") as string,
      company: (item.company ?? "Unknown company") as string,
      location: (item.location ?? "Remote / unspecified") as string,
      status: (item.status ?? "applied") as ApplicationStatus,
      applied_at: (item.applied_at ?? item.date_applied ?? "") as string,
      updated_at: (item.updated_at ?? item.date_updated ?? "") as string,
      notes: (item.notes ?? "") as string,
      apply_url: (item.apply_url ?? item.link ?? "") as string,
    };
  });
  return {
    applications,
    total: typeof data.total === "number" ? data.total : applications.length,
    page: typeof data.page === "number" ? data.page : page,
    limit: typeof data.limit === "number" ? data.limit : limit,
    pages: typeof data.pages === "number" ? data.pages : 1,
  };
}

// ── PATCH /api/v1/applications/{job_id} ──────────────────────────────────────
export async function updateApplicationStatus(
  jobId: string,
  payload: ApplicationActionRequest
): Promise<ApplicationActionResponse> {
  if (USE_MOCK) {
    const app = MOCK_APPS.find((a) => a.job_id === jobId);
    return {
      status: payload.status,
      job_id: jobId,
      message: "Status updated",
    };
  }
  const { data } = await api.patch<ApplicationActionResponse>(
    `/api/applications/${jobId}`,
    payload
  );
  return data;
}

// ── GET /api/v1/applications/stats ───────────────────────────────────────────
export async function getApplicationStats(): Promise<Record<string, number>> {
  if (USE_MOCK) {
    return {
      applied: 2,
      interview_scheduled: 1,
      offer_extended: 0,
      rejected: 1,
      saved: 0,
    };
  }
  const { data } = await api.get<Record<string, number>>(
    "/api/applications/stats"
  );
  return data;
}
