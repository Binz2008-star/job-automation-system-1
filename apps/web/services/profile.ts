import api from "@/lib/client";
import type {
  CVUploadResponse,
  ProfileUpdateRequest,
  UserProfile,
} from "@/types";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

const MOCK_PROFILE: UserProfile = {
  user_id: "dev_user",
  name: "Dev User",
  email: "dev@rico.ai",
  telegram_username: "@devrico",
  dream_role: "Environmental Manager",
  preferred_city: "Dubai",
  cv_uploaded: false,
  created_at: new Date().toISOString(),
};

// ── GET /api/profile?user_id= ─────────────────────────────────────────────────
export async function getProfile(userId: string): Promise<UserProfile> {
  if (USE_MOCK) return MOCK_PROFILE;
  const { data } = await api.get<UserProfile>("/api/profile", {
    params: { user_id: userId },
  });
  return data;
}

// ── POST /api/profile ─────────────────────────────────────────────────────────
export async function updateProfile(
  payload: ProfileUpdateRequest
): Promise<UserProfile> {
  if (USE_MOCK) return { ...MOCK_PROFILE, ...payload };
  const { data } = await api.post<UserProfile>("/api/profile", payload);
  return data;
}

// ── POST /api/upload-cv (multipart/form-data) ─────────────────────────────────
export async function uploadCV(
  userId: string,
  file: File
): Promise<CVUploadResponse> {
  if (USE_MOCK) {
    return {
      success: true,
      message: "[MOCK] CV received — backend not connected.",
      skills_extracted: ["ISO 14001", "HSE", "ESG"],
      experience_years: 10,
    };
  }
  const form = new FormData();
  form.append("file", file);
  form.append("user_id", userId);
  const { data } = await api.post<CVUploadResponse>("/api/upload-cv", form);
  return data;
}
