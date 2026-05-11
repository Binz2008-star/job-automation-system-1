import Link from "next/link";

interface StatusCardProps {
  title: string;
  badge?: "live" | "pending" | "error" | "placeholder";
  value?: string;
  href?: string;
  children?: React.ReactNode;
}

const BADGE_STYLES: Record<NonNullable<StatusCardProps["badge"]>, string> = {
  live: "bg-[rgba(0,201,167,0.08)] text-[#00c9a7] ring-1 ring-[rgba(0,201,167,0.2)]",
  pending: "bg-[rgba(245,166,35,0.08)] text-[#f5a623] ring-1 ring-[rgba(245,166,35,0.2)]",
  error: "bg-[rgba(255,94,91,0.08)] text-[#ff5e5b] ring-1 ring-[rgba(255,94,91,0.2)]",
  placeholder: "bg-[rgba(255,255,255,0.04)] text-[#5a5a7a] ring-1 ring-[rgba(255,255,255,0.08)]",
};

const BADGE_LABELS: Record<NonNullable<StatusCardProps["badge"]>, string> = {
  live: "Live",
  pending: "Pending",
  error: "Error",
  placeholder: "Not connected",
};

export function StatusCard({ title, badge, value, href, children }: StatusCardProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-[#8080a0]">{title}</span>
        {badge && (
          <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold shrink-0 ${BADGE_STYLES[badge]}`}>
            {BADGE_LABELS[badge]}
          </span>
        )}
      </div>
      {value && (
        <p className="font-['Cabinet_Grotesk',sans-serif] font-800 text-[28px] text-[#eeeef5] tracking-tight">
          {value}
        </p>
      )}
      {children}
    </>
  );

  const className =
    "rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#13132a]/80 p-5 flex flex-col gap-3 transition-all duration-300 hover:border-[rgba(255,255,255,0.1)] hover:bg-[#13132a] hover:-translate-y-0.5 hover:shadow-[0_20px_45px_rgba(0,0,0,0.22)]";

  if (href) {
    return (
      <Link href={href} className={className}>
        {body}
      </Link>
    );
  }

  return <div className={className}>{body}</div>;
}
