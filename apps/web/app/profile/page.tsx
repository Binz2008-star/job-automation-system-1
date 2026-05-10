"use client";

import { useEffect, useState } from "react";
import { fetchProfile, type ProfileResponse } from "@/lib/api";
import { DashboardShell } from "@/components/DashboardShell";
import { StatusCard } from "@/components/StatusCard";

function Tag({ label }: { label: string }) {
  return (
    <span className="rounded-md bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300">
      {label}
    </span>
  );
}

function ProfileDetail({ profile }: { profile: ProfileResponse }) {
  return (
    <div className="flex flex-col gap-4">
      {/* Identity */}
      <StatusCard title="Identity" badge="live">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-zinc-500">Name</dt>
          <dd className="text-zinc-200">{profile.name ?? "—"}</dd>
          <dt className="text-zinc-500">Email</dt>
          <dd className="text-zinc-200">{profile.email ?? "—"}</dd>
          {profile.phone && (
            <>
              <dt className="text-zinc-500">Phone</dt>
              <dd className="text-zinc-200">{profile.phone}</dd>
            </>
          )}
          {profile.telegram_username && (
            <>
              <dt className="text-zinc-500">Telegram</dt>
              <dd className="text-zinc-200">{profile.telegram_username}</dd>
            </>
          )}
        </dl>
      </StatusCard>

      {/* Job preferences */}
      <StatusCard title="Job preferences" badge="live">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <dt className="text-zinc-500">Target roles</dt>
          <dd className="flex flex-wrap gap-1">
            {profile.target_roles?.length
              ? profile.target_roles.map((r) => <Tag key={r} label={r} />)
              : <span className="text-zinc-500">—</span>}
          </dd>

          <dt className="text-zinc-500">Cities</dt>
          <dd className="flex flex-wrap gap-1">
            {profile.preferred_cities?.length
              ? profile.preferred_cities.map((c) => <Tag key={c} label={c} />)
              : <span className="text-zinc-500">—</span>}
          </dd>

          {profile.salary_expectation_aed != null && (
            <>
              <dt className="text-zinc-500">Salary target</dt>
              <dd className="text-zinc-200">
                AED {profile.salary_expectation_aed.toLocaleString()}
              </dd>
            </>
          )}

          {profile.years_experience != null && (
            <>
              <dt className="text-zinc-500">Experience</dt>
              <dd className="text-zinc-200">{profile.years_experience} yrs</dd>
            </>
          )}

          {profile.visa_status && (
            <>
              <dt className="text-zinc-500">Visa</dt>
              <dd className="text-zinc-200">{profile.visa_status}</dd>
            </>
          )}

          {profile.notice_period && (
            <>
              <dt className="text-zinc-500">Notice</dt>
              <dd className="text-zinc-200">{profile.notice_period}</dd>
            </>
          )}
        </dl>
      </StatusCard>

      {/* Skills */}
      {profile.skills && profile.skills.length > 0 && (
        <StatusCard title="Skills" badge="live">
          <div className="flex flex-wrap gap-1.5">
            {profile.skills.map((s) => <Tag key={s} label={s} />)}
          </div>
        </StatusCard>
      )}
    </div>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error,   setError]   = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProfile()
      .then(setProfile)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  return (
    <DashboardShell title="Profile">
      <div className="max-w-2xl">
        {loading && (
          <StatusCard title="Profile" badge="pending">
            <p className="text-sm text-zinc-500">Loading…</p>
          </StatusCard>
        )}
        {!loading && error && (
          <StatusCard title="Profile" badge="error">
            <p className="text-sm text-zinc-400">
              Could not load profile. Make sure you are signed in.
            </p>
          </StatusCard>
        )}
        {!loading && !error && profile && !profile.profile_exists && (
          <StatusCard title="Profile" badge="pending">
            <p className="text-sm text-zinc-500">
              No profile yet. Use the Rico chat to complete onboarding and
              your profile will appear here.
            </p>
          </StatusCard>
        )}
        {!loading && !error && profile?.profile_exists && (
          <ProfileDetail profile={profile} />
        )}
      </div>
    </DashboardShell>
  );
}
