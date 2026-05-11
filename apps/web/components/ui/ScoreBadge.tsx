import { cn } from "@/lib/utils";

export function ScoreBadge({ score }: { score?: number | null }) {
  const safe = typeof score === "number" ? score : 0;
  const className =
    safe >= 85
      ? "text-[#00c9a7] bg-[rgba(0,201,167,0.1)] border-[rgba(0,201,167,0.2)]"
      : safe >= 65
        ? "text-amber-300 bg-amber-400/10 border-amber-400/20"
        : "text-white/50 bg-white/4 border-white/10";

  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-1 rounded-full text-[13px] font-black border font-['Cabinet_Grotesk',sans-serif] tracking-tight",
        className
      )}
    >
      {safe}%
    </span>
  );
}
