"use client";

import type { ChatApiResponse, JobMatch, RicoOption, UploadCVResponse } from "@/lib/api";
import { fetchMe, logout, sendChat, sendChatPublic, uploadCV } from "@/lib/api";
import { buildAuthHref } from "@/lib/redirect";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

function getSessionId(): string {
  if (typeof window === "undefined") return "ssr-session";
  let sid = localStorage.getItem("rico_sid");
  if (!sid) {
    sid = "web-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 9);
    localStorage.setItem("rico_sid", sid);
  }
  return sid;
}

interface Message {
  id: number;
  role: "user" | "rico";
  text: string;
  type?: string;
  matches?: JobMatch[];
  options?: RicoOption[];
  next_action?: string;
  freeMode?: boolean;
}

type ChatAudience = "checking" | "authenticated" | "public";

let _id = 0;
function nextId() { return ++_id; }

const QUICK_ACTIONS = [
  { label: "Find UAE jobs for me", prompt: "Find matching UAE jobs for me." },
  { label: "Set my target role", prompt: "I want to set my target role and job preferences." },
  { label: "Upload my CV", prompt: "__cv_upload__" },
  { label: "Track my applications", prompt: "Show my tracked applications." },
  { label: "Prepare for an interview", prompt: "Help me prepare for an interview." },
  { label: "Draft a cover letter", prompt: "Draft a cover letter for a job." },
];
const CHAT_LOGIN_HREF = buildAuthHref("/login", "/chat");
const CHAT_SIGNUP_HREF = buildAuthHref("/signup", "/chat");

function ThinkingIndicator() {
  return (
    <div className="flex justify-start animate-pulse">
      <div className="bg-[#13132a] border border-white/5 rounded-2xl rounded-tl-none px-4 py-4 flex gap-1.5 items-center backdrop-blur-md">
        <span className="w-1.5 h-1.5 bg-[#a78bfa] rounded-full animate-bounce [animation-duration:0.8s]" />
        <span className="w-1.5 h-1.5 bg-[#a78bfa] rounded-full animate-bounce [animation-duration:0.8s] [animation-delay:0.2s]" />
        <span className="w-1.5 h-1.5 bg-[#a78bfa] rounded-full animate-bounce [animation-duration:0.8s] [animation-delay:0.4s]" />
      </div>
    </div>
  );
}

function JobMatchCard({ match, onAction }: { match: JobMatch; onAction: (prompt: string) => void }) {
  const score = match.score ?? 0;
  const scoreLabel = score >= 0.8 ? "Strong match" : score >= 0.6 ? "Good match" : "Possible match";
  return (
    <div className="rounded-xl border border-white/8 bg-[#0f0f24] p-3 mb-2">
      <div className="flex items-start justify-between gap-2 mb-1">
        <div>
          <div className="text-[13px] font-semibold text-white">{match.title}</div>
          <div className="text-[11px] text-[#8080a0]">{match.company}{match.location ? ` · ${match.location}` : ""}</div>
        </div>
        {score > 0 && (
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0 ${score >= 0.8
            ? "bg-[#5dcaa522] text-[#5dcaa5]"
            : score >= 0.6
              ? "bg-[#facc1522] text-[#facc15]"
              : "bg-[#a78bfa22] text-[#a78bfa]"
            }`}>
            {scoreLabel}
          </span>
        )}
      </div>
      {match.why && <p className="text-[11px] text-[#5a5a7a] mb-2 leading-relaxed">{match.why}</p>}
      {match.actions && match.actions.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-1">
          {match.actions.map((action) => (
            <button
              key={action}
              onClick={() => onAction(`${action} — ${match.title} at ${match.company}`)}
              className="text-[10px] px-2.5 py-1 rounded-lg border border-white/10 text-[#8080a0] hover:border-[#5b4fff]/40 hover:text-white transition-colors"
            >
              {action}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function OptionButtons({ options, onAction }: { options: RicoOption[]; onAction: (prompt: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {options.map((opt) => (
        <button
          key={opt.action}
          onClick={() => onAction(opt.label)}
          className="text-[12px] px-3 py-2 rounded-xl border border-[#5b4fff]/30 text-[#a78bfa] hover:bg-[#5b4fff]/10 hover:border-[#5b4fff]/60 transition-colors"
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export default function ChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [slowHint, setSlowHint] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [chatAudience, setChatAudience] = useState<ChatAudience>("checking");
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const promptSentRef = useRef(false);

  useEffect(() => {
    const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";
    if (USE_MOCK) {
      setChatAudience("authenticated");
      return;
    }

    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (cancelled) return;
        setChatAudience(me.authenticated ? "authenticated" : "public");
      })
      .catch(() => {
        if (cancelled) return;
        setChatAudience("public");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (chatAudience === "checking" || typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const prompt = params.get("prompt");
    if (prompt && !promptSentRef.current) {
      promptSentRef.current = true;
      sendMessage(prompt);
    } else if (!promptSentRef.current) {
      promptSentRef.current = true;
      // Greet immediately
      setMessages([{ id: 1, role: "rico", text: "Hi, I'm Rico. Tell me what UAE job you're looking for — role, city, and salary — and I'll find your best matches. You can also upload your CV and I'll set up your profile automatically." }]);
    }
  }, [chatAudience]);

  function scrollBottom() {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  async function sendMessage(text: string) {
    if (chatAudience === "checking") return;
    if (text === "__cv_upload__") {
      fileInputRef.current?.click();
      return;
    }
    const trimmed = text.trim();
    if (!trimmed || thinking) return;

    setMessages((prev) => [...prev, { id: nextId(), role: "user", text: trimmed }]);
    setThinking(true);
    scrollBottom();

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45_000);
    const slowHintId = setTimeout(() => setSlowHint(true), 5_000);

    try {
      const res: ChatApiResponse =
        chatAudience === "authenticated"
          ? await sendChat(trimmed, controller.signal)
          : await sendChatPublic(trimmed, getSessionId(), controller.signal);
      const reply =
        res.response ??
        res.reply ??
        res.message ??
        res.content ??
        res.answer ??
        res.data?.response ??
        res.data?.reply ??
        res.data?.message ??
        res.data?.content ??
        "";
      const provider = res.provider ?? res.response_source ?? "unknown";
      const isRateLimited = res.response_source === "rate_limited" || res.provider_state === "rate_limited";
      const hfMode = provider === "huggingface" || provider === "hf";
      const deepseekMode = provider === "deepseek";
      const providerAvailable =
        res.provider_available ??
        (provider === "openai"
          ? (res.openai_available ?? true)
          : deepseekMode
            ? (res.deepseek_available ?? true)
            : hfMode);
      const freeMode =
        isRateLimited ||
        provider === "fallback" ||
        provider === "none" ||
        (!hfMode && !deepseekMode && providerAvailable === false);

      if (isRateLimited) {
        setMessages((prev) => [...prev, { id: nextId(), role: "rico", text: "Rico's AI is rate-limited right now — please try again in a minute.", freeMode: true }]);
      } else if (!reply && !res.matches && !res.options) {
        setMessages((prev) => [...prev, { id: nextId(), role: "rico", text: "Rico returned an empty response. Please try again." }]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "rico",
            text: reply,
            type: res.type,
            matches: res.matches as JobMatch[] | undefined,
            options: res.options as RicoOption[] | undefined,
            next_action: res.next_action,
            freeMode: freeMode && !hfMode,
          },
        ]);
      }
    } catch (err) {
      if (err instanceof Error) {
        if (err.name === "AbortError") {
          setMessages((prev) => [...prev, { id: nextId(), role: "rico", text: "Rico is taking longer than usual — the server may be waking up. Please try again in 30 seconds." }]);
          return;
        }
        if (err.message.includes("401")) { setSessionExpired(true); return; }
        if (err.name === "TypeError" || err.message === "Failed to fetch" || err.message.includes("network")) {
          setMessages((prev) => [...prev, { id: nextId(), role: "rico", text: "Could not reach Rico. Check your connection or try again." }]);
          return;
        }
      }
      setMessages((prev) => [...prev, { id: nextId(), role: "rico", text: "Something went wrong. Please try again." }]);
    } finally {
      clearTimeout(timeoutId);
      clearTimeout(slowHintId);
      setSlowHint(false);
      setThinking(false);
      scrollBottom();
      textareaRef.current?.focus();
    }
  }

  async function handleCVUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || chatAudience === "checking") return;
    e.target.value = "";
    setUploadError("");
    setMessages((prev) => [...prev, { id: nextId(), role: "user", text: `📎 Uploading CV: ${file.name}` }]);
    setThinking(true);
    scrollBottom();
    try {
      const result: UploadCVResponse =
        chatAudience === "authenticated"
          ? await uploadCV(file)
          : await uploadCV(file, `public:${getSessionId()}`);
      const p = result.parsed;
      const summary = [
        p.skills?.length ? `Skills detected: ${p.skills.slice(0, 6).join(", ")}` : "",
        p.emails?.length ? `Email: ${p.emails[0]}` : "",
        p.phones?.length ? `Phone: ${p.phones[0]}` : "",
        p.years_experience_hint ? `Experience: ~${p.years_experience_hint} years` : "",
      ].filter(Boolean).join(" · ");
      const text = `CV received: ${file.name}. I extracted your details and pre-filled your profile.${summary ? `\n\n${summary}` : ""}\n\nTell me your target roles and I'll start finding matches.`;
      setMessages((prev) => [...prev, { id: nextId(), role: "rico", text }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setUploadError(msg);
      setMessages((prev) => [...prev, { id: nextId(), role: "rico", text: `Could not process CV: ${msg}. Please make sure it's a PDF under 10 MB.` }]);
    } finally {
      setThinking(false);
      scrollBottom();
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text) return;
    setInput("");
    await sendMessage(text);
  }

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (sessionExpired) {
    return (
      <div className="min-h-screen bg-[#06060f] flex items-center justify-center">
        <div className="flex max-w-lg flex-col items-center gap-4 rounded-2xl border border-white/5 bg-[#13132a]/80 p-8 text-center backdrop-blur-md">
          <p className="text-sm font-medium text-[#eeeef5]">Session expired.</p>
          <p className="text-sm text-[#5a5a7a]">Sign in again to continue chatting with Rico.</p>
          <Link href={CHAT_LOGIN_HREF} className="rounded-lg bg-[#5b4fff] px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#4a3fe0]">
            Sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#06060f] flex flex-col relative overflow-hidden">
      {/* Ambient glows matching landing page */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute -top-[250px] -left-[150px] w-[700px] h-[700px] rounded-full bg-[rgba(91,79,255,0.06)] blur-[140px]" />
        <div className="absolute bottom-0 -right-[100px] w-[500px] h-[500px] rounded-full bg-[rgba(0,201,167,0.04)] blur-[140px]" />
      </div>

      {/* Top nav — minimal, matches landing */}
      <header className="relative z-10 flex items-center justify-between px-6 py-4 border-b border-white/[0.05]">
        <Link href="/" className="flex items-center gap-2 text-white font-black text-lg tracking-tight">
          <div className="w-8 h-8 rounded-[9px] bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-sm font-black shadow-[0_4px_16px_rgba(91,79,255,0.3)]">R</div>
          Rico<span className="text-[#5b4fff]">.ai</span>
        </Link>
        <div className="flex items-center gap-3">
          {chatAudience === "authenticated" ? (
            <>
              <Link href="/dashboard" className="text-[13px] text-[#5a5a7a] hover:text-white transition-colors">Dashboard</Link>
              <button
                type="button"
                onClick={handleLogout}
                className="text-[12px] px-3 py-1.5 rounded-lg bg-[#5b4fff] text-white hover:bg-[#4a3fdf] transition-colors font-medium"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link href={CHAT_LOGIN_HREF} className="text-[13px] text-[#5a5a7a] hover:text-white transition-colors">Sign in</Link>
              <Link href={CHAT_SIGNUP_HREF} className="text-[12px] px-3 py-1.5 rounded-lg bg-[#5b4fff] text-white hover:bg-[#4a3fdf] transition-colors font-medium">Sign up free</Link>
            </>
          )}
        </div>
      </header>

      {/* Hidden file input for CV upload */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        aria-label="Upload CV PDF"
        title="Upload CV PDF"
        className="hidden"
        onChange={handleCVUpload}
      />

      <div className="relative z-10 flex flex-col flex-1 h-[calc(100vh-65px)] max-w-3xl w-full mx-auto px-4">
        {/* Messages Container */}
        <div className="flex-1 overflow-y-auto px-2 py-6 space-y-5 pb-32">

          {/* Quick start (shown above first message) */}
          {messages.length <= 1 && !thinking && (
            <div className="flex flex-wrap justify-center gap-2 pb-4">
              {QUICK_ACTIONS.map((qa) => (
                <button
                  key={qa.label}
                  onClick={() => sendMessage(qa.prompt)}
                  disabled={thinking || chatAudience === "checking"}
                  className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-xs text-[#8080a0] transition-colors hover:border-[rgba(91,79,255,0.3)] hover:bg-white/[0.05] hover:text-[#eeeef5] disabled:opacity-50"
                >
                  {qa.label}
                </button>
              ))}
            </div>
          )}

          {/* Messages */}
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex items-end gap-2 animate-in fade-in slide-in-from-bottom-2 ${m.role === "user" ? "justify-end" : "justify-start"
                }`}
            >
              {m.role === "rico" && (
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-[11px] font-black text-white shrink-0 mb-1 shadow-[0_2px_8px_rgba(91,79,255,0.3)]">
                  R
                </div>
              )}
              <div className={`max-w-[82%] ${m.role === "user"
                ? "rounded-2xl rounded-tr-none bg-[#5b4fff] px-4 py-3 text-[14px] text-white leading-relaxed shadow-[0_4px_15px_rgba(91,79,255,0.2)]"
                : "rounded-2xl rounded-tl-none bg-[#13132a] border border-white/5 px-4 py-3 text-[14px] text-[#eeeef5] leading-relaxed backdrop-blur-md"
                }`}>
                {/* Message text */}
                {m.text && <div className="whitespace-pre-wrap">{m.text}</div>}

                {/* Job match cards */}
                {m.matches && m.matches.length > 0 && (
                  <div className="mt-3">
                    {m.matches.map((match, i) => (
                      <JobMatchCard key={i} match={match} onAction={(prompt) => sendMessage(prompt)} />
                    ))}
                  </div>
                )}

                {/* Option buttons */}
                {m.options && m.options.length > 0 && (
                  <OptionButtons options={m.options} onAction={(prompt) => sendMessage(prompt)} />
                )}

                {m.freeMode && (
                  <p className="mt-2 text-[11px] text-[#5a5a7a]">Free mode — HF fallback active</p>
                )}
              </div>
              {m.role === "user" && (
                <div className="w-6 h-6 rounded-full bg-white/[0.08] flex items-center justify-center text-[10px] font-medium text-[#8080a0] shrink-0 mb-1">
                  You
                </div>
              )}
            </div>
          ))}

          {thinking && (
            <div className="flex flex-col gap-2">
              <ThinkingIndicator />
              {slowHint && (
                <p className="text-[11px] text-[#5a5a7a] pl-9 animate-pulse">
                  Rico is waking up — first request after idle can take up to a minute…
                </p>
              )}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Floating input bar */}
        <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-[#06060f] via-[#06060f]/95 to-transparent">
          {uploadError && (
            <p className="text-[11px] text-red-400 mb-2 text-center">{uploadError}</p>
          )}
          <div className="flex items-end gap-2">
            {/* CV upload button */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={thinking || chatAudience === "checking"}
              title="Upload your CV (PDF)"
              className="w-10 h-10 rounded-xl border border-white/10 bg-[#13132a]/80 text-[#8080a0] flex items-center justify-center hover:border-[#5b4fff]/40 hover:text-white transition-all disabled:opacity-30 shrink-0"
              aria-label="Upload CV"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>

            {/* Text input */}
            <div className="relative flex-1">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={thinking || chatAudience === "checking"}
                rows={1}
                placeholder={chatAudience === "checking"
                  ? "Checking your session…"
                  : "Ask Rico anything — jobs, CV, applications, interviews…"}
                className="w-full resize-none bg-[#13132a]/80 border border-white/10 backdrop-blur-xl rounded-2xl py-3 pl-4 pr-12 text-sm text-white placeholder:text-[#5a5a7a] focus:outline-none focus:border-[#5b4fff]/50 transition-all shadow-2xl"
              />
              <button
                onClick={handleSend}
                disabled={thinking || chatAudience === "checking" || !input.trim()}
                className="absolute right-2 top-1.5 bottom-1.5 w-9 h-9 rounded-xl bg-[#5b4fff] text-white flex items-center justify-center hover:bg-[#4a3fdf] transition-all disabled:opacity-30 disabled:grayscale"
                aria-label={thinking ? "Sending…" : "Send"}
              >
                {thinking ? (
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
                  </svg>
                )}
              </button>
            </div>
          </div>
          <p className="text-center text-[10px] text-[#5a5a7a] mt-2 opacity-40">
            Enter to send · Shift+Enter for new line · 📎 to upload CV
          </p>
        </div>
      </div>
    </div>
  );
}
