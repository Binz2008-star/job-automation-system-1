"use client";

import { login } from "@/lib/api";
import { buildAuthHref, resolveNextPath } from "@/lib/redirect";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [requestedNext, setRequestedNext] = useState("");
  const nextPath = requestedNext || "/dashboard";

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setRequestedNext(resolveNextPath(params.get("next"), ""));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const publicUserId = typeof window !== "undefined" ? localStorage.getItem("rico_public_uid") : null;
      await login(email, password, publicUserId);
      // Clear stored public ID after successful auth merge
      if (typeof window !== "undefined") {
        localStorage.removeItem("rico_public_uid");
      }
      router.push(nextPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#06060f] px-4 relative overflow-hidden">
      {/* Ambient glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute -top-[200px] -left-[100px] w-[600px] h-[600px] rounded-full bg-[rgba(91,79,255,0.06)] blur-[140px]" />
        <div className="absolute bottom-0 -right-[100px] w-[400px] h-[400px] rounded-full bg-[rgba(0,201,167,0.04)] blur-[140px]" />
      </div>

      <div className="w-full max-w-sm relative z-10">
        {/* Brand */}
        <div className="mb-8 text-center">
          <Link href="/" className="inline-flex items-center gap-2.5 justify-center">
            <div className="w-9 h-9 rounded-[10px] bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-sm font-black text-white shadow-[0_4px_16px_rgba(91,79,255,0.3)]">
              R
            </div>
            <span className="font-['Cabinet_Grotesk',sans-serif] font-black text-xl text-white tracking-tight">Rico AI</span>
          </Link>
          <p className="mt-3 text-sm text-[#5a5a7a]">Sign in to your autonomous job agent</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#13132a]/80 p-6 backdrop-blur-xl"
        >
          {/* Email */}
          <div>
            <label htmlFor="email" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[#5a5a7a]">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="you@example.com"
              className="w-full rounded-lg border border-[rgba(255,255,255,0.08)] bg-[#0d0d1f] px-3 py-2.5 text-sm text-[#eeeef5] placeholder-[#5a5a7a] focus:border-[rgba(91,79,255,0.5)] focus:outline-none focus:ring-1 focus:ring-[rgba(91,79,255,0.3)] transition-colors"
            />
          </div>

          {/* Password + forgot link */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label htmlFor="password" className="text-xs font-semibold uppercase tracking-wider text-[#5a5a7a]">
                Password
              </label>
              <Link
                href="/forgot-password"
                className="text-xs text-[#a78bfa] hover:text-[#c4b5fd] transition-colors"
              >
                Forgot password?
              </Link>
            </div>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
              className="w-full rounded-lg border border-[rgba(255,255,255,0.08)] bg-[#0d0d1f] px-3 py-2.5 text-sm text-[#eeeef5] placeholder-[#5a5a7a] focus:border-[rgba(91,79,255,0.5)] focus:outline-none focus:ring-1 focus:ring-[rgba(91,79,255,0.3)] transition-colors"
            />
          </div>

          {/* Error */}
          {error && (
            <p className="rounded-lg border border-[rgba(255,94,91,0.3)] bg-[rgba(255,94,91,0.08)] px-3 py-2 text-sm text-[#ff5e5b]">
              {error}
            </p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-[#5b4fff] py-3 text-sm font-semibold text-white transition-colors hover:bg-[#4a3fdf] disabled:cursor-not-allowed disabled:opacity-50 shadow-[0_4px_15px_rgba(91,79,255,0.2)]"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-[#5a5a7a]">
          No account yet?{" "}
          <Link
            href={buildAuthHref("/signup", requestedNext)}
            className="text-[#a78bfa] hover:text-[#c4b5fd] transition-colors"
          >
            Create one free →
          </Link>
        </p>
      </div>
    </main>
  );
}
