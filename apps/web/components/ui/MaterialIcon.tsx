import { cn } from '@/lib/utils';
import React from 'react';

interface MaterialIconProps extends React.SVGAttributes<SVGSVGElement> {
    icon: string;
    filled?: boolean;
    weight?: 100 | 200 | 300 | 400 | 500 | 600 | 700;
    size?: number;
}

type IconRenderer = (filled: boolean) => React.ReactNode;

const ICONS: Record<string, IconRenderer> = {
    account_circle: () => (
        <>
            <circle cx="12" cy="12" r="9" />
            <circle cx="12" cy="10" r="3" />
            <path d="M6.8 18.2a6.2 6.2 0 0 1 10.4 0" />
        </>
    ),
    arrow_forward: () => (
        <>
            <path d="M5 12h12" />
            <path d="m13 6 6 6-6 6" />
        </>
    ),
    auto_awesome: (filled) => (
        <>
            <path d="m12 3 1.8 4.5L18 9.3l-4.2 1.8L12 16l-1.8-4.9L6 9.3l4.2-1.8L12 3Z" fill={filled ? 'currentColor' : 'none'} />
            <path d="m19 5 .7 1.8L21.5 7.5l-1.8.7L19 10l-.7-1.8-1.8-.7 1.8-.7L19 5Z" fill={filled ? 'currentColor' : 'none'} />
            <path d="m5 14 .8 2 2 .8-2 .8L5 20l-.8-2-2-.8 2-.8L5 14Z" fill={filled ? 'currentColor' : 'none'} />
        </>
    ),
    business: () => (
        <>
            <path d="M4 20h16" />
            <path d="M6 20V7l6-3 6 3v13" />
            <path d="M9 10h.01" />
            <path d="M15 10h.01" />
            <path d="M9 14h.01" />
            <path d="M15 14h.01" />
        </>
    ),
    check_circle: () => (
        <>
            <circle cx="12" cy="12" r="9" />
            <path d="m8.5 12 2.2 2.2 4.8-4.8" />
        </>
    ),
    history: () => (
        <>
            <path d="M4.5 11a7.5 7.5 0 1 1 2.2 5.3" />
            <path d="M4.5 7.5V11H8" />
            <path d="M12 8.5V12l2.5 1.5" />
        </>
    ),
    hourglass_empty: () => (
        <>
            <path d="M7 4h10" />
            <path d="M7 20h10" />
            <path d="M8 4c0 3 1.8 4.5 4 6 2.2 1.5 4 3 4 6" />
            <path d="M16 4c0 3-1.8 4.5-4 6-2.2 1.5-4 3-4 6" />
        </>
    ),
    insights: () => (
        <>
            <path d="M5 18V9" />
            <path d="M10 18V6" />
            <path d="M15 18v-4" />
            <path d="M20 18V8" />
            <path d="m5 13 5-4 5 2 5-5" />
        </>
    ),
    lock: () => (
        <>
            <rect x="6.5" y="11" width="11" height="8" rx="2" />
            <path d="M9 11V8.8a3 3 0 1 1 6 0V11" />
        </>
    ),
    rocket_launch: () => (
        <>
            <path d="M13 4c2.5.6 4.4 2.5 5 5L13 14c-2.5-.6-4.4-2.5-5-5l5-5Z" />
            <path d="M9 15 5 19" />
            <path d="M14 10a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4Z" />
            <path d="m7 17-2 2" />
        </>
    ),
    upload_file: () => (
        <>
            <path d="M14 3H8a2 2 0 0 0-2 2v14h12V9l-4-6Z" />
            <path d="M14 3v6h6" />
            <path d="m12 16 0-6" />
            <path d="m9.5 12.5 2.5-2.5 2.5 2.5" />
        </>
    ),
    waves: () => (
        <>
            <path d="M3 13c2.2-2 4.3-2 6.5 0s4.3 2 6.5 0 4.3-2 6.5 0" />
            <path d="M3 17c2.2-2 4.3-2 6.5 0s4.3 2 6.5 0 4.3-2 6.5 0" />
            <path d="M3 9c2.2-2 4.3-2 6.5 0s4.3 2 6.5 0 4.3-2 6.5 0" />
        </>
    ),
};

export const MaterialIcon = React.forwardRef<SVGSVGElement, MaterialIconProps>(
    ({ icon, filled = false, weight = 300, size = 24, className, ...props }, ref) => {
        const glyph = ICONS[icon] ?? ICONS.auto_awesome;
        const ariaLabel = props['aria-label'];
        return (
            <svg
                ref={ref}
                viewBox="0 0 24 24"
                width={size}
                height={size}
                fill="none"
                stroke="currentColor"
                strokeWidth={Math.max(1.5, weight / 220)}
                strokeLinecap="round"
                strokeLinejoin="round"
                className={cn('inline-block shrink-0', className)}
                aria-hidden={ariaLabel ? undefined : true}
                role={ariaLabel ? 'img' : undefined}
                focusable="false"
                {...props}
            >
                {glyph(filled)}
            </svg>
        );
    }
);

MaterialIcon.displayName = 'MaterialIcon';
