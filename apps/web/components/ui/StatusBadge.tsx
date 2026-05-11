import { cn } from "@/lib/utils";
import type { ApplicationStatus } from "@/types";

const config: Record<
  ApplicationStatus,
  { label: string; className: string }
> = {
  applied: {
    label: "Applied",
    className:
      "text-indigo-300 bg-indigo-400/10 border-indigo-400/20",
  },
  interview_scheduled: {
    label: "Interview",
    className:
      "text-[#00c9a7] bg-[rgba(0,201,167,0.08)] border-[rgba(0,201,167,0.2)]",
  },
  offer_extended: {
    label: "Offer",
    className:
      "text-amber-300 bg-amber-400/10 border-amber-400/20",
  },
  rejected: {
    label: "Rejected",
    className:
      "text-[#ff5e5b] bg-[rgba(255,94,91,0.08)] border-[rgba(255,94,91,0.2)]",
  },
  saved: {
    label: "Saved",
    className: "text-white/50 bg-white/4 border-white/10",
  },
};

export function StatusBadge({ status }: { status: ApplicationStatus }) {
  const { label, className } = config[status] ?? config.applied;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border",
        className
      )}
    >
      {label}
    </span>
  );
}
