'use client';

import { cn } from '@/lib/utils';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import React from 'react';
import { MaterialIcon } from '../ui/MaterialIcon';

interface TopNavProps {
    className?: string;
}

export const TopNav = React.forwardRef<HTMLElement, TopNavProps>(
    ({ className }, ref) => {
        const pathname = usePathname();

        const linkClass = (href: string) =>
            pathname === href
                ? 'text-primary font-bold'
                : 'text-on-surface-muted font-normal hover:text-primary transition-colors duration-500';

        return (
            <header
                ref={ref as any}
                className={cn(
                    'fixed top-0 w-full z-50',
                    'flex justify-between items-center',
                    'px-container-padding-desktop py-8',
                    'bg-transparent',
                    className
                )}
            >
                <div className="flex justify-between items-center w-full max-w-7xl">
                    <Link href="/" className="font-headline-xl text-headline-xl tracking-tighter text-on-surface">
                        Rico AI
                    </Link>
                    <div className="flex items-center gap-8">
                        <nav className="hidden md:flex items-center gap-10" aria-label="Primary navigation">
                            <Link
                                href="/command"
                                aria-current={pathname === "/command" ? "page" : undefined}
                                className={linkClass("/command")}
                            >
                                Command
                            </Link>
                            <Link
                                href="/signals"
                                aria-current={pathname === "/signals" ? "page" : undefined}
                                className={linkClass("/signals")}
                            >
                                Signals
                            </Link>
                            <Link
                                href="/flow"
                                aria-current={pathname === "/flow" ? "page" : undefined}
                                className={linkClass("/flow")}
                            >
                                Flow
                            </Link>
                            <Link
                                href="/archive"
                                aria-current={pathname === "/archive" ? "page" : undefined}
                                className={linkClass("/archive")}
                            >
                                Archive
                            </Link>
                        </nav>
                        <div className="flex items-center gap-4">
                            <MaterialIcon icon="account_circle" className="text-primary cursor-pointer hover:scale-110 transition-transform" />
                        </div>
                    </div>
                </div>
            </header>
        );
    }
);

TopNav.displayName = 'TopNav';
