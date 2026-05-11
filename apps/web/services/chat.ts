/* eslint-disable @typescript-eslint/no-unused-vars */
// DO NOT IMPORT FROM THIS MODULE. Scheduled for deletion in PR #86.

/**
 * @deprecated LEGACY — not imported anywhere.
 * The active chat implementation is sendChat() in lib/api.ts, called directly
 * by app/chat/page.tsx. This file targets /api/chat which does not exist.
 * Remove in PR #86 (architecture cleanup).
 */

import api from "@/lib/client";
import type { ChatRequest, ChatResponse } from "@/types";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

// ── POST /api/chat ────────────────────────────────────────────────────────────
export async function sendMessage(payload: ChatRequest): Promise<ChatResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 800)); // simulate latency
    return {
      reply: `[MOCK] Rico received: "${payload.message}". Backend not connected.`,
      jobs: [],
      actions: [],
    };
  }
  const { data } = await api.post<ChatResponse>("/api/chat", payload);
  return data;
}
