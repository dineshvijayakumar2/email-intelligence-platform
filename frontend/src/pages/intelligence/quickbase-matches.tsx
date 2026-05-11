/**
 * QB Match Review -- Browse QB customers (matched, staged, unmatched).
 * Candidates view allows confirm/skip with searchable company selector.
 * Matched/unmatched views are read-only for verifiability.
 * Zero antd -- Tailwind CSS + Lucide icons.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  CheckCircle2, RefreshCw, Search, ChevronDown, ChevronUp, ArrowUpDown,
  TrendingUp, AlertCircle, Link2, FileQuestion,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { StatusBadge } from '@/components/ui/status-badge';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { notify } from '@/lib/toast';
import { useClient } from '../../contexts/ClientContext';
import api from '../../services/apiClient';
import { formatCurrency, formatCurrencyCompact } from '../../utils/numberFormat';

const PAGE_SIZE = 30;

// -- Interfaces -------------------------------------------------------------------------------

interface RevenueBucket { count: number; revenue: number }

interface RevenueStats {
  total_revenue: number;
  matched_revenue: number;
  unmatched_revenue: number;
  revenue_match_rate_pct: number;
  revenue_target_pct: number;
  method_revenue: Record<string, { revenue: number; count: number }>;
  buckets: {
    email_linked: RevenueBucket;
    staged: RevenueBucket;
    no_link: RevenueBucket;
  };
}

interface HealthData {
  qb_configured: boolean;
  qb_customers: { total: number; matched: number; unmatched: number; match_rate_pct: number };
  qb_contacts: { total: number; matched: number; unmatched: number; match_rate_pct: number };
  company_enrichment: { total: number; enriched: number; not_enriched: number; coverage_pct: number };
  active_companies: { total: number; with_qb_data: number; coverage_pct: number };
  qb_unique_emails?: { total: number; valid: number };
  match_methods?: { email_lookup: number; name_based: number };
  revenue?: RevenueStats;
}

type ViewType = 'candidates' | 'matched' | 'unmatched';

interface BrowseRow {
  id: string;
  qb_record_id?: string;
  qb_name: string;
  qb_total_revenue?: number;
  match_status: 'matched' | 'candidate' | 'unmatched';
  match_method?: string;
  match_score?: number;
  sb_company_id?: string;
  sb_company_name?: string;
  sb_total_emails?: number;
  candidate_id?: string;
  qb_customer_id?: string;
}

// -- Server-side search Select for SB companies -----------------------------------------------

interface CompanyOption { value: string; label: string }

function CompanySearchSelect({
  clientId,
  defaultValue,
  defaultLabel,
  onChange,
}: {
  clientId: string;
  defaultValue: string;
  defaultLabel: string;
  onChange: (id: string, name: string) => void;
}) {
  const [options, setOptions] = useState<CompanyOption[]>(
    defaultValue ? [{ value: defaultValue, label: defaultLabel }] : []
  );
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSearch = (q: string) => {
    setQuery(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q || q.length < 2) {
      if (defaultValue) setOptions([{ value: defaultValue, label: defaultLabel }]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await api.get(
          `/v1/quickbase/companies-lookup?client_id=${clientId}&search=${encodeURIComponent(q)}&limit=30`
        ) as { companies: { id: string; company_name: string }[] };
        const results = (data.companies || []).map(c => ({
          value: c.id,
          label: c.company_name,
        }));
        if (defaultValue && !results.find(r => r.value === defaultValue)) {
          results.unshift({ value: defaultValue, label: defaultLabel });
        }
        setOptions(results);
      } catch { /* silent */ }
      setSearching(false);
    }, 300);
  };

  const selectedLabel = options.find(o => o.value === defaultValue)?.label || defaultLabel;

  return (
    <div ref={wrapperRef} className="relative w-full">
      <div
        className="flex items-center gap-1.5 w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-xs cursor-pointer hover:border-slate-400 transition-colors"
        onClick={() => setOpen(true)}
      >
        <Search className="h-3 w-3 text-slate-400 shrink-0" />
        {open ? (
          <input
            autoFocus
            className="flex-1 outline-none text-xs bg-transparent min-w-0"
            placeholder="Type to search companies..."
            value={query}
            onChange={(e) => handleSearch(e.target.value)}
          />
        ) : (
          <span className="flex-1 truncate text-slate-700">
            {selectedLabel || 'Type to search companies...'}
          </span>
        )}
        {searching && <Spinner className="h-3 w-3 animate-spin text-slate-400" />}
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-slate-200 bg-white shadow-lg max-h-48 overflow-auto">
          {options.length === 0 && !searching && (
            <div className="px-3 py-2 text-xs text-slate-400">Type 2+ chars to search</div>
          )}
          {options.map((opt) => (
            <button
              key={opt.value}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-slate-50 transition-colors ${
                opt.value === defaultValue ? 'bg-slate-50 font-medium text-slate-900' : 'text-slate-700'
              }`}
              onClick={() => {
                onChange(opt.value, opt.label);
                setOpen(false);
                setQuery('');
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// -- Sort icon helper -------------------------------------------------------------------------

function SortIcon({ field, sortBy, sortDesc }: { field: string; sortBy: string; sortDesc: boolean }) {
  if (sortBy !== field) return <ArrowUpDown className="h-3 w-3 text-slate-300 ml-1" />;
  return sortDesc
    ? <ChevronDown className="h-3 w-3 text-slate-600 ml-1" />
    : <ChevronUp className="h-3 w-3 text-slate-600 ml-1" />;
}

// -- Helpers ----------------------------------------------------------------------------------

const METHOD_LABELS: Record<string, string> = {
  email_lookup: 'Email',
  email_multi_match: 'Email (multi)',
  contact_chain: 'Contact chain',
  exact_name: 'Name',
  domain_root: 'Domain',
  fuzzy: 'Fuzzy',
};

// -- Main page ---------------------------------------------------------------------------------

export default function QuickbaseMatchesPage() {
  const { clientId } = useClient();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const [view, setView] = useState<ViewType>('candidates');
  const [rows, setRows] = useState<BrowseRow[]>([]);
  const [browseTotal, setBrowseTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState('match_score');
  const [sortDesc, setSortDesc] = useState(true);

  const [rematchLoading, setRematchLoading] = useState(false);
  const [rowSelections, setRowSelections] = useState<Record<string, { id: string; name: string }>>({});
  const [savingRow, setSavingRow] = useState<string | null>(null);
  const [rematchMenuOpen, setRematchMenuOpen] = useState(false);
  const rematchRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (rematchRef.current && !rematchRef.current.contains(e.target as Node)) {
        setRematchMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // -- Data loading ---------------------------------------------------------------------------

  const loadHealth = useCallback(async () => {
    if (!clientId) return;
    setHealthLoading(true);
    try {
      const data = await api.get(`/v1/quickbase/health?client_id=${clientId}`) as HealthData;
      setHealth(data);
    } catch { /* silent */ }
    setHealthLoading(false);
  }, [clientId]);

  const loadBrowseData = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    try {
      const off = (page - 1) * PAGE_SIZE;
      let backendSort = sortBy;
      if (view !== 'candidates') {
        if (sortBy === 'qb_total_revenue' || sortBy === 'match_score') backendSort = 'total_invoiced';
        else if (sortBy === 'qb_name') backendSort = 'customer_name';
        else backendSort = 'total_invoiced';
      }
      const data = await api.get(
        `/v1/quickbase/qb-customers-browse?client_id=${clientId}&view=${view}&limit=${PAGE_SIZE}&offset=${off}&sort_by=${backendSort}&sort_desc=${sortDesc}`
      ) as { items: BrowseRow[]; total: number };
      setRows(data.items || []);
      setBrowseTotal(data.total || 0);
    } catch { /* silent */ }
    setLoading(false);
  }, [clientId, view, page, sortBy, sortDesc]);

  useEffect(() => { loadHealth(); }, [loadHealth]);
  useEffect(() => { loadBrowseData(); }, [loadBrowseData]);

  // -- Actions --------------------------------------------------------------------------------

  const handleConfirm = async (row: BrowseRow) => {
    if (!row.candidate_id) return;
    const override = rowSelections[row.candidate_id];
    const targetName = override?.name || row.sb_company_name;
    setSavingRow(row.candidate_id);
    try {
      const params = new URLSearchParams({ accepted: 'true' });
      if (override && override.id !== row.sb_company_id) {
        params.set('sb_company_id', override.id);
      }
      await api.post(`/v1/quickbase/match-candidates/${row.candidate_id}/review?${params}`);
      notify.success(`Linked "${row.qb_name}" → "${targetName}"`);
      setRows(prev => prev.filter(r => r.candidate_id !== row.candidate_id));
      setBrowseTotal(prev => prev - 1);
      setRowSelections(prev => { const n = { ...prev }; delete n[row.candidate_id!]; return n; });
      const addedRevenue = row.qb_total_revenue || 0;
      setHealth(prev => {
        if (!prev) return prev;
        const newMatched = prev.qb_customers.matched + 1;
        const newRevenue = prev.revenue ? {
          ...prev.revenue,
          matched_revenue: prev.revenue.matched_revenue + addedRevenue,
          unmatched_revenue: prev.revenue.unmatched_revenue - addedRevenue,
          revenue_match_rate_pct: prev.revenue.total_revenue
            ? Math.round((prev.revenue.matched_revenue + addedRevenue) / prev.revenue.total_revenue * 1000) / 10
            : 0,
        } : prev.revenue;
        return {
          ...prev,
          qb_customers: { ...prev.qb_customers, matched: newMatched, unmatched: prev.qb_customers.unmatched - 1, match_rate_pct: prev.qb_customers.total ? Math.round(newMatched / prev.qb_customers.total * 1000) / 10 : 0 },
          revenue: newRevenue,
        };
      });
    } catch {
      notify.error('Failed to save mapping');
    }
    setSavingRow(null);
  };

  const handleSkip = async (candidateId: string) => {
    setSavingRow(candidateId);
    try {
      await api.post(`/v1/quickbase/match-candidates/${candidateId}/review?accepted=false`);
      setRows(prev => prev.filter(r => r.candidate_id !== candidateId));
      setBrowseTotal(prev => prev - 1);
    } catch {
      notify.error('Failed to skip');
    }
    setSavingRow(null);
  };

  const handleRematch = async (reset = false) => {
    if (!clientId) return;
    setRematchLoading(true);
    setRematchMenuOpen(false);
    try {
      const params = reset ? `client_id=${clientId}&reset=true` : `client_id=${clientId}`;
      await api.post(`/v1/quickbase/rematch?${params}`);
      notify.success(reset
        ? 'Full re-match started (clearing all matches first)'
        : 'Re-match started (processing unmatched only)');
    } catch {
      notify.error('Rematch failed');
    }
    setTimeout(() => setRematchLoading(false), 2000);
  };

  const switchView = (v: ViewType) => {
    if (v === view) return;
    setView(v);
    setPage(1);
    setSortBy(v === 'candidates' ? 'match_score' : 'qb_total_revenue');
    setSortDesc(true);
    setRowSelections({});
  };

  const scoreVariant = (score: number): 'success' | 'warning' | 'info' | 'neutral' => {
    if (score >= 85) return 'success';
    if (score >= 75) return 'warning';
    if (score >= 65) return 'info';
    return 'neutral';
  };

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortDesc(!sortDesc);
    } else {
      setSortBy(field);
      setSortDesc(true);
    }
    setPage(1);
  };

  const totalPages = Math.ceil(browseTotal / PAGE_SIZE);
  const rev = health?.revenue;

  // -- Tab config -----------------------------------------------------------------------------

  const tabs: { key: ViewType; label: string; count: number }[] = [
    { key: 'candidates', label: 'Candidates', count: rev?.buckets.staged.count ?? 0 },
    { key: 'matched', label: 'Matched', count: health?.qb_customers.matched ?? 0 },
    { key: 'unmatched', label: 'Unmatched', count: health?.qb_customers.unmatched ?? 0 },
  ];

  // -- Render ---------------------------------------------------------------------------------

  return (
    <PageShell>
      <PageHeader
        title="QB ↔ Company Match Review"
        actions={
          <>
            {/* Re-Match split button */}
            <div ref={rematchRef} className="relative inline-flex">
              <button
                className="inline-flex items-center gap-1.5 rounded-l-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50 transition-colors"
                disabled={!clientId || rematchLoading}
                onClick={() => handleRematch(false)}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${rematchLoading ? 'animate-spin' : ''}`} />
                Re-Match
              </button>
              <button
                className="inline-flex items-center rounded-r-md border-l border-slate-700 bg-slate-900 px-1.5 py-1.5 text-white hover:bg-slate-800 disabled:opacity-50 transition-colors"
                disabled={!clientId || rematchLoading}
                onClick={() => setRematchMenuOpen(prev => !prev)}
              >
                <ChevronDown className="h-3.5 w-3.5" />
              </button>
              {rematchMenuOpen && (
                <div className="absolute right-0 top-full mt-1 z-50 w-64 rounded-md border border-slate-200 bg-white shadow-lg">
                  <button
                    className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 transition-colors rounded-md"
                    onClick={() => handleRematch(true)}
                  >
                    Full Reset (clear all &amp; rebuild)
                  </button>
                </div>
              )}
            </div>

            <button
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
              disabled={!clientId}
              onClick={() => { loadHealth(); loadBrowseData(); }}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          </>
        }
      />

      {!clientId && (
        <div className="rounded-lg border bg-white shadow-sm p-8 text-center mt-10">
          <p className="text-sm text-slate-500">Select a client above to view match data</p>
        </div>
      )}

      {clientId && health && !health.qb_configured && (
        <div className="rounded-lg border bg-white shadow-sm p-8 text-center mt-10">
          <p className="text-sm text-slate-500">
            QuickBase is not configured for this client. Set up QB integration on the{' '}
            <a href="/manage/quickbase" className="text-blue-600 hover:underline">QB Config</a> page first.
          </p>
        </div>
      )}

      {clientId && (!health || health.qb_configured) && (
        <>
          {/* Revenue Dashboard */}
          {healthLoading ? (
            <ContentSkeleton rows={3} className="mb-5" />
          ) : (() => {
            const matchedPct = rev?.revenue_match_rate_pct ?? 0;
            const targetPct = rev?.revenue_target_pct ?? 95;
            const totalRev = rev?.total_revenue ?? 0;
            const matchedRev = rev?.matched_revenue ?? 0;
            const unmatchedRev = rev?.unmatched_revenue ?? 0;
            const gapToTarget = totalRev > 0 ? Math.max(0, totalRev * targetPct / 100 - matchedRev) : 0;

            return (
              <>
                {/* Row 1: Revenue Progress Bar */}
                <div className="rounded-lg border bg-white shadow-sm p-5 mb-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-emerald-600" />
                      <h3 className="text-sm font-semibold text-slate-800">Revenue Match Coverage</h3>
                    </div>
                    <span className="text-sm font-medium text-slate-600">
                      {formatCurrencyCompact(matchedRev)} / {formatCurrencyCompact(totalRev)}
                    </span>
                  </div>
                  <div className="relative h-5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${matchedPct >= targetPct ? 'bg-emerald-500' : 'bg-amber-500'}`}
                      style={{ width: `${Math.min(matchedPct, 100)}%` }}
                    />
                    <div
                      className="absolute inset-y-0 w-0.5 bg-slate-800 z-10"
                      style={{ left: `${targetPct}%` }}
                      title={`${targetPct}% target`}
                    />
                  </div>
                  <div className="flex justify-between mt-1.5">
                    <span className="text-xs font-medium text-slate-600">
                      {matchedPct}% matched
                    </span>
                    <span className="text-xs text-slate-500">
                      {targetPct}% target
                      {gapToTarget > 0 && <span className="ml-1 text-amber-600">({formatCurrencyCompact(gapToTarget)} gap)</span>}
                    </span>
                  </div>
                </div>

                {/* Row 2: Revenue KPI Cards (clickable) */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                  <div className="rounded-lg border bg-white shadow-sm p-4">
                    <p className="text-xs font-medium text-slate-500 mb-1">Total QB Revenue</p>
                    <span className="text-2xl font-semibold text-slate-900">
                      {formatCurrencyCompact(totalRev)}
                    </span>
                    <p className="text-xs text-slate-400 mt-1">{health?.qb_customers.total || 0} QB customers</p>
                  </div>

                  <div
                    className={`rounded-lg border shadow-sm p-4 cursor-pointer transition-all hover:shadow-md ${
                      view === 'matched' ? 'ring-2 ring-emerald-500 bg-emerald-50/30' : 'bg-white hover:border-emerald-300'
                    }`}
                    onClick={() => switchView('matched')}
                  >
                    <p className="text-xs font-medium text-slate-500 mb-1">Matched Revenue</p>
                    <span className="text-2xl font-semibold text-emerald-600">
                      {formatCurrencyCompact(matchedRev)}
                    </span>
                    <p className="text-xs text-slate-400 mt-1">
                      {health?.qb_customers.matched || 0} customers | {health?.match_methods?.email_lookup || 0} via email
                    </p>
                  </div>

                  <div
                    className={`rounded-lg border shadow-sm p-4 cursor-pointer transition-all hover:shadow-md ${
                      view === 'unmatched' ? 'ring-2 ring-amber-500 bg-amber-50/30' : 'bg-white hover:border-amber-300'
                    }`}
                    onClick={() => switchView('unmatched')}
                  >
                    <p className="text-xs font-medium text-slate-500 mb-1">Unmatched Revenue</p>
                    <span className="text-2xl font-semibold text-amber-600">
                      {formatCurrencyCompact(unmatchedRev)}
                    </span>
                    <p className="text-xs text-slate-400 mt-1">{health?.qb_customers.unmatched || 0} QB customers unmatched</p>
                  </div>

                  <div
                    className={`rounded-lg border shadow-sm p-4 cursor-pointer transition-all hover:shadow-md ${
                      view === 'candidates' ? 'ring-2 ring-purple-500 bg-purple-50/30' : 'bg-white hover:border-purple-300'
                    }`}
                    onClick={() => switchView('candidates')}
                  >
                    <p className="text-xs font-medium text-slate-500 mb-1">Candidates to Review</p>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-2xl font-semibold text-purple-600">{rev?.buckets.staged.count ?? 0}</span>
                      <span className="text-sm text-slate-400">staged</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">{health?.qb_contacts.match_rate_pct || 0}% contacts matched</p>
                  </div>
                </div>

                {/* Row 3: Unmatched Buckets (clickable) */}
                {rev && unmatchedRev > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
                    <div
                      className={`rounded-lg border p-4 cursor-pointer transition-all hover:shadow-md ${
                        view === 'unmatched' ? 'ring-2 ring-amber-400 border-amber-300 bg-amber-50' : 'border-amber-200 bg-amber-50/50 hover:border-amber-300'
                      }`}
                      onClick={() => switchView('unmatched')}
                    >
                      <div className="flex items-center gap-1.5 mb-1">
                        <Link2 className="h-3.5 w-3.5 text-amber-600" />
                        <p className="text-xs font-medium text-amber-700">Has Email Link</p>
                      </div>
                      <span className="text-lg font-semibold text-amber-700">
                        {formatCurrencyCompact(rev.buckets.email_linked.revenue)}
                      </span>
                      <p className="text-xs text-amber-600/70 mt-0.5">
                        {rev.buckets.email_linked.count} customers — fixable
                      </p>
                    </div>

                    <div
                      className={`rounded-lg border p-4 cursor-pointer transition-all hover:shadow-md ${
                        view === 'candidates' ? 'ring-2 ring-purple-400 border-purple-300 bg-purple-50' : 'border-purple-200 bg-purple-50/50 hover:border-purple-300'
                      }`}
                      onClick={() => switchView('candidates')}
                    >
                      <div className="flex items-center gap-1.5 mb-1">
                        <AlertCircle className="h-3.5 w-3.5 text-purple-600" />
                        <p className="text-xs font-medium text-purple-700">Staged for Review</p>
                      </div>
                      <span className="text-lg font-semibold text-purple-700">
                        {formatCurrencyCompact(rev.buckets.staged.revenue)}
                      </span>
                      <p className="text-xs text-purple-600/70 mt-0.5">
                        {rev.buckets.staged.count} customers — needs review
                      </p>
                    </div>

                    <div
                      className={`rounded-lg border p-4 cursor-pointer transition-all hover:shadow-md ${
                        view === 'unmatched' ? 'ring-2 ring-slate-400 border-slate-300 bg-slate-100' : 'border-slate-200 bg-slate-50/50 hover:border-slate-300'
                      }`}
                      onClick={() => switchView('unmatched')}
                    >
                      <div className="flex items-center gap-1.5 mb-1">
                        <FileQuestion className="h-3.5 w-3.5 text-slate-500" />
                        <p className="text-xs font-medium text-slate-600">No Link</p>
                      </div>
                      <span className="text-lg font-semibold text-slate-600">
                        {formatCurrencyCompact(rev.buckets.no_link.revenue)}
                      </span>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {rev.buckets.no_link.count} customers — manual effort
                      </p>
                    </div>
                  </div>
                )}
              </>
            );
          })()}

          {/* View Tabs + Table */}
          <div className="rounded-lg border bg-white shadow-sm">
            {/* Tab bar */}
            <div className="flex items-center gap-1 px-4 py-3 border-b border-slate-100">
              {tabs.map(tab => (
                <button
                  key={tab.key}
                  className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    view === tab.key
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'
                  }`}
                  onClick={() => switchView(tab.key)}
                >
                  {tab.label}
                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                    view === tab.key ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'
                  }`}>
                    {tab.count.toLocaleString()}
                  </span>
                </button>
              ))}
              <div className="flex-1" />
              <span className="text-xs text-slate-400">
                {browseTotal.toLocaleString()} {view === 'candidates' ? 'candidates' : 'customers'}
              </span>
            </div>

            {loading ? (
              <ContentSkeleton rows={6} />
            ) : rows.length === 0 ? (
              <div className="py-12 text-center text-sm text-slate-400">
                {view === 'candidates'
                  ? 'No candidates to review — run Re-Match to generate'
                  : view === 'matched'
                  ? 'No matched QB customers yet'
                  : 'All QB customers are matched'}
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-slate-100">
                        <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[200px]">
                          QB Customer
                        </th>
                        <th
                          className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-right w-[110px] cursor-pointer select-none"
                          onClick={() => handleSort('qb_total_revenue')}
                        >
                          <span className="inline-flex items-center justify-end">
                            QB Revenue
                            <SortIcon field="qb_total_revenue" sortBy={sortBy} sortDesc={sortDesc} />
                          </span>
                        </th>
                        {view === 'candidates' && (
                          <th
                            className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-center w-[70px] cursor-pointer select-none"
                            onClick={() => handleSort('match_score')}
                          >
                            <span className="inline-flex items-center justify-center">
                              Score
                              <SortIcon field="match_score" sortBy={sortBy} sortDesc={sortDesc} />
                            </span>
                          </th>
                        )}
                        {view === 'matched' && (
                          <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-center w-[100px]">
                            Method
                          </th>
                        )}
                        {view !== 'unmatched' && (
                          <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[280px]">
                            {view === 'candidates' ? 'Map to SB Company' : 'SB Company'}
                          </th>
                        )}
                        {view !== 'unmatched' && (
                          <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-center w-[70px]">
                            Emails
                          </th>
                        )}
                        {view === 'candidates' && (
                          <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[150px]" />
                        )}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {rows.map((row) => (
                        <tr key={row.candidate_id || row.id} className="hover:bg-slate-50/50 transition-colors">
                          {/* QB Customer */}
                          <td className="px-4 py-2 text-sm font-medium text-slate-900 truncate max-w-[200px]">
                            {row.qb_name}
                          </td>

                          {/* QB Revenue */}
                          <td className="px-4 py-2 text-sm text-right">
                            {row.qb_total_revenue != null
                              ? <span className="text-slate-700">{formatCurrency(Number(row.qb_total_revenue))}</span>
                              : <span className="text-slate-400">-</span>
                            }
                          </td>

                          {/* Score (candidates only) */}
                          {view === 'candidates' && (
                            <td className="px-4 py-2 text-center">
                              <StatusBadge variant={scoreVariant(row.match_score ?? 0)} size="sm">
                                {row.match_score?.toFixed(0)}%
                              </StatusBadge>
                            </td>
                          )}

                          {/* Method (matched only) */}
                          {view === 'matched' && (
                            <td className="px-4 py-2 text-center">
                              <StatusBadge variant={scoreVariant(row.match_score ?? 0)} size="sm">
                                {METHOD_LABELS[row.match_method || ''] || row.match_method || '—'}
                              </StatusBadge>
                            </td>
                          )}

                          {/* SB Company */}
                          {view === 'candidates' && (
                            <td className="px-4 py-2">
                              <CompanySearchSelect
                                clientId={clientId}
                                defaultValue={rowSelections[row.candidate_id!]?.id || row.sb_company_id || ''}
                                defaultLabel={rowSelections[row.candidate_id!]?.name || row.sb_company_name || ''}
                                onChange={(id, name) => setRowSelections(prev => ({ ...prev, [row.candidate_id!]: { id, name } }))}
                              />
                            </td>
                          )}
                          {view === 'matched' && (
                            <td className="px-4 py-2 text-sm text-slate-700 truncate max-w-[280px]">
                              {row.sb_company_name || '—'}
                            </td>
                          )}

                          {/* Emails */}
                          {view !== 'unmatched' && (
                            <td className="px-4 py-2 text-center text-sm">
                              {row.sb_total_emails ? (
                                <a
                                  href={`/emails/all?company_id=${row.sb_company_id}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-blue-600 hover:underline"
                                >
                                  {row.sb_total_emails}
                                </a>
                              ) : (
                                <span className="text-slate-400">0</span>
                              )}
                            </td>
                          )}

                          {/* Actions (candidates only) */}
                          {view === 'candidates' && (
                            <td className="px-4 py-2">
                              <div className="flex items-center gap-1">
                                <button
                                  className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50 transition-colors"
                                  disabled={savingRow === row.candidate_id}
                                  onClick={() => handleConfirm(row)}
                                >
                                  {savingRow === row.candidate_id ? (
                                    <Spinner className="h-3 w-3 animate-spin" />
                                  ) : (
                                    <CheckCircle2 className="h-3 w-3" />
                                  )}
                                  Confirm
                                </button>
                                <button
                                  className="rounded-md px-2 py-1 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                                  disabled={savingRow === row.candidate_id}
                                  onClick={() => handleSkip(row.candidate_id!)}
                                >
                                  Skip
                                </button>
                              </div>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
                    <span className="text-xs text-slate-500">
                      {browseTotal.toLocaleString()} {view === 'candidates' ? 'candidates' : 'customers'}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        className="rounded-md px-2.5 py-1 text-xs border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
                        disabled={page <= 1}
                        onClick={() => setPage(page - 1)}
                      >
                        Previous
                      </button>
                      <span className="text-xs text-slate-500 px-2">
                        {page} / {totalPages}
                      </span>
                      <button
                        className="rounded-md px-2.5 py-1 text-xs border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
                        disabled={page >= totalPages}
                        onClick={() => setPage(page + 1)}
                      >
                        Next
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}
    </PageShell>
  );
}
