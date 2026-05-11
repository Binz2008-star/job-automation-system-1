"use client";

import { DashboardShell } from "@/components/DashboardShell";
import { JobCard } from "@/components/jobs/JobCard";
import { ToastContainer } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/client";
import { applyJob, getJobs } from "@/services/jobs";
import type { Job } from "@/types";
import { useEffect, useState } from "react";

type Filter = "all" | "high" | "mid";

export default function JobsPage() {
  const { user } = useAuth();
  const { toasts, toast } = useToast();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<"auth" | "other" | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    setError(null);
    getJobs()
      .then((r) => setJobs(r.jobs))
      .catch((err) => {
        const is401 = err instanceof ApiError && err.statusCode === 401;
        setError(is401 ? "auth" : "other");
        toast(is401 ? "Session expired — please log in again" : "Could not load jobs", "error");
      })
      .finally(() => setLoading(false));
  }, [user, toast]);

  const filtered = jobs.filter((j) =>
    filter === "high" ? j.score >= 85 : filter === "mid" ? j.score >= 65 && j.score < 85 : true
  );

  const handleAction = async (jobId: string, action: string) => {
    if (!user) return;
    const job = jobs.find((j) => j.job_id === jobId);
    if (!job) return;
    if (action === "apply") {
      const result = await applyJob(jobId, {
        job: {
          link: job.apply_url,
          title: job.title,
          company: job.company,
          location: job.location,
          score: job.score,
        },
      });
      const successStatuses = ["applied", "success", "submitted", "saved"];
      if (successStatuses.includes(String(result.status ?? "").toLowerCase())) {
        toast("Application submitted ✓", "success");
      } else {
        toast(result.message || "Manual apply required for this job.", "error");
      }
    } else {
      toast("Action recorded", "success");
    }
  };

  return (
    <DashboardShell>
      <div className="px-8 py-6 border-b border-white/5 bg-[rgba(7,7,18,0.7)] backdrop-blur-md sticky top-0 z-10 flex items-center justify-between">
        <div>
          <h1 className="font-['Cabinet_Grotesk',sans-serif] font-900 text-[22px] tracking-tight">
            Job Matches
          </h1>
          <p className="text-[13px] text-white/35 mt-0.5">
            {loading ? "Loading…" : `${jobs.length} roles matched your profile today`}
          </p>
        </div>

        <div className="flex gap-2">
          {(["all", "high", "mid"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-[12px] font-semibold transition-all ${filter === f
                ? "bg-[rgba(91,79,255,0.15)] text-[#a78bfa] border border-[rgba(91,79,255,0.25)]"
                : "text-white/35 hover:text-white/60 hover:bg-white/5"
                }`}
            >
              {f === "all" ? "All" : f === "high" ? "85%+ match" : "65–84%"}
            </button>
          ))}
        </div>
      </div>

      <div className="p-8">
        {loading ? (
          <div className="grid grid-cols-2 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-52 rounded-2xl bg-white/3 animate-pulse" />
            ))}
          </div>
        ) : error === "auth" ? (
          <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
            <span className="text-5xl opacity-25">🔒</span>
            <p className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[18px] text-white/30">
              Session expired
            </p>
            <a
              href="/login"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[rgba(91,79,255,0.15)] text-[#a78bfa] border border-[rgba(91,79,255,0.25)] text-[13px] font-semibold hover:bg-[rgba(91,79,255,0.25)] transition-all"
            >
              Log in again
            </a>
          </div>
        ) : error === "other" ? (
          <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
            <span className="text-5xl opacity-25">⚠️</span>
            <p className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[18px] text-white/30">
              Could not load jobs
            </p>
            <p className="text-[13px] text-white/20 max-w-xs">
              The backend may be unavailable. Please try again in a moment.
            </p>
          </div>
        ) : filtered.length > 0 ? (
          <div className="grid grid-cols-2 gap-4">
            {filtered.map((job) => (
              <JobCard key={job.job_id} job={job} onAction={handleAction} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
            <span className="text-5xl opacity-25">🔍</span>
            <p className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[18px] text-white/30">
              No matches in this range
            </p>
            <p className="text-[13px] text-white/20 max-w-xs">
              Try &quot;All&quot; filter, or Rico will surface more matches in the next scan
            </p>
          </div>
        )}
      </div>
      <ToastContainer toasts={toasts} />
    </DashboardShell>
  );
}
