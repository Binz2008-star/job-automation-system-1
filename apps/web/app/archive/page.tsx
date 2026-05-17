'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { fetchChatHistory, type ChatHistoryMessage } from '@/lib/api';
import { TopNav } from '@/components/layout/TopNav';
import { Navigation } from '@/components/layout/Navigation';
import { AuraGlow } from '@/components/ui/AuraGlow';
import { GlassPanel } from '@/components/ui/GlassPanel';
import { MaterialIcon } from '@/components/ui/MaterialIcon';

function summarize(content: string): string {
  const text = content.replace(/\s+/g, ' ').trim();
  return text.length > 140 ? `${text.slice(0, 137)}...` : text;
}

function formatTimestamp(timestamp?: string | null): string {
  if (!timestamp) return 'Recent';
  return new Date(timestamp).toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function ArchivePage() {
  const [messages, setMessages] = useState<ChatHistoryMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadArchive = useCallback(async () => {
    try {
      const response = await fetchChatHistory(8);
      setMessages(response.messages);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadArchive();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadArchive]);

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <AuraGlow aria-hidden="true" variant="magenta" position="bottom-left" />
      <AuraGlow aria-hidden="true" variant="cyan" position="top-right" />
      <TopNav />

      <main className="relative z-10 pt-40 pb-60 px-container-padding-mobile md:px-container-padding-desktop max-w-7xl mx-auto">
        <div className="mb-section-gap">
          <h1 className="font-headline-xl text-headline-xl text-on-surface mb-4">Memory Archive</h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant max-w-xl">
            Live strategic memory from Rico&apos;s recent conversation history, preserved as operational context rather than decorative placeholders.
          </p>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {Array.from({ length: 4 }).map((_, index) => (
              <GlassPanel key={index} className="p-6 rounded-xl border border-white/10 animate-pulse motion-reduce:animate-none">
                <div className="h-5 w-24 rounded bg-white/5 mb-4" />
                <div className="h-4 w-full rounded bg-white/5 mb-2" />
                <div className="h-4 w-2/3 rounded bg-white/5" />
              </GlassPanel>
            ))}
          </div>
        ) : error ? (
          <GlassPanel className="p-6 rounded-xl border border-white/10">
            <p className="text-on-surface mb-2">Could not load memory history.</p>
            <p className="text-body-md text-on-surface-variant">
              Rico&apos;s archive view is connected to the live chat history endpoint, but this request did not complete successfully.
            </p>
          </GlassPanel>
        ) : messages.length === 0 ? (
          <GlassPanel className="p-6 rounded-xl border border-white/10">
            <p className="text-on-surface mb-2">No archived memory yet.</p>
            <p className="text-body-md text-on-surface-variant">
              Start a conversation in Command and Rico will begin building the live memory timeline shown here.
            </p>
          </GlassPanel>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {messages.map((message, index) => (
              <GlassPanel key={`${message.timestamp ?? 'recent'}-${index}`} className="p-6 rounded-xl border border-white/10 hover:border-primary/30 transition-all group">
                <div className="flex items-start justify-between mb-4 gap-4">
                  <h3 className="font-headline-lg text-headline-lg text-on-surface">{formatTimestamp(message.timestamp)}</h3>
                  <MaterialIcon icon="history" className="text-on-surface-variant/40 group-hover:text-primary transition-colors shrink-0" />
                </div>
                <div className="mb-4">
                  <p className="text-body-md text-on-surface-variant mb-2">
                    {message.role === 'user' ? 'User instruction' : 'Rico response'}
                  </p>
                  <p className="text-[12px] text-on-surface-variant/60 italic">{summarize(message.content)}</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className={`w-1.5 h-1.5 rounded-full ${message.role === 'user' ? 'bg-secondary' : 'bg-primary'}`} />
                  <span className="text-label-caps text-[10px] text-primary">MEMORY INTEGRATED</span>
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
