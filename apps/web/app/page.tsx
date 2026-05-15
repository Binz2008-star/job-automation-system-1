"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

const JOTFORM_URL = "https://form.jotform.com/261278237812056";
const CHAT_URL = "/chat";

/* ─── Reveal on scroll ─── */
function useReveal() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) setVisible(true); }),
      { threshold: 0.08 }
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
      className={`transition-all duration-700 ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-5"} ${className}`}
    >
      {children}
    </div>
  );
}

/* ─── Ticker items (generic company names) ─── */
const TICKER_ITEMS = [
  "Executive Assistant to CEO · Dubai · Strong match",
  "Chief of Staff · Abu Dhabi · Strong match",
  "Operations Manager · Dubai · Good match",
  "Compliance Manager · Sharjah · Good match",
  "Founder Office Manager · Dubai · Strong match",
  "QHSE Manager · Energy Company · Good match",
  "Senior EA · Real Estate Group · Strong match",
  "HSE Manager · Abu Dhabi · Strong match",
  "Sustainability Lead · Dubai · Good match",
  "EA to Group CEO · Major UAE Holding · Strong match",
];

/* ─── Phone mockup with animated typing completion ─── */
function PhoneMockup() {
  const [replied, setReplied] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setReplied(true), 3500);
    return () => clearTimeout(t);
  }, []);

  return (
    <div style={{ animation: "float 4s ease-in-out infinite" }}>
      <div style={{
        width: 270, background: "#0a0b0d", borderRadius: 36,
        padding: 13, boxShadow: "0 32px 64px rgba(0,0,0,.28)",
      }}>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 10 }}>
          <div style={{ width: 88, height: 7, background: "#1a1d22", borderRadius: 100 }} />
        </div>
        <div style={{ background: "#0f1117", borderRadius: 24, overflow: "hidden" }}>
          {/* Header */}
          <div style={{ padding: "12px", borderBottom: "1px solid rgba(255,255,255,.06)", display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{ width: 30, height: 30, borderRadius: "50%", background: "#1246d6", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "Georgia,serif", fontSize: 13, color: "#fff", fontStyle: "italic" }}>R</div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 500, color: "#fff" }}>Rico AI</div>
              <div style={{ fontSize: 10, color: "#3d6bef" }}>● Active · finding UAE jobs</div>
            </div>
          </div>
          {/* Messages */}
          <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 9, minHeight: 340 }}>
            <Bubble side="user">Show me EA to CEO jobs in Dubai above 80% match</Bubble>
            <Bubble side="rico">
              <span>Found <strong style={{ color: "#5dcaa5" }}>3 strong matches</strong> for you</span>
              <JobCard title="Executive Assistant to CEO" company="Leading Dubai Group" salary="AED 32k/mo" />
              <JobCard title="Chief of Staff — Founder Office" company="Major UAE Holding Company" salary="AED 40k/mo" />
            </Bubble>
            <Bubble side="user">Help me apply to the first one</Bubble>
            <Bubble side="rico">
              <span style={{ color: "#facc15" }}>⚠</span> Your approval needed first.<br /><br />
              <strong style={{ color: "#e8eaed" }}>Leading Dubai Group — EA to CEO</strong><br />
              <span style={{ color: "#555b66", fontSize: 10 }}>Strong match · AED 32,000/mo</span><br /><br />
              Confirm and I will prepare your cover letter.
            </Bubble>
            <Bubble side="user">Yes, go ahead</Bubble>
            {replied ? (
              <Bubble side="rico">
                Cover letter ready to review.<br /><br />
                <span style={{ color: "#5dcaa5" }}>Application saved: <strong>Leading Dubai Group — EA to CEO</strong></span>
              </Bubble>
            ) : (
              <Bubble side="rico"><TypingDots /></Bubble>
            )}
          </div>
          {/* Input bar */}
          <div style={{ padding: 10, borderTop: "1px solid rgba(255,255,255,.06)", display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ flex: 1, background: "#1a1d22", borderRadius: 18, padding: "7px 12px", fontSize: 10, color: "#555" }}>Message Rico...</div>
            <div style={{ width: 26, height: 26, borderRadius: "50%", background: "#1246d6", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 13 }}>↑</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Bubble({ side, children }: { side: "user" | "rico"; children: React.ReactNode }) {
  const isUser = side === "user";
  return (
    <div style={{
      background: isUser ? "#1246d6" : "#1a1d22",
      color: isUser ? "#fff" : "#c8cdd6",
      fontSize: 11, padding: "9px 12px", lineHeight: 1.55,
      borderRadius: isUser ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
      alignSelf: isUser ? "flex-end" : "flex-start",
      maxWidth: isUser ? "80%" : "88%",
    }}>
      {children}
    </div>
  );
}

function JobCard({ title, company, salary }: { title: string; company: string; salary: string }) {
  return (
    <div style={{ background: "#141720", borderRadius: 10, padding: 10, marginTop: 6, border: ".5px solid rgba(61,107,239,.2)" }}>
      <div style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "rgba(13,107,82,.2)", color: "#5dcaa5", fontSize: 9, fontWeight: 500, padding: "2px 7px", borderRadius: 100, marginBottom: 5 }}>Strong match</div>
      <div style={{ fontSize: 11, fontWeight: 500, color: "#e8eaed", marginBottom: 2 }}>{title}</div>
      <div style={{ fontSize: 10, color: "#555b66" }}>{company} · {salary}</div>
    </div>
  );
}

function TypingDots() {
  return (
    <div style={{ display: "flex", gap: 3, alignItems: "center", padding: "2px 0" }}>
      {[0, 200, 400].map((delay) => (
        <div key={delay} style={{ width: 5, height: 5, borderRadius: "50%", background: "#3d6bef", animation: `pulse 1.1s ${delay}ms infinite` }} />
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════
   Main page
═══════════════════════════════════════ */
export default function HomePage() {
  const ink = "#0a0b0d";
  const ink2 = "#3d4147";
  const ink3 = "#7a7f88";
  const bg = "#f7f5f0";
  const white = "#fff";
  const blue = "#1246d6";
  const blueMid = "#3d6bef";
  const blueLight = "#e8eeff";
  const teal = "#0d6b52";
  const tealLight = "#e0f5ee";
  const border = "#e2dfd8";
  const serif = "'Fraunces', Georgia, serif";

  return (
    <div style={{ fontFamily: "'DM Sans', system-ui, sans-serif", background: bg, color: ink }}>
      <style>{`
        @keyframes fadeUp { from { opacity:0; transform:translateY(18px) } to { opacity:1; transform:translateY(0) } }
        @keyframes float  { 0%,100% { transform:translateY(0) } 50% { transform:translateY(-7px) } }
        @keyframes pulse  { 0%,100% { opacity:1 } 50% { opacity:.35 } }
        @keyframes ticker { 0% { transform:translateX(0) } 100% { transform:translateX(-50%) } }
        .fu { animation: fadeUp .65s ease both }
        .d1 { animation-delay:.1s } .d2 { animation-delay:.2s }
        .d3 { animation-delay:.3s } .d4 { animation-delay:.45s }
      `}</style>

      {/* Nav */}
      <nav style={{ background: "rgba(247,245,240,.96)", borderBottom: `1px solid ${border}`, padding: "16px 40px", display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 100 }}>
        <Link href="/" style={{ fontFamily: serif, fontSize: 20, fontWeight: 400, letterSpacing: "-.5px", color: ink, textDecoration: "none" }}>
          Rico<span style={{ color: blue }}>.</span>ai
        </Link>
        <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
          <a href="#how-it-works" style={{ fontSize: 13, color: ink3, textDecoration: "none" }}>How it works</a>
          <a href="#features" style={{ fontSize: 13, color: ink3, textDecoration: "none" }}>What Rico does</a>
          <a href="#safety" style={{ fontSize: 13, color: ink3, textDecoration: "none" }}>Safety</a>
          <Link href={CHAT_URL}
            style={{ background: ink, color: white, padding: "8px 18px", borderRadius: 100, fontSize: 13, fontWeight: 500, textDecoration: "none" }}>
            Start chatting with Rico →
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section style={{ padding: "72px 40px 64px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 56, alignItems: "center", maxWidth: 1080, margin: "0 auto" }}>
          <div>
            <div className="fu" style={{ display: "inline-flex", alignItems: "center", gap: 7, background: tealLight, color: teal, fontSize: 11, fontWeight: 500, letterSpacing: ".8px", textTransform: "uppercase", padding: "5px 13px", borderRadius: 100, marginBottom: 24, border: ".5px solid rgba(13,107,82,.25)" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: teal, display: "inline-block", animation: "pulse 2s infinite" }} />
              Active now · UAE job market
            </div>
            <h1 className="fu d1" style={{ fontFamily: serif, fontSize: "clamp(38px,4.8vw,58px)", fontWeight: 300, lineHeight: 1.07, letterSpacing: -2, color: ink, marginBottom: 22 }}>
              Stop searching<br />for UAE jobs.<br />
              <em style={{ color: blue }}>Talk to Rico</em><br />
              <strong style={{ fontWeight: 600 }}>instead.</strong>
            </h1>
            <p className="fu d2" style={{ fontSize: 17, color: ink2, fontWeight: 300, lineHeight: 1.7, maxWidth: 480, marginBottom: 32 }}>
              Rico AI finds the best UAE jobs for you, shows why they match, helps prepare your application, and tracks every opportunity until you get interviews.
            </p>
            <div className="fu d3" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 28 }}>
              <Link href={CHAT_URL}
                style={{ display: "inline-flex", alignItems: "center", gap: 7, background: blue, color: white, padding: "13px 24px", borderRadius: 100, fontSize: 14, fontWeight: 500, textDecoration: "none" }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
                Start chatting with Rico
              </Link>
              <Link href="/login"
                style={{ display: "inline-flex", alignItems: "center", gap: 7, background: "transparent", color: ink2, padding: "13px 20px", borderRadius: 100, fontSize: 13, border: `1px solid ${border}`, textDecoration: "none" }}>
                Sign in
              </Link>
            </div>
            <div className="fu d4" style={{ display: "flex", flexWrap: "wrap", gap: 16, fontSize: 12, color: ink3 }}>
              {["No CV spam", "You approve every application", "UAE jobs only"].map((t) => (
                <div key={t} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span style={{ width: 15, height: 15, borderRadius: "50%", background: tealLight, display: "inline-flex", alignItems: "center", justifyContent: "center", color: teal, fontSize: 9, flexShrink: 0 }}>✓</span>
                  {t}
                </div>
              ))}
            </div>
          </div>
          <div className="fu d3">
            <PhoneMockup />
          </div>
        </div>
      </section>

      {/* Ticker */}
      <div style={{ background: ink, padding: "12px 0", overflow: "hidden" }}>
        <div style={{ display: "flex", animation: "ticker 30s linear infinite", whiteSpace: "nowrap" }}>
          {[...TICKER_ITEMS, ...TICKER_ITEMS].map((item, i) => (
            <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "0 36px", fontSize: 11, color: "#3a4050" }}>
              <b style={{ color: blueMid }}>✓</b> {item}
            </span>
          ))}
        </div>
      </div>

      {/* Flow bar */}
      <div id="how-it-works" style={{ background: white, borderTop: `1px solid ${border}`, borderBottom: `1px solid ${border}`, padding: "28px 40px" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "center", flexWrap: "wrap" }}>
          {[
            { n: "1", label: "Chat with Rico" },
            { n: "2", label: "Get your matches" },
            { n: "3", label: "Apply faster" },
            { n: "4", label: "Track everything" },
          ].map((step, i) => (
            <div key={step.n} style={{ display: "flex", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 24px" }}>
                <div style={{ width: 28, height: 28, borderRadius: "50%", background: blueLight, color: blue, fontSize: 12, fontWeight: 500, display: "flex", alignItems: "center", justifyContent: "center" }}>{step.n}</div>
                <div style={{ fontSize: 13, fontWeight: 500, color: ink }}>{step.label}</div>
              </div>
              {i < 3 && <span style={{ color: border, fontSize: 18, padding: "0 4px" }}>→</span>}
            </div>
          ))}
        </div>
      </div>

      {/* Problem / Solution */}
      <Reveal>
        <section style={{ padding: "80px 40px", background: white }}>
          <div style={{ maxWidth: 1080, margin: "0 auto" }}>
            <div style={{ fontSize: 11, letterSpacing: 2, textTransform: "uppercase" as const, color: ink3, fontWeight: 500, marginBottom: 14 }}>Why job hunting in the UAE is hard</div>
            <h2 style={{ fontFamily: serif, fontSize: "clamp(28px,3.2vw,44px)", fontWeight: 300, letterSpacing: -1.8, lineHeight: 1.1, marginBottom: 48 }}>
              Hours of searching.<br /><em style={{ color: blue }}>Rarely the right result.</em>
            </h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48, alignItems: "start" }}>
              <div style={{ display: "flex", flexDirection: "column" as const, gap: 14 }}>
                {[
                  { ico: "⏱", t: "You spend hours searching every day", d: "Switching between LinkedIn, Indeed, Bayt, NaukriGulf — the same keywords, the same results, every single day." },
                  { ico: "🎯", t: "Most results are not right for you", d: "Wrong level, wrong sector, wrong company. You read 50 jobs to find 2 worth sending a CV for." },
                  { ico: "📋", t: "Applications get lost and forgotten", d: "No system. You apply and forget. No follow-up, no tracking, no idea where anything stands." },
                  { ico: "🔕", t: "Good jobs disappear before you see them", d: "UAE executive roles close fast. By the time you check in the evening, the window has passed." },
                ].map((p) => (
                  <div key={p.t} style={{ display: "flex", gap: 14, padding: 18, borderRadius: 14, border: `1px solid ${border}`, background: white }}>
                    <div style={{ width: 36, height: 36, borderRadius: 10, background: "#fff5f5", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0 }}>{p.ico}</div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 500, color: ink, marginBottom: 3 }}>{p.t}</div>
                      <div style={{ fontSize: 12, color: ink3, lineHeight: 1.6 }}>{p.d}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ background: ink, borderRadius: 20, padding: 36 }}>
                <div style={{ fontFamily: serif, fontSize: 26, fontWeight: 300, fontStyle: "italic", lineHeight: 1.2, marginBottom: 14, color: white }}>Rico does the searching.<br />You do the interviews.</div>
                <div style={{ fontSize: 14, color: "rgba(255,255,255,.5)", lineHeight: 1.7, marginBottom: 28 }}>While you focus on work, family, or life — Rico checks every UAE job source daily, finds roles that match your goals, and alerts you the moment something worth applying for appears.</div>
                <div style={{ display: "flex", flexDirection: "column" as const, gap: 12 }}>
                  {[
                    "Searches every UAE job source for you daily",
                    "Shows a match score so you know what fits",
                    "Instant Telegram alert for strong matches",
                    "Helps you write cover letters and follow-ups",
                    "Tracks every application in one place",
                    "Never applies without your approval",
                  ].map((f) => (
                    <div key={f} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "rgba(255,255,255,.75)" }}>
                      <span style={{ width: 7, height: 7, borderRadius: "50%", background: blueMid, flexShrink: 0, display: "inline-block" }} />{f}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      </Reveal>

      {/* Steps */}
      <Reveal>
        <section style={{ padding: "80px 40px" }}>
          <div style={{ maxWidth: 1080, margin: "0 auto" }}>
            <div style={{ fontSize: 11, letterSpacing: 2, textTransform: "uppercase" as const, color: ink3, fontWeight: 500, marginBottom: 14 }}>How it works</div>
            <h2 style={{ fontFamily: serif, fontSize: "clamp(28px,3.2vw,44px)", fontWeight: 300, letterSpacing: -1.8, lineHeight: 1.1, marginBottom: 18 }}>
              Five steps.<br /><em style={{ color: blue }}>No manual work.</em>
            </h2>
            <p style={{ fontSize: 16, color: ink2, fontWeight: 300, lineHeight: 1.7, maxWidth: 500, marginBottom: 0 }}>Tell Rico what you are looking for. He handles everything after that — you only get involved when a real opportunity is ready for you.</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 8, marginTop: 48 }}>
              {[
                { n: "01", ico: "💬", t: "Tell Rico what you want", d: "Chat with Rico about your target roles, salary, location, and experience." },
                { n: "02", ico: "🔍", t: "Rico finds jobs for you", d: "Rico checks every UAE job source daily and removes repeated and irrelevant jobs automatically." },
                { n: "03", ico: "✅", t: "See your best matches first", d: "Every job comes with a clear match score so you know which roles are worth your time." },
                { n: "04", ico: "📲", t: "Get alerts on Telegram", d: "Strong matches are sent to your phone the moment they are found. No missed opportunities." },
                { n: "05", ico: "📋", t: "Apply and track everything", d: "Rico helps you apply faster and keeps track of every saved, applied, and interview stage." },
              ].map((s) => (
                <div key={s.n} style={{ background: white, border: `1px solid ${border}`, borderRadius: 16, padding: "22px 16px", textAlign: "center" as const }}>
                  <div style={{ fontSize: 10, color: blue, fontWeight: 500, letterSpacing: 1, marginBottom: 12 }}>STEP {s.n}</div>
                  <div style={{ fontSize: 26, marginBottom: 12 }}>{s.ico}</div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: ink, marginBottom: 6 }}>{s.t}</div>
                  <div style={{ fontSize: 11, color: ink3, lineHeight: 1.6 }}>{s.d}</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </Reveal>

      {/* Features */}
      <Reveal>
        <section id="features" style={{ padding: "80px 40px", background: white }}>
          <div style={{ maxWidth: 1080, margin: "0 auto" }}>
            <div style={{ fontSize: 11, letterSpacing: 2, textTransform: "uppercase" as const, color: ink3, fontWeight: 500, marginBottom: 14 }}>What Rico does for you</div>
            <h2 style={{ fontFamily: serif, fontSize: "clamp(28px,3.2vw,44px)", fontWeight: 300, letterSpacing: -1.8, lineHeight: 1.1, marginBottom: 48 }}>
              Everything your job search<br /><em style={{ color: blue }}>needs in one place.</em>
            </h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 2, background: border, border: `1px solid ${border}`, borderRadius: 18, overflow: "hidden" }}>
              {[
                { ico: "🔍", t: "Finds UAE jobs for you", d: "Rico searches daily and brings you roles that match your goals, salary, location, and experience. Removes repeated and irrelevant jobs automatically." },
                { ico: "🎯", t: "Shows your best matches first", d: "Every job comes with a clear match score so you know which roles are worth your time — and exactly why they matched." },
                { ico: "✍️", t: "Helps you apply faster", d: "Rico can prepare application messages, cover letters, and follow-up notes for each role — ready for you to review and send." },
                { ico: "📲", t: "Sends alerts to your phone", d: "Get strong matches on Telegram so you never miss a good opportunity, even when you are not checking the app." },
                { ico: "📋", t: "Tracks every application", d: "Rico keeps your saved, applied, interview, and follow-up jobs organised in one clear view — nothing falls through the cracks." },
                { ico: "🧠", t: "Learns what jobs you like", d: "When you save, skip, or reject jobs, Rico gets better at finding the right ones. The more you use it, the smarter it gets." },
              ].map((f) => (
                <div key={f.t} style={{ background: white, padding: "28px 24px" }}>
                  <div style={{ fontSize: 24, marginBottom: 12 }}>{f.ico}</div>
                  <div style={{ fontSize: 14, fontWeight: 500, color: ink, marginBottom: 8 }}>{f.t}</div>
                  <div style={{ fontSize: 13, color: ink3, lineHeight: 1.65 }}>{f.d}</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </Reveal>

      {/* Safety */}
      <Reveal>
        <section id="safety" style={{ padding: "80px 40px" }}>
          <div style={{ maxWidth: 1080, margin: "0 auto", textAlign: "center" as const }}>
            <div style={{ fontSize: 11, letterSpacing: 2, textTransform: "uppercase" as const, color: ink3, fontWeight: 500, marginBottom: 14 }}>Your control, always</div>
            <h2 style={{ fontFamily: serif, fontSize: "clamp(28px,3.2vw,44px)", fontWeight: 300, letterSpacing: -1.8, lineHeight: 1.1, marginBottom: 18 }}>
              Rico <em style={{ color: blue }}>never applies</em><br />without your approval.
            </h2>
            <p style={{ fontSize: 16, color: ink2, fontWeight: 300, lineHeight: 1.7, maxWidth: 500, margin: "0 auto 48px" }}>
              Your career is too important to hand to a bot. Rico finds and prepares — you decide and approve. Every single time.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
              {[
                "Rico never sends an application without you saying yes. You see every job and every message before anything is submitted.",
                "Your information stays private. Your profile, applications, and job history are never shared with anyone.",
                "You control what Rico ignores. Set your own rules — wrong job types, certain companies, irrelevant keywords — and Rico will never show them again.",
              ].map((text, i) => (
                <div key={i} style={{ background: white, border: `1px solid ${border}`, borderRadius: 14, padding: 24, textAlign: "left" as const }}>
                  <div style={{ fontSize: 28, fontWeight: 500, color: blue, marginBottom: 8 }}>0{i + 1}</div>
                  <div style={{ fontSize: 13, color: ink3, lineHeight: 1.6 }}>{text}</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </Reveal>

      {/* Final CTA */}
      <div style={{ background: ink, padding: "100px 40px", textAlign: "center" as const }}>
        <h2 style={{ fontFamily: serif, fontSize: "clamp(30px,4vw,52px)", fontWeight: 300, letterSpacing: -2.5, color: white, marginBottom: 16, lineHeight: 1.05 }}>
          Ready to apply<br /><em style={{ color: blueMid }}>smarter?</em>
        </h2>
        <p style={{ fontSize: 16, color: "rgba(255,255,255,.45)", fontWeight: 300, marginBottom: 40, lineHeight: 1.7 }}>
          Tell Rico what job you want.<br />Rico finds your matches and helps you apply.
        </p>
        <div style={{ display: "flex", justifyContent: "center", gap: 14, flexWrap: "wrap" }}>
          <Link href={CHAT_URL}
            style={{ display: "inline-flex", alignItems: "center", gap: 7, background: white, color: ink, padding: "14px 28px", borderRadius: 100, fontSize: 14, fontWeight: 500, textDecoration: "none" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
            Start chatting with Rico
          </Link>
          <a href={JOTFORM_URL} target="_blank" rel="noopener noreferrer"
            style={{ display: "inline-flex", alignItems: "center", gap: 7, background: "transparent", color: "rgba(255,255,255,.6)", padding: "14px 24px", borderRadius: 100, fontSize: 13, border: "1px solid rgba(255,255,255,.18)", textDecoration: "none" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
            Set up Telegram alerts
          </a>
        </div>
      </div>

      {/* Footer */}
      <footer style={{ background: ink, borderTop: "1px solid #181b22", padding: "24px 40px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div style={{ fontFamily: serif, fontSize: 16, color: "rgba(255,255,255,.4)" }}>Rico<span style={{ color: blueMid }}>.</span>ai</div>
        <div style={{ display: "flex", gap: 20 }}>
          <Link href="/login" style={{ fontSize: 11, color: "rgba(255,255,255,.25)", textDecoration: "none" }}>Sign in</Link>
          <Link href={CHAT_URL} style={{ fontSize: 11, color: "rgba(255,255,255,.25)", textDecoration: "none" }}>Get started</Link>
          <a href="#how-it-works" style={{ fontSize: 11, color: "rgba(255,255,255,.25)", textDecoration: "none" }}>How it works</a>
          <a href="#features" style={{ fontSize: 11, color: "rgba(255,255,255,.25)", textDecoration: "none" }}>What Rico does</a>
        </div>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,.2)" }}>© 2026 Rico AI · Your UAE AI Career Agent</div>
      </footer>
    </div>
  );
}
