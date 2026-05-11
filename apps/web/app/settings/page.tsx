"use client";

import { DashboardShell } from "@/components/DashboardShell";
import { StatusCard } from "@/components/StatusCard";
import { ToastContainer } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/client";
import { getHealth } from "@/services/health";
import { getSettings, updateSettings } from "@/services/settings";
import type { HealthResponse, SettingsResponse } from "@/types";
import { useEffect, useState } from "react";

function Row({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-white/5 last:border-0">
      <span className="text-[13px] text-[#5a5a7a]">{label}</span>
      <span className={`text-[13px] font-medium flex items-center gap-1.5 ${ok === true ? "text-[#00c9a7]" : ok === false ? "text-[#ff5e5b]" : "text-[#8080a0]"
        }`}>
        {ok === true && <span className="w-1.5 h-1.5 rounded-full bg-[#00c9a7]" />}
        {ok === false && <span className="w-1.5 h-1.5 rounded-full bg-[#ff5e5b]" />}
        {value}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const { user } = useAuth();
  const { toasts, toast } = useToast();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<"auth" | "other" | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => toast("Backend unreachable", "error"))
      .finally(() => setLoadingHealth(false));
  }, [toast]);

  useEffect(() => {
    if (!user) return;
    setLoadingSettings(true);
    setError(null);
    getSettings()
      .then(setSettings)
      .catch((err) => {
        const is401 = err instanceof ApiError && err.statusCode === 401;
        setError(is401 ? "auth" : "other");
        toast(is401 ? "Session expired" : "Could not load settings", "error");
      })
      .finally(() => setLoadingSettings(false));
  }, [user, toast]);

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await updateSettings({
        min_score: settings.min_score,
        max_daily_applies: settings.max_daily_applies,
        score_threshold_apply: settings.score_threshold_apply,
        score_threshold_watch: settings.score_threshold_watch,
        telegram_chat_id: settings.telegram_chat_id,
        include_keywords: settings.include_keywords,
        exclude_keywords: settings.exclude_keywords,
      });
      setSettings(updated);
      toast("Settings saved", "success");
    } catch (err) {
      const is401 = err instanceof ApiError && err.statusCode === 401;
      toast(is401 ? "Session expired — please log in again" : "Save failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const isMock = process.env.NEXT_PUBLIC_USE_MOCK === "true";

  return (
    <DashboardShell>
      {/* Header */}
      <div className="px-8 py-6 border-b border-white/5 bg-[rgba(7,7,18,0.7)] backdrop-blur-md sticky top-0 z-10">
        <h1 className="font-['Cabinet_Grotesk',sans-serif] font-black text-[22px] tracking-tight">System Logic</h1>
        <p className="text-[13px] text-[#5a5a7a] mt-0.5">System configuration and job matching preferences</p>
      </div>

      <div className="p-8 max-w-3xl flex flex-col gap-8 animate-in fade-in duration-500">

        {/* Automation Tuning — Rico Cards */}
        {settings && (
          <section className="space-y-4">
            <h2 className="text-[11px] font-black text-[#5a5a7a] uppercase tracking-[0.2em] ml-1">Automation Tuning</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <StatusCard title="Daily Apply Limit" value={String(settings.max_daily_applies)}>
                <div className="mt-2">
                  <input
                    type="range" min={0} max={50} step={1}
                    aria-label="Daily apply limit"
                    value={settings.max_daily_applies}
                    onChange={(e) => setSettings({ ...settings, max_daily_applies: Number(e.target.value) })}
                    className="w-full h-1.5 bg-white/5 rounded-lg appearance-none cursor-pointer accent-[#5b4fff]"
                  />
                  <div className="flex justify-between mt-2 text-[10px] text-[#5a5a7a] font-bold uppercase tracking-tighter">
                    <span>Safety</span>
                    <span>Aggressive</span>
                  </div>
                </div>
              </StatusCard>

              <StatusCard title="Min Fit Score" value={`${settings.min_score}%`}>
                <div className="mt-2">
                  <input
                    type="range" min={50} max={95} step={5}
                    aria-label="Minimum fit score"
                    value={settings.min_score}
                    onChange={(e) => setSettings({ ...settings, min_score: Number(e.target.value) })}
                    className="w-full h-1.5 bg-white/5 rounded-lg appearance-none cursor-pointer accent-[#00c9a7]"
                  />
                  <div className="flex justify-between mt-2 text-[10px] text-[#5a5a7a] font-bold uppercase tracking-tighter">
                    <span>General</span>
                    <span>High Match Only</span>
                  </div>
                </div>
              </StatusCard>
            </div>
          </section>
        )}

        {/* Job Matching — Full Form */}
        <section className="bg-[#13132a]/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md relative overflow-hidden">
          <div className="absolute -top-10 -right-10 w-32 h-32 bg-[#5b4fff]/5 blur-3xl rounded-full pointer-events-none" />

          <h3 className="font-['Cabinet_Grotesk',sans-serif] font-bold text-[17px] text-white mb-6">Job Matching</h3>

          {loadingSettings ? (
            <div className="flex flex-col gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-10 rounded-lg bg-white/[0.03] animate-pulse" />
              ))}
            </div>
          ) : error === "auth" ? (
            <div className="flex flex-col items-center justify-center py-10 gap-3 text-center">
              <span className="text-4xl opacity-25">🔒</span>
              <p className="text-[14px] text-[#5a5a7a]">Session expired</p>
              <a
                href="/login"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[rgba(91,79,255,0.15)] text-[#a78bfa] border border-[rgba(91,79,255,0.25)] text-[13px] font-semibold hover:bg-[rgba(91,79,255,0.25)] transition-all"
              >
                Log in again
              </a>
            </div>
          ) : error === "other" ? (
            <div className="flex flex-col items-center justify-center py-10 gap-3 text-center">
              <span className="text-4xl opacity-25">⚠️</span>
              <p className="text-[14px] text-[#5a5a7a]">Could not load settings</p>
              <p className="text-[12px] text-[#5a5a7a]">The backend may be unavailable.</p>
            </div>
          ) : settings ? (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-4">
                <label className="flex flex-col gap-1.5">
                  <span className="text-[11px] text-[#5a5a7a] uppercase tracking-wider font-semibold">Apply threshold</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={settings.score_threshold_apply}
                    onChange={(e) => setSettings({ ...settings, score_threshold_apply: Number(e.target.value) })}
                    className="bg-[#0d0d1f] border border-white/[0.08] rounded-lg px-3 py-2 text-[13px] text-[#8080a0] outline-none focus:border-[rgba(91,79,255,0.4)]"
                  />
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="text-[11px] text-[#5a5a7a] uppercase tracking-wider font-semibold">Watch threshold</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={settings.score_threshold_watch}
                    onChange={(e) => setSettings({ ...settings, score_threshold_watch: Number(e.target.value) })}
                    className="bg-[#0d0d1f] border border-white/[0.08] rounded-lg px-3 py-2 text-[13px] text-[#8080a0] outline-none focus:border-[rgba(91,79,255,0.4)]"
                  />
                </label>
              </div>
              <label className="flex flex-col gap-1.5">
                <span className="text-[11px] text-[#5a5a7a] uppercase tracking-wider font-semibold">Telegram chat ID</span>
                <input
                  type="text"
                  value={settings.telegram_chat_id}
                  onChange={(e) => setSettings({ ...settings, telegram_chat_id: e.target.value })}
                  placeholder="Optional — for job alerts"
                  className="bg-[#0d0d1f] border border-white/[0.08] rounded-lg px-3 py-2 text-[13px] text-[#8080a0] outline-none focus:border-[rgba(91,79,255,0.4)] placeholder:text-[#5a5a7a]"
                />
              </label>
              <button
                onClick={handleSave}
                disabled={saving}
                className="self-start px-4 py-2 rounded-lg bg-[rgba(91,79,255,0.15)] text-[#a78bfa] border border-[rgba(91,79,255,0.25)] text-[13px] font-semibold hover:bg-[rgba(91,79,255,0.25)] transition-all disabled:opacity-40"
              >
                {saving ? "Saving…" : "Save settings"}
              </button>
            </div>
          ) : null}
        </section>

        {/* Channel Preferences — Glow Card */}
        <section className="bg-[#13132a]/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md relative overflow-hidden">
          <div className="absolute -top-10 -right-10 w-32 h-32 bg-[#00c9a7]/5 blur-3xl rounded-full pointer-events-none" />

          <h3 className="font-['Cabinet_Grotesk',sans-serif] font-bold text-[17px] text-white mb-6">Channel Preferences</h3>

          <div className="space-y-6">
            <div className="flex items-center justify-between group">
              <div className="space-y-1">
                <p className="text-sm font-bold text-[#eeeef5] group-hover:text-white transition-colors">Telegram Notifications</p>
                <p className="text-xs text-[#5a5a7a]">Rico sends cards to your mobile for instant approval.</p>
              </div>
              <div className="w-10 h-5 rounded-full bg-[#5b4fff]/20 border border-[#5b4fff]/40 relative">
                <div className="absolute right-1 top-0.5 bottom-0.5 w-3.5 h-3.5 bg-[#5b4fff] rounded-full shadow-[0_0_10px_rgba(91,79,255,0.5)]" />
              </div>
            </div>

            <div className="pt-6 border-t border-white/5 flex items-center justify-between">
              <span className="text-[11px] text-[#5a5a7a] font-medium uppercase tracking-widest">
                {saving ? "Syncing with Rico…" : "Status: Cloud Synced"}
              </span>
              {saving && <div className="w-3 h-3 border-2 border-[#5b4fff] border-t-transparent rounded-full animate-spin" />}
            </div>
          </div>
        </section>

        {/* Backend Status */}
        <section className="bg-[#13132a]/80 border border-white/[0.06] rounded-2xl p-6">
          <h2 className="font-['Cabinet_Grotesk',sans-serif] font-bold text-[15px] mb-4 text-white">Backend Status</h2>
          {loadingHealth ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-10 rounded-lg bg-white/[0.03] animate-pulse" />
              ))}
            </div>
          ) : health ? (
            (() => {
              const rico = health.rico;
              const readyForHf = health.ready_for_hf ?? rico?.ready_for_hf ?? false;
              const readyForOpenAI =
                health.ready_for_openai ?? rico?.ready_for_openai ?? health.openai ?? false;
              const readyForJotform =
                health.ready_for_jotform ?? rico?.ready_for_jotform ?? false;
              const readyForTelegram =
                health.telegram ?? rico?.ready_for_telegram ?? false;
              const aiProvider = health.ai_provider ?? rico?.ai_provider ?? "unknown";
              const dbStatus =
                health.database ?? health.db ?? (rico?.ready_for_db ? "connected" : "unknown");

              return (
                <>
                  <Row label="Service" value={health.service ?? "—"} />
                  <Row label="Status" value={health.status} ok={health.status === "ok" || health.status === "healthy"} />
                  <Row label="Environment" value={health.environment ?? "—"} />
                  <Row label="Database" value={dbStatus} ok={dbStatus === "connected"} />
                  <Row
                    label="AI Provider"
                    value={aiProvider}
                    ok={readyForHf || readyForOpenAI}
                  />
                  <Row
                    label="Hugging Face"
                    value={readyForHf ? "Configured" : "Not configured"}
                    ok={readyForHf}
                  />
                  <Row
                    label="OpenAI"
                    value={readyForOpenAI ? "Active" : "Not active"}
                    ok={readyForOpenAI}
                  />
                  <Row
                    label="Jotform"
                    value={readyForJotform ? "Configured" : "Not configured"}
                    ok={readyForJotform}
                  />
                  <Row
                    label="Telegram"
                    value={readyForTelegram ? "Connected" : "Not configured"}
                    ok={readyForTelegram}
                  />
                  <Row label="Version" value={`v${health.version ?? "0"}`} />
                </>
              );
            })()
          ) : (
            <p className="text-[13px] text-[#ff5e5b]">Could not reach backend</p>
          )}
        </section>

        {/* Frontend Config */}
        <section className="bg-[#13132a]/80 border border-white/[0.06] rounded-2xl p-6">
          <h2 className="font-['Cabinet_Grotesk',sans-serif] font-bold text-[15px] mb-4 text-white">Frontend Config</h2>
          <Row label="Mock mode" value={isMock ? "ENABLED — using dev fixtures" : "OFF — hitting real backend"} ok={!isMock} />
        </section>

      </div>
      <ToastContainer toasts={toasts} />
    </DashboardShell>
  );
}
