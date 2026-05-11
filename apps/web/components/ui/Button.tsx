import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type ButtonVariant = "primary" | "ghost" | "teal" | "danger" | "outline";
export type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-[#5b4fff] text-white shadow-[0_4px_16px_rgba(91,79,255,0.28)] hover:bg-[#6d5fff] hover:-translate-y-px",
  ghost:
    "bg-white/5 text-white border border-white/10 hover:bg-white/8 hover:border-white/16",
  teal:
    "bg-[rgba(0,201,167,0.12)] text-[#00c9a7] border border-[rgba(0,201,167,0.22)] hover:bg-[rgba(0,201,167,0.2)]",
  danger:
    "bg-[rgba(255,94,91,0.1)] text-[#ff5e5b] border border-[rgba(255,94,91,0.2)] hover:bg-[rgba(255,94,91,0.18)]",
  outline:
    "border border-white/12 text-white/70 hover:border-white/24 hover:text-white",
};

const sizes: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-xs rounded-lg gap-1.5",
  md: "px-4 py-2 text-sm rounded-[10px] gap-2",
  lg: "px-6 py-3 text-[15px] rounded-xl gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "primary",
      size = "md",
      loading = false,
      disabled,
      children,
      ...props
    },
    ref
  ) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center font-semibold transition-all duration-150 select-none",
        "disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none",
        variants[variant],
        sizes[size],
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg
          className="animate-spin h-3.5 w-3.5 flex-shrink-0"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v8H4z"
          />
        </svg>
      )}
      {children}
    </button>
  )
);
Button.displayName = "Button";
