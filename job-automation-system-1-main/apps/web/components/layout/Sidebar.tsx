"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";

const navItems = [
  {
    label: "Dashboard",
    href: "/dashboard",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
        <rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
      </svg>
    ),
  },
  {
    label: "Jobs",
    href: "/jobs",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
  {
    label: "Chat",
    href: "/chat",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    label: "Applications",
    href: "/applications",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" /><line x1="9" y1="13" x2="15" y2="13" /><line x1="9" y1="17" x2="15" y2="17" />
      </svg>
    ),
  },
  {
    label: "Profile",
    href: "/profile",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
      </svg>
    ),
  },
  {
    label: "Settings",
    href: "/settings",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14" />
      </svg>
    ),
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const initials = user?.name
    ? user.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
    : "R";

  return (
    <aside className="w-[220px] flex-shrink-0 bg-[#0a0a1a] border-r border-white/5 flex flex-col h-full overflow-y-auto">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-white/5 flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-[8px] bg-gradient-to-br from-[#5b4fff] to-[#8b5cf6] flex items-center justify-center text-white font-['Cabinet_Grotesk',sans-serif] font-black text-[12px] shadow-[0_4px_12px_rgba(91,79,255,0.3)]">
          R
        </div>
        <span className="font-['Cabinet_Grotesk',sans-serif] font-800 text-[17px] tracking-tight text-white">
          Rico AI
        </span>
      </div>

      {/* Live status */}
      <div className="px-5 py-3 flex items-center gap-2 border-b border-white/5">
        <span className="w-1.5 h-1.5 rounded-full bg-[#00c9a7] shadow-[0_0_6px_#00c9a7] animate-pulse" />
        <span className="text-[11px] text-[#00c9a7] font-medium">System live · UAE</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 flex flex-col gap-0.5">
        <p className="px-3 pb-2 pt-2 text-[10px] uppercase tracking-widest text-white/25 font-semibold">
          Navigation
        </p>
        {navItems.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 px-3 py-2 rounded-[9px] text-[13px] font-medium transition-all duration-150",
                active
                  ? "bg-[rgba(91,79,255,0.12)] text-[#a78bfa] border border-[rgba(91,79,255,0.2)]"
                  : "text-white/45 hover:text-white/80 hover:bg-white/5"
              )}
            >
              <span className={cn("flex-shrink-0", active ? "opacity-100" : "opacity-60")}>
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* User footer */}
      <div className="px-3 py-4 border-t border-white/5">
        <button
          onClick={logout}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-[9px] hover:bg-white/5 transition-colors group"
        >
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-[#5b4fff] to-[#00c9a7] flex items-center justify-center text-white font-['Cabinet_Grotesk',sans-serif] font-black text-[10px] flex-shrink-0">
            {initials}
          </div>
          <div className="flex-1 min-w-0 text-left">
            <p className="text-[12px] font-medium text-white/70 truncate group-hover:text-white/90">
              {user?.name ?? "User"}
            </p>
            <p className="text-[10px] text-white/30 truncate">{user?.email ?? ""}</p>
          </div>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="opacity-30 flex-shrink-0">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
      </div>
    </aside>
  );
}
