"use client";

import { cn } from "@/lib/utils";
import type { Toast } from "@/hooks/useToast";

const icons: Record<Toast["variant"], string> = {
  success: "✓",
  error: "✕",
  info: "·",
};

const borders: Record<Toast["variant"], string> = {
  success: "border-l-[#00c9a7]",
  error: "border-l-[#ff5e5b]",
  info: "border-l-[#5b4fff]",
};

export function ToastItem({ toast }: { toast: Toast }) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 px-4 py-3 rounded-xl",
        "bg-[#14142a] border border-white/10 border-l-2",
        "shadow-[0_8px_32px_rgba(0,0,0,0.5)]",
        "animate-in slide-in-from-right-4 duration-300 text-sm text-white/90",
        borders[toast.variant]
      )}
    >
      <span className="font-bold text-xs">{icons[toast.variant]}</span>
      {toast.message}
    </div>
  );
}

export function ToastContainer({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none max-w-xs w-full">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}
