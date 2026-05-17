'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { getApplications } from '@/lib/api';
import { TopNav } from '@/components/layout/TopNav';
import { Navigation } from '@/components/layout/Navigation';
import { AuraGlow } from '@/components/ui/AuraGlow';
import { GlassPanel } from '@/components/ui/GlassPanel';
import { MaterialIcon } from '@/components/ui/MaterialIcon';
import type { Application } from '@/types';

const STATUS_LABELS: Record<Application['status'], string> = {
  applied: 'Applied',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
  saved: 'Saved',
  opened: 'Opened',
  decision_made: 'Decision',
};

export default function FlowPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadApplications = useCallback(async () => {
    try {
      const response = await getApplications(undefined, 1, 6);
      setApplications(response.applications);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadApplications();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadApplications]);

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <AuraGlow aria-hidden="true" variant="cyan" position="top-left" />
      <AuraGlow aria-hidden="true" variant="magenta" position="bottom-right" />
      <TopNav />

      <main className="relative z-10 pt-40 pb-60 px-container-padding-mobile md:px-container-padding-desktop max-w-7xl mx-auto">
        <div className="mb-section-gap">
          <h1 className="font-headline-xl text-headline-xl text-on-surface mb-4">Application Flow</h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant max-w-xl">
            Live application state from the backend pipeline, mapped into Rico&apos;s active flow view.
          </p>
        </div>

        {loading ? (
          <div className="space-y-8">
            {Array.from({ length: 3 }).map((_, index) => (
              <GlassPanel key={index} className="p-8 rounded-xl border border-white/10 animate-pulse motion-reduce:animate-none">
                <div className="h-5 w-32 rounded bg-white/5 mb-4" />
                <div className="h-4 w-44 rounded bg-white/5 mb-2" />
                <div className="h-4 w-28 rounded bg-white/5" />
              </GlassPanel>
            ))}
          </div>
        ) : error ? (
          <GlassPanel className="p-6 rounded-xl border border-white/10">
            <p className="text-on-surface mb-2">Could not load the live pipeline.</p>
            <p className="text-body-md text-on-surface-variant">
              Rico&apos;s command interface is available, but this flow surface could not fetch current applications.
            </p>
          </GlassPanel>
        ) : applications.length === 0 ? (
          <GlassPanel className="p-6 rounded-xl border border-white/10">
            <p className="text-on-surface mb-2">No applications tracked yet.</p>
            <p className="text-body-md text-on-surface-variant">
              Apply to jobs or mark openings as tracked to populate the live flow timeline.
            </p>
          </GlassPanel>
        ) : (
          <div className="space-y-8">
            {applications.map((item, index) => (
              <GlassPanel key={item.application_id} className="p-8 rounded-xl border border-white/10 hover:border-primary/30 transition-all">
                <div className="flex items-start justify-between mb-4 gap-4">
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="w-12 h-12 rounded-full bg-surface-container flex items-center justify-center shrink-0">
                      <span className="font-headline-lg text-headline-lg text-primary">{index + 1}</span>
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-headline-lg text-headline-lg text-on-surface truncate">{item.company}</h3>
                      <p className="text-on-surface-variant truncate">{item.title}</p>
                    </div>
                  </div>
                  <span className="text-label-caps text-[10px] px-3 py-1 border border-white/10 rounded-full shrink-0">
                    {STATUS_LABELS[item.status]}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-full h-[1px] bg-white/10" />
                  <span className="text-label-caps text-[10px] text-secondary shrink-0">
                    {item.applied_at ? new Date(item.applied_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Live'}
                  </span>
                  <MaterialIcon icon="check_circle" className="text-secondary text-sm" />
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
