"use client";

import { submitOnboarding, uploadCV, type OnboardingPayload, type ParsedCV } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

// ── Missing-fields form config ────────────────────────────────────────────────

const MISSING_FIELDS: { key: keyof OnboardingPayload; label: string; placeholder: string; isNumber?: boolean; isList?: boolean }[] = [
  { key: "target_roles", label: "Target roles", placeholder: "e.g. HSE Manager, Operations Director", isList: true },
  { key: "preferred_cities", label: "Preferred cities", placeholder: "e.g. Dubai, Abu Dhabi, Remote", isList: true },
  { key: "salary_expectation_aed", label: "Salary expectation (AED/month)", placeholder: "e.g. 25000", isNumber: true },
  { key: "years_experience", label: "Years of experience", placeholder: "e.g. 8", isNumber: true },
  { key: "skills", label: "Additional skills (if any missed)", placeholder: "Comma-separated", isList: true },
];

// ── Brand header ─────────────────────────────────────────────────────────────

function BrandHeader() {
  return (
    <Link href="/" className="mb-10 inline-flex items-center gap-2.5">
      <div className="w-8 h-8 rounded-[9px] bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-sm font-black text-white shadow-[0_4px_16px_rgba(91,79,255,0.3)]">
        R
      </div>
      <span className="font-['Cabinet_Grotesk',sans-serif] font-black text-lg text-white tracking-tight">Rico AI</span>
    </Link>
  );
}

// ── Ambient glow ─────────────────────────────────────────────────────────────

function AmbientGlow() {
  return (
    <div className="fixed inset-0 pointer-events-none">
      <div className="absolute -top-[200px] -left-[100px] w-[600px] h-[600px] rounded-full bg-[rgba(91,79,255,0.06)] blur-[140px]" />
      <div className="absolute bottom-0 -right-[100px] w-[400px] h-[400px] rounded-full bg-[rgba(0,201,167,0.04)] blur-[140px]" />
    </div>
  );
}

// ── Spinner card ─────────────────────────────────────────────────────────────

function SpinnerCard({ label }: { label: string }) {
  return (
    <div className="w-full max-w-lg rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#13132a]/80 p-8 backdrop-blur-xl text-center">
      <div className="mb-4 mx-auto w-10 h-10 rounded-full border-2 border-[rgba(91,79,255,0.3)] border-t-[#5b4fff] animate-spin" />
      <p className="text-sm text-[#5a5a7a]">{label}</p>
    </div>
  );
}

// ── Completion screen ─────────────────────────────────────────────────────────

function CompletionCard({ onGo }: { onGo: () => void }) {
  return (
    <div className="w-full max-w-lg text-center">
      <div className="mb-6 mx-auto w-14 h-14 rounded-full bg-[rgba(0,201,167,0.12)] border border-[rgba(0,201,167,0.2)] flex items-center justify-center">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00c9a7" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
      <h2 className="mb-2 font-['Cabinet_Grotesk',sans-serif] font-bold text-[24px] text-[#eeeef5] tracking-tight">
        Profile saved
      </h2>
      <p className="mb-8 text-[14px] text-[#5a5a7a] leading-relaxed max-w-sm mx-auto">
        Rico now has enough context to start hunting. Your first batch of scored jobs will appear on the dashboard shortly.
      </p>
      <button
        onClick={onGo}
        className="inline-flex items-center gap-2 rounded-lg bg-[#5b4fff] px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#4a3fdf] shadow-[0_4px_15px_rgba(91,79,255,0.2)]"
      >
        Go to dashboard →
      </button>
    </div>
  );
}

// ── Error screen ──────────────────────────────────────────────────────────────

function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="w-full max-w-lg rounded-2xl border border-[rgba(255,94,91,0.3)] bg-[rgba(255,94,91,0.05)] p-6 text-center">
      <p className="mb-4 text-sm text-[#ff5e5b]">{message}</p>
      <button
        onClick={onRetry}
        className="rounded-lg bg-[#5b4fff] px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#4a3fdf]"
      >
        Try again
      </button>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

type PageState = "upload" | "parsing" | "form" | "submitting" | "done" | "error";

export default function OnboardingPage() {
  const router = useRouter();
  const [pageState, setPageState] = useState<PageState>("upload");
  const [parsed, setParsed] = useState<ParsedCV | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [errorMsg, setErrorMsg] = useState("");

  const handleFile = useCallback(async (file: File) => {
    if (file.type !== "application/pdf") {
      setErrorMsg("Only PDF files are accepted.");
      return;
    }
    setPageState("parsing");
    setErrorMsg("");
    try {
      const res = await uploadCV(file);
      setParsed(res.parsed);
      // Pre-fill skills from CV extraction
      if (res.parsed.skills.length > 0) {
        setFieldValues((prev) => ({
          ...prev,
          skills: res.parsed.skills.join(", "),
        }));
      }
      setPageState("form");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Upload failed. Please try again.");
      setPageState("upload");
    }
  }, []);

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  const handleSubmit = useCallback(async () => {
    setPageState("submitting");
    setErrorMsg("");

    const payload: OnboardingPayload = {};
    for (const field of MISSING_FIELDS) {
      const raw = (fieldValues[field.key] ?? "").trim();
      if (!raw) continue;
      if (field.isNumber) {
        const n = parseFloat(raw.replace(/[^0-9.]/g, ""));
        if (!isNaN(n)) (payload as Record<string, unknown>)[field.key] = n;
      } else if (field.isList) {
        const arr = raw.split(",").map((s) => s.trim()).filter(Boolean);
        if (arr.length) (payload as Record<string, unknown>)[field.key] = arr;
      }
    }

    try {
      await submitOnboarding(payload);
      setPageState("done");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Could not save your profile. Please try again.");
      setPageState("form");
    }
  }, [fieldValues]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-[#06060f] px-4 relative overflow-hidden">
      <AmbientGlow />

      <div className="relative z-10 flex flex-col items-center w-full">
        <BrandHeader />

        {/* ── Upload zone ── */}
        {pageState === "upload" && (
          <div className="w-full max-w-md">
            <div className="mb-8 text-center">
              <h1 className="font-['Cabinet_Grotesk',sans-serif] font-bold text-[28px] text-[#eeeef5] tracking-tight mb-1">
                Start with your CV
              </h1>
              <p className="text-[14px] text-[#5a5a7a]">
                Upload your CV (PDF) — Rico extracts everything and only asks for missing details.
              </p>
            </div>

            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              className="w-full rounded-2xl border-2 border-dashed border-[rgba(255,255,255,0.12)] bg-[#13132a]/80 p-10 text-center backdrop-blur-xl transition-colors hover:border-[rgba(91,79,255,0.4)]"
            >
              <input type="file" accept="application/pdf" onChange={handleFileInput} className="hidden" id="cv-upload" />
              <label htmlFor="cv-upload" className="flex flex-col items-center gap-3 cursor-pointer">
                <div className="w-12 h-12 rounded-full bg-[rgba(91,79,255,0.12)] flex items-center justify-center">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                </div>
                <span className="text-sm text-[#eeeef5] font-medium">Click to upload or drag &amp; drop</span>
                <span className="text-xs text-[#5a5a7a]">PDF only · max 10 MB</span>
              </label>
            </div>

            {errorMsg && (
              <p className="mt-4 rounded-lg border border-[rgba(255,94,91,0.3)] bg-[rgba(255,94,91,0.08)] px-3 py-2 text-sm text-[#ff5e5b]">
                {errorMsg}
              </p>
            )}

            <p className="mt-6 text-[12px] text-[#5a5a7a] text-center">
              Already have a profile?{" "}
              <Link href="/dashboard?skip=1" className="text-[#a78bfa] hover:text-[#c4b5fd] transition-colors">
                Go to dashboard →
              </Link>
            </p>
          </div>
        )}

        {/* ── Parsing spinner ── */}
        {pageState === "parsing" && <SpinnerCard label="Parsing your CV…" />}

        {/* ── Missing fields form ── */}
        {pageState === "form" && (
          <div className="w-full max-w-2xl">
            <div className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#13132a]/80 p-6 backdrop-blur-xl">
              <h1 className="mb-1 font-['Cabinet_Grotesk',sans-serif] font-bold text-[24px] text-[#eeeef5] tracking-tight">
                Profile extracted
              </h1>
              <p className="mb-6 text-[14px] text-[#5a5a7a]">
                Rico read your CV. Fill in any missing details to complete your profile.
              </p>

              {parsed && (
                <div className="mb-6 rounded-xl bg-[#0d0d1f] p-4 border border-[rgba(255,255,255,0.06)] space-y-1">
                  <p className="text-[11px] uppercase tracking-wider text-[#5a5a7a] mb-2">Extracted from CV</p>
                  {parsed.years_experience_hint != null && (
                    <p className="text-sm text-[#8080a0]">
                      <span className="text-[#5a5a7a]">Experience: </span>{parsed.years_experience_hint} yrs
                    </p>
                  )}
                  {parsed.skills.length > 0 && (
                    <p className="text-sm text-[#8080a0]">
                      <span className="text-[#5a5a7a]">Skills: </span>{parsed.skills.slice(0, 8).join(", ")}
                    </p>
                  )}
                  {parsed.certifications.length > 0 && (
                    <p className="text-sm text-[#8080a0]">
                      <span className="text-[#5a5a7a]">Certs: </span>{parsed.certifications.join(", ")}
                    </p>
                  )}
                  {parsed.languages.length > 0 && (
                    <p className="text-sm text-[#8080a0]">
                      <span className="text-[#5a5a7a]">Languages: </span>{parsed.languages.join(", ")}
                    </p>
                  )}
                </div>
              )}

              <div className="space-y-4">
                {MISSING_FIELDS.map((field) => (
                  <div key={field.key}>
                    <label className="block text-sm font-medium text-[#eeeef5] mb-1">{field.label}</label>
                    <input
                      type="text"
                      value={fieldValues[field.key] ?? ""}
                      onChange={(e) => setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      placeholder={field.placeholder}
                      className="w-full rounded-lg border border-[rgba(255,255,255,0.08)] bg-[#0d0d1f] px-3 py-2.5 text-sm text-[#eeeef5] placeholder-[#5a5a7a] focus:border-[rgba(91,79,255,0.5)] focus:outline-none focus:ring-1 focus:ring-[rgba(91,79,255,0.3)] transition-colors"
                    />
                  </div>
                ))}
              </div>

              {errorMsg && (
                <p className="mt-4 rounded-lg border border-[rgba(255,94,91,0.3)] bg-[rgba(255,94,91,0.08)] px-3 py-2 text-sm text-[#ff5e5b]">
                  {errorMsg}
                </p>
              )}

              <div className="mt-6 flex items-center justify-between">
                <button
                  onClick={() => router.push("/dashboard?skip=1")}
                  className="text-sm text-[#5a5a7a] hover:text-[#8080a0] transition-colors"
                >
                  Skip for now
                </button>
                <button
                  onClick={handleSubmit}
                  className="rounded-lg bg-[#5b4fff] px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#4a3fdf] shadow-[0_4px_15px_rgba(91,79,255,0.2)]"
                >
                  Complete profile →
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Saving spinner ── */}
        {pageState === "submitting" && <SpinnerCard label="Saving your profile…" />}

        {/* ── Done ── */}
        {pageState === "done" && (
          <CompletionCard onGo={() => router.push("/dashboard?skip=1")} />
        )}

        {/* ── Error (fatal upload failure already handled inline above) ── */}
        {pageState === "error" && (
          <ErrorCard
            message={errorMsg}
            onRetry={() => { setPageState("upload"); setErrorMsg(""); }}
          />
        )}
      </div>
    </main>
  );
}
