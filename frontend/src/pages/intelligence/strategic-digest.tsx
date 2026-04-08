/**
 * Strategic Digest Page — Sprint 3
 *
 * Displays AI-generated strategic digest with executive summary,
 * AM performance, relationship health, pipeline, risks, opportunities,
 * competitive landscape, and action items.
 *
 * Migrated from Ant Design to Tailwind CSS + shadcn/ui primitives.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { ArrowUp, ArrowDown, Minus, RefreshCw, AlertTriangle, AlertCircle, Info } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { strategicDigestApi, streamDigestGeneration } from '../../services/strategicDigestService';
import type { StrategicDigest, PeriodType, LifecycleTier } from '../../types/strategic-digest';
import { LIFECYCLE_CONFIG, SIGNAL_CONFIG } from '../../types/strategic-digest';
import { useClient } from '../../contexts/ClientContext';
import { formatRelativeTime } from '../../utils/dateUtils';
import { formatCurrency } from '../../utils/numberFormat';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { Spinner } from '@/lib/icons';

/* ---------- StatusBadge variant maps ---------- */

const LIFECYCLE_VARIANT: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple'> = {
  champion: 'success',
  active_customer: 'info',
  at_risk: 'warning',
  dormant: 'neutral',
  new_customer: 'purple',
  prospect: 'info',
};

const SIGNAL_VARIANT: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple'> = {
  response_urgency: 'danger',
  deal_at_risk: 'warning',
  retention_risk: 'danger',
  revenue_opportunity: 'success',
  new_relationship: 'info',
  account_neglect: 'warning',
};

function lifecycleBadge(tier?: LifecycleTier | string) {
  if (!tier) return null;
  const cfg = LIFECYCLE_CONFIG[tier as LifecycleTier];
  const label = cfg?.label || tier.replace(/_/g, ' ');
  const variant = LIFECYCLE_VARIANT[tier] || 'neutral';
  return <StatusBadge variant={variant} size="sm">{label}</StatusBadge>;
}

function signalTag(type?: string) {
  if (!type) return null;
  const cfg = SIGNAL_CONFIG[type as keyof typeof SIGNAL_CONFIG];
  const label = cfg?.label || type.replace(/_/g, ' ');
  const variant = SIGNAL_VARIANT[type] || 'neutral';
  return <StatusBadge variant={variant} size="sm">{label}</StatusBadge>;
}

const PERIOD_OPTIONS = [
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'ytd', label: 'Year to Date' },
];

function trendIcon(trend?: string) {
  if (!trend) return <Minus className="h-4 w-4 text-slate-400" />;
  const t = trend.toLowerCase();
  if (t === 'up' || t === 'increasing' || t === 'improving') return <ArrowUp className="h-4 w-4 text-emerald-500" />;
  if (t === 'down' || t === 'decreasing' || t === 'declining') return <ArrowDown className="h-4 w-4 text-red-500" />;
  return <Minus className="h-4 w-4 text-slate-400" />;
}

function fmtCurrency(val?: number) {
  if (val == null) return '-';
  return formatCurrency(val);
}

/* ---------- Severity icon for risk alerts ---------- */
function severityIcon(severity?: string) {
  if (severity === 'critical') return <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />;
  if (severity === 'high') return <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />;
  return <Info className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />;
}

/* ---------- Severity colors for risk alerts ---------- */
function severityBorder(severity?: string) {
  if (severity === 'critical') return 'border-l-red-500';
  if (severity === 'high') return 'border-l-amber-500';
  return 'border-l-blue-400';
}

function severityBg(severity?: string) {
  if (severity === 'critical') return 'bg-red-50';
  if (severity === 'high') return 'bg-amber-50';
  return 'bg-blue-50';
}


export default function StrategicDigestPage() {
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const { clientId } = useClient();
  const [periodType, setPeriodType] = useState<PeriodType>('monthly');
  const [digest, setDigest] = useState<StrategicDigest | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState<{ pct: number; message: string; phase: string } | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadDigest = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    setError('');
    try {
      const resp = await strategicDigestApi.get(clientId, periodType);
      if (!isMountedRef.current) return;
      setDigest(resp?.digest ?? null);
    } catch (err: any) {
      if (isMountedRef.current) setError(err?.message || 'Failed to load digest');
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [clientId, periodType]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  const stopPolling = () => {
    if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null; }
  };

  // Shared polling function — used both after Generate and on page load resume
  const startPolling = () => {
    stopPolling();
    const poll = async () => {
      if (!isMountedRef.current || !clientId) return;
      try {
        const prog = await strategicDigestApi.getProgress(clientId);
        if (!isMountedRef.current) return;

        if (prog.phase === 'idle') {
          // No active generation — stop polling
          setGenerating(false);
          setProgress(null);
          return;
        }

        setProgress({ pct: prog.pct, phase: prog.phase, message: prog.message });

        if (prog.phase === 'completed') {
          try {
            const resp = await strategicDigestApi.get(clientId, periodType);
            if (isMountedRef.current) setDigest(resp?.digest ?? null);
          } catch { /* ignore */ }
          setGenerating(false);
          setProgress(null);
          return;
        }

        if (prog.phase === 'failed') {
          if (isMountedRef.current) setError(prog.message || 'Generation failed');
          setGenerating(false);
          setProgress(null);
          setCancelling(false);
          return;
        }

        if (prog.phase === 'cancelled') {
          setGenerating(false);
          setProgress(null);
          setCancelling(false);
          return;
        }
      } catch { /* keep polling */ }

      pollRef.current = setTimeout(poll, 4000);
    };

    pollRef.current = setTimeout(poll, 1000);
  };

  // On page load: check if there's an active generation running (survives navigation)
  useEffect(() => {
    if (!clientId) return;
    loadDigest();

    // Check for in-progress generation
    strategicDigestApi.getProgress(clientId).then(prog => {
      if (!isMountedRef.current) return;
      if (prog.phase && prog.phase !== 'idle') {
        // Resume showing progress
        setGenerating(true);
        setProgress({ pct: prog.pct, phase: prog.phase, message: prog.message });
        startPolling();
      }
    }).catch(() => {});
  }, [clientId, periodType]);

  const handleGenerate = async () => {
    if (!clientId) return;
    setGenerating(true);
    setError('');
    setCancelling(false);
    setProgress({ pct: 0, phase: 'starting', message: 'Initialising\u2026' });
    stopPolling();
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    try {
      await streamDigestGeneration(
        clientId,
        periodType,
        {
          onProgress: (phase, pct, message) => {
            if (!isMountedRef.current) return;
            setProgress({ phase, pct, message });
          },
          onComplete: (digestData) => {
            if (!isMountedRef.current) return;
            setDigest(digestData);
            setGenerating(false);
            setProgress(null);
          },
          onError: (detail) => {
            if (!isMountedRef.current) return;
            setError(detail);
            setGenerating(false);
            setProgress(null);
          },
          onCancelled: () => {
            if (!isMountedRef.current) return;
            setGenerating(false);
            setProgress(null);
            setCancelling(false);
          },
        },
        abortRef.current.signal,
      );
    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      if (!isMountedRef.current) return;
      // SSE failed mid-stream — cancel the in-flight job first to prevent
      // a double-job if it was already running, then fall back to polling.
      console.warn('SSE streaming failed, falling back to polling:', err?.message);
      try {
        await strategicDigestApi.cancel(clientId).catch(() => {});
        await strategicDigestApi.generate(clientId, periodType);
        startPolling();
      } catch (fallbackErr: any) {
        setError(fallbackErr?.message || 'Failed to start generation');
        setGenerating(false);
        setProgress(null);
      }
    }
  };

  const handleCancel = async () => {
    if (!clientId || cancelling) return;
    setCancelling(true);
    // Abort the SSE connection (triggers server-side cancellation)
    abortRef.current?.abort();
    // Also signal via API in case the SSE already disconnected
    try {
      await strategicDigestApi.cancel(clientId);
    } catch { /* ignore */ }
  };

  // Clean up on unmount
  useEffect(() => () => {
    stopPolling();
    abortRef.current?.abort();
  }, []);

  // AM performance: v2 stores as {summary: [...], ...}; v1 was an array
  const amRaw = digest?.am_performance;
  const amData: any[] = Array.isArray(amRaw)
    ? amRaw
    : (amRaw as any)?.summary || [];
  const pipeline = digest?.pipeline_intelligence;
  const risksRaw = digest?.risk_alerts;
  const risks: any[] = Array.isArray(risksRaw) ? risksRaw : [];
  const oppsRaw = digest?.opportunities;
  const opportunities: any[] = Array.isArray(oppsRaw) ? oppsRaw : [];
  const competitive = digest?.competitive_landscape;
  const actionsRaw = digest?.action_items;
  const actionItems: any[] = Array.isArray(actionsRaw) ? actionsRaw : [];
  const relationshipsRaw = digest?.relationship_health;
  const relationships: any[] = Array.isArray(relationshipsRaw) ? relationshipsRaw : [];

  /* ---------- Response time color helper ---------- */
  function responseTimeColor(v: number) {
    if (v <= 4) return 'text-emerald-600';
    if (v <= 8) return 'text-amber-600';
    return 'text-red-600';
  }
  function rateColor(v: number, good: number, warn: number) {
    if (v >= good) return 'text-emerald-600';
    if (v >= warn) return 'text-amber-600';
    return 'text-red-600';
  }

  /* ---------- Progress bar color ---------- */
  function progressBarColor(phase?: string) {
    if (phase === 'ai_analysis') return 'bg-indigo-500';
    if (phase === 'am_performance') return 'bg-emerald-500';
    return 'bg-primary';
  }

  /* ---------- Priority badge ---------- */
  function priorityBadge(v: string | number) {
    const label = typeof v === 'string' ? v.toUpperCase() : `P${v}`;
    const variant: 'danger' | 'warning' | 'info' =
      v === 'urgent' ? 'danger' : v === 'high' ? 'warning' : 'info';
    return <StatusBadge variant={variant} size="sm">{label}</StatusBadge>;
  }

  return (
    <PageShell>
      {/* Header */}
      <PageHeader
        title="Strategic Digest"
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={periodType}
              onChange={(e) => setPeriodType(e.target.value as PeriodType)}
              className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              {PERIOD_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <button
              onClick={handleGenerate}
              disabled={generating || !clientId}
              className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {generating ? (
                <Spinner className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Generate Digest
            </button>
          </div>
        }
      />

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 mb-4">
          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="flex-1 text-sm text-amber-800">{error}</div>
          <button onClick={() => setError('')} className="text-amber-400 hover:text-amber-600 text-sm font-medium">&times;</button>
        </div>
      )}

      {/* No client selected */}
      {!clientId && (
        <div className="rounded-lg border bg-white shadow-sm p-12 text-center">
          <p className="text-sm text-slate-500">Select a client to view the strategic digest</p>
        </div>
      )}

      {/* Loading state */}
      {loading && clientId && !generating && (
        <div className="rounded-lg border bg-white shadow-sm">
          <ContentSkeleton rows={6} />
        </div>
      )}

      {/* Generation in progress */}
      {generating && clientId && (
        <div className="rounded-lg border bg-white shadow-sm p-8 max-w-xl mx-auto">
          <div className="text-center mb-5">
            <p className="text-base font-semibold text-slate-800">
              {progress?.phase === 'ai_analysis' ? 'Running AI Analysis' :
               progress?.phase === 'am_performance' ? 'Building AM Performance' :
               progress?.phase === 'building_context' ? 'Building Relationship Context' :
               'Generating Strategic Digest'}
            </p>
          </div>
          {/* Progress bar */}
          <div className="h-2 rounded-full bg-slate-100 overflow-hidden mb-3">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                progress?.phase === 'failed' ? 'bg-red-500' : progressBarColor(progress?.phase)
              }`}
              style={{ width: `${progress?.pct ?? 0}%` }}
            />
          </div>
          <p className="text-center text-sm text-slate-500 mb-5">
            {progress?.message || 'Please wait \u2014 this may take several minutes for large accounts\u2026'}
          </p>
          <p className="text-center text-xs text-slate-400 mb-3">
            You can navigate away \u2014 generation continues in the background.
          </p>
          <div className="text-center">
            <button
              onClick={handleCancel}
              disabled={cancelling || progress?.phase === 'cancelling'}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-red-200 text-red-600 text-sm font-medium hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {(cancelling || progress?.phase === 'cancelling') && (
                <Spinner className="h-3.5 w-3.5 animate-spin" />
              )}
              {progress?.phase === 'cancelling' ? 'Cancelling\u2026' : 'Cancel'}
            </button>
          </div>
        </div>
      )}

      {/* No digest yet */}
      {!loading && !generating && clientId && !digest && !error && (
        <div className="rounded-lg border bg-white shadow-sm p-12 text-center">
          <p className="text-sm text-slate-500 mb-4">No strategic digest available for this period.</p>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Generate Digest Now
          </button>
        </div>
      )}

      {/* Digest content */}
      {!loading && !generating && digest && !error && (
        <div className="space-y-4">

          {/* Meta info */}
          <div className="rounded-lg border bg-white shadow-sm px-4 py-3">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-slate-500">
              <span>Period: {digest.period_start} to {digest.period_end}</span>
              {digest.emails_analyzed != null && (
                <span>{digest.emails_analyzed} emails analyzed</span>
              )}
              {digest.companies_analyzed != null && (
                <span>{digest.companies_analyzed} companies</span>
              )}
              {digest.contacts_analyzed != null && (
                <span>{digest.contacts_analyzed} contacts</span>
              )}
              {digest.created_at && (
                <span>Generated {formatRelativeTime(digest.created_at)}</span>
              )}
              {digest.total_cost_usd != null && (
                <span>Cost: ${digest.total_cost_usd.toFixed(4)}</span>
              )}
            </div>
          </div>

          {/* Section 1: Executive Summary */}
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="border-b px-5 py-3">
              <h2 className="text-sm font-semibold text-slate-800">Executive Summary</h2>
            </div>
            <div className="px-5 py-4">
              <p className="text-[15px] leading-relaxed text-slate-700 whitespace-pre-line">
                {digest.executive_summary || 'No executive summary available.'}
              </p>
            </div>
          </div>

          {/* Section 2: AM Performance */}
          {amData.length > 0 && (
            <div className="rounded-lg border bg-white shadow-sm">
              <div className="border-b px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-800">Account Manager Performance</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-slate-50/50">
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Account Manager</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">BH Response</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Response Rate</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">After Hours</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Revenue</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Quote Conv.</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">At Risk</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Note</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {amData.map((row: any, idx: number) => (
                      <tr key={row.account_manager || idx} className="hover:bg-slate-50/50 transition-colors">
                        <td className="px-4 py-2.5 font-medium text-slate-800">{row.am_name || '-'}</td>
                        <td className="px-4 py-2.5">
                          {row.avg_bh_response_hours != null ? (
                            <span className={responseTimeColor(row.avg_bh_response_hours)}>
                              {row.avg_bh_response_hours.toFixed(1)}h
                            </span>
                          ) : '-'}
                        </td>
                        <td className="px-4 py-2.5">
                          {row.response_rate_pct != null ? (
                            <span className={rateColor(row.response_rate_pct, 80, 60)}>
                              {row.response_rate_pct.toFixed(0)}%
                            </span>
                          ) : '-'}
                        </td>
                        <td className="px-4 py-2.5">
                          {row.after_hours_pct != null ? (
                            <span className={row.after_hours_pct > 30 ? 'text-amber-600' : 'text-emerald-600'}>
                              {row.after_hours_pct.toFixed(0)}%
                            </span>
                          ) : '-'}
                        </td>
                        <td className="px-4 py-2.5 text-slate-700">{fmtCurrency(row.revenue_attributed)}</td>
                        <td className="px-4 py-2.5 text-slate-700">
                          {row.quote_conversion_rate != null ? `${row.quote_conversion_rate.toFixed(0)}%` : '-'}
                        </td>
                        <td className="px-4 py-2.5">
                          {row.accounts_at_risk > 0 ? (
                            <StatusBadge variant="danger" size="sm">{row.accounts_at_risk}</StatusBadge>
                          ) : (
                            <StatusBadge variant="success" size="sm">0</StatusBadge>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-slate-500">{row.performance_note || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Section 3: Relationship Health */}
          {relationships.length > 0 && (
            <div className="rounded-lg border bg-white shadow-sm">
              <div className="border-b px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-800">Relationship Health</h2>
              </div>
              <div className="p-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                  {relationships.map((r, idx) => {
                    const borderColor =
                      r.lifecycle_tier === 'at_risk' ? 'border-l-amber-500' :
                      r.lifecycle_tier === 'dormant' ? 'border-l-slate-400' :
                      r.lifecycle_tier === 'champion' ? 'border-l-yellow-400' : 'border-l-transparent';
                    return (
                      <div
                        key={r.company_id || idx}
                        onClick={() => r.company_id ? navigate(`/customers/${r.company_id}`) : undefined}
                        className={`rounded-lg border border-l-[3px] ${borderColor} bg-white p-3 hover:shadow-md transition-shadow cursor-pointer`}
                      >
                        <p className="font-medium text-sm text-slate-800 mb-1.5">{r.company_name}</p>
                        <div className="flex flex-wrap items-center gap-1 mb-2">
                          {lifecycleBadge(r.lifecycle_tier)}
                          {r.tier && <StatusBadge variant="info" size="sm">{r.tier}</StatusBadge>}
                        </div>
                        {r.am_owner && (
                          <p className="text-xs text-slate-500 mb-1">AM: {r.am_owner}</p>
                        )}
                        {r.signal && (
                          <p className="text-xs text-slate-500 italic mb-1">{r.signal}</p>
                        )}
                        {r.recommended_action && (
                          <p className="text-[11px] text-primary mt-1">&rarr; {r.recommended_action}</p>
                        )}
                        {r.revenue_impact_estimate && (
                          <div className="mt-1">
                            <StatusBadge variant="warning" size="sm">{r.revenue_impact_estimate}</StatusBadge>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Section 4: Pipeline Intelligence + Lifecycle Breakdown */}
          {pipeline && (
            <div className="rounded-lg border bg-white shadow-sm">
              <div className="border-b px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-800">Pipeline &amp; Customer Lifecycle</h2>
              </div>
              <div className="px-5 py-4 space-y-4">
                {/* Lifecycle breakdown */}
                {pipeline.lifecycle_breakdown && Object.keys(pipeline.lifecycle_breakdown).length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-slate-700 mb-2">Customer Lifecycle Distribution</p>
                    <div className="flex flex-wrap gap-1.5">
                      {(Object.entries(pipeline.lifecycle_breakdown) as [LifecycleTier, number][])
                        .filter(([, count]) => count > 0)
                        .map(([tier, count]) => {
                          const variant = LIFECYCLE_VARIANT[tier] || 'neutral';
                          const label = LIFECYCLE_CONFIG[tier]?.label || tier;
                          return (
                            <StatusBadge key={tier} variant={variant} size="default">
                              {label}: {count}
                            </StatusBadge>
                          );
                        })}
                    </div>
                  </div>
                )}

                {/* Pipeline stats */}
                {(pipeline.active_quotes_value != null || pipeline.conversion_trend) && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {pipeline.active_quotes_value != null && (
                      <div>
                        <p className="text-xs text-slate-500 mb-0.5">Active Quotes Value</p>
                        <p className="text-sm font-medium text-slate-800">{fmtCurrency(pipeline.active_quotes_value)}</p>
                      </div>
                    )}
                    {pipeline.conversion_trend && (
                      <div>
                        <p className="text-xs text-slate-500 mb-0.5">Conversion Trend</p>
                        <div className="flex items-center gap-1.5">
                          {trendIcon(pipeline.conversion_trend)}
                          <span className="text-sm font-medium text-slate-800">{pipeline.conversion_trend}</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Stalled quotes */}
                {pipeline.stalled_quotes && pipeline.stalled_quotes.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-slate-700 mb-2">Stalled Quotes</p>
                    <div className="space-y-1.5">
                      {pipeline.stalled_quotes.map((q, i) => (
                        <div key={i} className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
                          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                          <span className="text-sm text-amber-800">{q}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* New relationships */}
                {pipeline.new_relationships_this_period && pipeline.new_relationships_this_period.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-slate-700 mb-2">New Relationships</p>
                    <div className="flex flex-wrap gap-1.5">
                      {pipeline.new_relationships_this_period.map((r, i) => (
                        <StatusBadge key={i} variant="info" size="default">{r}</StatusBadge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Section 5: Risk Alerts */}
          {risks.length > 0 && (
            <div className="rounded-lg border bg-white shadow-sm">
              <div className="border-b px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-800">Risk Alerts ({risks.length})</h2>
              </div>
              <div className="p-4 space-y-2">
                {risks.map((risk, idx) => (
                  <div
                    key={idx}
                    className={`rounded-lg border border-l-[3px] ${severityBorder(risk.severity)} ${severityBg(risk.severity)} p-3`}
                  >
                    <div className="flex items-start gap-2">
                      {severityIcon(risk.severity)}
                      <div className="flex-1 min-w-0">
                        {/* Header row */}
                        <div className="flex flex-wrap items-center gap-1.5 mb-1">
                          <span className="text-sm font-medium text-slate-800">
                            {risk.affected_company || risk.company_name}
                          </span>
                          <StatusBadge
                            variant={risk.severity === 'critical' ? 'danger' : risk.severity === 'high' ? 'warning' : 'info'}
                            size="sm"
                          >
                            {risk.severity}
                          </StatusBadge>
                          {signalTag(risk.type) || (
                            <StatusBadge variant="neutral" size="sm">
                              {(risk.risk_type || risk.type || '').replace(/_/g, ' ')}
                            </StatusBadge>
                          )}
                          {risk.am_owner && (
                            <span className="text-xs text-slate-500">AM: {risk.am_owner}</span>
                          )}
                          {risk.days_overdue != null && risk.days_overdue > 0 && (
                            <StatusBadge variant="danger" size="sm">{risk.days_overdue}d overdue</StatusBadge>
                          )}
                        </div>
                        {/* Description */}
                        <p className="text-sm text-slate-600">{risk.description}</p>
                        {risk.recommended_action && (
                          <p className="text-xs text-primary mt-1">&rarr; {risk.recommended_action}</p>
                        )}
                        {risk.revenue_at_risk != null && (
                          <p className="text-xs text-red-600 font-medium mt-1">
                            Revenue at risk: {fmtCurrency(risk.revenue_at_risk)}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section 6: Opportunities */}
          {opportunities.length > 0 && (
            <div className="rounded-lg border bg-white shadow-sm">
              <div className="border-b px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-800">Opportunities ({opportunities.length})</h2>
              </div>
              <div className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {opportunities.map((opp, idx) => (
                    <div key={idx} className="rounded-lg border border-l-[3px] border-l-emerald-500 bg-white p-3">
                      <div className="flex flex-wrap items-center gap-1.5 mb-2">
                        <StatusBadge variant="success" size="sm">
                          {(opp.type || opp.opportunity_type || '').replace(/_/g, ' ')}
                        </StatusBadge>
                        <span className="text-sm font-medium text-slate-800">{opp.company_name}</span>
                        {lifecycleBadge(opp.lifecycle_tier)}
                        {opp.estimated_value && (
                          <StatusBadge variant="warning" size="sm">{opp.estimated_value}</StatusBadge>
                        )}
                      </div>
                      <p className="text-[13px] text-slate-600 mb-1">{opp.description}</p>
                      {opp.next_step && (
                        <p className="text-xs text-primary">&rarr; {opp.next_step}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Section 7: Competitive Landscape */}
          {competitive && (competitive.competitor_mentions?.length || competitive.price_sensitivity_signals?.length) ? (
            <div className="rounded-lg border bg-white shadow-sm">
              <div className="border-b px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-800">Competitive Landscape</h2>
              </div>
              <div className="px-5 py-4 space-y-4">
                {competitive.competitor_mentions?.length ? (
                  <div>
                    <p className="text-sm font-medium text-slate-700 mb-2">Competitor Mentions</p>
                    <div className="flex flex-wrap gap-1.5">
                      {competitive.competitor_mentions.map((c, i) => (
                        <StatusBadge key={i} variant="danger" size="default">{c}</StatusBadge>
                      ))}
                    </div>
                  </div>
                ) : null}
                {competitive.price_sensitivity_signals?.length ? (
                  <div>
                    <p className="text-sm font-medium text-slate-700 mb-2">Price Sensitivity</p>
                    <ul className="space-y-1">
                      {competitive.price_sensitivity_signals.map((s, i) => (
                        <li key={i} className="text-sm text-slate-500">&bull; {s}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {competitive.win_loss_insights?.length ? (
                  <div>
                    <p className="text-sm font-medium text-slate-700 mb-2">Win/Loss Insights</p>
                    <ul className="space-y-1">
                      {competitive.win_loss_insights.map((s, i) => (
                        <li key={i} className="text-sm text-slate-500">&bull; {s}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {/* Section 8: Action Items */}
          {actionItems.length > 0 && (
            <div className="rounded-lg border bg-white shadow-sm">
              <div className="border-b px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-800">Action Items ({actionItems.length})</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-slate-50/50">
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-[85px]">Priority</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-[160px]">Signal</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Action</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-[120px]">Owner</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-[140px]">Company</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-[110px]">Due</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Context</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {actionItems.map((item: any, idx: number) => (
                      <tr key={idx} className="hover:bg-slate-50/50 transition-colors">
                        <td className="px-4 py-2.5">{priorityBadge(item.priority)}</td>
                        <td className="px-4 py-2.5">{signalTag(item.signal_type)}</td>
                        <td className="px-4 py-2.5 text-slate-700">{item.action}</td>
                        <td className="px-4 py-2.5 text-slate-600">{item.owner || '-'}</td>
                        <td className="px-4 py-2.5 text-slate-600">{item.company || '-'}</td>
                        <td className="px-4 py-2.5">
                          {item.deadline_suggestion ? (
                            <StatusBadge variant="neutral" size="sm">{item.deadline_suggestion}</StatusBadge>
                          ) : '-'}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-slate-500">{item.context || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>
      )}
    </PageShell>
  );
}
