"use client";

import { DashboardShell } from "@/components/DashboardShell";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ToastContainer } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import {
  ApiError,
  getApplications,
  updateApplicationStatus,
} from "@/lib/api";
import type { Application, ApplicationStatus } from "@/types";
import { useCallback, useEffect, useState } from "react";

const STATUS_OPTIONS: ApplicationStatus[] = [
  "applied",
  "interview",
  "offer",
  "rejected",
  "saved",
  "opened",
  "decision_made",
];

const STAT_LABELS: Record<ApplicationStatus, string> = {
  applied: "Applied",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  saved: "Saved",
  opened: "Opened",
  decision_made: "Decision",
};

function fmtDate(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export default function ApplicationsPage() {
  const { user } = useAuth();
  const { toasts, toast } = useToast();
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<"auth" | "other" | null>(null);
  const [updating, setUpdating] = useState<string | null>(null);

  const fetchApps = useCallback(() => {
    if (!user) return;
    setLoading(true);
    setError(null);
    getApplications()
      .then((r) => setApps(r.applications))
      .catch((err) => {
        const is401 = err instanceof ApiError && err.statusCode === 401;
        setError(is401 ? "auth" : "other");
        toast(is401 ? "Session expired — please log in again" : "Could not load applications", "error");
      })
      .finally(() => setLoading(false));
  }, [user, toast]);

  useEffect(() => {
    fetchApps();
  }, [fetchApps]);

  const changeStatus = async (app: Application, status: ApplicationStatus) => {
    if (!user || updating) return;
    setUpdating(app.application_id);
    try {
      await updateApplicationStatus(app.job_id, { status });
      setApps((prev) => prev.map((a) => (a.job_id === app.job_id ? { ...a, status } : a)));
      toast("Status updated", "success");
    } catch {
      toast("Update failed", "error");
    } finally {
      setUpdating(null);
    }
  };

  const grouped = STATUS_OPTIONS.reduce<Record<ApplicationStatus, Application[]>>(
    (acc, s) => ({ ...acc, [s]: apps.filter((a) => a.status === s) }),
    {} as Record<ApplicationStatus, Application[]>
  );

  return (
    <DashboardShell
      title="Applications"
      subtitle={loading ? "Loading…" : `${apps.length} tracked across all stages`}
    >
      <div className="flex flex-col gap-6">
        {/* Summary strip */}
        {!loading && !error && (
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-3">
            {STATUS_OPTIONS.map((s) => (
              <div key={s} className="bg-rico-surface-2/80 border border-rico-border rounded-xl p-4 text-center">
                <p className="font-display font-black text-[28px] tracking-tight text-rico-text">
                  {grouped[s].length}
                </p>
                <p className="text-[10px] text-rico-text-dim mt-1 uppercase tracking-wider">{STAT_LABELS[s]}</p>
              </div>
            ))}
          </div>
        )}

        {/* Table */}
        <div className="bg-rico-surface-2/80 border border-rico-border rounded-2xl overflow-hidden">
          {loading ? (
            <div className="flex flex-col gap-0">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-16 border-b border-white/[0.04] bg-white/[0.015] animate-pulse" />
              ))}
            </div>
          ) : error ? (
            <div className="p-6">
              <ErrorState
                variant={error === "auth" ? "auth" : "network"}
                onRetry={fetchApps}
              />
            </div>
          ) : apps.length === 0 ? (
            <div className="p-6">
              <EmptyState
                title="No applications tracked yet"
                description="Apply to jobs from the Jobs page and they'll appear here."
                actionLabel="Browse jobs"
                actionHref="/jobs"
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <div className="min-w-[760px]">
                {/* Header row */}
                <div className="grid grid-cols-[2fr_1.5fr_1fr_1fr_1fr] gap-4 px-5 py-3 border-b border-white/5">
                  {["Role", "Company", "Applied", "Status", "Action"].map((h) => (
                    <span key={h} className="text-[10px] uppercase tracking-wider text-rico-text-dim font-semibold">
                      {h}
                    </span>
                  ))}
                </div>
                {apps.map((app, i) => (
                  <div
                    key={app.application_id}
                    className={`grid grid-cols-[2fr_1.5fr_1fr_1fr_1fr] gap-4 px-5 py-4 items-center transition-colors hover:bg-white/[0.015] ${i < apps.length - 1 ? "border-b border-white/[0.04]" : ""}`}
                  >
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-rico-text truncate">{app.title}</p>
                      {app.apply_url && app.apply_url !== "#" && (
                        <a href={app.apply_url} target="_blank" rel="noreferrer" className="text-[11px] text-rico-purple hover:text-rico-text">
                          View listing ↗
                        </a>
                      )}
                    </div>
                    <p className="text-[13px] text-rico-text-muted truncate">{app.company}</p>
                    <p className="text-[12px] text-rico-text-dim">{fmtDate(app.applied_at)}</p>
                    <StatusBadge status={app.status} />
                    <select
                      value={app.status}
                      onChange={(e) => changeStatus(app, e.target.value as ApplicationStatus)}
                      disabled={updating === app.application_id}
                      aria-label={`Change status for ${app.title}`}
                      className="bg-rico-bg border border-white/[0.08] rounded-lg px-2 py-1.5 text-[11px] text-rico-text-muted outline-none focus:border-rico-accent/40 cursor-pointer disabled:opacity-40"
                    >
                      {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>{STAT_LABELS[s]}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
      <ToastContainer toasts={toasts} />
    </DashboardShell>
  );
}
