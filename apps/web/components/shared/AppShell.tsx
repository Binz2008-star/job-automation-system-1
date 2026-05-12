"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { logout } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
      </svg>
    ),
  },
  {
    href: "/jobs",
    label: "Jobs",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
      </svg>
    ),
  },
  {
    href: "/applications",
    label: "Applications",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
      </svg>
    ),
  },
  {
    href: "/chat",
    label: "Chat",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    href: "/profile",
    label: "Profile",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
      </svg>
    ),
  },
  {
    href: "/settings",
    label: "Settings",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    ),
  },
];

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export interface AppShellProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export function AppShell({ children, title, subtitle, actions }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <div className="flex min-h-screen bg-rico-bg relative overflow-hidden">
      {/* Ambient glow backgrounds */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute -top-[250px] -left-[150px] w-[700px] h-[700px] rounded-full bg-rico-accent-glow blur-[140px] opacity-25" />
        <div className="absolute bottom-0 -right-[100px] w-[500px] h-[500px] rounded-full bg-rico-teal/[0.04] blur-[140px]" />
        <div className="absolute top-[45%] left-[40%] w-[350px] h-[350px] rounded-full bg-rico-amber/[0.03] blur-[140px]" />
      </div>

      {/* Sidebar — desktop */}
      <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-rico-border bg-rico-surface/60 backdrop-blur-xl px-4 py-6 relative z-10">
        {/* Brand */}
        <div className="mb-8">
          <Link href="/" className="flex items-center gap-2.5 text-white tracking-tight">
            <div className="w-8 h-8 rounded-[9px] bg-gradient-to-br from-rico-accent to-[#8b5cf6] flex items-center justify-center text-sm font-black shadow-[0_4px_16px_rgba(91,79,255,0.3)]">
              R
            </div>
            <span className="font-display font-black text-lg">Rico AI</span>
          </Link>
          <p className="mt-1 text-[11px] text-rico-text-dim pl-[42px]">Autonomous job hunter</p>
        </div>

        {/* Nav */}
        <nav className="flex flex-1 flex-col gap-1">
          {NAV_ITEMS.map(({ href, label, icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "rounded-lg px-3 py-2 text-sm transition-all duration-200 flex items-center gap-2.5",
                  active
                    ? "bg-rico-accent-muted text-rico-purple border border-rico-accent-border font-medium"
                    : "text-rico-text-dim hover:bg-white/[0.04] hover:text-rico-text"
                )}
              >
                <span className="shrink-0 opacity-80">{icon}</span>
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Sign out */}
        <button
          onClick={handleLogout}
          className="mt-4 text-left rounded-lg px-3 py-2 text-sm text-rico-text-dim hover:text-rico-text transition-colors"
        >
          Sign out
        </button>
      </aside>

      {/* Main area */}
      <div className="flex min-w-0 flex-1 flex-col relative z-10">
        {/* Header — mobile */}
        <header className="flex items-center justify-between border-b border-rico-border bg-rico-surface/60 backdrop-blur-xl px-4 py-3 md:hidden">
          <Link href="/" className="shrink-0 flex items-center gap-2 text-sm font-bold text-white">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-rico-accent to-[#8b5cf6] flex items-center justify-center text-[10px] font-black">
              R
            </div>
            Rico AI
          </Link>

          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="p-2 text-rico-text-dim hover:text-rico-text transition-colors"
            aria-label="Toggle navigation"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {mobileOpen ? (
                <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>
              ) : (
                <><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></>
              )}
            </svg>
          </button>
        </header>

        {/* Mobile nav dropdown */}
        {mobileOpen && (
          <nav className="md:hidden border-b border-rico-border bg-rico-surface/90 backdrop-blur-xl px-4 py-3 flex flex-col gap-1 relative z-20">
            {NAV_ITEMS.map(({ href, label, icon }) => (
              <Link
                key={href}
                href={href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "rounded-lg px-3 py-2.5 text-sm transition-all flex items-center gap-2.5",
                  isActive(pathname, href)
                    ? "bg-rico-accent-muted text-rico-purple border border-rico-accent-border"
                    : "text-rico-text-dim hover:text-rico-text"
                )}
              >
                <span className="shrink-0">{icon}</span>
                {label}
              </Link>
            ))}
            <button
              onClick={handleLogout}
              className="mt-1 text-left rounded-lg px-3 py-2.5 text-sm text-rico-text-dim hover:text-rico-text transition-colors"
            >
              Sign out
            </button>
          </nav>
        )}

        {/* Page content */}
        <main className="flex-1 px-6 py-8 md:px-8 md:py-10">
          {(title || actions) && (
            <div className="mb-6 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <div>
                {title && (
                  <h1 className="font-display font-extrabold text-[22px] tracking-tight text-rico-text">
                    {title}
                  </h1>
                )}
                {subtitle && (
                  <p className="mt-0.5 text-sm text-rico-text-muted">{subtitle}</p>
                )}
              </div>
              {actions && <div className="mt-2 sm:mt-0 flex gap-2">{actions}</div>}
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
