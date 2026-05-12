import Link from "next/link";
import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  className?: string;
}

const DEFAULT_ICON = (
  <svg
    width="40"
    height="40"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="text-rico-text-dim"
  >
    <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
    <polyline points="13 2 13 9 20 9" />
  </svg>
);

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  actionHref,
  onAction,
  className,
}: EmptyStateProps) {
  const renderedIcon = icon ?? DEFAULT_ICON;

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-rico-border bg-rico-surface-2/40 px-6 py-14 text-center",
        className
      )}
    >
      <div className="mb-1 opacity-60">{renderedIcon}</div>
      <h3 className="text-sm font-semibold text-rico-text">{title}</h3>
      {description && (
        <p className="max-w-sm text-sm text-rico-text-muted">{description}</p>
      )}
      {actionLabel && actionHref && (
        <Link
          href={actionHref}
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-rico-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-rico-accent-hover"
        >
          {actionLabel}
        </Link>
      )}
      {actionLabel && onAction && !actionHref && (
        <button
          onClick={onAction}
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-rico-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-rico-accent-hover"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
