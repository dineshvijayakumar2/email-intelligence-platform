import React, { useState, useEffect, useRef } from 'react';
import { useClient } from '../../contexts/ClientContext';
import { patternsApi, formatRelativeTime, formatRatio } from '../../services/analyticsService';
import type { InitiationPattern, FrequencyPattern, EngagementTrend } from '../../types/analytics';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { cn } from '@/lib/utils';
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';

export const CommunicationPatterns: React.FC = () => {
  const isMountedRef = useRef(true);
  const { clientId } = useClient();
  const [activeTab, setActiveTab] = useState<'initiation' | 'frequency' | 'trends'>('initiation');
  const [initiation, setInitiation] = useState<InitiationPattern[]>([]);
  const [initLoading, setInitLoading] = useState(false);
  const [frequency, setFrequency] = useState<FrequencyPattern[]>([]);
  const [freqLoading, setFreqLoading] = useState(false);
  const [trends, setTrends] = useState<EngagementTrend[]>([]);
  const [trendsLoading, setTrendsLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    if (activeTab === 'initiation') { setInitLoading(true); patternsApi.initiation(clientId).then(r => { if (isMountedRef.current) setInitiation(r); }).finally(() => { if (isMountedRef.current) setInitLoading(false); }); }
    if (activeTab === 'frequency') { setFreqLoading(true); patternsApi.frequency(clientId).then(r => { if (isMountedRef.current) setFrequency(r); }).finally(() => { if (isMountedRef.current) setFreqLoading(false); }); }
    if (activeTab === 'trends') { setTrendsLoading(true); patternsApi.engagementTrends(clientId).then(r => { if (isMountedRef.current) setTrends(r); }).finally(() => { if (isMountedRef.current) setTrendsLoading(false); }); }
  }, [clientId, activeTab]);

  const TrendIcon: React.FC<{ trend: string }> = ({ trend }) => {
    if (trend === 'increasing') return <ArrowUp className="h-3.5 w-3.5 text-success" />;
    if (trend === 'decreasing') return <ArrowDown className="h-3.5 w-3.5 text-destructive" />;
    return <Minus className="h-3.5 w-3.5 text-slate-400" />;
  };

  return (
    <PageShell>
      <PageHeader title="Communication Patterns" description="Who initiates, how often, and engagement trends" />

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-slate-200 pb-px">
        {([['initiation', 'Thread Initiation'], ['frequency', 'Frequency'], ['trends', 'Engagement Trends']] as const).map(([key, label]) => (
          <button key={key} onClick={() => setActiveTab(key as any)}
            className={cn('px-4 py-2 text-sm font-medium rounded-t-md transition-colors -mb-px',
              activeTab === key ? 'text-primary border-b-2 border-primary bg-white' : 'text-slate-500 hover:text-slate-700')}>{label}</button>
        ))}
      </div>

      {/* Initiation tab */}
      {activeTab === 'initiation' && (
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
          {initLoading ? <ContentSkeleton rows={6} /> : (
            <table className="w-full text-sm">
              <thead><tr className="border-b bg-slate-50/50">
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Contact</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-36">Initiation</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Threads</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Us</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Them</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-50">
                {initiation.map(r => {
                  const pct = Math.round(r.initiation_ratio * 100);
                  return (
                    <tr key={r.contact_id || r.contact_email} className="hover:bg-slate-50/50">
                      <td className="px-4 py-2"><span className="font-medium text-slate-800">{r.contact_name || r.contact_email}</span>{r.company_name && <div className="text-xs text-slate-400">{r.company_name}</div>}</td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: pct > 60 ? '#10b981' : pct > 30 ? '#f59e0b' : '#ef4444' }} /></div>
                          <span className="text-xs text-slate-600 tabular-nums">{formatRatio(r.initiation_ratio)}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">{r.total_threads}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{r.threads_initiated_by_us}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{r.threads_initiated_by_them}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Frequency tab */}
      {activeTab === 'frequency' && (
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
          {freqLoading ? <ContentSkeleton rows={6} /> : (
            <table className="w-full text-sm">
              <thead><tr className="border-b bg-slate-50/50">
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Contact</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Total</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">/Wk</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">/Mo</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Active</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Last</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-50">
                {frequency.map(r => (
                  <tr key={r.contact_id || r.contact_email} className="hover:bg-slate-50/50">
                    <td className="px-4 py-2"><span className="font-medium text-slate-800">{r.contact_name || r.contact_email}</span>{r.company_name && <div className="text-xs text-slate-400">{r.company_name}</div>}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{r.total_emails}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-slate-600">{r.emails_per_week?.toFixed(1) ?? '—'}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-slate-600">{r.emails_per_month?.toFixed(1) ?? '—'}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{r.days_active}d</td>
                    <td className="px-4 py-2 text-xs text-slate-500">{formatRelativeTime(r.last_contact_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Trends tab */}
      {activeTab === 'trends' && (
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
          {trendsLoading ? <ContentSkeleton rows={6} /> : (
            <table className="w-full text-sm">
              <thead><tr className="border-b bg-slate-50/50">
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Contact</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Trend</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Last 30d</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Prev 30d</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Change</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-50">
                {trends.map(r => (
                  <tr key={r.contact_id || r.contact_email} className="hover:bg-slate-50/50">
                    <td className="px-4 py-2"><span className="font-medium text-slate-800">{r.contact_name || r.contact_email}</span>{r.company_name && <div className="text-xs text-slate-400">{r.company_name}</div>}</td>
                    <td className="px-4 py-2"><div className="flex items-center gap-1"><TrendIcon trend={r.trend} /><span className="text-xs text-slate-600">{r.trend}</span></div></td>
                    <td className="px-4 py-2 text-right tabular-nums">{r.last_30_days_emails}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-slate-500">{r.previous_30_days_emails}</td>
                    <td className={cn('px-4 py-2 text-right tabular-nums', r.change_percentage > 0 ? 'text-success' : r.change_percentage < 0 ? 'text-destructive' : 'text-slate-400')}>
                      {r.change_percentage > 0 ? '+' : ''}{r.change_percentage}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </PageShell>
  );
};
