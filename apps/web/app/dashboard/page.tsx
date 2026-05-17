import { DashboardShell } from "@/components/DashboardShell";
import { DashboardStats } from "@/components/DashboardStats";
import { ProfileSummaryCard } from "@/components/ProfileSummaryCard";
import { SavedSearchesList } from "@/components/SavedSearchesList";
import { StatusCard } from "@/components/StatusCard";
import { fetchHealth, type HealthResponse } from "@/lib/api";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

const RICO_API =
  process.env.BACKEND_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_RICO_API ??
  "http://localhost:8000";

async function checkProfileExists(): Promise<boolean | null> {
  try {
    const cookieStore = await cookies();
    const cookieHeader = cookieStore.getAll().map((c) => `${c.name}=${c.value}`).join("; ");
    const res = await fetch(`${RICO_API}/api/v1/rico/profile`, {
      headers: { Cookie: cookieHeader },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { profile_exists?: boolean };
    return data.profile_exists ?? false;
  } catch {
    return null;
  }
}

async function SystemStatus() {
  let health: HealthResponse | null = null;
  let fetchError = false;

  try {
    health = await fetchHealth();
  } catch {
    fetchError = true;
  }

  if (fetchError || !health) {
    return (
      <StatusCard title="API status" badge="error">
        <p className="text-sm text-rico-text-muted">
          Could not reach the backend. Check{" "}
          <code className="text-rico-text">NEXT_PUBLIC_API_BASE_URL</code>.
        </p>
      </StatusCard>
    );
  }

  const dbOk = health.db === "connected";

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <StatusCard
        title="API status"
        badge={health.status === "healthy" ? "live" : "error"}
        value={health.status === "healthy" ? "Healthy" : "Degraded"}
      />
      <StatusCard
        title="Database"
        badge={dbOk ? "live" : "error"}
        value={dbOk ? "Connected" : health.db}
      />
      <StatusCard
        title="Backend version"
        badge="live"
        value={`v${health.version}`}
      />
    </div>
  );
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ skip?: string }>;
}) {
  const params = await searchParams;
  if (!params.skip) {
    const profileExists = await checkProfileExists();
    if (profileExists === false) {
      redirect("/onboarding");
    }
  }

  return (
    <DashboardShell title="Dashboard">
      <div className="flex flex-col gap-10">
        {/* Live — system status from /health */}
        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            System status
          </h2>
          <SystemStatus />
        </section>

        {/* Live — profile from /api/v1/rico/profile */}
        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            Your profile
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <ProfileSummaryCard />
            <StatusCard title="CV status" badge="placeholder">
              <p className="text-sm text-zinc-500">
                Upload a CV to enable profile-based job matching.
              </p>
            </StatusCard>
          </div>
        </section>

        {/* Live — dashboard stats from /api/v1/jobs, /api/v1/applications, /api/v1/settings */}
        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            Overview
          </h2>
          <DashboardStats />
        </section>

        {/* Live — saved searches from /api/v1/rico/settings/saved-searches */}
        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            Job search
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <SavedSearchesList />
          </div>
        </section>
      </div>
    </DashboardShell>
  );
}
