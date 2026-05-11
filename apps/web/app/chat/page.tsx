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
    <div className="flex justify-start">
      <div className="rounded-2xl rounded-bl-sm bg-[#13132a] border border-[rgba(255,255,255,0.06)] px-4 py-3">
        <div className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-[#5a5a7a] animate-bounce"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
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
        <div className="flex max-w-lg flex-col items-center gap-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#13132a]/80 p-8 text-center">
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
    <DashboardShell title="Chat">
      <div className="flex max-w-2xl flex-col gap-3 h-[calc(100dvh-13rem)] md:h-[calc(100dvh-11rem)]">
        {/* Message area */}
        <div className="flex flex-1 flex-col overflow-y-auto rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0d1f]/40 p-4">

          {/* Empty / onboarding state */}
          {isEmpty && (
            <div className="flex flex-1 flex-col justify-between gap-6">
              {/* Greeting */}
              <div className="flex flex-col items-center gap-4 pt-4 text-center">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-xl font-black text-white shadow-[0_4px_16px_rgba(91,79,255,0.3)]">
                  R
                </div>
                <div>
                  <p className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[18px] text-[#eeeef5]">
                    Hello. I&apos;m Rico.
                  </p>
                  <p className="max-w-sm text-[13px] text-[#5a5a7a] mt-1.5 leading-relaxed">
                    Your AI job-search assistant for the UAE. Tell me your target role, preferred location, salary expectations, and key skills — I&apos;ll build your profile from our conversation.
                  </p>
                </div>
              </div>

              <div className="flex flex-col gap-4">
                {/* Quick action chips */}
                <div>
                  <p className="mb-2.5 text-center text-xs text-[#5a5a7a]">Quick start</p>
                  <div className="flex flex-wrap justify-center gap-2">
                    {QUICK_ACTIONS.map((qa) => (
                      <button
                        key={qa.label}
                        onClick={() => sendMessage(qa.prompt)}
                        disabled={thinking}
                        className="rounded-lg border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] px-3 py-2 text-xs text-[#8080a0] transition-colors hover:border-[rgba(91,79,255,0.3)] hover:bg-[rgba(255,255,255,0.05)] hover:text-[#eeeef5] disabled:opacity-50"
                      >
                        {qa.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* How Rico works panel */}
                <div className="rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] px-4 py-3">
                  <p className="mb-1.5 text-xs font-medium text-[#8080a0]">How Rico works</p>
                  <ul className="flex flex-col gap-1 text-xs text-[#5a5a7a]">
                    <li>· Tell Rico your target role, cities, salary range, and skills — it saves them to your profile.</li>
                    <li>· Once your profile is set, Rico searches jobs daily and scores them against your preferences.</li>
                    <li>· Profile setup happens through this chat. No forms or uploads needed to get started.</li>
                  </ul>
                  <p className="mt-2 text-xs text-[#5a5a7a]">
                    CV upload will be added when the upload endpoint is connected.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Messages */}
          <div className="flex flex-col gap-3">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex items-end gap-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {m.role === "rico" && (
                  <div className="w-6 h-6 rounded-md bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-[10px] font-black text-white shrink-0 mb-1">
                    R
                  </div>
                )}
                <div
                  className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${m.role === "user"
                    ? "rounded-br-sm bg-[#5b4fff] text-white"
                    : "rounded-bl-sm bg-[#13132a] border border-[rgba(255,255,255,0.06)] text-[#eeeef5]"
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
                  <div className="w-6 h-6 rounded-full bg-[rgba(255,255,255,0.08)] flex items-center justify-center text-[10px] font-medium text-[#8080a0] shrink-0 mb-1">
                    You
                  </div>
                )}
              </div>
            ))}

            {thinking && <ThinkingIndicator />}

            <div ref={bottomRef} />
          </div>
        </div>

        {/* Input */}
        <div className="flex gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={thinking}
            rows={1}
            placeholder="Message Rico…"
            className="flex-1 resize-none rounded-xl border border-[rgba(255,255,255,0.08)] bg-[#0d0d1f] px-4 py-3 text-sm text-[#eeeef5] placeholder-[#5a5a7a] focus:border-[rgba(91,79,255,0.4)] focus:outline-none focus:ring-1 focus:ring-[rgba(91,79,255,0.2)] disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={thinking || !input.trim()}
            className="shrink-0 rounded-xl bg-[#5b4fff] px-4 py-3 text-white transition-colors hover:bg-[#4a3fe0] disabled:cursor-not-allowed disabled:opacity-40 flex items-center justify-center"
            aria-label={thinking ? "Sending…" : "Send message"}
          >
            {thinking ? (
              <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2L11 13" />
                <path d="M22 2l-7 20-4-9-9-4 20-7z" />
              </svg>
            )}
          </button>
        </div>

        <p className="text-center text-xs text-[#5a5a7a]">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </DashboardShell>
  );
}
