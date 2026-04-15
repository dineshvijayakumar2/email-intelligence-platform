/**
 * Live Log Monitor — Real-time log viewer with filtering. Zero antd.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../../services/apiClient';
import { formatTime } from '../../utils/dateUtils';
import { PageShell } from '@/components/ui/page-shell';
import { cn } from '@/lib/utils';
import { RefreshCw, Play, Pause, Trash2, Search } from 'lucide-react';
import { StatusBadge } from '@/components/ui/status-badge';

interface LogEntry {
  ts: string; level: string; service: string; message: string;
  mailbox_id?: string; client_id?: string; job_id?: string; step?: string;
}

const LEVEL_VARIANT: Record<string, 'danger' | 'warning' | 'info' | 'neutral'> = {
  ERROR: 'danger', CRITICAL: 'danger', WARNING: 'warning', INFO: 'info', DEBUG: 'neutral',
};

const POLL_OPTIONS = [
  { value: 1000, label: '1s' }, { value: 3000, label: '3s' }, { value: 5000, label: '5s' },
  { value: 10000, label: '10s' }, { value: 30000, label: '30s' },
];

export default function LogMonitorPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [paused, setPaused] = useState(false);
  const [pollInterval, setPollInterval] = useState(3000);
  const [levelFilter, setLevelFilter] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');
  const [searchFilter, setSearchFilter] = useState('');
  const [services, setServices] = useState<string[]>([]);
  const [mailboxNames, setMailboxNames] = useState<Record<string, string>>({});
  const [clientNames, setClientNames] = useState<Record<string, string>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.get('/v1/logs/services').then((d: any) => setServices(d?.services || [])).catch(() => {});
    api.get('/v1/logs/context').then((d: any) => { setMailboxNames(d?.mailboxes || {}); setClientNames(d?.clients || {}); }).catch(() => {});
  }, []);

  const fetchLogs = useCallback(async () => {
    if (paused) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (levelFilter) params.set('level', levelFilter);
      if (serviceFilter) params.set('service', serviceFilter);
      if (searchFilter) params.set('search', searchFilter);
      const data = await api.get(`/v1/logs/recent?${params}`) as { logs: LogEntry[] };
      setLogs(data.logs || []);
    } catch {} finally { setLoading(false); }
  }, [paused, levelFilter, serviceFilter, searchFilter]);

  useEffect(() => {
    fetchLogs();
    pollRef.current = setInterval(fetchLogs, pollInterval);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchLogs, pollInterval]);

  const errorCount = logs.filter(l => l.level === 'ERROR' || l.level === 'CRITICAL').length;
  const warnCount = logs.filter(l => l.level === 'WARNING').length;

  return (
    <PageShell maxWidth="1600px">
      {/* Header + controls */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-slate-900">Live Log Monitor</h1>
          {errorCount > 0 && <StatusBadge variant="danger">{errorCount} errors</StatusBadge>}
          {warnCount > 0 && <StatusBadge variant="warning">{warnCount} warnings</StatusBadge>}
          {paused && <StatusBadge variant="warning">Paused</StatusBadge>}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select value={levelFilter} onChange={e => setLevelFilter(e.target.value)}
            className="h-7 px-2 text-xs rounded border border-slate-200 bg-white">
            <option value="">All Levels</option>
            {['ERROR', 'WARNING', 'INFO', 'DEBUG'].map(l => <option key={l} value={l}>{l}</option>)}
          </select>
          <select value={serviceFilter} onChange={e => setServiceFilter(e.target.value)}
            className="h-7 px-2 text-xs rounded border border-slate-200 bg-white max-w-[140px]">
            <option value="">All Services</option>
            {services.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400" />
            <input type="text" placeholder="Search..." value={searchFilter} onChange={e => setSearchFilter(e.target.value)}
              className="h-7 pl-7 pr-2 text-xs rounded border border-slate-200 bg-white w-40 focus:outline-none focus:ring-1 focus:ring-primary/20" />
          </div>
          <select value={pollInterval} onChange={e => setPollInterval(Number(e.target.value))}
            className="h-7 px-2 text-xs rounded border border-slate-200 bg-white w-16">
            {POLL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <button onClick={() => setPaused(!paused)} className={cn('h-7 px-2 text-xs rounded border inline-flex items-center gap-1', paused ? 'bg-primary text-white border-primary' : 'border-slate-200 hover:bg-slate-50')}>
            {paused ? <><Play className="h-3 w-3" />Resume</> : <><Pause className="h-3 w-3" />Pause</>}
          </button>
          <button onClick={fetchLogs} className="h-7 px-2 text-xs rounded border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1">
            <RefreshCw className={cn('h-3 w-3', loading && 'animate-spin')} />
          </button>
          <button onClick={() => setLogs([])} className="h-7 px-2 text-xs rounded border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1">
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* Log table */}
      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        <div className="overflow-auto" style={{ maxHeight: 'calc(100vh - 180px)' }}>
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10">
              <tr className="bg-slate-50 border-b">
                <th className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600 w-20">Time</th>
                <th className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600 w-16">Level</th>
                <th className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600 w-28">Service</th>
                <th className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600">Message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {logs.map((log, i) => (
                <tr key={i} className={cn(
                  (log.level === 'ERROR' || log.level === 'CRITICAL') && 'bg-destructive-subtle',
                  log.level === 'WARNING' && 'bg-warning-subtle',
                )}>
                  <td className="px-3 py-1.5 font-mono text-slate-500">{formatTime(log.ts)}</td>
                  <td className="px-3 py-1.5"><StatusBadge variant={LEVEL_VARIANT[log.level] || 'neutral'} size="sm">{log.level}</StatusBadge></td>
                  <td className="px-3 py-1.5 font-mono text-slate-600">{log.service}</td>
                  <td className="px-3 py-1.5 text-slate-700">
                    {log.message}
                    {(log.step || log.job_id || log.mailbox_id || log.client_id) && (
                      <div className="flex gap-1 mt-0.5">
                        {log.step && <span className="inline-flex px-1 text-[10px] rounded bg-slate-100 text-slate-500">Step {log.step}</span>}
                        {log.job_id && <span className="inline-flex px-1 text-[10px] rounded bg-primary-subtle text-primary">Job: {log.job_id.slice(0, 8)}</span>}
                        {log.mailbox_id && <span className="inline-flex px-1 text-[10px] rounded bg-slate-100 text-slate-500">{mailboxNames[log.mailbox_id] || `MB: ${log.mailbox_id.slice(0, 8)}`}</span>}
                        {log.client_id && <span className="inline-flex px-1 text-[10px] rounded bg-success-subtle text-success">{clientNames[log.client_id] || `Client: ${log.client_id.slice(0, 8)}`}</span>}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr><td colSpan={4} className="px-3 py-8 text-center text-slate-400">No logs</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </PageShell>
  );
}
