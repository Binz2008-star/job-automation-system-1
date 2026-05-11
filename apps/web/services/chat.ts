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
