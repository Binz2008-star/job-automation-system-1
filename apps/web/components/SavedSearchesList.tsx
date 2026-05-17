"use client";

import { StatusCard } from "@/components/StatusCard";
import { deleteSavedSearch, fetchSavedSearches, type SavedSearch } from "@/lib/api";
import { useEffect, useState } from "react";

export function SavedSearchesList() {
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [error, setError] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const handleDelete = async (id: string, query: string) => {
    if (!confirm(`Delete saved search: "${query}"?`)) {
      return;
    }

    setDeleteError(null);
    try {
      await deleteSavedSearch(id);
      // Remove the deleted item from local state
      setSearches((current) => current.filter((s) => s.id !== id));
    } catch (err) {
      setDeleteError("Failed to delete saved search");
    }
  };

  useEffect(() => {
    fetchSavedSearches()
      .then((r) => setSearches(r.searches))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <StatusCard title="Saved searches" badge="pending">
        <p className="text-sm text-zinc-500">Loading…</p>
      </StatusCard>
    );
  }

  if (error) {
    return (
      <StatusCard title="Saved searches" badge="error">
        <p className="text-sm text-zinc-400">Could not load saved searches.</p>
      </StatusCard>
    );
  }

  if (searches.length === 0) {
    return (
      <StatusCard title="Saved searches" badge="live" value="0">
        <p className="text-sm text-zinc-500">
          No saved searches yet. Use the Rico chat to save a job search.
        </p>
      </StatusCard>
    );
  }

  return (
    <StatusCard title="Saved searches" badge="live" value={String(searches.length)}>
      {deleteError && (
        <p className="mb-2 text-sm text-red-400">{deleteError}</p>
      )}
      <ul className="mt-1 flex flex-col gap-2">
        {searches.map((s) => (
          <li
            key={s.id}
            className="flex items-start justify-between gap-2 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.05)] px-3 py-2 text-sm"
          >
            <span className="text-[#eeeef5] break-all flex-1">{s.query}</span>
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-xs text-[#5a5a7a]">
                {new Date(s.created_at).toLocaleDateString()}
              </span>
              <button
                onClick={() => handleDelete(s.id, s.query)}
                className="text-xs text-red-400 hover:text-red-300 transition-colors"
                title="Delete saved search"
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </StatusCard>
  );
}
