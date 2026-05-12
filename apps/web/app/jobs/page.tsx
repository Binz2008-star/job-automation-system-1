"use client";

import { DashboardShell } from "@/components/DashboardShell";
import { JobCard } from "@/components/jobs/JobCard";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { ToastContainer } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { ApiError, applyJob, getJobs, saveJob, skipJob } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Job } from "@/types";
import { useCallback, useEffect, useMemo, useState } from "react";

const SCORE_THRESHOLDS = { HIGH: 85, MID: 65 };
const SUCCESS_STATUSES = ["applied", "success", "submitted", "saved"];
const TRACKED_STATUSES = ["saved", "skipped", "already_tracked"];

type Filter = "all" | "high" | "mid";

const FILTER_LABELS: Record<Filter, string> = {
  all: "All",
  high: "85%+ match",
  mid: "65–84%",
};

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
    setSubmittingId(jobId);

    const payload = {
      job: {
        link: job.apply_url,
        title: job.title,
        company: job.company,
        location: job.location,
        score: job.score,
      },
    };

    try {
      if (action === "apply") {
        if (!job.apply_url) {
          throw new Error("This job is missing an apply link.");
        }
        const result = await applyJob(jobId, payload);
        if (!SUCCESS_STATUSES.includes(String(result.status ?? "").toLowerCase())) {
          throw new Error(result.message || "Manual apply required for this job.");
        }
        toast("Application submitted", "success");
        return;
      }

      if (action === "save") {
        const result = await saveJob(jobId, payload);
        if (!TRACKED_STATUSES.includes(String(result.status ?? "").toLowerCase())) {
          throw new Error(result.message || "Could not save this job.");
        }
        toast(
          result.status === "already_tracked" ? "Job was already tracked" : "Job saved",
          "success"
        );
        return;
      }

      if (action === "ignore") {
        const result = await skipJob(jobId, payload);
        if (!TRACKED_STATUSES.includes(String(result.status ?? "").toLowerCase())) {
          throw new Error(result.message || "Could not ignore this job.");
        }
        toast(
          result.status === "already_tracked" ? "Job was already tracked" : "Job ignored",
          "success"
        );
        setJobs((prev) => prev.filter((item) => item.job_id !== jobId));
        return;
      }

      throw new Error(`Unsupported job action: ${action}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Action failed. Please try again.", "error");
      throw err;
    } finally {
      setSubmittingId(null);
    }
  };

  const filterBar = (
    <nav className="flex gap-2" aria-label="Job filters">
      {(Object.keys(FILTER_LABELS) as Filter[]).map((f) => (
        <button
          key={f}
          onClick={() => setFilter(f)}
          className={cn(
            "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
            filter === f
              ? "bg-rico-accent-muted text-rico-purple border border-rico-accent-border"
              : "text-rico-text-dim hover:text-rico-text hover:bg-white/[0.04]"
          )}
        >
          {FILTER_LABELS[f]}
        </button>
      ))}
    </nav>
  );

  return (
    <DashboardShell
      title="Job Matches"
      subtitle={loading ? "Loading…" : `${jobs.length} roles matched your profile`}
      actions={filterBar}
    >
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <LoadingState key={i} variant="card" />
          ))}
        </div>
      ) : error ? (
        <ErrorState
          variant={error === "auth" ? "auth" : "network"}
          onRetry={fetchJobs}
        />
      ) : filtered.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filtered.map((job) => (
            <JobCard key={job.job_id} job={job} onAction={handleAction} isSubmitting={submittingId === job.job_id} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No matches in this range"
          description="Try the 'All' filter, or Rico will surface more matches in the next scan."
          actionLabel={filter !== "all" ? "Show all jobs" : undefined}
          onAction={filter !== "all" ? () => setFilter("all") : undefined}
        />
      )}
      <ToastContainer toasts={toasts} />
    </DashboardShell>
  );
}
