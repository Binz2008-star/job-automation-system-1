"use client";

import { DashboardShell } from "@/components/DashboardShell";
import type { ChatApiResponse } from "@/lib/api";
import { sendChat } from "@/lib/api";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

interface Message {
  id: number;
  role: "user" | "rico";
  text: string;
  freeMode?: boolean;
}

let _id = 0;
function nextId() { return ++_id; }

const QUICK_ACTIONS = [
  { label: "Tell Rico my target role", prompt: "I'd like to set my target role and job title preferences." },
  { label: "Add UAE city preference", prompt: "I want to add my preferred cities in the UAE." },
  { label: "Add salary expectation", prompt: "I want to share my salary expectations." },
  { label: "List my key skills", prompt: "I want to share my key skills and experience." },
  { label: "Ask what Rico can do", prompt: "What can you help me with?" },
];

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

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const promptSentRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const prompt = params.get("prompt");
    if (prompt && !promptSentRef.current) {
      promptSentRef.current = true;
      sendMessage(prompt);
    }
  }, []);

  function scrollBottom() {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || thinking) return;

    setMessages((prev) => [...prev, { id: nextId(), role: "user", text: trimmed }]);
    setThinking(true);
    scrollBottom();

    try {
      const res: ChatApiResponse = await sendChat(trimmed);
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
      const freeMode = provider === "fallback" || provider === "none" || res.openai_available === false;
      const hfMode = provider === "huggingface" || provider === "hf";
      if (!reply) {
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "rico", text: "Rico returned an empty response. Please try again." },
        ]);
      } else {
        setMessages((prev) => [...prev, { id: nextId(), role: "rico", text: reply, freeMode: freeMode && !hfMode }]);
      }
    } catch (err) {
      if (err instanceof Error && err.message.includes("401")) {
        setSessionExpired(true);
        return;
      }
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "rico", text: "Something went wrong. Please try again." },
      ]);
    } finally {
      setThinking(false);
      scrollBottom();
      textareaRef.current?.focus();
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text) return;
    setInput("");
    await sendMessage(text);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (sessionExpired) {
    return (
      <DashboardShell title="Chat">
        <div className="flex max-w-lg flex-col items-center gap-4 rounded-2xl border border-white/5 bg-[#13132a]/80 p-8 text-center backdrop-blur-md">
          <p className="text-sm font-medium text-[#eeeef5]">Session expired.</p>
          <p className="text-sm text-[#5a5a7a]">Sign in again to continue chatting with Rico.</p>
          <Link
            href="/login"
            className="rounded-lg bg-[#5b4fff] px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#4a3fe0]"
          >
            Sign in
          </Link>
        </div>
      </DashboardShell>
    );
  }

  const isEmpty = messages.length === 0 && !thinking;

  return (
    <DashboardShell title="Rico Assistant">
      <div className="flex flex-col h-[calc(100vh-200px)] max-w-4xl mx-auto relative overflow-hidden">
        {/* Messages Container */}
        <div className="flex-1 overflow-y-auto px-2 py-4 space-y-6 pb-28 scrollbar-hide">
          {isEmpty && (
            <div className="flex flex-col items-center justify-center h-full text-center opacity-30 py-20 animate-in fade-in duration-500">
              <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4 border border-white/5 shadow-[0_4px_16px_rgba(91,79,255,0.1)]">
                <span className="text-2xl">🤖</span>
              </div>
              <h3 className="font-['Cabinet_Grotesk',sans-serif] font-bold text-lg text-white">Rico is ready</h3>
              <p className="text-sm max-w-xs mt-2 text-[#8080a0]">Ask about your profile, UAE job trends, or application status.</p>

              {/* Quick actions */}
              <div className="mt-8">
                <p className="mb-3 text-[11px] font-bold uppercase tracking-widest text-[#5a5a7a]">Quick start</p>
                <div className="flex flex-wrap justify-center gap-2">
                  {QUICK_ACTIONS.map((qa) => (
                    <button
                      key={qa.label}
                      onClick={() => sendMessage(qa.prompt)}
                      disabled={thinking}
                      className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2 text-xs text-[#8080a0] transition-colors hover:border-[rgba(91,79,255,0.3)] hover:bg-white/[0.05] hover:text-[#eeeef5] disabled:opacity-50"
                    >
                      {qa.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* How Rico works */}
              <div className="mt-6 max-w-sm rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3 text-left">
                <p className="mb-1.5 text-xs font-medium text-[#8080a0]">How Rico works</p>
                <ul className="flex flex-col gap-1 text-xs text-[#5a5a7a]">
                  <li>· Tell Rico your target role, cities, salary, and skills — it saves them to your profile.</li>
                  <li>· Once your profile is set, Rico searches jobs daily and scores them against your preferences.</li>
                  <li>· Profile setup happens through this chat. No forms needed to get started.</li>
                </ul>
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex items-end gap-2 animate-in fade-in slide-in-from-bottom-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {m.role === "rico" && (
                <div className="w-6 h-6 rounded-md bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-[10px] font-black text-white shrink-0 mb-1 shadow-[0_2px_8px_rgba(91,79,255,0.3)]">
                  R
                </div>
              )}
              <div
                className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-[15px] leading-relaxed shadow-sm ${m.role === "user"
                  ? "rounded-tr-none bg-[#5b4fff] text-white shadow-[0_4px_15px_rgba(91,79,255,0.2)]"
                  : "rounded-tl-none bg-[#13132a] border border-white/5 text-[#eeeef5] backdrop-blur-md"
                  }`}
              >
                {m.text}
                {m.freeMode && (
                  <p className="mt-1.5 text-[11px] text-[#5a5a7a]">
                    Free mode — AI fallback active
                  </p>
                )}
              </div>
              {m.role === "user" && (
                <div className="w-6 h-6 rounded-full bg-white/[0.08] flex items-center justify-center text-[10px] font-medium text-[#8080a0] shrink-0 mb-1">
                  You
                </div>
              )}
            </div>
          ))}

          {thinking && <ThinkingIndicator />}

          <div ref={bottomRef} />
        </div>

        {/* Input — Rico Floating Glass */}
        <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-[#06060f] via-[#06060f]/90 to-transparent">
          <div className="relative group">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={thinking}
              rows={1}
              placeholder="Ask Rico anything..."
              className="w-full resize-none bg-[#13132a]/80 border border-white/10 backdrop-blur-xl rounded-2xl py-4 pl-5 pr-14 text-sm text-white placeholder:text-[#5a5a7a] focus:outline-none focus:border-[#5b4fff]/50 transition-all shadow-2xl"
            />
            <button
              onClick={handleSend}
              disabled={thinking || !input.trim()}
              className="absolute right-2 top-2 bottom-2 w-10 h-10 rounded-xl bg-[#5b4fff] text-white flex items-center justify-center hover:bg-[#4a3fdf] transition-all disabled:opacity-30 disabled:grayscale"
              aria-label={thinking ? "Sending…" : "Send message"}
            >
              {thinking ? (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
                </svg>
              )}
            </button>
          </div>
          <p className="text-center text-[10px] text-[#5a5a7a] mt-2 uppercase tracking-widest font-bold opacity-50">
            Enter to send · Shift+Enter for new line
          </p>
        </div>
      </div>
    </DashboardShell>
  );
}
