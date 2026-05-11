"use client";

import { Button } from "@/components/ui/Button";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { cn } from "@/lib/utils";
import type { Job } from "@/types";
import { useMemo, useState } from "react";

interface JobCardProps {
  job: Job;
  onAction?: (jobId: string, action: string) => Promise<void>;
  isSubmitting?: boolean;
  className?: string;
}

const LOGO_COLORS = [
  "from-blue-500/20 to-blue-400/10 text-blue-300",
  "from-emerald-500/20 to-emerald-400/10 text-emerald-300",
  "from-amber-500/20 to-amber-400/10 text-amber-300",
  "from-purple-500/20 to-purple-400/10 text-purple-300",
  "from-rose-500/20 to-rose-400/10 text-rose-300",
];

export function JobCard({ job, onAction, isSubmitting, className }: JobCardProps) {
  const [localAction, setLocalAction] = useState<string | null>(null);
  const [isDone, setIsDone] = useState(false);

  const config = useMemo(() => {
    const name = job.company ?? "Unknown";
    const init = name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return { initials: init, colorClass: LOGO_COLORS[Math.abs(hash) % LOGO_COLORS.length] };
  }, [job.company]);

  const handleActionClick = async (action: string) => {
    if (!onAction || localAction || isSubmitting) return;
    setLocalAction(action);
    try {
      await onAction(job.job_id, action);
      setIsDone(true);
    } finally {
      setLocalAction(null);
    }
  };

  const title = job.title ?? "Untitled role";
  const company = job.company ?? "Unknown company";
  const location = job.location ?? "Remote / unspecified";
  const reason = job.reason ?? "";
  const salary = job.salary_range ?? job.salary ?? "";
  const tags = Array.isArray(job.tags) ? job.tags : [];

  return (
    <div
      className={cn(
        "group bg-[#0e0e20] border border-white/6 rounded-2xl p-5",
        "hover:border-[rgba(91,79,255,0.3)] hover:bg-[#14142a] transition-all duration-200",
        isDone && "opacity-60 grayscale-[0.5]",
        className
      )}
    >
      {/* top row */}
      <div className="flex gap-3 items-start">
        <div
          className={cn(
            "w-10 h-10 rounded-xl flex-shrink-0 flex items-center justify-center",
            "bg-gradient-to-br font-['Cabinet_Grotesk',sans-serif] font-black text-xs",
            config.colorClass
          )}
        >
          {config.initials}
        </div>

        <div className="flex-1 min-w-0">
          <p className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[15px] leading-snug tracking-tight truncate text-[#eeeef5]">
            {title}
          </p>
          <p className="text-[13px] text-[#8080a0] mt-0.5">
            {company} · {location}
          </p>
        </div>

        <ScoreBadge score={job.score} />
      </div>

      {/* reason */}
      {reason && (
        <p className="mt-3 text-[12px] text-[#5a5a7a] leading-relaxed bg-[rgba(255,255,255,0.025)] rounded-lg px-3 py-2 border border-[rgba(255,255,255,0.04)]">
          {reason}
        </p>
      )}

      {/* tags + salary */}
      <div className="flex gap-1.5 mt-3 flex-wrap items-center">
        {salary && (
          <span className="text-[11px] px-2.5 py-1 rounded-md bg-[rgba(91,79,255,0.1)] text-[#a78bfa] border border-[rgba(91,79,255,0.18)] font-medium">
            {salary}
          </span>
        )}
        {tags.map((tag) => (
          <span
            key={tag}
            className="text-[11px] px-2.5 py-1 rounded-md bg-[rgba(255,255,255,0.04)] text-[#5a5a7a] border border-[rgba(255,255,255,0.06)]"
          >
            {tag}
          </span>
        ))}
      </div>

      {/* actions */}
      {!isDone ? (
        <div className="flex gap-2 mt-4 pt-3 border-t border-white/6">
          <Button
            variant="teal"
            size="sm"
            loading={localAction === "apply" || isSubmitting}
            onClick={() => handleActionClick("apply")}
            className="flex-1"
          >
            Apply
          </Button>
          <Button
            variant="ghost"
            size="sm"
            loading={localAction === "save"}
            onClick={() => handleActionClick("save")}
          >
            Save
          </Button>
          <Button
            variant="outline"
            size="sm"
            loading={localAction === "ignore"}
            onClick={() => handleActionClick("ignore")}
          >
            Ignore
          </Button>
        </div>
      ) : (
        <p className="mt-4 pt-3 border-t border-[rgba(255,255,255,0.06)] text-[11px] text-[#5a5a7a] uppercase tracking-widest font-bold">
          Action Completed
        </p>
      )}
    </div>
  );
}
