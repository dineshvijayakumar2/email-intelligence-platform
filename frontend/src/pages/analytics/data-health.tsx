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
import { CheckCircle, AlertTriangle, XCircle, RefreshCw, Database, GitMerge, Brain, Zap, Download } from 'lucide-react';

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
  const [fetchingMissing, setFetchingMissing] = useState(false);
  const [fetchMissingResult, setFetchMissingResult] = useState<any>(null);

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

  const fetchMissingDates = async (startDate: string, endDate: string) => {
    if (!clientId || fetchingMissing) return;
    setFetchingMissing(true);
    setFetchMissingResult(null);
    try {
      const result = await api.post<any>('/v1/analytics/data-health/fetch-missing-dates', {
        client_id: clientId,
        start_date: startDate,
        end_date: endDate,
      });
      setFetchMissingResult(result);
      toast.success(`Fetch started — ${result.jobs_started} mailbox job(s) queued`);
    } catch (err: any) {
      toast.error(err?.message || 'Failed to start fetch');
    } finally {
      setFetchingMissing(false);
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

      {/* Missing weekdays alert + fetch action */}
      {data && data.missing_weekdays.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-4 mb-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle className="h-4 w-4 text-warning shrink-0" />
                <span className="text-sm font-medium">{data.missing_weekdays.length} weekday(s) with no email data in the last 30 days</span>
              </div>
              <p className="text-xs text-slate-600 mb-2">{data.missing_weekdays.join(', ')}</p>
              <p className="text-xs text-slate-400">
                These dates may have emails in Gmail/Outlook that were never fetched. Click "Fetch Missing" to pull them for all mailboxes.
              </p>
            </div>
            <button
              onClick={() => {
                const sorted = [...data.missing_weekdays].sort();
                fetchMissingDates(sorted[0], sorted[sorted.length - 1]);
              }}
              disabled={fetchingMissing || !clientId}
              className="h-8 px-3 text-xs font-medium rounded-md bg-warning text-white hover:bg-warning/90 inline-flex items-center gap-1.5 disabled:opacity-50 shrink-0"
            >
              {fetchingMissing ? <Spinner className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
              Fetch Missing
            </button>
          </div>

          {/* Result summary */}
          {fetchMissingResult && (
            <div className="mt-3 pt-3 border-t border-warning/20">
              <p className="text-xs font-medium text-slate-700 mb-1">
                {fetchMissingResult.jobs_started} job(s) started for {fetchMissingResult.start_date} → {fetchMissingResult.end_date}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(fetchMissingResult.jobs || []).map((j: any) => (
                  <StatusBadge key={j.job_id} variant="info" size="sm">
                    {j.email} ({j.provider})
                  </StatusBadge>
                ))}
                {(fetchMissingResult.skipped || []).map((s: any) => (
                  <StatusBadge key={s.mailbox_id} variant="neutral" size="sm">
                    {s.email} — {s.reason}
                  </StatusBadge>
                ))}
              </div>
            </div>
          )}
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

      {/* Database Performance Monitor */}
      <DbPerformancePanel />
    </PageShell>
  );
};


/* ------------------------------------------------------------------ */
/* Database Performance Monitor                                        */
/* ------------------------------------------------------------------ */

interface SlowQuery {
  query: string;
  calls: number;
  total_time_s: number;
  mean_time_ms: number;
  max_time_ms: number;
  rows: number;
  rows_per_call: number;
}

interface TableStat {
  table_name: string;
  row_estimate: number;
  total_size: string;
  total_bytes: number;
  table_size: string;
  index_size: string;
}

interface IndexStat {
  table_name: string;
  index_name: string;
  index_scans: number;
  rows_read: number;
  rows_fetched: number;
  index_size: string;
}

interface CacheStats {
  heap_hit_ratio: number;
  index_hit_ratio: number;
  db_size: string;
  db_size_bytes: number;
}

interface DbPerf {
  slow_queries: SlowQuery[];
  table_stats: TableStat[];
  index_stats: IndexStat[];
  cache_stats: CacheStats;
}

const DbPerformancePanel: React.FC = () => {
  const [data, setData] = useState<DbPerf | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<'queries' | 'tables' | 'indexes'>('queries');

  const load = async () => {
    setLoading(true);
    try {
      const resp = await api.get<DbPerf>('/v1/analytics/data-health/db-performance');
      if (resp) setData(resp);
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const cache = data?.cache_stats;
  const heapPct = cache?.heap_hit_ratio ?? 0;
  const idxPct = cache?.index_hit_ratio ?? 0;
  const heapColor = heapPct >= 99 ? 'text-emerald-600' : heapPct >= 95 ? 'text-amber-600' : 'text-red-600';
  const idxColor = idxPct >= 99 ? 'text-emerald-600' : idxPct >= 95 ? 'text-amber-600' : 'text-red-600';

  /** Turn raw seconds into "9.5h", "12m", "3.2s" */
  const fmtTime = (s: number) => {
    if (s >= 3600) return `${(s / 3600).toFixed(1)}h`;
    if (s >= 60) return `${(s / 60).toFixed(1)}m`;
    return `${s.toFixed(1)}s`;
  };

  /** Turn avg ms into "1.4s", "467ms" */
  const fmtMs = (ms: number) => ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;

  /** Extract a human-readable label from PostgREST-wrapped SQL */
  const queryLabel = (q: string): { name: string; op: string } => {
    // RPC call — extract function name
    const funcMatch = q.match(/"public"\."(\w+)"\(/);
    if (funcMatch) return { name: funcMatch[1].replace(/_/g, ' '), op: 'RPC' };
    // Table operation — extract table + detect SELECT/INSERT/UPDATE
    const tableMatch = q.match(/"public"\."(\w+)"/);
    const table = tableMatch ? tableMatch[1] : '?';
    if (q.includes('INSERT')) return { name: table, op: 'INSERT' };
    if (q.includes('UPDATE')) return { name: table, op: 'UPDATE' };
    if (q.includes('DELETE')) return { name: table, op: 'DELETE' };
    if (q.includes('count')) return { name: table, op: 'COUNT' };
    return { name: table, op: 'SELECT' };
  };

  /** Severity badge for total cumulative time */
  const timeBadge = (s: number) => {
    if (s >= 3600) return 'bg-red-100 text-red-700';
    if (s >= 600) return 'bg-amber-100 text-amber-700';
    if (s >= 60) return 'bg-blue-50 text-blue-700';
    return 'bg-slate-50 text-slate-600';
  };

  /** Operation type badge color */
  const opColor = (op: string) => {
    if (op === 'RPC') return 'bg-purple-100 text-purple-700';
    if (op === 'INSERT' || op === 'UPDATE') return 'bg-amber-50 text-amber-700';
    if (op === 'COUNT') return 'bg-cyan-50 text-cyan-700';
    return 'bg-slate-50 text-slate-600';
  };

  return (
    <div className="rounded-lg border bg-white shadow-sm overflow-hidden mt-6">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-indigo-500" />
          <h3 className="text-sm font-semibold text-slate-900">Database Performance</h3>
        </div>
        <div className="flex items-center gap-3">
          {cache && (
            <div className="flex items-center gap-4 text-xs">
              <span className="text-slate-500" title="Data pages served from RAM vs disk. Below 95% means heavy disk reads.">
                Data from RAM: <span className={`font-semibold ${heapColor}`}>{heapPct}%</span>
              </span>
              <span className="text-slate-500" title="Index lookups served from RAM vs disk. Below 95% means indexes don't fit in memory.">
                Index from RAM: <span className={`font-semibold ${idxColor}`}>{idxPct}%</span>
              </span>
              <span className="text-slate-500">DB: <span className="font-semibold text-slate-700">{cache.db_size}</span></span>
            </div>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 shadow-sm hover:bg-slate-50 transition disabled:opacity-50"
          >
            {loading ? <Spinner className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            Refresh
          </button>
        </div>
      </div>

      {/* Cache health alert */}
      {cache && (heapPct < 95 || idxPct < 95) && (
        <div className="px-4 py-2 bg-amber-50 border-b border-amber-100 text-xs text-amber-800">
          <AlertTriangle className="h-3.5 w-3.5 inline mr-1.5 -mt-0.5" />
          {heapPct < 95 && <>Only {heapPct}% of data reads come from RAM (target: 99%+). Your DB is reading heavily from disk — this burns Supabase IO budget. </>}
          {idxPct < 95 && <>Only {idxPct}% of index lookups are cached (target: 99%+). Consider adding missing indexes or upgrading compute. </>}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b">
        {(['queries', 'tables', 'indexes'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-xs font-medium transition ${
              tab === t
                ? 'text-indigo-600 border-b-2 border-indigo-600'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {t === 'queries' ? 'Slow Queries' : t === 'tables' ? 'Table Sizes' : 'Index Usage'}
          </button>
        ))}
      </div>

      <div className="p-0">
        {loading && !data ? (
          <div className="p-4"><ContentSkeleton rows={5} /></div>
        ) : tab === 'queries' ? (
          <>
          <p className="px-3 py-2 text-[11px] text-slate-400 border-b border-slate-50">
            Cumulative query time since last DB restart. Red = over 1 hour total, amber = over 10 minutes. High "calls" with high "avg" = optimization target.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-slate-50/50">
                  <th className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600 w-14">Type</th>
                  <th className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600">Target</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-20">Calls</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-24">Total Time</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-20">Avg</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-20">Max</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {(data?.slow_queries || []).map((q, i) => {
                  const { name, op } = queryLabel(q.query);
                  return (
                    <tr key={i} className="hover:bg-slate-25" title={q.query}>
                      <td className="px-3 py-1.5">
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold ${opColor(op)}`}>{op}</span>
                      </td>
                      <td className="px-3 py-1.5 text-slate-700 font-medium truncate max-w-[280px]">{name}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">{q.calls.toLocaleString()}</td>
                      <td className="px-3 py-1.5 text-right">
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[11px] font-semibold tabular-nums ${timeBadge(q.total_time_s)}`}>
                          {fmtTime(q.total_time_s)}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">{fmtMs(q.mean_time_ms)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{fmtMs(q.max_time_ms)}</td>
                    </tr>
                  );
                })}
                {(!data?.slow_queries?.length) && (
                  <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-400">No query stats available — run migration 067 first</td></tr>
                )}
              </tbody>
            </table>
          </div>
          </>
        ) : tab === 'tables' ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-slate-50/50">
                  <th className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600">Table</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-28">Rows (est.)</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-24">Total Size</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-24">Data</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-24">Indexes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {(data?.table_stats || []).map((t, i) => (
                  <tr key={i} className="hover:bg-slate-25">
                    <td className="px-3 py-1.5 font-mono text-slate-700">{t.table_name}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">{t.row_estimate.toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums font-semibold text-slate-700">{t.total_size}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">{t.table_size}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">{t.index_size}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <>
          <p className="px-3 py-2 text-[11px] text-slate-400 border-b border-slate-50">
            Indexes sorted by usage (least used first). Unused indexes waste disk space and slow down writes. Heavily used indexes are working well.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-slate-50/50">
                  <th className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600">Table</th>
                  <th className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600">Index</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-24">Scans</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-24">Rows Read</th>
                  <th className="px-3 py-2 text-right font-bold uppercase tracking-wider text-slate-600 w-20">Size</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {(data?.index_stats || []).map((idx, i) => {
                  const unused = idx.index_scans === 0;
                  return (
                    <tr key={i} className={`hover:bg-slate-25 ${unused ? 'bg-red-50/50' : ''}`}>
                      <td className="px-3 py-1.5 font-mono text-slate-600">{idx.table_name}</td>
                      <td className="px-3 py-1.5 font-mono text-slate-700">
                        {idx.index_name}
                        {unused && <span className="ml-2 text-[10px] text-red-500 font-semibold">UNUSED</span>}
                      </td>
                      <td className={`px-3 py-1.5 text-right tabular-nums ${unused ? 'text-red-600 font-semibold' : 'text-slate-600'}`}>
                        {idx.index_scans.toLocaleString()}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">{idx.rows_read.toLocaleString()}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">{idx.index_size}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          </>
        )}
      </div>
    </div>
  );
};
