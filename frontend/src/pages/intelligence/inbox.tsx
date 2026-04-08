/**
 * Smart Inbox — AI Intelligence Inbox Page (Session 6)
 *
 * Primary intelligence view:
 * - Mailbox selector + "Analyze New Emails" button
 * - Filter bar: bucket chips, intent/urgency/sentiment dropdowns, confidence slider
 * - Table with bucket tags, urgency, subject, sender, sentiment, summary, date
 * - Detail slide-over: full classification, entities, suggested action, feedback
 *
 * All business logic server-side — frontend only displays + confidence gating.
 *
 * Zero antd — Tailwind CSS + shadcn/ui + lucide-react
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  RefreshCw, Rocket, ArrowUpDown, X, ChevronLeft, ChevronRight,
  Inbox as InboxIcon, AlertCircle, CheckCircle2, Info, Loader2,
} from 'lucide-react';
import { formatDate, localDateToISOStart, formatDateForApi } from '../../utils/dateUtils';
import { MailboxSelector } from '../../components/MailboxSelector';
import { ActionBucketTag } from '../../components/ai/ActionBucketTag';
import { FeedbackButtons } from '../../components/ai/FeedbackButtons';
import { intelligenceApi, bucketApi } from '../../services/aiService';
import api from '../../services/apiClient';
import { PageShell } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { EmptyState, ContentSkeleton } from '@/components/ui/empty-state';
import { notify } from '@/lib/toast';
import { cn } from '@/lib/utils';
import type {
  IntelligenceResult, IntelligenceFilterParams,
  BucketSummary, IntentType, UrgencyLevel, SentimentType, BucketType,
} from '../../types/ai';

// Urgency variant map for StatusBadge
const URGENCY_VARIANT: Record<string, 'danger' | 'warning' | 'info' | 'neutral'> = {
  critical: 'danger', high: 'danger', medium: 'warning', low: 'info', none: 'neutral',
};

// Sentiment variant map for StatusBadge
const SENTIMENT_VARIANT: Record<string, 'success' | 'info' | 'neutral' | 'warning' | 'danger'> = {
  very_positive: 'success', positive: 'success', neutral: 'neutral',
  negative: 'warning', very_negative: 'danger',
};

// Intent labels
const INTENT_LABELS: Record<string, string> = {
  action_required: 'Action Required', fyi_update: 'FYI', meeting_scheduling: 'Meeting',
  question: 'Question', complaint: 'Complaint', positive_feedback: 'Positive',
  pricing_inquiry: 'Pricing', feature_request: 'Feature', expansion_signal: 'Expansion',
  churn_risk: 'Churn Risk', follow_up: 'Follow-up', introduction: 'Intro', other: 'Other',
};

// Bucket chip color mapping for border / bg tinting
const BUCKET_CHIP_STYLE: Record<string, { bg: string; border: string; text: string; activeBg: string }> = {
  response_urgency:    { bg: 'bg-red-50',    border: 'border-red-200',    text: 'text-red-700',    activeBg: 'bg-red-100' },
  deal_at_risk:        { bg: 'bg-orange-50',  border: 'border-orange-200',  text: 'text-orange-700',  activeBg: 'bg-orange-100' },
  retention_risk:      { bg: 'bg-red-50',    border: 'border-red-200',    text: 'text-red-700',    activeBg: 'bg-red-100' },
  revenue_opportunity: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', activeBg: 'bg-emerald-100' },
  new_relationship:    { bg: 'bg-blue-50',   border: 'border-blue-200',   text: 'text-blue-700',   activeBg: 'bg-blue-100' },
  account_neglect:     { bg: 'bg-amber-50',  border: 'border-amber-200',  text: 'text-amber-700',  activeBg: 'bg-amber-100' },
};

// Sort column type
type SortKey = 'urgency' | 'subject' | 'sender' | 'intent' | 'sentiment' | 'date' | null;
type SortDir = 'asc' | 'desc';

export const InboxPage: React.FC = () => {
  const isMountedRef = useRef(true);

  // Selection
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';

  // Data
  const [items, setItems] = useState<IntelligenceResult[]>([]);
  const [bucketSummary, setBucketSummary] = useState<BucketSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [rebucketing, setRebucketing] = useState(false);
  const [analysisStatus, setAnalysisStatus] = useState<{ status: string; message: string; pct?: number } | null>(null);
  const analysisPollRef = useRef<any>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);

  // Filters
  const [filters, setFilters] = useState<IntelligenceFilterParams>({});

  // Analysis date range (days lookback)
  const [analysisRange, setAnalysisRange] = useState<number>(7);

  // Sort
  const [sortKey, setSortKey] = useState<SortKey>(null);
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  // Drawer
  const [drawerItem, setDrawerItem] = useState<IntelligenceResult | null>(null);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!mailboxId) return;
    const loadAll = async () => {
      setLoading(true);
      const [listResult, summary] = await Promise.all([
        intelligenceApi.list(mailboxId, { ...filters, page, page_size: pageSize }),
        bucketApi.getSummary(mailboxId),
      ]);
      if (!isMountedRef.current) return;
      setItems(listResult.items || []);
      setBucketSummary(summary);
      setLoading(false);
    };
    loadAll();
  }, [mailboxId, page, filters]);

  const loadData = async () => {
    setLoading(true);
    const result = await intelligenceApi.list(mailboxId, {
      ...filters,
      page,
      page_size: pageSize,
    });
    if (isMountedRef.current) {
      setItems(result.items || []);
      setLoading(false);
    }
  };

  const stopAnalysisPoll = () => {
    if (analysisPollRef.current) { clearTimeout(analysisPollRef.current); analysisPollRef.current = null; }
  };

  const pollAnalysisJob = (mbId: string) => {
    stopAnalysisPoll();
    const poll = async () => {
      if (!isMountedRef.current) return;
      try {
        const resp = await api.get<any[]>(`/processing-jobs?mailbox_id=${mbId}&limit=5`);
        const jobs = Array.isArray(resp) ? resp : (resp as any)?.jobs || [];

        // Helper to extract progress from error_summary JSONB
        const getProgress = (job: any) => {
          const summary = job.error_summary || {};
          return {
            pct: summary.progress_pct ?? 0,
            message: summary.progress_message || '',
          };
        };

        // Find active ai_analysis job
        const activeJob = jobs.find((j: any) => j.job_type === 'ai_analysis' && ['running', 'pending'].includes(j.status));
        if (activeJob) {
          const prog = getProgress(activeJob);
          setAnalysisStatus({ status: activeJob.status, message: prog.message || 'Analyzing...', pct: prog.pct });
          setAnalyzing(true);
          analysisPollRef.current = setTimeout(poll, 5000);
          return;
        }

        // Check most recent completed/failed ai_analysis job
        const lastJob = jobs.find((j: any) => j.job_type === 'ai_analysis');
        if (lastJob && ['completed', 'failed'].includes(lastJob.status)) {
          const prog = getProgress(lastJob);
          const isError = lastJob.status === 'failed' || prog.message.toLowerCase().includes('failed');
          setAnalysisStatus({
            status: lastJob.status,
            message: prog.message || (isError ? 'Analysis failed' : 'Analysis complete'),
            pct: prog.pct,
          });
          setAnalyzing(false);
          if (!isError) {
            loadData();
            if (mbId) bucketApi.getSummary(mbId).then(setBucketSummary).catch(() => {});
          }
          return;
        }
      } catch { /* keep polling */ }
      setAnalyzing(false);
    };
    analysisPollRef.current = setTimeout(poll, 2000);
  };

  // Check for active analysis on page load / mailbox change
  useEffect(() => {
    if (mailboxId) pollAnalysisJob(mailboxId);
    return () => stopAnalysisPoll();
  }, [mailboxId]);

  const handleAnalyze = async () => {
    if (!mailboxId) return;
    setAnalyzing(true);
    setAnalysisStatus({ status: 'starting', message: 'Starting AI analysis...', pct: 0 });
    const fromDate = new Date();
    fromDate.setDate(fromDate.getDate() - analysisRange);
    const dateFrom = localDateToISOStart(formatDateForApi(fromDate));
    const result = await intelligenceApi.analyze(mailboxId, {
      max_emails: 500,
      date_from: dateFrom,
    });
    if (result) {
      setAnalysisStatus({ status: 'running', message: result.message || 'Analysis started...', pct: 5 });
      pollAnalysisJob(mailboxId);
    } else {
      setAnalysisStatus({ status: 'failed', message: 'Failed to start analysis', pct: 0 });
      setAnalyzing(false);
    }
  };

  const handleRebucket = async () => {
    if (!mailboxId) return;
    setRebucketing(true);
    try {
      await bucketApi.rebucket(mailboxId);
      notify.success('Re-bucketing started -- signals will refresh shortly');
      // Reload after a short delay to pick up new buckets
      setTimeout(() => { loadData(); bucketApi.getSummary(mailboxId).then(setBucketSummary); }, 3000);
    } catch {
      notify.error('Failed to start re-bucketing');
    } finally {
      setRebucketing(false);
    }
  };

  const handleFilterChange = (key: string, value: any) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
    setPage(1);
  };

  const handleBucketClick = (bucket: BucketType) => {
    if (filters.primary_bucket === bucket) {
      handleFilterChange('primary_bucket', undefined);
    } else {
      handleFilterChange('primary_bucket', bucket);
    }
  };

  // Sorting
  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sortedItems = React.useMemo(() => {
    if (!sortKey) return items;
    const sorted = [...items].sort((a, b) => {
      switch (sortKey) {
        case 'urgency': {
          const order = ['critical', 'high', 'medium', 'low', 'none'];
          return order.indexOf(a.urgency || 'none') - order.indexOf(b.urgency || 'none');
        }
        case 'subject':
          return (a.email_subject || '').localeCompare(b.email_subject || '');
        case 'sender':
          return (a.email_sender_name || a.email_sender || '').localeCompare(b.email_sender_name || b.email_sender || '');
        case 'intent':
          return (a.intent || '').localeCompare(b.intent || '');
        case 'sentiment': {
          const order = ['very_positive', 'positive', 'neutral', 'negative', 'very_negative'];
          return order.indexOf(a.sentiment || 'neutral') - order.indexOf(b.sentiment || 'neutral');
        }
        case 'date':
          return (a.email_date || '').localeCompare(b.email_date || '');
        default:
          return 0;
      }
    });
    return sortDir === 'desc' ? sorted.reverse() : sorted;
  }, [items, sortKey, sortDir]);

  // Signal summary bar (AM-centric v3)
  const bucketChips = bucketSummary ? [
    { key: 'response_urgency', label: 'Response Urgency', count: bucketSummary.response_urgency },
    { key: 'deal_at_risk', label: 'Deal at Risk', count: bucketSummary.deal_at_risk },
    { key: 'retention_risk', label: 'Retention Risk', count: bucketSummary.retention_risk },
    { key: 'revenue_opportunity', label: 'Revenue Opp.', count: bucketSummary.revenue_opportunity },
    { key: 'new_relationship', label: 'New Relationship', count: bucketSummary.new_relationship },
    { key: 'account_neglect', label: 'Account Neglect', count: bucketSummary.account_neglect },
  ] : [];

  // Analysis status banner
  const statusBannerType = analysisStatus?.status === 'failed' ? 'error'
    : analysisStatus?.status === 'completed' ? 'success'
    : 'info';

  const StatusIcon = statusBannerType === 'error' ? AlertCircle
    : statusBannerType === 'success' ? CheckCircle2
    : Info;

  const statusBannerBorder = statusBannerType === 'error' ? 'border-red-200 bg-red-50'
    : statusBannerType === 'success' ? 'border-emerald-200 bg-emerald-50'
    : 'border-blue-200 bg-blue-50';

  const statusIconColor = statusBannerType === 'error' ? 'text-red-500'
    : statusBannerType === 'success' ? 'text-emerald-500'
    : 'text-blue-500';

  // Column header helper
  const SortHeader = ({ label, sortField }: { label: string; sortField: SortKey }) => (
    <button
      className="inline-flex items-center gap-1 group"
      onClick={() => handleSort(sortField)}
    >
      {label}
      <ArrowUpDown className={cn(
        'h-3 w-3 transition-colors',
        sortKey === sortField ? 'text-slate-900' : 'text-slate-300 group-hover:text-slate-500',
      )} />
    </button>
  );

  return (
    <PageShell>
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex-1 min-w-[280px] max-w-[380px]">
          <MailboxSelector
            value={mailboxIds}
            onChange={setMailboxIds}
            mode="single"
            placeholder="Select a mailbox"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={loadData}
            disabled={!mailboxId}
            className="inline-flex items-center gap-1.5 h-8 px-3 text-xs font-medium rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>

          <select
            value={analysisRange}
            onChange={(e) => setAnalysisRange(Number(e.target.value))}
            className="h-8 px-2 text-xs rounded-md border border-slate-200 bg-white text-slate-700"
          >
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>

          <button
            onClick={handleRebucket}
            disabled={!mailboxId || rebucketing}
            className="inline-flex items-center gap-1.5 h-8 px-3 text-xs font-medium rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {rebucketing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Re-bucket
          </button>

          <button
            onClick={handleAnalyze}
            disabled={!mailboxId || analyzing}
            className="inline-flex items-center gap-1.5 h-8 px-3 text-xs font-medium rounded-md bg-primary text-white hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {analyzing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Rocket className="h-3.5 w-3.5" />}
            Analyze New Emails
          </button>
        </div>
      </div>

      {/* Analysis status banner */}
      {analysisStatus && (
        <div className={cn('rounded-lg border px-4 py-3 mb-4 flex items-start gap-3', statusBannerBorder)}>
          <StatusIcon className={cn('h-4 w-4 mt-0.5 shrink-0', statusIconColor)} />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-slate-700">{analysisStatus.message}</p>
            {analyzing && analysisStatus.pct != null && (
              <div className="mt-2 w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-500',
                    analysisStatus.status === 'failed' ? 'bg-red-500' : 'bg-primary',
                  )}
                  style={{ width: `${Math.min(analysisStatus.pct, 100)}%` }}
                />
              </div>
            )}
          </div>
          {['completed', 'failed'].includes(analysisStatus.status) && (
            <button
              onClick={() => setAnalysisStatus(null)}
              className="p-0.5 rounded hover:bg-black/5 text-slate-400 hover:text-slate-600 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      {/* Bucket summary chips */}
      {bucketChips.length > 0 && (
        <div className="rounded-lg border bg-white shadow-sm px-4 py-3 mb-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-slate-700 mr-1">Buckets:</span>
            {bucketChips.map((chip) => {
              const isActive = filters.primary_bucket === chip.key;
              const style = BUCKET_CHIP_STYLE[chip.key] || { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-600', activeBg: 'bg-slate-100' };
              return (
                <button
                  key={chip.key}
                  onClick={() => handleBucketClick(chip.key as BucketType)}
                  className={cn(
                    'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-all',
                    isActive
                      ? `${style.activeBg} ${style.border} ${style.text}`
                      : 'bg-white border-dashed border-slate-200 text-slate-500 hover:border-slate-300',
                    chip.count === 0 && 'opacity-40',
                  )}
                >
                  {chip.label}: {chip.count.toLocaleString('en-AU')}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Main table */}
      {!mailboxId ? (
        <div className="rounded-lg border bg-white shadow-sm">
          <EmptyState
            icon={<InboxIcon className="h-10 w-10" />}
            title="Select a mailbox to view AI intelligence"
            description="Choose a mailbox from the selector above to see analyzed emails."
          />
        </div>
      ) : loading ? (
        <div className="rounded-lg border bg-white shadow-sm">
          <ContentSkeleton rows={8} />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border bg-white shadow-sm">
          <EmptyState
            icon={<InboxIcon className="h-10 w-10" />}
            title="No intelligence results"
            description="Run an analysis to classify emails in this mailbox."
          />
        </div>
      ) : (
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px]">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/60">
                  <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[160px]">
                    Bucket
                  </th>
                  <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[90px]">
                    <SortHeader label="Urgency" sortField="urgency" />
                  </th>
                  <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600">
                    <SortHeader label="Subject" sortField="subject" />
                  </th>
                  <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[180px]">
                    <SortHeader label="Sender" sortField="sender" />
                  </th>
                  <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[120px]">
                    <SortHeader label="Intent" sortField="intent" />
                  </th>
                  <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[110px]">
                    <SortHeader label="Sentiment" sortField="sentiment" />
                  </th>
                  <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[100px]">
                    <SortHeader label="Date" sortField="date" />
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {sortedItems.map((r) => (
                  <tr
                    key={r.id || r.email_id || Math.random().toString()}
                    onClick={() => setDrawerItem(r)}
                    className="hover:bg-slate-50/60 cursor-pointer transition-colors"
                  >
                    {/* Bucket */}
                    <td className="px-4 py-2.5">
                      {!r.action_buckets?.length ? (
                        <span className="text-xs text-slate-400">None</span>
                      ) : (
                        <div className="flex items-center gap-1 flex-wrap">
                          {r.action_buckets.slice(0, 2).map((b, i) => (
                            <ActionBucketTag
                              key={i}
                              bucket={b.bucket}
                              confidence={b.confidence}
                              justification={b.justification}
                            />
                          ))}
                        </div>
                      )}
                    </td>

                    {/* Urgency */}
                    <td className="px-4 py-2.5">
                      {r.urgency && (
                        <StatusBadge variant={URGENCY_VARIANT[r.urgency] || 'neutral'} size="sm">
                          {r.urgency}
                        </StatusBadge>
                      )}
                    </td>

                    {/* Subject */}
                    <td className="px-4 py-2.5">
                      <span className="text-sm text-primary hover:underline truncate block max-w-[360px]">
                        {r.email_subject || '(no subject)'}
                      </span>
                    </td>

                    {/* Sender */}
                    <td className="px-4 py-2.5">
                      <span className="text-sm text-slate-600 truncate block max-w-[170px]">
                        {r.email_sender_name || r.email_sender || ''}
                      </span>
                    </td>

                    {/* Intent */}
                    <td className="px-4 py-2.5">
                      {r.intent && (
                        <StatusBadge variant="neutral" size="sm">
                          {INTENT_LABELS[r.intent] || r.intent}
                        </StatusBadge>
                      )}
                    </td>

                    {/* Sentiment */}
                    <td className="px-4 py-2.5">
                      {r.sentiment && (
                        <StatusBadge variant={SENTIMENT_VARIANT[r.sentiment] || 'neutral'} size="sm">
                          {r.sentiment?.replace('_', ' ')}
                        </StatusBadge>
                      )}
                    </td>

                    {/* Date */}
                    <td className="px-4 py-2.5">
                      {r.email_date && (
                        <span className="text-xs text-slate-500">{formatDate(r.email_date)}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
            <span className="text-xs text-slate-500">
              {items.length.toLocaleString('en-AU')} results
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="h-4 w-4 text-slate-600" />
              </button>
              <span className="text-xs text-slate-600 px-2">Page {page}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={items.length < pageSize}
                className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="h-4 w-4 text-slate-600" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail slide-over panel */}
      {drawerItem && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/20 z-40 transition-opacity"
            onClick={() => setDrawerItem(null)}
          />
          {/* Panel */}
          <div className="fixed inset-y-0 right-0 z-50 w-full max-w-[560px] bg-white shadow-xl border-l border-slate-200 flex flex-col animate-in slide-in-from-right duration-200">
            {/* Panel header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 shrink-0">
              <h2 className="text-sm font-semibold text-slate-900 truncate pr-4">
                {drawerItem.email_subject || 'Email Intelligence'}
              </h2>
              <button
                onClick={() => setDrawerItem(null)}
                className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {/* Panel body */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
              <IntelligenceDetail item={drawerItem} />
            </div>
          </div>
        </>
      )}
    </PageShell>
  );
};

// ============================================================================
// Detail panel inside slide-over
// ============================================================================

const IntelligenceDetail: React.FC<{ item: IntelligenceResult }> = ({ item }) => {
  const [bodyView, setBodyView] = useState<'html' | 'text'>(item.email_body_html ? 'html' : 'text');
  const recipients = (item.email_recipients || [])
    .map((r: any) => typeof r === 'string' ? r : r?.email || r?.name || '')
    .filter(Boolean);
  const ccList = (item.email_cc_list || [])
    .map((r: any) => typeof r === 'string' ? r : r?.email || r?.name || '')
    .filter(Boolean);
  const bccList = (item.email_bcc_list || [])
    .map((r: any) => typeof r === 'string' ? r : r?.email || r?.name || '')
    .filter(Boolean);

  const hasHtml = !!item.email_body_html;
  const hasText = !!item.email_body;

  return (
    <div className="space-y-4">
      {/* Email Header */}
      <div className="space-y-2">
        <div className="flex gap-2">
          <span className="text-xs font-medium text-slate-500 w-10 shrink-0 pt-0.5">From</span>
          <div className="text-sm">
            <span className="font-medium text-slate-900">{item.email_sender_name || item.email_sender}</span>
            {item.email_sender_name && (
              <span className="text-slate-500"> &lt;{item.email_sender}&gt;</span>
            )}
          </div>
        </div>
        {recipients.length > 0 && (
          <div className="flex gap-2">
            <span className="text-xs font-medium text-slate-500 w-10 shrink-0 pt-0.5">To</span>
            <span className="text-sm text-slate-600">{recipients.join(', ')}</span>
          </div>
        )}
        {ccList.length > 0 && (
          <div className="flex gap-2">
            <span className="text-xs font-medium text-slate-500 w-10 shrink-0 pt-0.5">CC</span>
            <span className="text-sm text-slate-600">{ccList.join(', ')}</span>
          </div>
        )}
        {bccList.length > 0 && (
          <div className="flex gap-2">
            <span className="text-xs font-medium text-slate-500 w-10 shrink-0 pt-0.5">BCC</span>
            <span className="text-sm text-slate-600">{bccList.join(', ')}</span>
          </div>
        )}
        <div className="flex gap-2">
          <span className="text-xs font-medium text-slate-500 w-10 shrink-0 pt-0.5">Date</span>
          <span className="text-sm text-slate-600">{item.email_date ? formatDate(item.email_date) : 'N/A'}</span>
        </div>
      </div>

      {/* View toggle */}
      {hasHtml && hasText && (
        <div className="flex items-center gap-1">
          <button
            onClick={() => setBodyView('html')}
            className={cn(
              'h-7 px-2.5 text-xs font-medium rounded-md transition-colors',
              bodyView === 'html'
                ? 'bg-primary text-white'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50',
            )}
          >
            HTML
          </button>
          <button
            onClick={() => setBodyView('text')}
            className={cn(
              'h-7 px-2.5 text-xs font-medium rounded-md transition-colors',
              bodyView === 'text'
                ? 'bg-primary text-white'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50',
            )}
          >
            Plain Text
          </button>
        </div>
      )}

      {/* Email Body */}
      {hasHtml && bodyView === 'html' ? (
        <iframe
          srcDoc={`<!DOCTYPE html><html><head><meta charset="UTF-8"><base target="_blank"><style>
            html, body { margin: 0; padding: 0; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.6; color: #333; padding: 16px; }
            img { max-width: 100%; height: auto; }
            a { color: #667eea; }
            blockquote { border-left: 3px solid #d9d9d9; padding-left: 16px; margin-left: 0; color: #666; }
            pre { background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }
          </style></head><body>${item.email_body_html}</body></html>`}
          className="w-full min-h-[300px] border border-slate-100 rounded-md"
          sandbox="allow-same-origin"
        />
      ) : hasText ? (
        <div className="p-3 bg-slate-50 border border-slate-100 rounded-md max-h-[400px] overflow-y-auto whitespace-pre-wrap text-[13px] leading-relaxed text-slate-700">
          {item.email_body}
        </div>
      ) : (
        <div className="p-3 bg-slate-50 border border-slate-100 rounded-md">
          <span className="text-sm text-slate-400">No email content available</span>
        </div>
      )}

      {/* AI Classification */}
      <div className="border-t border-slate-100 pt-4">
        <h4 className="text-sm font-semibold text-slate-900 mb-2">AI Classification</h4>
        <div className="flex items-center gap-1.5 flex-wrap">
          <StatusBadge variant="neutral">
            {INTENT_LABELS[item.intent || ''] || item.intent}
          </StatusBadge>
          <StatusBadge variant={URGENCY_VARIANT[item.urgency || ''] || 'neutral'}>
            {item.urgency}
          </StatusBadge>
          <StatusBadge variant={SENTIMENT_VARIANT[item.sentiment || ''] || 'neutral'}>
            {item.sentiment?.replace('_', ' ')}
          </StatusBadge>
          {item.confidence != null && (
            <StatusBadge variant="info">
              Confidence: {Math.round(item.confidence * 100)}%
            </StatusBadge>
          )}
        </div>
      </div>

      {/* Buckets */}
      {item.action_buckets?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-slate-900 mb-2">Action Buckets</h4>
          <div className="flex items-center gap-1.5 flex-wrap">
            {item.action_buckets.map((b, i) => (
              <ActionBucketTag key={i} bucket={b.bucket} confidence={b.confidence} justification={b.justification} />
            ))}
          </div>
        </div>
      )}

      {/* Suggested Action */}
      {item.suggested_action && (
        <div>
          <h4 className="text-sm font-semibold text-slate-900 mb-1">Suggested Action</h4>
          <p className="text-sm text-slate-600">{item.suggested_action}</p>
        </div>
      )}

      {/* Key Topics */}
      {item.key_topics?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-slate-900 mb-2">Key Topics</h4>
          <div className="flex items-center gap-1.5 flex-wrap">
            {item.key_topics.map((t, i) => (
              <StatusBadge key={i} variant="neutral" size="sm">{t}</StatusBadge>
            ))}
          </div>
        </div>
      )}

      {/* Entities */}
      {(item.competitors_mentioned?.length > 0 || item.products_mentioned?.length > 0 || item.buying_signals?.length > 0) && (
        <div className="rounded-lg border border-slate-100 overflow-hidden">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-100">
              {item.competitors_mentioned?.length > 0 && (
                <tr>
                  <td className="px-3 py-2 font-medium text-slate-600 bg-slate-50/60 w-[110px] align-top text-xs">Competitors</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {item.competitors_mentioned.map((c, i) => (
                        <StatusBadge key={i} variant="warning" size="sm">{c}</StatusBadge>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
              {item.products_mentioned?.length > 0 && (
                <tr>
                  <td className="px-3 py-2 font-medium text-slate-600 bg-slate-50/60 w-[110px] align-top text-xs">Products</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {item.products_mentioned.map((p, i) => (
                        <StatusBadge key={i} variant="info" size="sm">{p}</StatusBadge>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
              {item.buying_signals?.length > 0 && (
                <tr>
                  <td className="px-3 py-2 font-medium text-slate-600 bg-slate-50/60 w-[110px] align-top text-xs">Buying Signals</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {item.buying_signals.map((s, i) => (
                        <StatusBadge key={i} variant="success" size="sm">{s}</StatusBadge>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Feedback */}
      <div className="border-t border-slate-100 pt-4">
        <h4 className="text-sm font-semibold text-slate-900 mb-2">Was this classification correct?</h4>
        <FeedbackButtons
          emailId={item.email_id || ''}
          currentFeedback={item.human_feedback || undefined}
        />
      </div>
    </div>
  );
};

export default InboxPage;
