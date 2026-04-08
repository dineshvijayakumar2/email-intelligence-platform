/**
 * Daily Digest Page — Zero antd.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import dayjs from 'dayjs';
import { RefreshCw, Lightbulb } from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { digestApi, bucketApi } from '../../services/aiService';
import { MailboxSelector } from '../../components/MailboxSelector';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import type { DailyDigest, BucketSummary } from '../../types/ai';

const DigestPage: React.FC = () => {
  const isMountedRef = useRef(true);
  const [loading, setLoading] = useState(false);
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';
  const [selectedDate, setSelectedDate] = useState<string>(dayjs().format('YYYY-MM-DD'));
  const [digestType, setDigestType] = useState<'daily' | 'weekly'>('daily');
  const [digest, setDigest] = useState<DailyDigest | null>(null);
  const [error, setError] = useState('');

  const loadDigest = useCallback(async (force = false) => {
    if (!mailboxId) return;
    setLoading(true);
    setError('');
    try {
      const digestData = await digestApi.get(mailboxId, selectedDate, undefined, force, digestType);
      if (!isMountedRef.current) return;
      setDigest(digestData);
      if (!digestData) setError('No digest available. Try analyzing emails first.');
    } catch (err: any) {
      if (isMountedRef.current) setError(err?.message || 'Failed to load digest');
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [mailboxId, selectedDate, digestType]);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);
  useEffect(() => { if (mailboxId) loadDigest(); }, [mailboxId, selectedDate, digestType, loadDigest]);

  return (
    <PageShell>
      <PageHeader title={`${digestType === 'weekly' ? 'Weekly' : 'Daily'} Intelligence Digest`} />

      {/* Controls */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <MailboxSelector value={mailboxIds} onChange={setMailboxIds} mode="single" size="small" />
        <select value={digestType} onChange={e => setDigestType(e.target.value as any)}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
        </select>
        <input type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white" />
        <button onClick={() => loadDigest(true)} disabled={loading}
          className="h-8 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Regenerate
        </button>
      </div>

      {!mailboxId && (
        <div className="rounded-lg border bg-white shadow-sm p-8 text-center">
          <p className="text-sm text-slate-400">Select a mailbox to view the daily digest</p>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 mb-4 text-sm">{error}</div>
      )}

      {loading && (
        <div className="flex flex-col items-center py-16 gap-4">
          <Spinner className="h-8 w-8 text-primary animate-spin" />
          <p className="text-sm text-slate-400">Generating digest...</p>
        </div>
      )}

      {!loading && mailboxId && digest && (
        <>
          {/* Stats */}
          {digest.stats && (
            <div className="flex items-center gap-4 flex-wrap rounded-lg border bg-white shadow-sm px-4 py-2.5 mb-4 text-sm">
              <span><span className="font-medium text-slate-500">Inbound:</span> {digest.stats.in_count ?? 0}</span>
              <span><span className="font-medium text-slate-500">Outbound:</span> {digest.stats.out_count ?? 0}</span>
              <span><span className="font-medium text-slate-500">Open Threads:</span> {digest.stats.open_threads ?? 0}</span>
              {digest.stats.overdue_threads > 0 && <StatusBadge variant="danger" size="sm">Overdue: {digest.stats.overdue_threads}</StatusBadge>}
              {(() => {
                const custom = (digest as any).summary_stats || (digest as any).raw_ai_response?.summary_stats;
                if (!custom) return null;
                return Object.entries(custom).filter(([, v]) => v && v !== 0).map(([k, v]) => (
                  <StatusBadge key={k} variant="info" size="sm">{k.replace(/_/g, ' ')}: {String(v)}</StatusBadge>
                ));
              })()}
            </div>
          )}

          {/* Executive Summary */}
          <div className="rounded-lg border bg-white shadow-sm p-4 mb-4">
            <div className="flex items-center gap-2 mb-3">
              <Lightbulb className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold text-slate-900">Executive Summary</h3>
              <span className="text-xs text-slate-400">{selectedDate} | {digest.emails_analyzed || 0} emails analyzed</span>
            </div>
            <p className="text-sm text-slate-700 leading-relaxed">{digest.summary || 'No summary available.'}</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
            {/* Action Items */}
            <div className="lg:col-span-3 rounded-lg border bg-white shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b"><h3 className="text-sm font-semibold text-slate-900">Action Items</h3></div>
              {digest.action_items && digest.action_items.length > 0 ? (
                <div className="divide-y">
                  {digest.action_items.map((item: any, i: number) => (
                    <div key={i} className="px-4 py-3">
                      <div className="flex items-center gap-2 mb-1">
                        <StatusBadge variant={item.priority <= 2 ? 'danger' : item.priority <= 3 ? 'warning' : 'info'} size="sm">
                          P{item.priority}
                        </StatusBadge>
                        {item.bucket && <StatusBadge variant="neutral" size="sm">{item.bucket.replace(/_/g, ' ')}</StatusBadge>}
                        {item.contact_name && <span className="text-xs text-slate-400">{item.contact_name}</span>}
                      </div>
                      <p className="text-sm text-slate-700">{item.action}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-400 text-center py-8">No action items</p>
              )}
            </div>

            {/* Highlights */}
            <div className="lg:col-span-2 rounded-lg border bg-white shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b"><h3 className="text-sm font-semibold text-slate-900">Highlights</h3></div>
              {digest.highlights && digest.highlights.length > 0 ? (
                <div className="divide-y">
                  {digest.highlights.map((item: any, i: number) => (
                    <div key={i} className="px-4 py-3">
                      <StatusBadge variant="purple" size="sm">{item.label || item.type || 'Info'}</StatusBadge>
                      <p className="text-sm text-slate-700 mt-1">{item.detail || item.description}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-400 text-center py-8">No highlights</p>
              )}
            </div>
          </div>
        </>
      )}
    </PageShell>
  );
};

export default DigestPage;
