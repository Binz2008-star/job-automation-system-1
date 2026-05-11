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
      const freeMode = res.response_source === "free_mode" || res.openai_available === false;
      if (!reply) {
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "rico", text: "Rico returned an empty response. Please try again." },
        ]);
      } else {
        setMessages((prev) => [...prev, { id: nextId(), role: "rico", text: reply, freeMode }]);
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

  const isEmpty = messages.length === 0 && !thinking;

  return (
    <DashboardShell title="Chat">
      <div className="flex max-w-2xl flex-col gap-3 h-[calc(100dvh-13rem)] md:h-[calc(100dvh-11rem)]">
        {/* Message area */}
        <div className="flex flex-1 flex-col overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">

          {/* Empty / onboarding state */}
          {isEmpty && (
            <div className="flex flex-1 flex-col justify-between gap-6">
              {/* Greeting */}
              <div className="flex flex-col items-center gap-3 pt-2 text-center">
                <div className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs text-indigo-400">
                  Rico AI
                </div>
                <p className="text-sm font-medium text-zinc-300">
                  Hello. I&apos;m Rico, your AI job-search assistant.
                </p>
                <p className="max-w-sm text-sm text-zinc-500">
                  Tell me your target role, preferred location, salary expectations, and key
                  skills. I&apos;ll build your search profile from our conversation.
                </p>
              </div>

              <div className="flex flex-col gap-4">
                {/* Quick action chips */}
                <div>
                  <p className="mb-2.5 text-center text-xs text-zinc-600">Quick start</p>
                  <div className="flex flex-wrap justify-center gap-2">
                    {QUICK_ACTIONS.map((qa) => (
                      <button
                        key={qa.label}
                        onClick={() => sendMessage(qa.prompt)}
                        disabled={thinking}
                        className="rounded-lg border border-zinc-700 bg-zinc-800/50 px-3 py-2 text-xs text-zinc-300 transition-colors hover:border-indigo-500/40 hover:bg-zinc-800 hover:text-white disabled:opacity-50"
                      >
                        {qa.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* How Rico works panel */}
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3">
                  <p className="mb-1.5 text-xs font-medium text-zinc-400">How Rico works</p>
                  <ul className="flex flex-col gap-1 text-xs text-zinc-500">
                    <li>· Tell Rico your target role, cities, salary range, and skills — it saves them to your profile.</li>
                    <li>· Once your profile is set, Rico searches jobs daily and scores them against your preferences.</li>
                    <li>· Profile setup happens through this chat. No forms or uploads needed to get started.</li>
                  </ul>
                  <p className="mt-2 text-xs text-zinc-600">
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
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${m.role === "user"
                    ? "rounded-br-sm bg-indigo-600 text-white"
                    : "rounded-bl-sm bg-zinc-800 text-zinc-200"
                    }`}
                >
                  {m.text}
                  {m.freeMode && (
                    <p className="mt-1.5 text-[11px] text-zinc-500">
                      Free mode — OpenAI unavailable
                    </p>
                  )}
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
