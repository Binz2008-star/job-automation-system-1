"use client";

import { DashboardShell } from "@/components/DashboardShell";
import { JobCard } from "@/components/jobs/JobCard";
import { ToastContainer } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/client";
import { applyJob, getJobs } from "@/services/jobs";
import type { Job } from "@/types";
import { useCallback, useEffect, useMemo, useState } from "react";

const SCORE_THRESHOLDS = { HIGH: 85, MID: 65 };
const SUCCESS_STATUSES = ["applied", "success", "submitted", "saved"];

type Filter = "all" | "high" | "mid";

export default function JobsPage() {
  const { user } = useAuth();
  const { toasts, toast } = useToast();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<"auth" | "other" | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [submittingId, setSubmittingId] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const response = await getJobs();
      setJobs(response.jobs || []);
    } catch (err) {
      const is401 = err instanceof ApiError && err.statusCode === 401;
      setError(is401 ? "auth" : "other");
      toast(is401 ? "Session expired — please log in again" : "Could not load jobs", "error");
    } finally {
      setLoading(false);
    }
  }, [user, toast]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const filtered = useMemo(
    () =>
      jobs.filter((j) =>
        filter === "high"
          ? j.score >= SCORE_THRESHOLDS.HIGH
          : filter === "mid"
            ? j.score >= SCORE_THRESHOLDS.MID && j.score < SCORE_THRESHOLDS.HIGH
            : true
      ),
    [jobs, filter]
  );

  const handleAction = async (jobId: string, action: string) => {
    if (!user || submittingId) return;
    const job = jobs.find((j) => j.job_id === jobId);
    if (!job) return;
    if (action !== "apply") {
      toast("Action recorded", "success");
      return;
    }
    setSubmittingId(jobId);
    try {
      const result = await applyJob(jobId, {
        job: {
          link: job.apply_url,
          title: job.title,
          company: job.company,
          location: job.location,
          score: job.score,
        },
      });
      if (SUCCESS_STATUSES.includes(String(result.status ?? "").toLowerCase())) {
        toast("Application submitted ✓", "success");
        setJobs((prev) => prev.map((j) => (j.job_id === jobId ? { ...j, status: "applied" as const } : j)));
      } else {
        toast(result.message || "Manual apply required for this job.", "error");
      }
    } catch {
      toast("Application failed. Please try again.", "error");
    } finally {
      setSubmittingId(null);
    }
  };

  return (
    <DashboardShell>
      <header className="px-8 py-6 border-b border-white/5 bg-[rgba(7,7,18,0.7)] backdrop-blur-md sticky top-0 z-10 flex items-center justify-between">
        <div>
          <h1 className="font-['Cabinet_Grotesk',sans-serif] font-900 text-[22px] tracking-tight">
            Job Matches
          </h1>
          <p className="text-[13px] text-[#5a5a7a] mt-0.5">
            {loading ? "Loading…" : `${jobs.length} roles matched your profile today`}
          </p>
        </div>

        <nav className="flex gap-2" aria-label="Job filters">
          {(["all", "high", "mid"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-[12px] font-semibold transition-all ${filter === f
                ? "bg-[rgba(91,79,255,0.15)] text-[#a78bfa] border border-[rgba(91,79,255,0.25)]"
                : "text-[#5a5a7a] hover:text-[#eeeef5] hover:bg-[rgba(255,255,255,0.04)]"
                }`}
            >
              {f === "all" ? "All" : f === "high" ? "85%+ match" : "65–84%"}
            </button>
          ))}
        </nav>
      </header>

      <main className="p-8">
        {loading ? (
          <div className="grid grid-cols-2 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-52 rounded-2xl bg-[#13132a]/60 animate-pulse border border-[rgba(255,255,255,0.06)]" />
            ))}
          </div>
        ) : error ? (
          <ErrorState type={error} onRetry={fetchJobs} />
        ) : filtered.length > 0 ? (
          <div className="grid grid-cols-2 gap-4">
            {filtered.map((job) => (
              <JobCard key={job.job_id} job={job} onAction={handleAction} isSubmitting={submittingId === job.job_id} />
            ))}
          </div>
        ) : (
          <EmptyState />
        )}
      </main>
      <ToastContainer toasts={toasts} />
    </DashboardShell>
  );
}

function ErrorState({ type, onRetry }: { type: "auth" | "other"; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
      <span className="text-5xl opacity-25">{type === "auth" ? "🔒" : "⚠️"}</span>
      <h2 className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[18px] text-[#5a5a7a]">
        {type === "auth" ? "Session expired" : "Could not load jobs"}
      </h2>
      {type === "auth" ? (
        <a
          href="/login"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[rgba(91,79,255,0.15)] text-[#a78bfa] border border-[rgba(91,79,255,0.25)] text-[13px] font-semibold hover:bg-[rgba(91,79,255,0.25)] transition-all"
        >
          Log in again
        </a>
      ) : (
        <button
          onClick={onRetry}
          className="text-[13px] text-[#a78bfa] underline underline-offset-2 hover:text-white transition-colors"
        >
          Try again
        </button>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
      <span className="text-5xl opacity-25">🔍</span>
      <h2 className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[18px] text-[#5a5a7a]">
        No matches in this range
      </h2>
      <p className="text-[13px] text-[#5a5a7a] max-w-xs">
        Try &quot;All&quot; filter, or Rico will surface more matches in the next scan
      </p>
    </div>
  );
}
