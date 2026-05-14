import { cn } from "@/lib/utils";

export interface LoadingStateProps {
  message?: string;
  variant?: "page" | "card" | "inline";
  className?: string;
}

function Spinner({ size = 20 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className="animate-spin text-rico-accent"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeOpacity="0.2" />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SkeletonBar({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "h-3 rounded-md bg-white/[0.06] animate-pulse",
        className
      )}
    />
  );
}

export function LoadingState({
  message = "Loading…",
  variant = "page",
  className,
}: LoadingStateProps) {
  if (variant === "inline") {
    return (
      <div className={cn("flex items-center gap-2 text-sm text-rico-text-muted", className)}>
        <Spinner size={14} />
        <span>{message}</span>
      </div>
    );
  }

  if (variant === "card") {
    return (
      <div
        className={cn(
          "rounded-2xl border border-rico-border bg-rico-surface-2/80 p-5 flex flex-col gap-3",
          className
        )}
      >
        <div className="flex items-center gap-2">
          <Spinner size={16} />
          <span className="text-sm text-rico-text-muted">{message}</span>
        </div>
        <div className="flex flex-col gap-2">
          <SkeletonBar className="w-3/4" />
          <SkeletonBar className="w-1/2" />
          <SkeletonBar className="w-2/3" />
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-4 py-20 text-center",
        className
      )}
    >
      <Spinner size={28} />
      <p className="text-sm text-rico-text-muted">{message}</p>
    </div>
  );
}

export { Spinner, SkeletonBar };
