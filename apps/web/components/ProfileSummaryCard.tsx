"use client";

import { useEffect, useState } from "react";
import { fetchProfile, type ProfileResponse } from "@/lib/api";
import { StatusCard } from "@/components/StatusCard";

export function ProfileSummaryCard() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error,   setError]   = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProfile()
      .then(setProfile)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <StatusCard title="Profile summary" badge="pending">
        <p className="text-sm text-zinc-500">Loading…</p>
      </StatusCard>
    );
  }

  if (error) {
    return (
      <StatusCard title="Profile summary" badge="error">
        <p className="text-sm text-zinc-400">Could not load profile.</p>
      </StatusCard>
    );
  }

  if (!profile?.profile_exists) {
    return (
      <StatusCard title="Profile summary" badge="pending">
        <p className="text-sm text-zinc-500">
          No profile yet. Use the Rico chat to complete onboarding.
        </p>
      </StatusCard>
    );
  }

  const roles = profile.target_roles?.length
    ? profile.target_roles.slice(0, 3).join(", ")
    : null;

  return (
    <StatusCard title="Profile summary" badge="live">
      <p className="text-base font-medium text-white">
        {profile.name ?? profile.email ?? "—"}
      </p>
      {roles && (
        <p className="text-sm text-zinc-400">
          Targeting: <span className="text-zinc-200">{roles}</span>
        </p>
      )}
      {profile.years_experience != null && (
        <p className="text-sm text-zinc-400">
          Experience:{" "}
          <span className="text-zinc-200">{profile.years_experience} yrs</span>
        </p>
      )}
      {profile.visa_status && (
        <p className="text-sm text-zinc-400">
          Visa: <span className="text-zinc-200">{profile.visa_status}</span>
        </p>
      )}
    </StatusCard>
  );
}
