"use client";

import { StatusCard } from "@/components/StatusCard";
import { ApiError } from "@/lib/client";
import { getApplications, getApplicationStats } from "@/services/applications";
import { getJobs } from "@/services/jobs";
import { getSettings } from "@/services/settings";
import { useCallback, useEffect, useState } from "react";

interface Stats {
  jobsTotal: number;
  appsTotal: number;
  applied: number;
  interview: number;
  offer: number;
  rejected: number;
  minScore: number;
  maxDaily: number;
}

export function DashboardStats() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<"auth" | "other" | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [jobsResult, appsResult, statsResult, settingsResult] = await Promise.allSettled([
        getJobs(1, 1),
        getApplications(undefined, 1, 1),
        getApplicationStats(),
        getSettings(),
      ]);

      const jobsRes = jobsResult.status === "fulfilled" ? jobsResult.value : null;
      const appsRes = appsResult.status === "fulfilled" ? appsResult.value : null;
      const statsRes = statsResult.status === "fulfilled" ? statsResult.value : null;
      const settingsRes = settingsResult.status === "fulfilled" ? settingsResult.value : null;

      if (!jobsRes && !appsRes) {
        setError("other");
        return;
      }

      setStats({
        jobsTotal: jobsRes?.total ?? 0,
        appsTotal: appsRes?.total ?? 0,
        applied: statsRes?.applied ?? 0,
        interview: statsRes?.interview_scheduled ?? 0,
        offer: statsRes?.offer_extended ?? 0,
        rejected: statsRes?.rejected ?? 0,
        minScore: settingsRes?.min_score ?? 0,
        maxDaily: settingsRes?.max_daily_applies ?? 0,
      });
    } catch (err) {
      const is401 = err instanceof ApiError && err.statusCode === 401;
      setError(is401 ? "auth" : "other");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) return <StatsSkeleton />;

  if (error === "auth") return <ErrorMessage message="Session expired — please log in again." icon="🔒" />;

  if (error === "other") return <ErrorMessage message="Could not load dashboard stats. The backend may be unavailable." icon="⚠️" />;

  if (!stats) return null;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <StatusCard title="Job matches" badge="live" value={String(stats.jobsTotal)} href="/jobs">
        <p className="text-sm text-[#5a5a7a]">
          {stats.jobsTotal === 0 ? "No matches yet — Rico will scan soon." : "Active job recommendations"}
        </p>
      </StatusCard>
      <StatusCard title="Applications tracked" badge="live" value={String(stats.appsTotal)} href="/applications">
        <p className="text-sm text-[#5a5a7a]">
          {stats.applied > 0 && `${stats.applied} applied`}
          {stats.interview > 0 && ` · ${stats.interview} interview`}
          {stats.offer > 0 && ` · ${stats.offer} offer`}
        </p>
      </StatusCard>
      <StatusCard title="Daily limit" badge={stats.maxDaily > 0 ? "live" : "placeholder"} value={`${stats.maxDaily}`} href="/settings">
        <p className="text-sm text-[#5a5a7a]">Max {stats.maxDaily} auto-applies per day</p>
      </StatusCard>
    </div>
  );
}

function StatsSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-28 rounded-2xl bg-[#13132a]/60 border border-[rgba(255,255,255,0.06)] animate-pulse" />
      ))}
    </div>
  );
}

function ErrorMessage({ message, icon }: { message: string; icon: string }) {
  return (
    <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#13132a]/60 p-5 text-center">
      <span className="text-2xl block mb-2">{icon}</span>
      <p className="text-sm text-[#5a5a7a] font-medium">{message}</p>
    </div>
  );
}
