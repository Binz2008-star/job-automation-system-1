"use client";

import { logout } from "@/lib/api";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const NAV = [
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

export function DashboardShell({
  children,
  title,
}: {
  children: React.ReactNode;
  title?: string;
}) {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <div className="flex min-h-screen bg-[#06060f] relative overflow-hidden">
      {/* Ambient glow backgrounds */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute -top-[250px] -left-[150px] w-[700px] h-[700px] rounded-full bg-[rgba(91,79,255,0.06)] blur-[140px]" />
        <div className="absolute bottom-0 -right-[100px] w-[500px] h-[500px] rounded-full bg-[rgba(0,201,167,0.04)] blur-[140px]" />
        <div className="absolute top-[45%] left-[40%] w-[350px] h-[350px] rounded-full bg-[rgba(245,166,35,0.03)] blur-[140px]" />
        {/* Noise texture overlay */}
        <div
          className="absolute inset-0 opacity-[0.015]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E")`,
          }}
        />
      </div>

      {/* Sidebar — desktop */}
      <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-[rgba(255,255,255,0.06)] bg-[#0d0d1f]/60 backdrop-blur-xl px-4 py-6 relative z-10">
        <div className="mb-8">
          <Link href="/" className="flex items-center gap-2.5 text-white tracking-tight">
            <div className="w-8 h-8 rounded-[9px] bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-sm font-black shadow-[0_4px_16px_rgba(91,79,255,0.3)]">
              R
            </div>
            <span className="font-['Cabinet_Grotesk',sans-serif] font-black text-lg">Rico AI</span>
          </Link>
          <p className="mt-1 text-[11px] text-[#5a5a7a] pl-[42px]">Autonomous job hunter</p>
        </div>

        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map(({ href, label, icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                className={`rounded-lg px-3 py-2 text-sm transition-all duration-200 flex items-center gap-2.5 ${active
                  ? "bg-[rgba(91,79,255,0.12)] text-[#a78bfa] border border-[rgba(91,79,255,0.18)] font-medium"
                  : "text-[#5a5a7a] hover:bg-[rgba(255,255,255,0.04)] hover:text-[#eeeef5]"
                  }`}
              >
                <span className="shrink-0 opacity-80">{icon}</span>
                {label}
              </Link>
            );
          })}
        </nav>

        <button
          onClick={handleLogout}
          className="mt-4 text-left rounded-lg px-3 py-2 text-sm text-[#5a5a7a] hover:text-[#eeeef5] transition-colors"
        >
          Sign out
        </button>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col relative z-10">
        {/* Header — mobile */}
        <header className="flex items-center justify-between border-b border-[rgba(255,255,255,0.06)] bg-[#0d0d1f]/60 backdrop-blur-xl px-4 py-3 md:hidden">
          <Link href="/" className="shrink-0 flex items-center gap-2 text-sm font-bold text-white">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-[10px] font-black">
              R
            </div>
            Rico AI
          </Link>
          <nav className="flex gap-1 overflow-x-auto pl-3">
            {NAV.map(({ href, label, icon }) => (
              <Link
                key={href}
                href={href}
                className={`shrink-0 rounded-md px-2.5 py-2 text-xs transition-all flex items-center gap-1.5 ${isActive(pathname, href) ? "bg-[rgba(91,79,255,0.12)] text-[#a78bfa] border border-[rgba(91,79,255,0.18)]" : "text-[#5a5a7a] hover:text-[#eeeef5]"
                  }`}
              >
                <span className="shrink-0">{icon}</span>
                {label}
              </Link>
            ))}
          </nav>
        </header>

        <main className="flex-1 px-6 py-8 md:px-8 md:py-10">
          {title && (
            <h1 className="mb-6 font-['Cabinet_Grotesk',sans-serif] font-800 text-[22px] tracking-tight text-[#eeeef5]">
              {title}
            </h1>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
