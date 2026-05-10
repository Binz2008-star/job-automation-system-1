import { DashboardShell } from "@/components/DashboardShell";
import { StatusCard } from "@/components/StatusCard";
import { ProfileSummaryCard } from "@/components/ProfileSummaryCard";
import { SavedSearchesList } from "@/components/SavedSearchesList";
import { fetchHealth, type HealthResponse } from "@/lib/api";

export const dynamic = "force-dynamic";

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
        <p className="text-sm text-zinc-400">
          Could not reach the backend. Check{" "}
          <code className="text-zinc-300">NEXT_PUBLIC_RICO_API</code>.
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

export default async function DashboardPage() {
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
                Expose{" "}
                <code className="text-zinc-400">POST /api/v1/rico/upload-cv</code>{" "}
                to show CV status here.
              </p>
            </StatusCard>
          </div>
        </section>

        {/* Live — saved searches from /api/v1/rico/settings/saved-searches */}
        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            Job search
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatusCard title="Job matches" badge="placeholder">
              <p className="text-sm text-zinc-500">Connect endpoint</p>
            </StatusCard>
            <SavedSearchesList />
            <StatusCard title="Applications" badge="placeholder">
              <p className="text-sm text-zinc-500">Connect endpoint</p>
            </StatusCard>
          </div>
        </section>
      </div>
    </DashboardShell>
  );
}
