import React, { useState, useEffect, useRef } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { useClient } from '../../contexts/ClientContext';
import { MetricCard } from '../../components/analytics/MetricCard';
import { ChartCard } from '../../components/analytics/ChartCard';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import {
  dataHealthApi,
  type MailboxHealth,
  type DataHealthResponse,
  type ExtractionJobHealth,
} from '../../services/analyticsService';
import { CheckCircle, AlertTriangle, XCircle, RefreshCw, Database } from 'lucide-react';

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
  const [loading, setLoading] = useState(false);

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
    };
    load();
  }, [clientId]);

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
