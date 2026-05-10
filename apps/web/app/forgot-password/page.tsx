"use client";

import { useState } from "react";
import Link from "next/link";
import { forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email,     setEmail]     = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading,   setLoading]   = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await forgotPassword(email.trim());
    } catch {
      // Always show generic success — never reveal whether an email exists
    } finally {
      setLoading(false);
      setSubmitted(true);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="mb-8 text-center">
          <Link href="/" className="text-lg font-bold text-white tracking-tight">
            Rico AI
          </Link>
          <p className="mt-1 text-sm text-zinc-400">Reset your password</p>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-6">
          {submitted ? (
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs text-indigo-400">
                Email sent
              </div>
              <p className="text-sm text-zinc-300">
                If that address is registered, a reset link is on its way.
              </p>
              <p className="text-xs text-zinc-500">
                Can&apos;t find it? Check your spam folder.
              </p>
              <Link
                href="/login"
                className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 transition-colors underline underline-offset-2"
              >
                Back to sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="email" className="mb-1.5 block text-sm text-zinc-400">
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="you@example.com"
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <button
                type="submit"
                disabled={loading || !email.trim()}
                className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? "Sending…" : "Send reset link"}
              </button>

              <p className="text-center text-xs text-zinc-500">
                <Link
                  href="/login"
                  className="text-zinc-400 hover:text-white transition-colors"
                >
                  ← Back to sign in
                </Link>
              </p>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
