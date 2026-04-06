import React, { useState, useEffect, useRef } from 'react';
import { mailboxService, Mailbox } from '../services/mailboxService';
import { extractionApi, clearAnalyticsCache } from '../services/analyticsService';
import type { ExtractionJobResponse, ExtractionProgressResponse } from '../types/analytics';
import { formatDateTime } from '../utils/dateUtils';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { Rocket, Square, RefreshCw } from 'lucide-react';
import { toast } from '@/lib/toast';

const PAGE_SIZE = 20;

export const ExtractionManagement: React.FC = () => {
  const isMountedRef = useRef(true);
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [jobs, setJobs] = useState<ExtractionJobResponse[]>([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeProgress, setActiveProgress] = useState<Record<string, ExtractionProgressResponse>>({});
  const [resyncing, setResyncing] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // Form state
  const [mailboxId, setMailboxId] = useState('');
  const [mode, setMode] = useState<'full' | 'incremental'>('full');
  const [lookbackDays, setLookbackDays] = useState(7);
  const [exclLists, setExclLists] = useState(true);
  const [exclNoreply, setExclNoreply] = useState(true);
  const [exclInternal, setExclInternal] = useState(true);

  useEffect(() => {
    isMountedRef.current = true;
    loadMailboxes();
    loadJobs();
    return () => { isMountedRef.current = false; if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  useEffect(() => { loadJobs(); }, [page]);

  const loadMailboxes = async () => {
    const mbs = await mailboxService.getMailboxes();
    if (isMountedRef.current) setMailboxes(mbs);
  };

  const loadJobs = async () => {
    setLoading(true);
    const result = await extractionApi.listJobs({ limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
    if (isMountedRef.current) {
      setJobs(result.jobs); setJobsTotal(result.total); setLoading(false);
      const activeJobs = result.jobs.filter(j => ['pending', 'processing'].includes(j.status));
      if (activeJobs.length > 0) startPolling(activeJobs.map(j => j.id));
      else stopPolling();
    }
  };

  const startPolling = (jobIds: string[]) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      const updates: Record<string, ExtractionProgressResponse> = {};
      for (const id of jobIds) { const p = await extractionApi.getProgress(id); if (p) updates[id] = p; }
      if (isMountedRef.current) {
        setActiveProgress(updates);
        if (Object.values(updates).some(p => !['pending', 'processing'].includes(p.status))) { loadJobs(); clearAnalyticsCache(); }
      }
    }, 3000);
  };

  const stopPolling = () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mailboxId) { toast.warning('Select a mailbox'); return; }
    setSubmitting(true);
    const result = await extractionApi.run({
      mailbox_id: mailboxId, mode, lookback_days: lookbackDays,
      exclude_mailing_lists: exclLists, exclude_noreply: exclNoreply, exclude_internal: exclInternal,
    });
    if (result) { toast.success(`Extraction started! Job ID: ${result.id}`); loadJobs(); }
    else toast.error('Failed to start extraction');
    setSubmitting(false);
  };

  const handleCancel = async (jobId: string) => {
    const result = await extractionApi.cancelJob(jobId);
    if (result) { toast.success('Job cancelled'); loadJobs(); }
    else toast.error('Failed to cancel');
  };

  const handleResync = async () => {
    if (!mailboxId) { toast.warning('Select a mailbox first'); return; }
    const mb = mailboxes.find(m => m.id === mailboxId);
    if (mb && !['outlook_live', 'outlook'].includes(mb.mailbox_type)) {
      toast.warning('Metadata re-sync is only available for Outlook'); return;
    }
    setResyncing(true);
    try { await mailboxService.resyncMetadata(mailboxId); toast.success('Metadata re-sync started'); }
    catch { toast.error('Failed to start re-sync'); }
    finally { setResyncing(false); }
  };

  return (
    <PageShell>
      <PageHeader title="Extraction Management" description="Run contact extraction jobs and monitor progress" />

      {/* Trigger form */}
      <div className="rounded-lg border bg-white shadow-sm p-5 mb-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Run Extraction</h2>
        <form onSubmit={handleSubmit} className="flex items-end gap-3 flex-wrap">
          <div>
            <label className="text-xs font-medium text-slate-500 block mb-1">Mailbox</label>
            <select value={mailboxId} onChange={e => setMailboxId(e.target.value)}
              className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 min-w-[200px]">
              <option value="">Select mailbox...</option>
              {mailboxes.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 block mb-1">Mode</label>
            <div className="flex rounded-md border border-slate-200 overflow-hidden">
              <button type="button" onClick={() => setMode('full')}
                className={`px-3 py-1.5 text-sm ${mode === 'full' ? 'bg-primary text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>Full</button>
              <button type="button" onClick={() => setMode('incremental')}
                className={`px-3 py-1.5 text-sm border-l ${mode === 'incremental' ? 'bg-primary text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>Incremental</button>
            </div>
          </div>
          {mode === 'incremental' && (
            <div>
              <label className="text-xs font-medium text-slate-500 block mb-1">Days: {lookbackDays}</label>
              <input type="range" min={1} max={365} value={lookbackDays} onChange={e => setLookbackDays(Number(e.target.value))} className="w-28" />
            </div>
          )}
          <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={exclLists} onChange={e => setExclLists(e.target.checked)} className="rounded" />Excl Lists</label>
          <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={exclNoreply} onChange={e => setExclNoreply(e.target.checked)} className="rounded" />Excl NoReply</label>
          <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={exclInternal} onChange={e => setExclInternal(e.target.checked)} className="rounded" />Excl Internal</label>
          <button type="submit" disabled={submitting}
            className="h-9 px-4 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark disabled:opacity-50 inline-flex items-center gap-2">
            <Rocket className="h-4 w-4" />{submitting ? 'Starting...' : 'Run'}
          </button>
          <button type="button" onClick={handleResync} disabled={resyncing}
            className="h-9 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 disabled:opacity-50 inline-flex items-center gap-1.5"
            title="Re-fetch from Outlook to backfill attachment names & web links">
            <RefreshCw className={`h-3.5 w-3.5 ${resyncing ? 'animate-spin' : ''}`} />Re-sync
          </button>
        </form>
      </div>

      {/* Job History */}
      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b">
          <h2 className="text-sm font-bold text-slate-900">Extraction History</h2>
        </div>
        {loading && jobs.length === 0 ? <ContentSkeleton rows={5} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50/50">
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Step</th>
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Mode</th>
                  <th className="px-4 py-2 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Emails</th>
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-36">Started</th>
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-36">Completed</th>
                  <th className="px-4 py-2 w-20"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {jobs.map(job => {
                  const progress = activeProgress[job.id];
                  const pct = progress?.total_steps ? Math.round(((progress.current_step_number || 0) / progress.total_steps) * 100) : 0;
                  const isActive = ['pending', 'processing'].includes(job.status);
                  const variant = job.status === 'completed' ? 'success' : job.status === 'failed' ? 'danger' : isActive ? 'info' : 'neutral';
                  return (
                    <tr key={job.id} className="hover:bg-slate-50/50">
                      <td className="px-4 py-2">
                        {isActive && progress ? (
                          <div className="w-20">
                            <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                              <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${pct}%` }} />
                            </div>
                            <span className="text-[10px] text-slate-400">{pct}%</span>
                          </div>
                        ) : (
                          <StatusBadge variant={variant as any} size="sm">{job.status}</StatusBadge>
                        )}
                      </td>
                      <td className="px-4 py-2 text-slate-600 text-xs">{progress?.current_step || job.current_step || '—'}</td>
                      <td className="px-4 py-2 text-slate-500 text-xs">{job.extraction_mode || 'full'}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{job.emails_in_scope || '—'}</td>
                      <td className="px-4 py-2 text-xs text-slate-500">{job.started_at ? formatDateTime(job.started_at) : '—'}</td>
                      <td className="px-4 py-2 text-xs text-slate-500">{job.completed_at ? formatDateTime(job.completed_at) : '—'}</td>
                      <td className="px-4 py-2">
                        {isActive && (
                          <button onClick={() => handleCancel(job.id)}
                            className="inline-flex items-center gap-1 text-xs text-destructive hover:underline">
                            <Square className="h-3 w-3" />Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {jobsTotal > PAGE_SIZE && (
          <div className="flex items-center justify-end px-4 py-3 border-t">
            <span className="text-xs text-slate-500 mr-4">{jobsTotal} jobs</span>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="px-2 py-1 text-xs rounded hover:bg-slate-100 disabled:opacity-30">Prev</button>
            <span className="text-xs px-2 tabular-nums">{page}</span>
            <button onClick={() => setPage(p => p + 1)} disabled={page * PAGE_SIZE >= jobsTotal} className="px-2 py-1 text-xs rounded hover:bg-slate-100 disabled:opacity-30">Next</button>
          </div>
        )}
      </div>
    </PageShell>
  );
};
