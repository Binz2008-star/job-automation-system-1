'use client';

import React from 'react';
import { useOrchestration } from '@/hooks/useOrchestration';
import { TopNav } from '@/components/layout/TopNav';
import { Navigation } from '@/components/layout/Navigation';
import { AuraGlow } from '@/components/ui/AuraGlow';
import { GlassPanel } from '@/components/ui/GlassPanel';
import { MaterialIcon } from '@/components/ui/MaterialIcon';

function MomentumLabel({ momentum }: { momentum: 'high' | 'medium' | 'low' }) {
  const palette = {
    high: 'text-[#5dcaa5] border-[#5dcaa5]/30',
    medium: 'text-[#facc15] border-[#facc15]/30',
    low: 'text-[#a78bfa] border-[#a78bfa]/30',
  } as const;

  return (
    <span className={`text-label-caps text-[10px] px-2 py-1 border rounded ${palette[momentum]}`}>
      {momentum.toUpperCase()} MOMENTUM
    </span>
  );
}

export default function SignalsPage() {
  const { signals, isLoading, error } = useOrchestration();

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <AuraGlow aria-hidden="true" variant="magenta" position="top-left" />
      <AuraGlow aria-hidden="true" variant="cyan" position="bottom-right" />
      <TopNav />

      <main className="relative z-10 pt-40 pb-60 px-container-padding-mobile md:px-container-padding-desktop max-w-7xl mx-auto">
        <div className="mb-section-gap">
          <h1 className="font-headline-xl text-headline-xl text-on-surface mb-4">Opportunity Signals</h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant max-w-xl">
            Live market signals sourced from your matched jobs feed and scored against current opportunity momentum.
          </p>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 3 }).map((_, index) => (
              <GlassPanel key={index} className="p-6 rounded-xl border border-white/10 animate-pulse motion-reduce:animate-none">
                <div className="h-5 w-32 rounded bg-white/5 mb-4" />
                <div className="h-4 w-40 rounded bg-white/5 mb-2" />
                <div className="h-4 w-24 rounded bg-white/5" />
              </GlassPanel>
            ))}
          </div>
        ) : error ? (
          <GlassPanel className="p-6 rounded-xl border border-white/10">
            <p className="text-on-surface mb-2">Could not load live signals.</p>
            <p className="text-body-md text-on-surface-variant">
              The backend is reachable for command execution, but the signals surface could not read the current jobs feed.
            </p>
          </GlassPanel>
        ) : signals.length === 0 ? (
          <GlassPanel className="p-6 rounded-xl border border-white/10">
            <p className="text-on-surface mb-2">No live signals yet.</p>
            <p className="text-body-md text-on-surface-variant">
              Rico will populate this view when matched opportunities are available from the live jobs endpoint.
            </p>
          </GlassPanel>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {signals.map((signal) => (
              <GlassPanel key={signal.id} className="p-6 rounded-xl border border-white/10 hover:border-primary/30 transition-all group">
                <div className="flex items-start justify-between mb-4 gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                      <MaterialIcon icon="business" className="text-primary" />
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-headline-lg text-headline-lg text-on-surface truncate">{signal.company}</h3>
                      <p className="text-on-surface-variant text-sm truncate">{signal.location}</p>
                    </div>
                  </div>
                  <MomentumLabel momentum={signal.momentum} />
                </div>
                <div className="mb-4">
                  <p className="text-body-md text-on-surface-variant mb-2">{signal.role}</p>
                  <div className="flex gap-2 items-center">
                    <span className="text-[10px] text-on-surface-variant/60">Match score {signal.matchScore}%</span>
                    <span className="text-[10px] text-on-surface-variant/60">•</span>
                    <span className="text-[10px] text-on-surface-variant/60">
                      {signal.timestamp ? new Date(signal.timestamp).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : 'Fresh'}
                    </span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full ${signal.momentum === 'high' ? 'bg-secondary' : signal.momentum === 'medium' ? 'bg-[#facc15]' : 'bg-primary'}`} />
                    <span className="text-label-caps text-[10px] text-on-surface-variant">
                      Live backend signal
                    </span>
                  </div>
                  <MaterialIcon icon="arrow_forward" className="text-on-surface-variant/40 group-hover:text-primary transition-colors" />
                </div>
              </GlassPanel>
            ))}
          </div>
        )}
      </main>

      <Navigation />
    </div>
  );
}
