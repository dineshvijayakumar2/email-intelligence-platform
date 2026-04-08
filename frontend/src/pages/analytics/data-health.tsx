import React, { useState, useEffect, useRef } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { useClient } from '../../contexts/ClientContext';
import { MetricCard } from '../../components/analytics/MetricCard';
import { ChartCard } from '../../components/analytics/ChartCard';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { Spinner } from '@/lib/icons';
import { toast } from '@/lib/toast';
import { formatNumber } from '../../utils/numberFormat';
import {
  dataHealthApi,
  type MailboxHealth,
  type DataHealthResponse,
  type ExtractionJobHealth,
} from '../../services/analyticsService';
import api from '../../services/apiClient';
import { CheckCircle, AlertTriangle, XCircle, RefreshCw, Database, GitMerge, Brain, Zap } from 'lucide-react';

const THREAD_COLORS: Record<string, string> = {
  complete: '#10b981', awaiting_response: '#667eea', awaiting_our_response: '#f59e0b',
  overdue: '#ef4444', dropped: '#94a3b8', ongoing: '#06b6d4', unknown: '#d1d5db',
};

function lagBadge(hours: number | null) {
  if (hours == null) return <StatusBadge variant="neutral" size="sm">Never</StatusBadge>;
  if (hours < 2) return <StatusBadge variant="success" size="sm">{hours}h ago</StatusBadge>;
  if (hours < 24) return <StatusBadge variant="warning" size="sm">{hours}h ago</StatusBadge>;
  return <StatusBadge variant="danger" size="sm">{Math.round(hours / 24)}d ago</StatusBadge>;
}

function statusBadge(status: string) {
  const v = { active: 'success', connected: 'success', syncing: 'info', error: 'danger', disconnected: 'danger', pending: 'warning' }[status] || 'neutral';
  return <StatusBadge variant={v as any} size="sm">{status}</StatusBadge>;
}

function jobStatusBadge(status: string) {
  if (status === 'completed') return <StatusBadge variant="success" size="sm">Completed</StatusBadge>;
  if (status === 'failed') return <StatusBadge variant="danger" size="sm">Failed</StatusBadge>;
  if (status === 'processing') return <StatusBadge variant="info" size="sm">Running</StatusBadge>;
  return <StatusBadge variant="neutral" size="sm">{status}</StatusBadge>;
}

export const DataHealthDashboard: React.FC = () => {
  const isMountedRef = useRef(true);
  const { clientId } = useClient();
  const [data, setData] = useState<DataHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [classificationHealth, setClassificationHealth] = useState<any>(null);
  const [threadHealth, setThreadHealth] = useState<any>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [relinking, setRelinking] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    const load = async () => {
      setLoading(true);
      try {
        const result = await dataHealthApi.get(clientId);
        if (isMountedRef.current) setData(result);
      } catch { /* silent */ }
      finally { if (isMountedRef.current) setLoading(false); }
      // Load new health sections independently — don't block main data render
      try {
        const classHealth = await api.get<any>(`/v1/analytics/data-health/classification?client_id=${clientId}`);
        if (isMountedRef.current) setClassificationHealth(classHealth);
      } catch { /* silent */ }
      try {
        const thHealth = await api.get<any>(`/v1/analytics/data-health/threads?client_id=${clientId}`);
        if (isMountedRef.current) setThreadHealth(thHealth);
      } catch { /* silent */ }
    };
    load();
  }, [clientId]);

  const startBackfill = async () => {
    if (!clientId || backfilling) return;
    setBackfilling(true);
    try {
      await api.post(`/v1/ai/backfill-intent?client_id=${clientId}`);
      toast.success('Intent backfill started — this may take several minutes');
    } catch (err: any) {
      toast.error(err?.message || 'Failed to start backfill');
    } finally {
      setBackfilling(false);
    }
  };

  const startRelink = async () => {
    if (!clientId || relinking) return;
    setRelinking(true);
    try {
      await api.post(`/v1/analytics/extraction/backfill-email-links?client_id=${clientId}`);
      toast.success('Email re-linking started — this processes all emails for CC/BCC links');
    } catch (err: any) {
      toast.error(err?.message || 'Failed to start re-link');
    } finally {
      setRelinking(false);
    }
  };

  // Thread recompute state
  const [recomputing, setRecomputing] = useState(false);
  const [recomputeProgress, setRecomputeProgress] = useState<{ phase: string; pct: number; message: string; mailbox_errors?: any[] } | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startRecompute = async () => {
    if (!clientId || recomputing) return;
    setRecomputing(true);
    setRecomputeProgress({ phase: 'starting', pct: 0, message: 'Starting thread recompute...' });
    try {
      await api.post(`/v1/analytics/extraction/recompute-threads?client_id=${clientId}`);
      // Start polling for progress
      const poll = async () => {
        try {
          const prog = await api.get<any>(`/v1/analytics/extraction/thread-recompute-progress?client_id=${clientId}`);
          setRecomputeProgress(prog);
          if (prog.phase === 'completed' || prog.phase === 'completed_with_errors') {
            setRecomputing(false);
            setRecomputeProgress(prog); // Keep to show errors
            if (prog.phase === 'completed_with_errors') {
              toast.warning(prog.message || 'Completed with errors');
            } else {
              toast.success(prog.message || 'Thread recompute complete');
            }
            const result = await dataHealthApi.get(clientId);
            if (isMountedRef.current) setData(result);
            return;
          }
          if (prog.phase === 'failed') {
            setRecomputing(false);
            setRecomputeProgress(prog);
            toast.error(prog.message || 'Thread recompute failed');
            return;
          }
          pollRef.current = setTimeout(poll, 3000);
        } catch {
          pollRef.current = setTimeout(poll, 5000);
        }
      };
      pollRef.current = setTimeout(poll, 2000);
    } catch (err: any) {
      toast.error(err?.message || 'Failed to start recompute');
      setRecomputing(false);
      setRecomputeProgress(null);
    }
  };

  useEffect(() => {
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, []);

  const coveragePct = data?.identity_resolution?.coverage_percent ?? 0;
  const coverageColor = coveragePct >= 90 ? 'text-success' : coveragePct >= 70 ? 'text-warning' : 'text-destructive';

  const pieData = (data?.thread_distribution || []).map((t) => ({
    name: t.status.replace(/_/g, ' '),
    value: t.count,
    fill: THREAD_COLORS[t.status] || '#d1d5db',
  }));

  return (
    <PageShell>
      <PageHeader title="Data Health" description="Sync status, identity resolution, thread confidence, extraction jobs" />

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <MetricCard title="Mailboxes" value={data?.mailbox_health?.length ?? 0} prefix={<Database className="h-4 w-4 text-primary inline mr-1" />} loading={loading} />
        <MetricCard title="Identity Coverage" value={`${coveragePct}%`} loading={loading} />
        <MetricCard title="Missing Weekdays (30d)" value={data?.missing_weekday_count ?? 0} loading={loading} />
        <MetricCard title="Total Emails" value={data?.identity_resolution?.total_emails ?? 0} loading={loading} />
      </div>

      {/* Identity resolution bar */}
      {data && (
        <div className="rounded-lg border bg-white shadow-sm p-4 mb-4">
          <h3 className="text-sm font-semibold text-slate-900 mb-2">Identity Resolution</h3>
          <div className="h-2 rounded-full bg-slate-100 overflow-hidden mb-2">
            <div className={`h-full rounded-full transition-all ${coveragePct >= 90 ? 'bg-success' : coveragePct >= 70 ? 'bg-warning' : 'bg-destructive'}`}
              style={{ width: `${coveragePct}%` }} />
          </div>
          <p className="text-xs text-slate-600">
            {data.identity_resolution.resolved_emails.toLocaleString('en-AU')} / {data.identity_resolution.total_emails.toLocaleString('en-AU')} emails linked
          </p>
          {data.identity_resolution.unresolved_emails > 0 && (
            <p className="text-xs text-slate-400 mt-1">{data.identity_resolution.unresolved_emails.toLocaleString('en-AU')} emails not linked to any contact</p>
          )}
        </div>
      )}

      {/* Contact Links (junction table) coverage */}
      {data && (data as any).junction_coverage && (
        <div className="rounded-lg border bg-white shadow-sm p-4 mb-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-900">Contact Links (CC/BCC)</h3>
            <button
              onClick={startRelink}
              disabled={relinking || !clientId}
              className="h-7 px-3 text-xs font-medium rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5 disabled:opacity-50"
            >
              {relinking ? <Spinner className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              Re-link Emails
            </button>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-slate-500">Total Contact Links</p>
              <p className="text-lg font-semibold tabular-nums">{formatNumber((data as any).junction_coverage.total_links)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Total Emails</p>
              <p className="text-lg font-semibold tabular-nums">{formatNumber((data as any).junction_coverage.total_emails)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Avg Links / Email</p>
              <p className="text-lg font-semibold tabular-nums">{(data as any).junction_coverage.avg_links_per_email}</p>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-2">
            Each email can have multiple contact links (sender + recipients + CC/BCC). Re-link rebuilds all junction rows.
          </p>
        </div>
      )}

      {/* Mailbox health + Thread distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mb-4">
        <div className="lg:col-span-3 rounded-lg border bg-white shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b"><h3 className="text-sm font-semibold text-slate-900">Mailbox Health</h3></div>
          {loading ? <div className="p-4"><ContentSkeleton rows={4} /></div> : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50/50">
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Email</th>
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Provider</th>
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Last Sync</th>
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Last Extraction</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {(data?.mailbox_health || []).map(r => (
                  <tr key={r.mailbox_id}>
                    <td className="px-4 py-2 truncate">{r.email_address}</td>
                    <td className="px-4 py-2"><StatusBadge variant="neutral" size="sm">{r.provider}</StatusBadge></td>
                    <td className="px-4 py-2">{statusBadge(r.status)}</td>
                    <td className="px-4 py-2">{lagBadge(r.sync_lag_hours)}</td>
                    <td className="px-4 py-2">{lagBadge(r.extraction_lag_hours)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="lg:col-span-2">
          <ChartCard title="Thread Status Distribution" loading={loading} height={280}>
            {pieData.length > 0 ? (
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90}
                    label={(e) => `${e.name}: ${e.value}`}>
                    {pieData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-slate-400 text-center py-8">No thread data</p>
            )}
          </ChartCard>
        </div>
      </div>

      {/* Thread Health */}
      {data && (
        <div className="rounded-lg border bg-white shadow-sm p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <GitMerge className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold text-slate-900">Thread Health</h3>
            </div>
            <button
              onClick={startRecompute}
              disabled={recomputing || !clientId}
              className="h-7 px-3 text-xs font-medium rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5 disabled:opacity-50"
            >
              {recomputing ? <Spinner className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
              Recompute Threads
            </button>
          </div>

          {/* Progress bar */}
          {recomputing && recomputeProgress && (
            <div className="mb-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-slate-500">{recomputeProgress.message}</span>
                <span className="text-xs tabular-nums text-slate-400">{recomputeProgress.pct}%</span>
              </div>
              <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${recomputeProgress.pct}%` }}
                />
              </div>
            </div>
          )}

          {/* Thread stats */}
          {(() => {
            const th = (data as any).thread_health;
            if (!th) return null;
            const hasDupes = th.duplicate_rows > 0;
            return (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-slate-500">Total Rows</p>
                  <p className="text-lg font-semibold tabular-nums">{formatNumber(th.total_rows)}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Unique Threads</p>
                  <p className="text-lg font-semibold tabular-nums">{formatNumber(th.unique_threads)}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Duplicate Rows</p>
                  <p className={`text-lg font-semibold tabular-nums ${hasDupes ? 'text-destructive' : 'text-success'}`}>
                    {formatNumber(th.duplicate_rows)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Duplication Rate</p>
                  <p className={`text-lg font-semibold tabular-nums ${th.duplicate_pct > 5 ? 'text-destructive' : th.duplicate_pct > 0 ? 'text-warning' : 'text-success'}`}>
                    {th.duplicate_pct}%
                  </p>
                </div>
              </div>
            );
          })()}

          {/* Recompute errors */}
          {recomputeProgress?.mailbox_errors && recomputeProgress.mailbox_errors.length > 0 && !recomputing && (
            <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
              <div className="flex items-center gap-2 mb-2">
                <XCircle className="h-4 w-4 text-destructive" />
                <span className="text-xs font-medium text-destructive">
                  {recomputeProgress.mailbox_errors.length} mailbox(es) had errors during recompute
                </span>
              </div>
              <div className="space-y-1">
                {recomputeProgress.mailbox_errors.map((err: any, i: number) => (
                  <div key={i} className="flex items-center justify-between text-xs bg-white rounded px-2 py-1.5 border border-slate-100">
                    <span className="text-slate-600 font-mono">{err.mailbox_id?.slice(0, 8)}...</span>
                    <span className="text-slate-500">Fetched {formatNumber(err.emails_fetched)} emails before timeout at offset {formatNumber(err.offset)}</span>
                    <button
                      onClick={() => {
                        // TODO: Trigger per-mailbox recompute
                        toast.info('Per-mailbox recompute coming soon');
                      }}
                      className="text-primary hover:underline ml-2"
                    >
                      Retry
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Duplication warning */}
          {(data as any).thread_health?.duplicate_rows > 0 && !recomputing && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2">
              <AlertTriangle className="h-4 w-4 text-warning shrink-0" />
              <p className="text-xs text-slate-600">
                {formatNumber((data as any).thread_health.duplicate_rows)} duplicate thread rows detected.
                Click "Recompute Threads" to clean up and rebuild thread statuses.
              </p>
            </div>
          )}
        </div>
      )}

      {/* AI Classification Health */}
      {classificationHealth && (
        <div className="rounded-lg border bg-white shadow-sm p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold text-slate-900">AI Classification Health</h3>
            </div>
            <button
              onClick={startBackfill}
              disabled={backfilling || !clientId || (classificationHealth?.totals?.pending ?? 0) === 0}
              className="h-7 px-3 text-xs font-medium rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5 disabled:opacity-50"
            >
              {backfilling ? <Spinner className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
              Classify Pending ({formatNumber(classificationHealth?.totals?.pending ?? 0)})
            </button>
          </div>

          {/* Overall progress bar */}
          {(() => {
            const t = classificationHealth.totals;
            const pct = t?.coverage_pct ?? 0;
            return (
              <>
                <div className="h-2 rounded-full bg-slate-100 overflow-hidden mb-2">
                  <div className={`h-full rounded-full transition-all ${pct >= 90 ? 'bg-success' : pct >= 70 ? 'bg-warning' : 'bg-destructive'}`}
                    style={{ width: `${pct}%` }} />
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-3">
                  <div><p className="text-xs text-slate-500">Total Emails</p><p className="text-lg font-semibold tabular-nums">{formatNumber(t?.total_emails ?? 0)}</p></div>
                  <div><p className="text-xs text-slate-500">Classified</p><p className="text-lg font-semibold tabular-nums text-success">{formatNumber(t?.classified ?? 0)}</p></div>
                  <div><p className="text-xs text-slate-500">Pending</p><p className={`text-lg font-semibold tabular-nums ${(t?.pending ?? 0) > 0 ? 'text-warning' : 'text-success'}`}>{formatNumber(t?.pending ?? 0)}</p></div>
                  <div><p className="text-xs text-slate-500">Failed</p><p className={`text-lg font-semibold tabular-nums ${(t?.failed ?? 0) > 0 ? 'text-destructive' : 'text-success'}`}>{formatNumber(t?.failed ?? 0)}</p></div>
                  <div><p className="text-xs text-slate-500">Coverage</p><p className={`text-lg font-semibold tabular-nums ${pct >= 90 ? 'text-success' : pct >= 70 ? 'text-warning' : 'text-destructive'}`}>{pct}%</p></div>
                </div>
              </>
            );
          })()}

          {/* Per-mailbox breakdown */}
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-slate-50/50">
                <th className="px-3 py-1.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Mailbox</th>
                <th className="px-3 py-1.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Total</th>
                <th className="px-3 py-1.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Classified</th>
                <th className="px-3 py-1.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Pending</th>
                <th className="px-3 py-1.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Failed</th>
                <th className="px-3 py-1.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Coverage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {(classificationHealth.mailboxes || []).map((mb: any) => (
                <tr key={mb.mailbox_id}>
                  <td className="px-3 py-1.5 truncate">{mb.email_address}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{formatNumber(mb.total_emails)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-success">{formatNumber(mb.classified)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{mb.pending > 0 ? <span className="text-warning">{formatNumber(mb.pending)}</span> : '0'}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{mb.failed > 0 ? <span className="text-destructive">{formatNumber(mb.failed)}</span> : '0'}</td>
                  <td className="px-3 py-1.5 text-right">
                    <StatusBadge variant={mb.coverage_pct >= 90 ? 'success' : mb.coverage_pct >= 70 ? 'warning' : 'danger'} size="sm">{mb.coverage_pct}%</StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Thread Intent Coverage */}
      {threadHealth && (
        <div className="rounded-lg border bg-white shadow-sm p-4 mb-4">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-slate-900">Thread Intent Coverage</h3>
          </div>

          {/* Intent coverage bar */}
          {(() => {
            const t = threadHealth.totals;
            const pct = t?.intent_coverage_pct ?? 0;
            return (
              <>
                <div className="h-2 rounded-full bg-slate-100 overflow-hidden mb-2">
                  <div className={`h-full rounded-full transition-all ${pct >= 80 ? 'bg-success' : pct >= 50 ? 'bg-warning' : 'bg-destructive'}`}
                    style={{ width: `${pct}%` }} />
                </div>
                <p className="text-xs text-slate-600 mb-3">
                  {formatNumber(t?.with_intent ?? 0)} / {formatNumber(t?.total_threads ?? 0)} threads have intent classification ({pct}%)
                </p>
              </>
            );
          })()}

          {/* Intent distribution */}
          {threadHealth.intent_distribution && Object.keys(threadHealth.intent_distribution).length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {Object.entries(threadHealth.intent_distribution).map(([intent, count]) => {
                const v = intent === 'urgent' ? 'danger' : intent === 'escalation' ? 'warning' : intent === 'revenue_opportunity' ? 'success' : intent === 'closing' ? 'info' : 'neutral';
                return (
                  <StatusBadge key={intent} variant={v as any} size="sm">
                    {intent.replace(/_/g, ' ')}: {formatNumber(count as number)}
                  </StatusBadge>
                );
              })}
            </div>
          )}

          {/* Per-mailbox intent coverage */}
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-slate-50/50">
                <th className="px-3 py-1.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Mailbox</th>
                <th className="px-3 py-1.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Threads</th>
                <th className="px-3 py-1.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-28">With Intent</th>
                <th className="px-3 py-1.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Coverage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {(threadHealth.mailboxes || []).map((mb: any) => (
                <tr key={mb.mailbox_id}>
                  <td className="px-3 py-1.5 truncate">{mb.email_address}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{formatNumber(mb.thread_count)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-success">{formatNumber(mb.with_intent)}</td>
                  <td className="px-3 py-1.5 text-right">
                    <StatusBadge variant={mb.intent_coverage_pct >= 80 ? 'success' : mb.intent_coverage_pct >= 50 ? 'warning' : 'danger'} size="sm">
                      {mb.intent_coverage_pct}%
                    </StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Missing weekdays alert */}
      {data && data.missing_weekdays.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 mb-4">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="h-4 w-4 text-warning" />
            <span className="text-sm font-medium">{data.missing_weekdays.length} weekday(s) with no email data in the last 30 days</span>
          </div>
          <p className="text-xs text-slate-600">{data.missing_weekdays.join(', ')}</p>
        </div>
      )}

      {/* Recent extraction jobs */}
      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b"><h3 className="text-sm font-semibold text-slate-900">Recent Extraction Jobs</h3></div>
        {loading ? <div className="p-4"><ContentSkeleton rows={4} /></div> : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-slate-50/50">
                <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Status</th>
                <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Mode</th>
                <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-40">Progress</th>
                <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Started</th>
                <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Errors</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {(data?.recent_extraction_jobs || []).map(r => {
                const pct = r.total_emails ? Math.round(((r.processed_emails || 0) / r.total_emails) * 100) : 0;
                return (
                  <tr key={r.id}>
                    <td className="px-4 py-2">{jobStatusBadge(r.status)}</td>
                    <td className="px-4 py-2"><StatusBadge variant="neutral" size="sm">{r.extraction_mode}</StatusBadge></td>
                    <td className="px-4 py-2">
                      {r.total_emails ? (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 rounded-full bg-slate-100 overflow-hidden">
                            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs tabular-nums text-slate-500">{pct}%</span>
                        </div>
                      ) : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-4 py-2 text-slate-500">{r.started_at ? new Date(r.started_at).toLocaleString('en-AU') : '—'}</td>
                    <td className="px-4 py-2">
                      {r.errors && r.errors.length > 0 ? <span className="text-xs text-destructive">{r.errors.length} error(s)</span> : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </PageShell>
  );
};
