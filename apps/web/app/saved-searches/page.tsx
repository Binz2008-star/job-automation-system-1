"use client";

import { DashboardShell } from "@/components/DashboardShell";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { StatusCard } from "@/components/StatusCard";
import { fetchSavedSearches, type SavedSearch } from "@/lib/api";
import { useCallback, useEffect, useState } from "react";

export default function SavedSearchesPage() {
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadSearches = useCallback(() => {
    setError(false);
    setLoading(true);
    fetchSavedSearches()
      .then((r) => setSearches(r.searches))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadSearches();
  }, [loadSearches]);

  return (
    <DashboardShell title="Saved Searches">
      <div className="max-w-2xl">
        {loading && <LoadingState variant="card" message="Loading saved searches…" />}

        {!loading && error && (
          <ErrorState
            variant="network"
            onRetry={loadSearches}
          />
        )}

        {!loading && !error && searches.length === 0 && (
          <EmptyState
            title="No saved searches yet"
            description="Use the Rico chat to save a job search."
            actionLabel="Open chat"
            actionHref="/chat"
          />
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
                  className="flex items-start justify-between gap-3 rounded-lg bg-white/[0.03] px-3 py-2.5"
                >
                  <span className="text-sm text-rico-text break-all">
                    {s.query}
                  </span>
                  <span className="shrink-0 text-xs text-rico-text-dim mt-0.5">
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
