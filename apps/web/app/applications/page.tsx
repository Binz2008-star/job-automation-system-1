"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { getApplications, updateApplicationStatus } from "@/services/applications";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ToastContainer } from "@/components/ui/Toast";
import type { Application, ApplicationStatus } from "@/types";

const STATUS_OPTIONS: ApplicationStatus[] = [
  "applied",
  "interview_scheduled",
  "offer_extended",
  "rejected",
  "saved",
];

function fmtDate(iso?: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export default function ApplicationsPage() {
  const { user } = useAuth();
  const { toasts, toast } = useToast();
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    getApplications(user.user_id)
      .then((r) => setApps(r.applications))
      .catch(() => toast("Could not load applications", "error"))
      .finally(() => setLoading(false));
  }, [user]);

  const changeStatus = async (app: Application, status: ApplicationStatus) => {
    if (!user || updating) return;
    setUpdating(app.application_id);
    try {
      const updated = await updateApplicationStatus({
        user_id: user.user_id,
        application_id: app.application_id,
        status,
      });
      setApps((prev) => prev.map((a) => (a.application_id === updated.application_id ? updated : a)));
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

  const statLabels: Record<ApplicationStatus, string> = {
    applied: "Applied",
    interview_scheduled: "Interview",
    offer_extended: "Offer",
    rejected: "Rejected",
    saved: "Saved",
  };

  return (
    <>
      <div className="px-8 py-6 border-b border-white/5 bg-[rgba(7,7,18,0.7)] backdrop-blur-md sticky top-0 z-10">
        <h1 className="font-['Cabinet_Grotesk',sans-serif] font-900 text-[22px] tracking-tight">Applications</h1>
        <p className="text-[13px] text-white/35 mt-0.5">
          {loading ? "Loading…" : `${apps.length} tracked across all stages`}
        </p>
      </div>

      <div className="p-8 flex flex-col gap-6">
        {/* summary strip */}
        {!loading && (
          <div className="grid grid-cols-5 gap-3">
            {STATUS_OPTIONS.map((s) => (
              <div key={s} className="bg-[#0e0e20] border border-white/6 rounded-xl p-4 text-center">
                <p className="font-['Cabinet_Grotesk',sans-serif] font-900 text-[28px] tracking-tight text-white/80">
                  {grouped[s].length}
                </p>
                <p className="text-[10px] text-white/30 mt-1 uppercase tracking-wider">{statLabels[s]}</p>
              </div>
            ))}
          </div>
        )}

        {/* table */}
        <div className="bg-[#0e0e20] border border-white/6 rounded-2xl overflow-hidden">
          {loading ? (
            <div className="flex flex-col">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-16 border-b border-white/5 bg-white/2 animate-pulse" />
              ))}
            </div>
          ) : apps.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
              <span className="text-4xl opacity-25">📄</span>
              <p className="text-[14px] text-white/30">No applications tracked yet</p>
              <p className="text-[12px] text-white/20">Apply to jobs from the Jobs page and they'll appear here</p>
            </div>
          ) : (
            <>
              {/* header row */}
              <div className="grid grid-cols-[2fr_1.5fr_1fr_1fr_1fr] gap-4 px-5 py-3 border-b border-white/5">
                {["Role", "Company", "Applied", "Status", "Action"].map((h) => (
                  <span key={h} className="text-[10px] uppercase tracking-wider text-white/25 font-semibold">
                    {h}
                  </span>
                ))}
              </div>
              {apps.map((app, i) => (
                <div
                  key={app.application_id}
                  className={`grid grid-cols-[2fr_1.5fr_1fr_1fr_1fr] gap-4 px-5 py-4 items-center transition-colors hover:bg-white/2 ${
                    i < apps.length - 1 ? "border-b border-white/5" : ""
                  }`}
                >
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-white/80 truncate">{app.title}</p>
                    {app.apply_url && app.apply_url !== "#" && (
                      <a href={app.apply_url} target="_blank" rel="noreferrer" className="text-[11px] text-[#a78bfa] hover:text-white">
                        View listing ↗
                      </a>
                    )}
                  </div>
                  <p className="text-[13px] text-white/45 truncate">{app.company}</p>
                  <p className="text-[12px] text-white/30">{fmtDate(app.applied_at)}</p>
                  <StatusBadge status={app.status} />
                  <select
                    value={app.status}
                    onChange={(e) => changeStatus(app, e.target.value as ApplicationStatus)}
                    disabled={updating === app.application_id}
                    className="bg-[#14142a] border border-white/8 rounded-lg px-2 py-1.5 text-[11px] text-white/60 outline-none focus:border-[rgba(91,79,255,0.4)] cursor-pointer disabled:opacity-40"
                  >
                    {STATUS_OPTIONS.map((s) => (
                      <option key={s} value={s}>{statLabels[s]}</option>
                    ))}
                  </select>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
      <ToastContainer toasts={toasts} />
    </>
  );
}
