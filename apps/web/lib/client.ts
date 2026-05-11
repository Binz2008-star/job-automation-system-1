/**
 * lib/client.ts
 * Axios-compatible fetch wrapper for generated services.
 * Uses /proxy so session cookies are first-party (same-origin).
 */

export class ApiError extends Error {
  statusCode: number;
  constructor(message: string, statusCode: number) {
    super(message);
    this.statusCode = statusCode;
    this.name = "ApiError";
  }
}

const PROXY = "/proxy";

// Remap generated service paths to actual backend paths.
const PATH_MAP: Record<string, string> = {
  "/api/applications": "/api/v1/applications",
  "/api/jobs": "/api/v1/jobs",
  "/api/chat": "/api/v1/rico/chat",
  "/api/profile": "/api/v1/rico/profile",
  "/api/upload-cv": "/api/v1/rico/profile/cv",
  "/api/settings": "/api/v1/settings",
};

function resolve(path: string): string {
  // Exact match first (handles no-subpath routes like /api/settings)
  if (PATH_MAP[path]) return PATH_MAP[path];
  // Prefix match: find the longest registered prefix that matches
  const sorted = Object.keys(PATH_MAP).sort((a, b) => b.length - a.length);
  for (const prefix of sorted) {
    if (path === prefix || path.startsWith(`${prefix}/`)) {
      return PATH_MAP[prefix] + path.slice(prefix.length);
    }
  }
  return path;
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

function handleError(path: string, res: Response): never {
  throw new ApiError(`${res.status} ${path}`, res.status);
}

const client = {
  async get<T>(path: string, config?: { params?: Record<string, unknown> }) {
    const res = await fetch(buildUrl(path, config?.params), {
      credentials: "include",
    });
    if (!res.ok) handleError(path, res);
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
    if (!res.ok) handleError(path, res);
    return { data: (await res.json()) as T };
  },

  async patch<T>(path: string, data?: unknown) {
    const res = await fetch(buildUrl(path), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) handleError(path, res);
    return { data: (await res.json()) as T };
  },

  async put<T>(path: string, data?: unknown) {
    const res = await fetch(buildUrl(path), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) handleError(path, res);
    return { data: (await res.json()) as T };
  },
};

export default client;
