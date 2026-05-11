"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

/* ─── Icons ─── */
function ChevronRightIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 18l6-6-6-6" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <span className={`w-2 h-2 rounded-full ${active ? "bg-[#00c9a7] shadow-[0_0_8px_#00c9a7]" : "bg-[#5a5a7a]"}`} />
  );
}

/* ─── Scanline effect ─── */
function ScanlineOverlay() {
  return (
    <style jsx>{`
      .scanlines::before {
        content: "";
        position: fixed;
        inset: 0;
        background: repeating-linear-gradient(
          0deg,
          transparent,
          transparent 2px,
          rgba(0, 0, 0, 0.03) 2px,
          rgba(0, 0, 0, 0.03) 4px
        );
        pointer-events: none;
        z-index: 9998;
      }
      .scanlines::after {
        content: "";
        position: fixed;
        inset: 0;
        background: radial-gradient(ellipse at 50% 50%, transparent 0%, rgba(6, 6, 15, 0.4) 100%);
        pointer-events: none;
        z-index: 9997;
      }
    `}</style>
  );
}

/* ─── Subtle glow animation ─── */
function GlowEffect() {
  return (
    <style jsx>{`
      @keyframes subtlePulse {
        0%, 100% { opacity: 0.6; }
        50% { opacity: 1; }
      }
      .glow-pulse {
        animation: subtlePulse 4s ease-in-out infinite;
      }
    `}</style>
  );
}

/* ─── Reveal on scroll ─── */
function useReveal() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) setVisible(true); }),
      { threshold: 0.1 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return { ref, visible };
}

function Reveal({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const { ref, visible } = useReveal();
  return (
    <div
      ref={ref}
      className={`transition-all duration-700 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"} ${className}`}
    >
      {children}
    </div>
  );
}

/* ─── Mock job card ─── */
function JobCardMock({ title, company, score, tags, status }: {
  title: string; company: string; score: number; tags: string[]; status: "new" | "matched" | "applied";
}) {
  const statusColors = {
    new: "text-[#5b4fff] bg-[rgba(91,79,255,0.1)] border-[rgba(91,79,255,0.2)]",
    matched: "text-[#00c9a7] bg-[rgba(0,201,167,0.1)] border-[rgba(0,201,167,0.2)]",
    applied: "text-[#a78bfa] bg-[rgba(167,139,250,0.1)] border-[rgba(167,139,250,0.2)]",
  };
  return (
    <div className="bg-[#0e0e20] border border-[rgba(255,255,255,0.08)] rounded-lg p-3 flex gap-3 items-start hover:border-[rgba(91,79,255,0.2)] transition-colors">
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-semibold text-[#eeeef5] truncate font-['Space_Grotesk',sans-serif]">{title}</div>
        <div className="text-[11px] text-[#5a5a7a] mt-0.5">{company}</div>
        <div className="flex gap-1.5 mt-2 flex-wrap">
          {tags.map((t) => (
            <span key={t} className="text-[10px] px-2 py-0.5 rounded bg-[rgba(255,255,255,0.03)] text-[#5a5a7a] border border-[rgba(255,255,255,0.05)] font-['JetBrains_Mono',monospace]">{t}</span>
          ))}
        </div>
      </div>
      <div className={`text-[12px] font-bold px-2 py-1 rounded border shrink-0 font-['JetBrains_Mono',monospace] ${statusColors[status]}`}>
        {score}%
      </div>
    </div>
  );
}

/* ─── Scoring breakdown card ─── */
function ScoringBreakdown() {
  return (
    <div className="bg-[#0e0e20] border border-[rgba(255,255,255,0.08)] rounded-lg p-4">
      <div className="text-[12px] font-semibold text-[#eeeef5] mb-3 font-['Space_Grotesk',sans-serif]">Score Breakdown</div>
      <div className="space-y-2">
        {[
          { label: "Include keyword match", value: 35, color: "#00c9a7" },
          { label: "Profile role alignment", value: 25, color: "#5b4fff" },
          { label: "UAE location match", value: 20, color: "#a78bfa" },
          { label: "Salary range fit", value: 12, color: "#f5a623" },
          { label: "Seniority level", value: 8, color: "#60a5fa" },
        ].map((item) => (
          <div key={item.label}>
            <div className="flex justify-between text-[10px] mb-1">
              <span className="text-[#5a5a7a] font-['JetBrains_Mono',monospace]">{item.label}</span>
              <span className="text-[#eeeef5] font-['JetBrains_Mono',monospace]">+{item.value}</span>
            </div>
            <div className="h-1 bg-[rgba(255,255,255,0.05)] rounded overflow-hidden">
              <div className="h-full rounded" style={{ width: `${item.value}%`, backgroundColor: item.color }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── Telegram mock card ─── */
function TelegramAlertCard() {
  return (
    <div className="bg-[#0e0e20] border border-[rgba(255,255,255,0.08)] rounded-lg p-4 max-w-sm">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-full bg-[#5b4fff] flex items-center justify-center text-white text-xs font-bold">R</div>
        <div>
          <div className="text-[13px] font-semibold text-[#eeeef5] font-['Space_Grotesk',sans-serif]">Rico AI</div>
          <div className="text-[10px] text-[#5a5a7a] font-['JetBrains_Mono',monospace]">08:00 UAE · Daily Alert</div>
        </div>
      </div>
      <div className="bg-[#06060f] border border-[rgba(255,255,255,0.05)] rounded p-3 mb-3">
        <div className="text-[11px] text-[#5a5a7a] mb-2 font-['JetBrains_Mono',monospace]">🎯 3 NEW MATCHES FOUND</div>
        <JobCardMock title="HSE Manager" company="ADNOC · Abu Dhabi" score={96} tags={["ISO 14001", "Senior"]} status="matched" />
      </div>
      <div className="flex gap-2">
        <button className="flex-1 bg-[#5b4fff] text-white text-[11px] py-2 rounded font-semibold font-['Space_Grotesk',sans-serif]">Apply</button>
        <button className="flex-1 bg-[rgba(255,255,255,0.05)] text-[#eeeef5] text-[11px] py-2 rounded font-semibold border border-[rgba(255,255,255,0.08)] font-['Space_Grotesk',sans-serif]">Save</button>
        <button className="flex-1 bg-[rgba(255,255,255,0.05)] text-[#5a5a7a] text-[11px] py-2 rounded font-semibold border border-[rgba(255,255,255,0.08)] font-['Space_Grotesk',sans-serif]">Skip</button>
      </div>
    </div>
  );
}

/* ─── Main page ─── */
export default function HomePage() {
  const [navStuck, setNavStuck] = useState(false);

  useEffect(() => {
    const onScroll = () => setNavStuck(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="scanlines min-h-screen bg-[#06060f] text-[#eeeef5]">
      <ScanlineOverlay />
      <GlowEffect />

      {/* 1. Nav */}
      <nav className={`fixed top-0 left-0 right-0 z-[200] px-6 md:px-12 py-4 flex items-center justify-between transition-all duration-300 ${navStuck ? "bg-[rgba(6,6,15,0.95)] backdrop-blur-xl border-b border-[rgba(255,255,255,0.06)] py-3" : ""}`}>
        <Link href="/" className="flex items-center gap-2.5 font-['Space_Grotesk',sans-serif] font-bold text-[18px] text-[#eeeef5] tracking-tight no-underline">
          <div className="w-7 h-7 rounded-lg bg-[#5b4fff] flex items-center justify-center text-[13px] font-bold text-white">R</div>
          Rico
        </Link>
        <div className="flex items-center gap-6">
          <a href="#how-it-works" className="hidden md:block text-[13px] text-[#5a5a7a] font-medium no-underline hover:text-[#eeeef5] transition-colors font-['Space_Grotesk',sans-serif]">How it works</a>
          <a href="#engine" className="hidden md:block text-[13px] text-[#5a5a7a] font-medium no-underline hover:text-[#eeeef5] transition-colors font-['Space_Grotesk',sans-serif]">Engine</a>
          <Link href="/login" className="hidden md:block text-[13px] text-[#5a5a7a] font-medium no-underline hover:text-[#eeeef5] transition-colors font-['Space_Grotesk',sans-serif]">Sign in</Link>
          <Link href="/login" className="bg-[#5b4fff] text-white px-5 py-2 rounded-lg text-[13px] font-semibold no-underline transition-all hover:bg-[#4b3ff0] font-['Space_Grotesk',sans-serif]">
            Launch Rico
          </Link>
        </div>
      </nav>

      {/* 2. Hero */}
      <section className="relative min-h-screen flex flex-col items-center justify-center text-center px-6 pt-32 pb-24">
        <div className="max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 bg-[rgba(91,79,255,0.08)] border border-[rgba(91,79,255,0.2)] rounded-full px-4 py-1.5 text-[11px] text-[#5b4fff] font-semibold tracking-wider uppercase mb-6 font-['Space_Grotesk',sans-serif]">
            <StatusDot active={true} />
            Autonomous Job Operations System
          </div>

          <h1 className="font-['Space_Grotesk',sans-serif] font-bold text-[clamp(40px,7vw,72px)] leading-[1.1] tracking-tight max-w-[900px] mx-auto mb-6">
            Your autonomous<br />
            <span className="bg-gradient-to-r from-[#5b4fff] to-[#a78bfa] bg-clip-text text-transparent">job hunting pipeline.</span>
          </h1>

          <p className="text-[16px] text-[#5a5a7a] max-w-[580px] mx-auto mb-10 leading-[1.7]">
            Rico finds relevant jobs, scores them against your profile, tracks applications, monitors responses, and sends daily opportunities automatically.
          </p>

          <div className="flex gap-3 items-center justify-center mb-16 flex-wrap">
            <Link href="/login" className="bg-[#5b4fff] text-white px-8 py-3 rounded-lg text-[15px] font-semibold no-underline transition-all hover:bg-[#4b3ff0] font-['Space_Grotesk',sans-serif] shadow-[0_4px_20px_rgba(91,79,255,0.3)]">
              Open My Dashboard
            </Link>
            <a href="https://form.jotform.com/261278237812056" target="_blank" rel="noopener noreferrer" className="text-[#5a5a7a] px-6 py-3 text-[14px] font-medium no-underline transition-colors hover:text-[#eeeef5] flex items-center gap-1.5 font-['Space_Grotesk',sans-serif]">
              New user? Request access
              <ChevronRightIcon />
            </a>
          </div>

          {/* Live system mockup */}
          <div className="relative max-w-[800px] mx-auto">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_30%,rgba(91,79,255,0.12)_0%,transparent_60%)] pointer-events-none" />
            <div className="bg-[#0e0e20] border border-[rgba(255,255,255,0.1)] rounded-xl overflow-hidden shadow-[0_32px_80px_rgba(0,0,0,0.5)] relative">
              <div className="bg-[rgba(255,255,255,0.02)] border-b border-[rgba(255,255,255,0.06)] px-4 py-3 flex items-center gap-2">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
                </div>
                <div className="flex-1 text-center text-[11px] text-[#5a5a7a] font-['JetBrains_Mono',monospace]">rico-dashboard.local</div>
                <div className="flex items-center gap-2 text-[10px] text-[#00c9a7] font-['JetBrains_Mono',monospace]">
                  <StatusDot active={true} />
                  PIPELINE ACTIVE
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3">
                <div className="p-4 border-r border-[rgba(255,255,255,0.06)]">
                  <div className="text-[10px] uppercase tracking-wider text-[#5a5a7a] mb-3 font-['JetBrains_Mono',monospace]">Today&apos;s Matches</div>
                  <JobCardMock title="HSE Manager" company="ADNOC · Abu Dhabi" score={96} tags={["ISO 14001", "Senior"]} status="matched" />
                  <JobCardMock title="Operations Director" company="Emaar · Dubai" score={88} tags={["MBA", "Facilities"]} status="matched" />
                  <JobCardMock title="Compliance Lead" company="TAQA · Abu Dhabi" score={82} tags={["ESG", "5+ yrs"]} status="new" />
                </div>
                <div className="p-4 border-r border-[rgba(255,255,255,0.06)]">
                  <div className="text-[10px] uppercase tracking-wider text-[#5a5a7a] mb-3 font-['JetBrains_Mono',monospace]">Scoring</div>
                  <ScoringBreakdown />
                </div>
                <div className="p-4">
                  <div className="text-[10px] uppercase tracking-wider text-[#5a5a7a] mb-3 font-['JetBrains_Mono',monospace]">Status</div>
                  <div className="space-y-3">
                    <div className="bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.05)] rounded p-2.5">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[10px] text-[#5a5a7a] font-['JetBrains_Mono',monospace]">Jobs scanned</span>
                        <span className="text-[13px] font-bold text-[#eeeef5] font-['JetBrains_Mono',monospace]">24</span>
                      </div>
                      <div className="text-[9px] text-[#5a5a7a] font-['JetBrains_Mono',monospace]">Last sync: 08:00 UAE</div>
                    </div>
                    <div className="bg-[rgba(0,201,167,0.05)] border border-[rgba(0,201,167,0.15)] rounded p-2.5">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[10px] text-[#00c9a7] font-['JetBrains_Mono',monospace]">High-quality</span>
                        <span className="text-[13px] font-bold text-[#00c9a7] font-['JetBrains_Mono',monospace]">3</span>
                      </div>
                      <div className="text-[9px] text-[#5a5a7a] font-['JetBrains_Mono',monospace]">Score threshold ≥ 45</div>
                    </div>
                    <div className="bg-[rgba(91,79,255,0.05)] border border-[rgba(91,79,255,0.15)] rounded p-2.5">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[10px] text-[#5b4fff] font-['JetBrains_Mono',monospace]">Telegram alerts</span>
                        <span className="text-[13px] font-bold text-[#5b4fff] font-['JetBrains_Mono',monospace]">Sent</span>
                      </div>
                      <div className="text-[9px] text-[#5a5a7a] font-['JetBrains_Mono',monospace]">Daily schedule active</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Proof Strip */}
      <section className="border-y border-[rgba(255,255,255,0.06)] bg-[#0e0e20] py-6 px-6">
        <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-center gap-8 md:gap-16">
          {[
            { label: "Jobs scored per run", value: "LLM + Keywords" },
            { label: "Sources", value: "Indeed" },
            { label: "Agent decides", value: "Apply · Watch · Skip" },
            { label: "Applications tracked", value: "Full history" },
            { label: "Alerts via", value: "Telegram" },
          ].map((item) => (
            <div key={item.label} className="text-center">
              <div className="text-[20px] font-bold text-[#eeeef5] font-['JetBrains_Mono',monospace]">{item.value}</div>
              <div className="text-[10px] uppercase tracking-wider text-[#5a5a7a] font-['JetBrains_Mono',monospace]">{item.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 4. How Rico Works */}
      <section id="how-it-works" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <Reveal>
            <div className="text-[11px] uppercase tracking-wider text-[#5b4fff] font-semibold mb-3 font-['JetBrains_Mono',monospace]">Operational Pipeline</div>
          </Reveal>
          <Reveal>
            <h2 className="font-['Space_Grotesk',sans-serif] font-bold text-[clamp(32px,5vw,48px)] tracking-tight mb-12">
              How Rico works
            </h2>
          </Reveal>
          <Reveal>
            <div className="flex flex-wrap items-center justify-center gap-4 md:gap-6 text-[13px] font-['JetBrains_Mono',monospace]">
              {["Fetch", "→", "Deduplicate", "→", "Score", "→", "Agent Decide", "→", "Filter Applied", "→", "Notify", "→", "Feedback Loop", "→", "Dashboard"].map((item, i) => (
                <span key={i} className={item === "→" ? "text-[#5a5a7a]" : "px-3 py-1.5 bg-[#0e0e20] border border-[rgba(255,255,255,0.08)] rounded text-[#eeeef5]"}>
                  {item}
                </span>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* 5. Matching Engine */}
      <section id="engine" className="py-24 px-6 bg-[#0e0e20]">
        <div className="max-w-6xl mx-auto">
          <Reveal>
            <div className="text-[11px] uppercase tracking-wider text-[#5b4fff] font-semibold mb-3 font-['JetBrains_Mono',monospace]">Core Intelligence</div>
          </Reveal>
          <Reveal>
            <h2 className="font-['Space_Grotesk',sans-serif] font-bold text-[clamp(32px,5vw,48px)] tracking-tight mb-6">
              Rico scores jobs with LLM + keyword intelligence.
            </h2>
          </Reveal>
          <Reveal>
            <p className="text-[15px] text-[#5a5a7a] max-w-[600px] mb-12">
              Every job is scored against your profile using an LLM scorer with keyword fallback. Positive signals boost the score; excluded keywords and mismatches penalize it. The agent then decides: apply, watch, or skip.
            </p>
          </Reveal>
          <Reveal>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-[#06060f] border border-[rgba(255,255,255,0.08)] rounded-lg p-6">
                <div className="text-[12px] font-semibold text-[#00c9a7] mb-4 font-['Space_Grotesk',sans-serif]">Positive Signals</div>
                <ul className="space-y-2 text-[13px] text-[#5a5a7a]">
                  {["Include keywords in title/description", "Target role match", "UAE location specified", "Salary within range", "Profile context available", "Seniority level aligned"].map((item) => (
                    <li key={item} className="flex items-start gap-2"><CheckIcon />{item}</li>
                  ))}
                </ul>
              </div>
              <div className="bg-[#06060f] border border-[rgba(255,255,255,0.08)] rounded-lg p-6">
                <div className="text-[12px] font-semibold text-[#f5a623] mb-4 font-['Space_Grotesk',sans-serif]">Negative Penalties</div>
                <ul className="space-y-2 text-[13px] text-[#5a5a7a]">
                  {["Exclude keywords present", "Salary below threshold", "Location outside UAE", "Seniority mismatch", "Role outside target list", "Spam / scam signals"].map((item) => (
                    <li key={item} className="flex items-start gap-2"><span className="text-[#f5a623]">−</span>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* 6. Job Command Center */}
      <section className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <Reveal>
            <div className="text-[11px] uppercase tracking-wider text-[#5b4fff] font-semibold mb-3 font-['JetBrains_Mono',monospace]">Dashboard</div>
          </Reveal>
          <Reveal>
            <h2 className="font-['Space_Grotesk',sans-serif] font-bold text-[clamp(32px,5vw,48px)] tracking-tight mb-12">
              Job Command Center
            </h2>
          </Reveal>
          <Reveal>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: "Pipeline runs", value: "2× daily", color: "#5b4fff" },
                { label: "Match threshold", value: "≥ 45", color: "#00c9a7" },
                { label: "Apply cap", value: "Top 4", color: "#a78bfa" },
                { label: "Sources", value: "Indeed", color: "#f5a623" },
                { label: "Scoring", value: "LLM + Keywords", color: "#5a5a7a" },
                { label: "Agent decisions", value: "Apply · Watch · Skip", color: "#00c9a7" },
                { label: "Alerts", value: "Telegram", color: "#5b4fff" },
                { label: "Profile setup", value: "Jotform + CV", color: "#a78bfa" },
              ].map((item) => (
                <div key={item.label} className="bg-[#0e0e20] border border-[rgba(255,255,255,0.08)] rounded-lg p-4">
                  <div className="text-[10px] uppercase tracking-wider text-[#5a5a7a] mb-2 font-['JetBrains_Mono',monospace]">{item.label}</div>
                  <div className="text-[24px] font-bold font-['JetBrains_Mono',monospace]" style={{ color: item.color }}>{item.value}</div>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* 7. Telegram Workflow */}
      <section className="py-24 px-6 bg-[#0e0e20]">
        <div className="max-w-6xl mx-auto">
          <Reveal>
            <div className="text-[11px] uppercase tracking-wider text-[#5b4fff] font-semibold mb-3 font-['JetBrains_Mono',monospace]">Primary Interface</div>
          </Reveal>
          <Reveal>
            <h2 className="font-['Space_Grotesk',sans-serif] font-bold text-[clamp(32px,5vw,48px)] tracking-tight mb-6">
              Telegram Workflow
            </h2>
          </Reveal>
          <Reveal>
            <p className="text-[15px] text-[#5a5a7a] max-w-[600px] mb-12">
              Rico delivers daily job alerts directly to Telegram with match scores, one-tap actions, and follow-up reminders.
            </p>
          </Reveal>
          <Reveal>
            <div className="flex justify-center">
              <TelegramAlertCard />
            </div>
          </Reveal>
        </div>
      </section>

      {/* 8. Application Memory */}
      <section className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <Reveal>
            <div className="text-[11px] uppercase tracking-wider text-[#5b4fff] font-semibold mb-3 font-['JetBrains_Mono',monospace]">Memory Layer</div>
          </Reveal>
          <Reveal>
            <h2 className="font-['Space_Grotesk',sans-serif] font-bold text-[clamp(32px,5vw,48px)] tracking-tight mb-6">
              Application Memory
            </h2>
          </Reveal>
          <Reveal>
            <p className="text-[15px] text-[#5a5a7a] max-w-[600px] mb-12">
              Rico tracks every job you&apos;ve seen, applied to, and the outcomes — so you never miss a follow-up or duplicate effort.
            </p>
          </Reveal>
          <Reveal>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {[
                "Applied jobs tracked",
                "Interview scheduled",
                "Offer extended",
                "Rejected status",
                "Saved for later",
                "Full application history",
              ].map((item) => (
                <div key={item} className="bg-[#0e0e20] border border-[rgba(255,255,255,0.08)] rounded-lg p-4 flex items-center gap-3">
                  <CheckIcon />
                  <span className="text-[13px] text-[#eeeef5] font-['Space_Grotesk',sans-serif]">{item}</span>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* 9. Who Rico Is Built For */}
      <section className="py-24 px-6 bg-[#0e0e20]">
        <div className="max-w-6xl mx-auto">
          <Reveal>
            <div className="text-[11px] uppercase tracking-wider text-[#5b4fff] font-semibold mb-3 font-['JetBrains_Mono',monospace]">Target Users</div>
          </Reveal>
          <Reveal>
            <h2 className="font-['Space_Grotesk',sans-serif] font-bold text-[clamp(32px,5vw,48px)] tracking-tight mb-6">
              Who Rico Is Built For
            </h2>
          </Reveal>
          <Reveal>
            <p className="text-[15px] text-[#5a5a7a] max-w-[600px] mb-12">
              Rico is focused on UAE professionals in specific operational roles.
            </p>
          </Reveal>
          <Reveal>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {[
                "HSE Managers",
                "ESG Managers",
                "QHSE Professionals",
                "Environmental Managers",
                "Sustainability Managers",
                "Compliance Managers",
                "Safety / EHS Managers",
              ].map((item) => (
                <div key={item} className="bg-[#06060f] border border-[rgba(255,255,255,0.08)] rounded-lg p-4 text-center">
                  <span className="text-[13px] text-[#eeeef5] font-['Space_Grotesk',sans-serif]">{item}</span>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* 10. Live Output Preview */}
      <section className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <Reveal>
            <div className="text-[11px] uppercase tracking-wider text-[#5b4fff] font-semibold mb-3 font-['JetBrains_Mono',monospace]">Live Output</div>
          </Reveal>
          <Reveal>
            <h2 className="font-['Space_Grotesk',sans-serif] font-bold text-[clamp(32px,5vw,48px)] tracking-tight mb-12">
              Live Output Preview
            </h2>
          </Reveal>
          <Reveal>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <TelegramAlertCard />
              <ScoringBreakdown />
            </div>
          </Reveal>
        </div>
      </section>

      {/* 11. Final CTA */}
      <section className="py-24 px-6 bg-[#0e0e20]">
        <div className="max-w-4xl mx-auto text-center">
          <Reveal>
            <h2 className="font-['Space_Grotesk',sans-serif] font-bold text-[clamp(36px,6vw,56px)] tracking-tight mb-6">
              Stop manually searching job boards.
            </h2>
          </Reveal>
          <Reveal>
            <p className="text-[16px] text-[#5a5a7a] mb-10">
              Let Rico run your job hunt every day.
            </p>
          </Reveal>
          <Reveal>
            <a href="https://form.jotform.com/261278237812056" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 bg-[#5b4fff] text-white px-10 py-4 rounded-lg text-[16px] font-semibold no-underline transition-all hover:bg-[#4b3ff0] font-['Space_Grotesk',sans-serif] shadow-[0_4px_20px_rgba(91,79,255,0.3)]">
              Launch Rico →
            </a>
          </Reveal>
        </div>
      </section>

      {/* 12. Footer */}
      <footer className="border-t border-[rgba(255,255,255,0.06)] py-12 px-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <Link href="/" className="flex items-center gap-2.5 font-['Space_Grotesk',sans-serif] font-bold text-[16px] text-[#eeeef5] no-underline">
            <div className="w-6 h-6 rounded-lg bg-[#5b4fff] flex items-center justify-center text-[12px] font-bold text-white">R</div>
            Rico
          </Link>
          <div className="flex gap-6">
            <Link href="/login" className="text-[13px] text-[#5a5a7a] no-underline hover:text-[#eeeef5] transition-colors font-['Space_Grotesk',sans-serif]">Sign In</Link>
            <Link href="/dashboard" className="text-[13px] text-[#5a5a7a] no-underline hover:text-[#eeeef5] transition-colors font-['Space_Grotesk',sans-serif]">Dashboard</Link>
            <a href="https://github.com/Binz2008-star/job-automation-system-1" target="_blank" rel="noopener noreferrer" className="text-[13px] text-[#5a5a7a] no-underline hover:text-[#eeeef5] transition-colors font-['Space_Grotesk',sans-serif]">GitHub</a>
          </div>
          <div className="text-[12px] text-[#5a5a7a] font-['JetBrains_Mono',monospace]">© 2026 Rico</div>
        </div>
      </footer>
    </div>
  );
}
