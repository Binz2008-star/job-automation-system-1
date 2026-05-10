"use client";

import { useEffect, useState } from "react";
import { fetchSavedSearches, type SavedSearch } from "@/lib/api";
import { DashboardShell } from "@/components/DashboardShell";
import { StatusCard } from "@/components/StatusCard";

export default function SavedSearchesPage() {
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [error,    setError]    = useState(false);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    fetchSavedSearches()
      .then((r) => setSearches(r.searches))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  return (
    <DashboardShell title="Saved Searches">
      <div className="max-w-2xl">
        {loading && (
          <StatusCard title="Saved searches" badge="pending">
            <p className="text-sm text-zinc-500">Loading…</p>
          </StatusCard>
        )}

        {!loading && error && (
          <StatusCard title="Saved searches" badge="error">
            <p className="text-sm text-zinc-400">
              Could not load saved searches. Make sure you are signed in.
            </p>
          </StatusCard>
        )}

        {!loading && !error && searches.length === 0 && (
          <StatusCard title="Saved searches" badge="live" value="0">
            <p className="text-sm text-zinc-500">
              No saved searches yet. Use the Rico chat to save a job search.
            </p>
          </StatusCard>
        )}

        {!loading && !error && searches.length > 0 && (
          <StatusCard
            title="Saved searches"
            badge="live"
            value={String(searches.length)}
          >
            <ul className="mt-1 flex flex-col gap-2">
              {searches.map((s) => (
                <li
                  key={s.id}
                  className="flex items-start justify-between gap-3 rounded-lg bg-zinc-800/50 px-3 py-2.5"
                >
                  <span className="text-sm text-zinc-200 break-all">
                    {s.query}
                  </span>
                  <span className="shrink-0 text-xs text-zinc-500 mt-0.5">
                    {new Date(s.created_at).toLocaleDateString()}
                  </span>
                </li>
              ))}
            </ul>
          </StatusCard>
        )}
      </div>
    </DashboardShell>
  );
}
