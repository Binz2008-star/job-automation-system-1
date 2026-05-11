/**
 * lib/client.ts
 * Axios-compatible fetch wrapper for generated services.
 * Uses /proxy so session cookies are first-party (same-origin).
 */

const PROXY = "/proxy";

// Remap generated service paths to actual backend paths.
const PATH_MAP: Record<string, string> = {
  "/api/applications": "/api/v1/applications",
  "/api/applications/update": "/api/v1/applications",
  "/api/jobs/recommended": "/api/v1/jobs/recommended",
  "/api/jobs/action": "/api/v1/actions/run",
  "/api/chat": "/api/v1/rico/chat",
  "/api/profile": "/api/v1/rico/profile",
  "/api/upload-cv": "/api/v1/rico/profile/cv",
};

function resolve(path: string): string {
  return PATH_MAP[path] ?? path;
}

function buildUrl(path: string, params?: Record<string, unknown>): string {
  const mapped = resolve(path);
  const url = `${PROXY}${mapped}`;
  if (!params) return url;
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v != null) qs.append(k, String(v));
  });
  return `${url}?${qs.toString()}`;
}

const client = {
  async get<T>(path: string, config?: { params?: Record<string, unknown> }) {
    const res = await fetch(buildUrl(path, config?.params), {
      credentials: "include",
    });
    if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
    return { data: (await res.json()) as T };
  },

  async post<T>(path: string, data?: unknown) {
    const isForm = data instanceof FormData;
    const res = await fetch(buildUrl(path), {
      method: "POST",
      headers: isForm ? undefined : { "Content-Type": "application/json" },
      credentials: "include",
      body: isForm ? data : JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
    return { data: (await res.json()) as T };
  },

  async patch<T>(path: string, data?: unknown) {
    const res = await fetch(buildUrl(path), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`PATCH ${path} failed: ${res.status}`);
    return { data: (await res.json()) as T };
  },
};

export default client;
