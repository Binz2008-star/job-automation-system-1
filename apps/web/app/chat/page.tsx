"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { DashboardShell } from "@/components/DashboardShell";
import { sendChat } from "@/lib/api";

interface Message {
  id: number;
  role: "user" | "rico";
  text: string;
}

let _id = 0;
function nextId() { return ++_id; }

function ThinkingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="rounded-2xl rounded-bl-sm bg-zinc-800 px-4 py-3">
        <div className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages,       setMessages]       = useState<Message[]>([]);
  const [input,          setInput]          = useState("");
  const [thinking,       setThinking]       = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function scrollBottom() {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || thinking) return;

    setInput("");
    setMessages((prev) => [...prev, { id: nextId(), role: "user", text }]);
    setThinking(true);
    scrollBottom();

    try {
      const res = await sendChat(text);
      const reply = res.reply ?? res.message ?? "—";
      setMessages((prev) => [...prev, { id: nextId(), role: "rico", text: reply }]);
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

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (sessionExpired) {
    return (
      <DashboardShell title="Chat">
        <div className="flex max-w-lg flex-col items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900/60 p-8 text-center">
          <p className="text-sm font-medium text-zinc-300">Session expired.</p>
          <p className="text-sm text-zinc-500">Sign in again to continue chatting with Rico.</p>
          <Link
            href="/login"
            className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500"
          >
            Sign in
          </Link>
        </div>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell title="Chat">
      <div className="flex max-w-2xl flex-col gap-3 h-[calc(100dvh-13rem)] md:h-[calc(100dvh-11rem)]">
        {/* Message area */}
        <div className="flex flex-1 flex-col overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
          {/* Empty state */}
          {messages.length === 0 && !thinking && (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
              <div className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs text-indigo-400">
                Rico AI
              </div>
              <p className="text-sm font-medium text-zinc-300">
                Hello. I&apos;m Rico, your AI job-search assistant.
              </p>
              <p className="max-w-xs text-sm text-zinc-500">
                Tell me what kind of role you&apos;re looking for and I&apos;ll help you
                build a profile, find matching jobs, and track applications.
              </p>
            </div>
          )}

          {/* Messages */}
          <div className="flex flex-col gap-3">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "rounded-br-sm bg-indigo-600 text-white"
                      : "rounded-bl-sm bg-zinc-800 text-zinc-200"
                  }`}
                >
                  {m.text}
                </div>
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
            className="flex-1 resize-none rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-3 text-sm text-white placeholder-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={thinking || !input.trim()}
            className="shrink-0 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {thinking ? "…" : "Send"}
          </button>
        </div>

        <p className="text-center text-xs text-zinc-600">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </DashboardShell>
  );
}
