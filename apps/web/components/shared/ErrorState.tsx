import Link from "next/link";
import { cn } from "@/lib/utils";

export type ErrorVariant = "generic" | "auth" | "network" | "not_found";

export interface ErrorStateProps {
  variant?: ErrorVariant;
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

const VARIANT_DEFAULTS: Record<ErrorVariant, { title: string; message: string; icon: React.ReactNode }> = {
  generic: {
    title: "Something went wrong",
    message: "An unexpected error occurred. Please try again.",
    icon: (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-rico-red">
        <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    ),
  },
  auth: {
    title: "Authentication required",
    message: "Your session may have expired. Please sign in again.",
    icon: (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-rico-amber">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
      </svg>
    ),
  },
  network: {
    title: "Connection failed",
    message: "Could not reach the server. Check your connection and try again.",
    icon: (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-rico-amber">
        <line x1="1" y1="1" x2="23" y2="23" /><path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55" /><path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39" /><path d="M10.71 5.05A16 16 0 0 1 22.56 9" /><path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88" /><path d="M8.53 16.11a6 6 0 0 1 6.95 0" /><line x1="12" y1="20" x2="12.01" y2="20" />
      </svg>
    ),
  },
  not_found: {
    title: "Not found",
    message: "The resource you're looking for doesn't exist or has been removed.",
    icon: (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-rico-text-dim">
        <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /><line x1="8" y1="11" x2="14" y2="11" />
      </svg>
    ),
  },
};

export function ErrorState({
  variant = "generic",
  title,
  message,
  onRetry,
  className,
}: ErrorStateProps) {
  const defaults = VARIANT_DEFAULTS[variant];

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-2xl border border-rico-red/20 bg-rico-red/[0.04] px-6 py-14 text-center",
        variant === "auth" && "border-rico-amber/20 bg-rico-amber/[0.04]",
        variant === "network" && "border-rico-amber/20 bg-rico-amber/[0.04]",
        variant === "not_found" && "border-rico-border bg-rico-surface-2/40",
        className
      )}
    >
      <div className="mb-1">{defaults.icon}</div>
      <h3 className="text-sm font-semibold text-rico-text">{title ?? defaults.title}</h3>
      <p className="max-w-sm text-sm text-rico-text-muted">{message ?? defaults.message}</p>

      <div className="mt-2 flex gap-2">
        {onRetry && (
          <button
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-lg bg-rico-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-rico-accent-hover"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            Try again
          </button>
        )}
        {variant === "auth" && (
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 rounded-lg border border-rico-border px-4 py-2 text-sm font-medium text-rico-text transition-colors hover:bg-white/[0.04]"
          >
            Sign in
          </Link>
        )}
      </div>
    </div>
  );
}
