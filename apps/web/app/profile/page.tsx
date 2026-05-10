"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
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

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-zinc-500">{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

function ChatCTA({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/5 px-4 py-3">
      <p className="mb-2 text-sm text-zinc-400">{message}</p>
      <Link
        href="/chat"
        className="inline-block rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-indigo-500"
      >
        Open Rico chat →
      </Link>
    </div>
  );
}

function ProfileDetail({ profile }: { profile: ProfileResponse }) {
  const hasJobPrefs =
    (profile.target_roles?.length ?? 0) > 0 ||
    (profile.preferred_cities?.length ?? 0) > 0 ||
    profile.salary_expectation_aed != null ||
    profile.years_experience != null;

  const hasSkills = (profile.skills?.length ?? 0) > 0;

  return (
    <div className="flex flex-col gap-4">
      {/* Identity */}
      <StatusCard title="Identity" badge="live">
        <dl className="grid grid-cols-1 gap-y-3 text-sm sm:grid-cols-2 sm:gap-x-6">
          <Row label="Name">
            <span className="text-zinc-200">{profile.name ?? "—"}</span>
          </Row>
          <Row label="Email">
            <span className="text-zinc-200">{profile.email ?? "—"}</span>
          </Row>
          {profile.phone && (
            <Row label="Phone">
              <span className="text-zinc-200">{profile.phone}</span>
            </Row>
          )}
          {profile.telegram_username && (
            <Row label="Telegram">
              <span className="text-zinc-200">{profile.telegram_username}</span>
            </Row>
          )}
          {profile.visa_status && (
            <Row label="Visa">
              <span className="text-zinc-200">{profile.visa_status}</span>
            </Row>
          )}
          {profile.notice_period && (
            <Row label="Notice">
              <span className="text-zinc-200">{profile.notice_period}</span>
            </Row>
          )}
        </dl>
      </StatusCard>

      {/* Job preferences */}
      {hasJobPrefs ? (
        <StatusCard title="Job preferences" badge="live">
          <dl className="grid grid-cols-1 gap-y-3 text-sm sm:grid-cols-2 sm:gap-x-6">
            {(profile.target_roles?.length ?? 0) > 0 && (
              <Row label="Target roles">
                <div className="flex flex-wrap gap-1">
                  {profile.target_roles!.map((r) => <Tag key={r} label={r} />)}
                </div>
              </Row>
            )}
            {(profile.preferred_cities?.length ?? 0) > 0 && (
              <Row label="Cities">
                <div className="flex flex-wrap gap-1">
                  {profile.preferred_cities!.map((c) => <Tag key={c} label={c} />)}
                </div>
              </Row>
            )}
            {profile.salary_expectation_aed != null && (
              <Row label="Salary target">
                <span className="text-zinc-200">
                  AED {profile.salary_expectation_aed.toLocaleString()}
                </span>
              </Row>
            )}
            {profile.minimum_salary_aed != null && (
              <Row label="Minimum salary">
                <span className="text-zinc-200">
                  AED {profile.minimum_salary_aed.toLocaleString()}
                </span>
              </Row>
            )}
            {profile.years_experience != null && (
              <Row label="Experience">
                <span className="text-zinc-200">{profile.years_experience} yrs</span>
              </Row>
            )}
          </dl>
        </StatusCard>
      ) : (
        <StatusCard title="Job preferences" badge="pending">
          <ChatCTA message="Tell Rico your target roles, preferred cities, and salary expectations to complete your job preferences." />
        </StatusCard>
      )}

      {/* Skills */}
      {hasSkills ? (
        <StatusCard title="Skills" badge="live">
          <div className="flex flex-wrap gap-1.5">
            {profile.skills!.map((s) => <Tag key={s} label={s} />)}
          </div>
        </StatusCard>
      ) : (
        <StatusCard title="Skills" badge="pending">
          <ChatCTA message="Share your skills with Rico to improve job matching accuracy." />
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
            <p className="mb-3 text-sm text-zinc-400">
              Could not load your profile. Make sure you are signed in.
            </p>
            <Link
              href="/login"
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors underline underline-offset-2"
            >
              Go to sign in
            </Link>
          </StatusCard>
        )}

        {!loading && !error && profile && !profile.profile_exists && (
          <div className="flex flex-col gap-4">
            <StatusCard title="Profile" badge="pending">
              <p className="mb-1 text-sm text-zinc-300">No profile set up yet.</p>
              <p className="mb-4 text-sm text-zinc-500">
                Rico builds your profile through a short conversation. Tell it your
                target role, experience, location, and salary range to get started.
              </p>
              <Link
                href="/chat"
                className="inline-block rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500"
              >
                Start setup with Rico →
              </Link>
            </StatusCard>

            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
              <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
                What Rico will set up
              </h3>
              <ul className="flex flex-col gap-2 text-sm text-zinc-400">
                {[
                  "Target roles and preferred job titles",
                  "Preferred cities and remote preferences",
                  "Salary expectations",
                  "Years of experience and skills",
                  "Visa status and notice period",
                ].map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <span className="mt-0.5 text-indigo-500">·</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {!loading && !error && profile?.profile_exists && (
          <ProfileDetail profile={profile} />
        )}
      </div>
    </DashboardShell>
  );
}
