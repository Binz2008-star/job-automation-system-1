import api from "@/lib/client";
import type { SettingsResponse, SettingsUpdateRequest } from "@/types";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

const MOCK_SETTINGS: SettingsResponse = {
  include_keywords: ["Environmental", "HSE", "ESG", "Sustainability"],
  exclude_keywords: ["Sales", "Marketing", "Retail"],
  min_score: 65,
  max_daily_applies: 5,
  telegram_chat_id: "",
  score_threshold_apply: 80,
  score_threshold_watch: 60,
};

// ── GET /api/v1/settings ─────────────────────────────────────────────────────
export async function getSettings(): Promise<SettingsResponse> {
  if (USE_MOCK) return MOCK_SETTINGS;
  const { data } = await api.get<SettingsResponse>("/api/settings");
  return data;
}

// ── PUT /api/v1/settings ─────────────────────────────────────────────────────
export async function updateSettings(
  payload: SettingsUpdateRequest
): Promise<SettingsResponse> {
  if (USE_MOCK) {
    return { ...MOCK_SETTINGS, ...payload };
  }
  const { data } = await api.put<SettingsResponse>("/api/settings", payload);
  return data;
}
