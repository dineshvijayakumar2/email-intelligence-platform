import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import api from '../services/apiClient';
import { formatDateTime } from '../utils/dateUtils';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { KPICard, KPIStrip } from '@/components/ui/kpi-card';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { cn } from '@/lib/utils';
import { toast } from '@/lib/toast';
import { Search, RefreshCw, Download, X, ChevronLeft, ChevronRight, Clock, Zap, FileText, User } from 'lucide-react';

interface AuditLogEntry {
  id: string; user_id: string | null; user_email: string | null;
  action: string; resource_type: string; resource_id: string | null;
  details: Record<string, unknown> | null; ip_address: string | null; created_at: string;
}
interface AuditLogResponse { data: AuditLogEntry[]; total: number; page: number; page_size: number; }
interface AuditLogStats {
  total_entries: number; actions: { name: string; count: number }[];
  resource_types: { name: string; count: number }[]; active_users: { email: string; count: number }[];
}

const AuditLogsPage: React.FC = () => {
  const isMountedRef = useRef(true);
  const [data, setData] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const [actionFilter, setActionFilter] = useState('');
  const [resourceFilter, setResourceFilter] = useState('');
  const [searchText, setSearchText] = useState('');
  const [stats, setStats] = useState<AuditLogStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { page, page_size: pageSize };
      if (actionFilter) params.action = actionFilter;
      if (resourceFilter) params.resource_type = resourceFilter;
      if (searchText) params.search = searchText;
      const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
      const result = await api.get<AuditLogResponse>(`/auth/audit-logs?${qs}`);
      if (isMountedRef.current) { setData(result.data); setTotal(result.total); }
    } catch {} finally { if (isMountedRef.current) setLoading(false); }
  }, [page, actionFilter, resourceFilter, searchText]);

  const fetchStats = useCallback(async () => {
    setStatsLoading(true);
    try { const r = await api.get<AuditLogStats>('/auth/audit-logs/stats?days=30'); if (isMountedRef.current) setStats(r); }
    catch {} finally { if (isMountedRef.current) setStatsLoading(false); }
  }, []);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  const actionOptions = useMemo(() => (stats?.actions || []).map(a => ({ value: a.name, label: `${a.name.replace(/_/g, ' ')} (${a.count})` })), [stats]);
  const resourceOptions = useMemo(() => (stats?.resource_types || []).map(r => ({ value: r.name, label: `${r.name.replace(/_/g, ' ')} (${r.count})` })), [stats]);

  const exportCSV = () => {
    if (!data.length) { toast.warning('No data'); return; }
    const cols = ['created_at', 'action', 'resource_type', 'resource_id', 'user_email', 'details'];
    const rows = data.map(row => cols.map(col => { const v = row[col as keyof AuditLogEntry]; return v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v); }).join(','));
    const blob = new Blob(['\uFEFF' + [cols.join(','), ...rows].join('\n')], { type: 'text/csv' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = `audit_logs_${new Date().toISOString().split('T')[0]}.csv`; a.click();
    toast.success(`Exported ${data.length} entries`);
  };

  const hasFilters = !!actionFilter || !!resourceFilter || !!searchText;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <PageShell>
      <PageHeader title="Audit Logs" description="Security and activity audit trail" />

      {/* Stats */}
      <KPIStrip className="mb-4">
        <KPICard title="Total (30d)" value={stats?.total_entries ?? 0} loading={statsLoading} />
        <KPICard title="Action Types" value={stats?.actions?.length ?? 0} loading={statsLoading} />
        <KPICard title="Resource Types" value={stats?.resource_types?.length ?? 0} loading={statsLoading} />
        <KPICard title="Active Users" value={stats?.active_users?.length ?? 0} loading={statsLoading} />
      </KPIStrip>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input type="text" placeholder="Search..." value={searchText}
            onChange={e => { setSearchText(e.target.value); setPage(1); }}
            className="h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-48" />
        </div>
        <select value={actionFilter} onChange={e => { setActionFilter(e.target.value); setPage(1); }}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
          <option value="">All Actions</option>
          {actionOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={resourceFilter} onChange={e => { setResourceFilter(e.target.value); setPage(1); }}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
          <option value="">All Resources</option>
          {resourceOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {hasFilters && (
          <button onClick={() => { setActionFilter(''); setResourceFilter(''); setSearchText(''); setPage(1); }}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><X className="h-3 w-3" />Clear</button>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => { fetchLogs(); fetchStats(); }} className="h-8 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" />Refresh
          </button>
          <button onClick={exportCSV} className="h-8 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5">
            <Download className="h-3.5 w-3.5" />Export
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        {loading && data.length === 0 ? <ContentSkeleton rows={8} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50/50">
                  <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-40">Time</th>
                  <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-32">Action</th>
                  <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Resource</th>
                  <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-36">Resource ID</th>
                  <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-44">User</th>
                  <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {data.map(row => (
                  <tr key={row.id} className="hover:bg-slate-50/50">
                    <td className="px-3 py-2 text-xs text-slate-500">{formatDateTime(row.created_at)}</td>
                    <td className="px-3 py-2 text-xs text-slate-700">{row.action.replace(/_/g, ' ')}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{row.resource_type?.replace(/_/g, ' ') || '—'}</td>
                    <td className="px-3 py-2 text-xs font-mono text-slate-400 truncate max-w-[140px]">{row.resource_id?.slice(0, 12) || '—'}</td>
                    <td className="px-3 py-2 text-xs text-slate-600">{row.user_email || 'system'}</td>
                    <td className="px-3 py-2 text-xs text-slate-400 truncate max-w-[200px]" title={row.details ? JSON.stringify(row.details) : undefined}>
                      {row.details && Object.keys(row.details).length > 0 ? JSON.stringify(row.details).slice(0, 80) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {total > pageSize && (
          <div className="flex items-center justify-between px-4 py-3 border-t bg-slate-50/30">
            <span className="text-xs text-slate-500">{total.toLocaleString()} entries</span>
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
              <span className="text-xs text-slate-600 px-2 tabular-nums">{page} / {totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
            </div>
          </div>
        )}
      </div>

      {/* Active users */}
      {stats && stats.active_users.length > 0 && (
        <div className="rounded-lg border bg-white shadow-sm p-4 mt-4">
          <h3 className="text-sm font-bold text-slate-900 mb-2">Most Active Users (30d)</h3>
          <div className="flex flex-wrap gap-1.5">
            {stats.active_users.map(u => (
              <button key={u.email} onClick={() => { setSearchText(u.email); setPage(1); }}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors">
                <User className="h-3 w-3" />{u.email.split('@')[0]} ({u.count})
              </button>
            ))}
          </div>
        </div>
      )}
    </PageShell>
  );
};

export default AuditLogsPage;
