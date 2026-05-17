"use client";

import { StatusCard } from "@/components/StatusCard";
import { fetchProfile, type ProfileResponse } from "@/lib/api";
import { useCallback, useEffect, useState } from "react";

export function ProfileSummaryCard() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading");

  const loadProfile = useCallback(async () => {
    try {
      const data = await fetchProfile();
      setProfile(data);
      setStatus("ready");
    } catch (err) {
      console.error("Profile Load Error:", err);
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadProfile();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadProfile]);

  const handleRetry = useCallback(() => {
    setStatus("loading");
    void loadProfile();
  }, [loadProfile]);

  const displayRoles = profile?.target_roles?.length
    ? profile.target_roles.slice(0, 3).join(", ")
    : null;

  if (status === "loading") {
    return (
      <StatusCard title="Profile Summary" badge="pending">
        <div className="animate-pulse space-y-2">
          <div className="h-4 w-24 bg-white/5 rounded" />
          <div className="h-3 w-32 bg-white/5 rounded" />
        </div>
      </StatusCard>
    );
  }

  if (status === "error") {
    return (
      <StatusCard title="Profile Summary" badge="error">
        <p className="text-sm text-[#5a5a7a] mb-2">Could not load profile.</p>
        <button
          onClick={handleRetry}
          className="text-xs text-[#a78bfa] underline hover:text-[#eeeef5] transition-colors"
        >
          Try again
        </button>
      </StatusCard>
    );
  }

  if (!profile?.profile_exists) {
    return (
      <StatusCard title="Profile Summary" badge="pending">
        <p className="text-[13px] text-[#8080a0] leading-relaxed">
          No profile yet. Use the Rico chat to complete onboarding.
        </p>
      </StatusCard>
    );
  }

  return (
    <StatusCard title="Profile Summary" badge="live">
      <div className="space-y-1.5">
        <p className="text-[16px] font-black font-['Cabinet_Grotesk',sans-serif] text-[#eeeef5] tracking-tight">
          {profile.name ?? profile.email ?? "—"}
        </p>

        {displayRoles && (
          <p className="text-[13px] text-[#5a5a7a]">
            Targeting: <span className="text-[#8080a0]">{displayRoles}</span>
          </p>
        )}

        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
          {profile.years_experience != null && (
            <p className="text-[12px] text-[#5a5a7a]">
              Experience: <span className="text-[#8080a0] font-medium">{profile.years_experience} yrs</span>
            </p>
          )}

          {profile.visa_status && (
            <p className="text-[12px] text-[#5a5a7a]">
              Visa: <span className="text-[#8080a0] font-medium">{profile.visa_status}</span>
            </p>
          )}
        </div>
      </div>
    </StatusCard>
  );
}
