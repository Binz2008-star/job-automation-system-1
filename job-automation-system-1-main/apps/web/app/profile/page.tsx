"use client";

import { DashboardShell } from "@/components/DashboardShell";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { StatusCard } from "@/components/StatusCard";
import { fetchProfile, type ProfileResponse } from "@/lib/api";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

function Tag({ label }: { label: string }) {
  return (
    <span className="rounded-md bg-white/[0.06] px-2 py-0.5 text-xs text-rico-text-muted">
      {label}
    </span>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-rico-text-dim">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function ChatCTA({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-rico-accent-border bg-rico-accent/[0.05] px-4 py-3">
      <p className="mb-2 text-sm text-rico-text-dim">{message}</p>
      <Link
        href="/chat"
        className="inline-block rounded-lg bg-rico-accent px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-rico-accent-hover"
      >
        Open Rico chat →
      </Link>
    </div>
  );
}

function ChatEditCTA({ prompt }: { prompt: string }) {
  return (
    <Link
      href={`/chat?prompt=${encodeURIComponent(prompt)}`}
      className="ml-2 text-[11px] text-rico-purple hover:text-[#c4b5fd] transition-colors underline underline-offset-2"
    >
      Edit
    </Link>
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
            <span className="text-[#eeeef5]">{profile.name ?? "—"}</span>
            <ChatEditCTA prompt="Update my name" />
          </Row>
          <Row label="Email">
            <span className="text-[#eeeef5]">{profile.email ?? "—"}</span>
          </Row>
          <Row label="Phone">
            <span className="text-[#eeeef5]">{profile.phone ?? "—"}</span>
            <ChatEditCTA prompt="Update my phone number" />
          </Row>
          <Row label="Telegram">
            <span className="text-[#eeeef5]">{profile.telegram_username ?? "—"}</span>
            <ChatEditCTA prompt="Update my Telegram username" />
          </Row>
          <Row label="Visa">
            <span className="text-[#eeeef5]">{profile.visa_status ?? "—"}</span>
            <ChatEditCTA prompt="Update my visa status" />
          </Row>
          <Row label="Notice">
            <span className="text-[#eeeef5]">{profile.notice_period ?? "—"}</span>
            <ChatEditCTA prompt="Update my notice period" />
          </Row>
        </dl>
      </StatusCard>

      {/* Job preferences */}
      <StatusCard title="Job preferences" badge={hasJobPrefs ? "live" : "pending"}>
        {hasJobPrefs ? (
          <dl className="grid grid-cols-1 gap-y-3 text-sm sm:grid-cols-2 sm:gap-x-6">
            <Row label="Target roles">
              {(profile.target_roles?.length ?? 0) > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {profile.target_roles!.map((r) => <Tag key={r} label={r} />)}
                </div>
              ) : (
                <span className="text-[#eeeef5]">—</span>
              )}
              <ChatEditCTA prompt="Update my target roles" />
            </Row>
            <Row label="Cities">
              {(profile.preferred_cities?.length ?? 0) > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {profile.preferred_cities!.map((c) => <Tag key={c} label={c} />)}
                </div>
              ) : (
                <span className="text-[#eeeef5]">—</span>
              )}
              <ChatEditCTA prompt="Update my preferred cities" />
            </Row>
            <Row label="Salary target">
              <span className="text-[#eeeef5]">
                {profile.salary_expectation_aed != null ? `AED ${profile.salary_expectation_aed.toLocaleString()}` : "—"}
              </span>
              <ChatEditCTA prompt="Update my salary target" />
            </Row>
            <Row label="Minimum salary">
              <span className="text-[#eeeef5]">
                {profile.minimum_salary_aed != null ? `AED ${profile.minimum_salary_aed.toLocaleString()}` : "—"}
              </span>
              <ChatEditCTA prompt="Update my minimum salary" />
            </Row>
            <Row label="Experience">
              <span className="text-[#eeeef5]">
                {profile.years_experience != null ? `${profile.years_experience} yrs` : "—"}
              </span>
              <ChatEditCTA prompt="Update my years of experience" />
            </Row>
          </dl>
        ) : (
          <ChatCTA message="Tell Rico your target roles, preferred cities, and salary expectations to complete your job preferences." />
        )}
      </StatusCard>

      {/* Skills */}
      <StatusCard title="Skills" badge={hasSkills ? "live" : "pending"}>
        {hasSkills ? (
          <div className="flex flex-wrap gap-1.5">
            {profile.skills!.map((s) => <Tag key={s} label={s} />)}
            <ChatEditCTA prompt="Update my skills" />
          </div>
        ) : (
          <ChatCTA message="Share your skills with Rico to improve job matching accuracy." />
        )}
      </StatusCard>
    </div>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error, setError] = useState<"auth" | "other" | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(() => {
    setError(null);
    setLoading(true);
    fetchProfile()
      .then(setProfile)
      .catch((err: unknown) => {
        const is401 = err instanceof Error && err.message.includes("401");
        setError(is401 ? "auth" : "other");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  return (
    <DashboardShell title="Profile">
      <div className="max-w-2xl">
        {loading && <LoadingState variant="card" message="Loading profile…" />}

        {!loading && error && (
          <ErrorState
            variant={error === "auth" ? "auth" : "network"}
            onRetry={loadProfile}
          />
        )}

        {!loading && !error && profile && !profile.profile_exists && (
          <div className="flex flex-col gap-4">
            <EmptyState
              title="No profile set up yet"
              description="Rico builds your profile through a short conversation. Tell it your target role, experience, location, and salary range to get started."
              actionLabel="Start setup with Rico"
              actionHref="/chat"
            />

            <div className="rounded-xl border border-rico-border bg-rico-surface-2/60 p-5">
              <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-rico-text-dim">
                What Rico will set up
              </h3>
              <ul className="flex flex-col gap-2 text-sm text-rico-text-muted">
                {[
                  "Target roles and preferred job titles",
                  "Preferred cities and remote preferences",
                  "Salary expectations",
                  "Years of experience and skills",
                  "Visa status and notice period",
                ].map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <span className="mt-0.5 text-rico-purple">·</span>
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
