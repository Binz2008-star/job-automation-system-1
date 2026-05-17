'use client';

import { cn } from '@/lib/utils';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import React from 'react';
import { MaterialIcon } from '../ui/MaterialIcon';

interface NavigationProps {
    className?: string;
}

export const Navigation = React.forwardRef<HTMLElement, NavigationProps>(
    ({ className }, ref) => {
        const pathname = usePathname();

        const navClass = (href: string, activeIcon: string) =>
            pathname === href
                ? activeIcon
                : 'text-on-surface-variant/60 px-6 py-2 flex flex-col items-center gap-1 hover:bg-white/5 transition-all duration-300 active:scale-95';

        return (
            <nav
                ref={ref as any}
                className={cn(
                    'fixed bottom-10 left-1/2 -translate-x-1/2 z-50',
                    'flex items-center gap-4 p-2',
                    'bg-surface-glass/80 backdrop-blur-xl',
                    'border-t-[0.5px] border-l-[0.5px] border-white/10',
                    'shadow-2xl rounded-full',
                    className
                )}
                aria-label="Section navigation"
            >
                <Link
                    href="/command"
                    aria-current={pathname === "/command" ? "page" : undefined}
                    className={navClass('/command', 'bg-secondary/10 text-secondary-fixed-dim rounded-full px-6 py-2 flex flex-col items-center gap-1 hover:bg-white/5 transition-all duration-300 active:scale-95')}
                >
                    <MaterialIcon icon="auto_awesome" filled size={20} />
                    <span className="text-label-caps text-[10px]">Command</span>
                </Link>
                <Link
                    href="/signals"
                    aria-current={pathname === "/signals" ? "page" : undefined}
                    className={navClass('/signals', 'bg-secondary/10 text-secondary-fixed-dim rounded-full px-6 py-2 flex flex-col items-center gap-1 hover:bg-white/5 transition-all duration-300 active:scale-95')}
                >
                    <MaterialIcon icon="insights" size={20} />
                    <span className="text-label-caps text-[10px]">Signals</span>
                </Link>
                <Link
                    href="/flow"
                    aria-current={pathname === "/flow" ? "page" : undefined}
                    className={navClass('/flow', 'bg-secondary/10 text-secondary-fixed-dim rounded-full px-6 py-2 flex flex-col items-center gap-1 hover:bg-white/5 transition-all duration-300 active:scale-95')}
                >
                    <MaterialIcon icon="waves" size={20} />
                    <span className="text-label-caps text-[10px]">Flow</span>
                </Link>
                <Link
                    href="/archive"
                    aria-current={pathname === "/archive" ? "page" : undefined}
                    className={navClass('/archive', 'bg-secondary/10 text-secondary-fixed-dim rounded-full px-6 py-2 flex flex-col items-center gap-1 hover:bg-white/5 transition-all duration-300 active:scale-95')}
                >
                    <MaterialIcon icon="history" size={20} />
                    <span className="text-label-caps text-[10px]">Archive</span>
                </Link>
            </nav>
        );
    }
);

Navigation.displayName = 'Navigation';
