"use client";

import { Button } from "@/components/ui/Button";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { cn } from "@/lib/utils";
import type { Job } from "@/types";
import { useState } from "react";

interface JobCardProps {
  job: Job;
  onAction?: (jobId: string, action: string) => Promise<void>;
  className?: string;
}

/** Two-letter abbreviation for company logo placeholder */
function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

const logoColors = [
  "from-blue-500/20 to-blue-400/10 text-blue-300",
  "from-emerald-500/20 to-emerald-400/10 text-emerald-300",
  "from-amber-500/20 to-amber-400/10 text-amber-300",
  "from-purple-500/20 to-purple-400/10 text-purple-300",
  "from-rose-500/20 to-rose-400/10 text-rose-300",
];

function pickColor(name: string) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) & 0xffffffff;
  return logoColors[Math.abs(h) % logoColors.length];
}

export function JobCard({ job, onAction, className }: JobCardProps) {
  const [loading, setLoading] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const handle = async (action: string) => {
    if (!onAction || loading) return;
    setLoading(action);
    try {
      await onAction(job.job_id, action);
      setDone(action);
    } finally {
      setLoading(null);
    }
  };

  const salary = job.salary_range ?? job.salary;

  return (
    <div
      className={cn(
        "group bg-[#0e0e20] border border-white/6 rounded-2xl p-5",
        "hover:border-[rgba(91,79,255,0.3)] hover:bg-[#14142a] transition-all duration-200",
        done && "opacity-60",
        className
      )}
    >
      {/* top row */}
      <div className="flex gap-3 items-start">
        <div
          className={cn(
            "w-10 h-10 rounded-xl flex-shrink-0 flex items-center justify-center",
            "bg-gradient-to-br font-['Cabinet_Grotesk',sans-serif] font-black text-xs",
            pickColor(job.company)
          )}
        >
          {initials(job.company)}
        </div>

        <div className="flex-1 min-w-0">
          <p className="font-['Cabinet_Grotesk',sans-serif] font-700 text-[15px] leading-snug tracking-tight truncate text-white">
            {job.title}
          </p>
          <p className="text-[13px] text-white/50 mt-0.5">
            {job.company} · {job.location}
          </p>
        </div>

        <ScoreBadge score={job.score} />
      </div>

      {/* reason */}
      <p className="mt-3 text-[12px] text-white/40 leading-relaxed bg-black/20 rounded-lg px-3 py-2 border border-white/4">
        {job.reason}
      </p>

      {/* tags + salary */}
      <div className="flex gap-1.5 mt-3 flex-wrap items-center">
        {salary && (
          <span className="text-[11px] px-2.5 py-1 rounded-md bg-[rgba(91,79,255,0.1)] text-[#a78bfa] border border-[rgba(91,79,255,0.18)] font-medium">
            {salary}
          </span>
        )}
        {job.tags.map((tag) => (
          <span
            key={tag}
            className="text-[11px] px-2.5 py-1 rounded-md bg-white/4 text-white/40 border border-white/6"
          >
            {tag}
          </span>
        ))}
      </div>

      {/* actions */}
      {onAction && !done && (
        <div className="flex gap-2 mt-4 pt-3 border-t border-white/6">
          <Button
            variant="teal"
            size="sm"
            loading={loading === "apply"}
            onClick={() => handle("apply")}
            className="flex-1"
          >
            Apply
          </Button>
          <Button
            variant="ghost"
            size="sm"
            loading={loading === "save"}
            onClick={() => handle("save")}
          >
            Save
          </Button>
          <Button
            variant="outline"
            size="sm"
            loading={loading === "ignore"}
            onClick={() => handle("ignore")}
          >
            Ignore
          </Button>
        </div>
      )}

      {done && (
        <p className="text-[12px] text-white/30 mt-3 pt-3 border-t border-white/6 capitalize">
          Marked as <span className="text-white/60 font-medium">{done}</span>
        </p>
      )}
    </div>
  );
}
