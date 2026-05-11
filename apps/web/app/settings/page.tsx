"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/services/health";
import { ToastContainer } from "@/components/ui/Toast";
import { useToast } from "@/hooks/useToast";
import type { HealthResponse } from "@/types";

function Row({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-white/5 last:border-0">
      <span className="text-[13px] text-white/45">{label}</span>
      <span className={`text-[13px] font-medium flex items-center gap-1.5 ${
        ok === true ? "text-[#00c9a7]" : ok === false ? "text-[#ff5e5b]" : "text-white/70"
      }`}>
        {ok === true && <span className="w-1.5 h-1.5 rounded-full bg-[#00c9a7]" />}
        {ok === false && <span className="w-1.5 h-1.5 rounded-full bg-[#ff5e5b]" />}
        {value}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const { toasts, toast } = useToast();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => toast("Backend unreachable", "error"))
      .finally(() => setLoading(false));
  }, []);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const isMock = process.env.NEXT_PUBLIC_USE_MOCK === "true";

  return (
    <>
      <div className="px-8 py-6 border-b border-white/5 bg-[rgba(7,7,18,0.7)] backdrop-blur-md sticky top-0 z-10">
        <h1 className="font-['Cabinet_Grotesk',sans-serif] font-900 text-[22px] tracking-tight">Settings</h1>
        <p className="text-[13px] text-white/35 mt-0.5">System configuration and status</p>
      </div>

      <div className="p-8 max-w-2xl flex flex-col gap-6">

        {/* Backend status */}
        <div className="bg-[#0e0e20] border border-white/6 rounded-2xl p-6">
          <h2 className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[15px] mb-4">Backend Status</h2>
          {loading ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-10 rounded-lg bg-white/3 animate-pulse" />
              ))}
            </div>
          ) : health ? (
            <>
              <Row label="Service" value={health.service} />
              <Row label="Status" value={health.status} ok={health.status === "ok"} />
              <Row label="Environment" value={health.environment} />
              <Row label="Database" value={health.database} ok={health.database === "connected"} />
              <Row label="OpenAI" value={health.openai ? "Connected" : "Not configured"} ok={health.openai} />
              <Row label="Telegram" value={health.telegram ? "Connected" : "Not configured"} ok={health.telegram} />
              <Row label="Version" value={`v${health.version}`} />
            </>
          ) : (
            <p className="text-[13px] text-[#ff5e5b]">Could not reach backend at {apiUrl}</p>
          )}
        </div>

        {/* Frontend config */}
        <div className="bg-[#0e0e20] border border-white/6 rounded-2xl p-6">
          <h2 className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[15px] mb-4">Frontend Config</h2>
          <Row label="API URL" value={apiUrl} />
          <Row label="Mock mode" value={isMock ? "ENABLED — using dev fixtures" : "OFF — hitting real backend"} ok={!isMock} />
          <Row label="Jotform onboarding form" value="261278237812056" />

          <div className="mt-4 pt-4 border-t border-white/5">
            <p className="text-[11px] text-white/25 mb-3 uppercase tracking-wider font-semibold">Required env variables</p>
            {[
              "NEXT_PUBLIC_API_URL",
              "NEXT_PUBLIC_USE_MOCK",
            ].map((v) => (
              <p key={v} className="font-mono text-[12px] text-white/40 py-1">{v}</p>
            ))}
          </div>
        </div>

        {/* Onboarding */}
        <div className="bg-[#0e0e20] border border-white/6 rounded-2xl p-6">
          <h2 className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[15px] mb-2">Onboarding</h2>
          <p className="text-[13px] text-white/35 mb-4">
            New users onboard via Jotform Quick Start, which fires a webhook to{" "}
            <code className="text-white/50 text-[12px]">POST /api/webhooks/jotform</code>
          </p>
          <a
            href="https://form.jotform.com/261278237812056"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 text-[13px] text-[#a78bfa] hover:text-white transition-colors"
          >
            Open Quick Start form ↗
          </a>
        </div>

      </div>
      <ToastContainer toasts={toasts} />
    </>
  );
}
