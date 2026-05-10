"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/api";

const NAV = [
  { href: "/dashboard",      label: "Dashboard" },
  { href: "/chat",           label: "Chat" },
  { href: "/profile",        label: "Profile" },
  { href: "/saved-searches", label: "Saved Searches" },
];

export function DashboardShell({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  const pathname = usePathname();
  const router   = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <div className="flex min-h-screen bg-zinc-950">
      {/* Sidebar — desktop */}
      <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-zinc-800 bg-zinc-900/40 px-4 py-6">
        <div className="mb-8">
          <Link href="/" className="text-lg font-bold text-white tracking-tight">
            Rico AI
          </Link>
          <p className="mt-0.5 text-xs text-zinc-500">Autonomous job hunter</p>
        </div>

        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map(({ href, label }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`rounded-lg px-3 py-2 text-sm transition-colors ${
                  active
                    ? "bg-zinc-800 text-white font-medium"
                    : "text-zinc-400 hover:bg-zinc-800/60 hover:text-white"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>

        <button
          onClick={handleLogout}
          className="mt-4 text-left rounded-lg px-3 py-2 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Sign out
        </button>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header — mobile */}
        <header className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900/40 px-4 py-3 md:hidden">
          <Link href="/" className="shrink-0 text-sm font-bold text-white">
            Rico AI
          </Link>
          <nav className="flex gap-1 overflow-x-auto pl-3">
            {NAV.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={`shrink-0 rounded-md px-2.5 py-2 text-xs transition-colors ${
                  pathname === href ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"
                }`}
              >
                {label}
              </Link>
            ))}
          </nav>
        </header>

        <main className="flex-1 px-6 py-8 md:px-8 md:py-10">
          <h1 className="mb-6 text-xl font-semibold text-white">{title}</h1>
          {children}
        </main>
      </div>
    </div>
  );
}
