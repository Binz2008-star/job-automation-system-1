import api from "@/lib/client";
import type {
  Application,
  ApplicationActionRequest,
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

// ── GET /api/applications?user_id= ───────────────────────────────────────────
export async function getApplications(
  userId: string
): Promise<ApplicationsResponse> {
  if (USE_MOCK) {
    return { user_id: userId, count: MOCK_APPS.length, applications: MOCK_APPS };
  }
  const { data } = await api.get<ApplicationsResponse>("/api/applications", {
    params: { user_id: userId },
  });
  return data;
}

// ── POST /api/applications/update ────────────────────────────────────────────
export async function updateApplicationStatus(
  payload: ApplicationActionRequest
): Promise<Application> {
  if (USE_MOCK) {
    const app = MOCK_APPS.find(
      (a) => a.application_id === payload.application_id
    );
    return { ...(app ?? MOCK_APPS[0]), status: payload.status };
  }
  const { data } = await api.post<Application>(
    "/api/applications/update",
    payload
  );
  return data;
}
