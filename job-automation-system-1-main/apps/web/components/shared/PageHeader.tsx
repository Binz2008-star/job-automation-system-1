import { cn } from "@/lib/utils";

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, subtitle, actions, className }: PageHeaderProps) {
  return (
    <div className={cn("mb-6 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between", className)}>
      <div>
        <h1 className="font-display font-extrabold text-[22px] tracking-tight text-rico-text">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-0.5 text-sm text-rico-text-muted">{subtitle}</p>
        )}
      </div>
      {actions && <div className="mt-2 sm:mt-0 flex gap-2">{actions}</div>}
    </div>
  );
}
