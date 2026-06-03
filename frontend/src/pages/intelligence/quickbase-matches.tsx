/**
 * QB Cleanup Dashboard -- Full pipeline view: QB -> Companies -> Contacts -> Emails.
 * Single RPC call for all stats. Browse table for candidates/matched/unmatched.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  CheckCircle2, RefreshCw, Search, ChevronDown, ChevronUp, ArrowUpDown,
  TrendingUp, AlertTriangle, Building2, Users, Mail, ArrowRight,
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

// -- Types ------------------------------------------------------------------------------------

interface DashboardData {
  qb_configured: boolean;
  revenue?: {
    total: number;
    matched: number;
    unmatched: number;
    match_rate_pct: number;
    method_breakdown: Record<string, { count: number; revenue: number }>;
    buckets: {
      email_linked: { count: number; revenue: number };
      staged: { count: number; revenue: number };
      no_link: { count: number; revenue: number };
    };
  };
  companies?: {
    total_qb_customers: number;
    matched_qb_customers: number;
    unmatched_qb_customers: number;
    total_sb_companies: number;
    qb_anchored_sb: number;
    contaminated_sb: number;
  };
  contacts?: {
    total: number;
    with_qb_company: number;
    with_non_qb_company: number;
    no_company: number;
  };
  emails?: {
    total: number;
    with_qb_company: number;
    with_non_qb_company: number;
    no_company: number;
  };
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
  sb_email_domains?: string[];
  sb_website?: string;
  candidate_id?: string;
  qb_customer_id?: string;
}

// -- CompanySearchSelect ----------------------------------------------------------------------

interface CompanyOption { value: string; label: string }

function CompanySearchSelect({
  clientId, defaultValue, defaultLabel, onChange,
}: {
  clientId: string; defaultValue: string; defaultLabel: string;
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
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) setOpen(false);
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
        const results = (data.companies || []).map(c => ({ value: c.id, label: c.company_name }));
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
          <input autoFocus className="flex-1 outline-none text-xs bg-transparent min-w-0"
            placeholder="Type to search companies..." value={query}
            onChange={(e) => handleSearch(e.target.value)} />
        ) : (
          <span className="flex-1 truncate text-slate-700">{selectedLabel || 'Type to search...'}</span>
        )}
        {searching && <Spinner className="h-3 w-3 animate-spin text-slate-400" />}
      </div>
      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-slate-200 bg-white shadow-lg max-h-48 overflow-auto">
          {options.length === 0 && !searching && (
            <div className="px-3 py-2 text-xs text-slate-400">Type 2+ chars to search</div>
          )}
          {options.map((opt) => (
            <button key={opt.value}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-slate-50 transition-colors ${
                opt.value === defaultValue ? 'bg-slate-50 font-medium text-slate-900' : 'text-slate-700'}`}
              onClick={() => { onChange(opt.value, opt.label); setOpen(false); setQuery(''); }}>
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// -- Helpers ----------------------------------------------------------------------------------

// Freemail domains carry no matching signal — de-emphasize them.
const FREEMAIL_DOMAINS = new Set([
  'gmail.com', 'outlook.com', 'hotmail.com', 'yahoo.com', 'yahoo.com.au',
  'bigpond.com', 'icloud.com', 'live.com', 'me.com', 'aol.com', 'optusnet.com.au',
]);

function DomainChips({ domains, website }: { domains?: string[]; website?: string | null }) {
  const list = (domains || []).filter(Boolean);
  if (list.length === 0 && !website) {
    return <span className="text-[11px] text-slate-300">no email domains</span>;
  }
  // Business domains first, freemail last; cap display to keep the cell compact.
  const sorted = [...list].sort((a, b) => {
    const af = FREEMAIL_DOMAINS.has(a.toLowerCase()) ? 1 : 0;
    const bf = FREEMAIL_DOMAINS.has(b.toLowerCase()) ? 1 : 0;
    return af - bf;
  });
  const shown = sorted.slice(0, 4);
  const extra = sorted.length - shown.length;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((d) => {
        const isFree = FREEMAIL_DOMAINS.has(d.toLowerCase());
        return (
          <span
            key={d}
            className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${
              isFree ? 'bg-slate-100 text-slate-400' : 'bg-blue-50 text-blue-700'
            }`}
            title={isFree ? 'Freemail domain (weak signal)' : 'Email domain'}
          >
            {d}
          </span>
        );
      })}
      {extra > 0 && (
        <span className="text-[10px] text-slate-400" title={sorted.slice(4).join(', ')}>
          +{extra}
        </span>
      )}
    </div>
  );
}

function SortIcon({ field, sortBy, sortDesc }: { field: string; sortBy: string; sortDesc: boolean }) {
  if (sortBy !== field) return <ArrowUpDown className="h-3 w-3 text-slate-300 ml-1" />;
  return sortDesc
    ? <ChevronDown className="h-3 w-3 text-slate-600 ml-1" />
    : <ChevronUp className="h-3 w-3 text-slate-600 ml-1" />;
}

const METHOD_LABELS: Record<string, string> = {
  email_lookup: 'Email',
  email_multi_match: 'Email (multi)',
  contact_chain: 'Contact chain',
  exact_name: 'Name',
  domain_root: 'Domain',
  fuzzy: 'Fuzzy',
  qb_anchored_link: 'QB link',
  qb_anchored_create: 'QB create',
};

function pct(part: number, total: number): string {
  if (!total) return '0';
  return (part / total * 100).toFixed(1);
}

function PipelineArrow() {
  return (
    <div className="hidden lg:flex items-center justify-center">
      <ArrowRight className="h-5 w-5 text-slate-300" />
    </div>
  );
}

// -- Pipeline card (reused 4x) ----------------------------------------------------------------

function PipelineCard({ icon, label, matched, matchedLabel, total, color, secondaryValue, secondaryLabel }: {
  icon: React.ReactNode; label: string; matched: number; matchedLabel: string;
  total: number; color: string; secondaryValue?: number; secondaryLabel?: string;
}) {
  const percentage = total > 0 ? (matched / total * 100) : 0;
  const colorMap: Record<string, { bg: string; bar: string; text: string; light: string }> = {
    emerald: { bg: 'bg-emerald-50', bar: 'bg-emerald-500', text: 'text-emerald-700', light: 'text-emerald-600' },
    blue: { bg: 'bg-blue-50', bar: 'bg-blue-500', text: 'text-blue-700', light: 'text-blue-600' },
    violet: { bg: 'bg-violet-50', bar: 'bg-violet-500', text: 'text-violet-700', light: 'text-violet-600' },
    amber: { bg: 'bg-amber-50', bar: 'bg-amber-500', text: 'text-amber-700', light: 'text-amber-600' },
  };
  const c = colorMap[color] || colorMap.emerald;

  return (
    <div className={`rounded-lg border p-4 ${c.bg} border-${color}-200`}>
      <div className="flex items-center gap-1.5 mb-2">
        {icon}
        <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">{label}</span>
      </div>
      <div className="flex items-baseline gap-1.5 mb-1">
        <span className={`text-2xl font-bold ${c.text}`}>{matched.toLocaleString()}</span>
        <span className="text-xs text-slate-500">/ {total.toLocaleString()}</span>
      </div>
      <div className="text-xs text-slate-500 mb-2">{matchedLabel} ({pct(matched, total)}%)</div>
      <div className="h-1.5 bg-white/60 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${c.bar} transition-all duration-500`} style={{ width: `${Math.min(percentage, 100)}%` }} />
      </div>
      {secondaryValue !== undefined && secondaryLabel && (
        <div className="text-[11px] text-slate-400 mt-1.5">{secondaryValue.toLocaleString()} {secondaryLabel}</div>
      )}
    </div>
  );
}

// -- Main page ---------------------------------------------------------------------------------

export default function QuickbaseMatchesPage() {
  const { clientId } = useClient();
  const [data, setData] = useState<DashboardData | null>(null);
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
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [methodFilter, setMethodFilter] = useState('');
  const [rematchMenuOpen, setRematchMenuOpen] = useState(false);
  const rematchRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (rematchRef.current && !rematchRef.current.contains(e.target as Node)) setRematchMenuOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // -- Data loading ---------------------------------------------------------------------------

  const loadHealth = useCallback(async () => {
    if (!clientId) return;
    setHealthLoading(true);
    try {
      const d = await api.get(`/v1/quickbase/health?client_id=${clientId}`) as DashboardData;
      setData(d);
    } catch { /* silent */ }
    setHealthLoading(false);
  }, [clientId]);

  const loadBrowseData = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    try {
      const off = (page - 1) * PAGE_SIZE;
      let backendSort = sortBy;
      if (sortBy === 'qb_total_revenue') {
        backendSort = 'total_invoiced';
      } else if (view !== 'candidates') {
        if (sortBy === 'qb_name') backendSort = 'customer_name';
        else if (sortBy === 'sb_total_emails') backendSort = 'sb_total_emails';
        else if (sortBy === 'match_score') backendSort = 'total_invoiced';
        else backendSort = 'total_invoiced';
      }
      const searchParam = debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : '';
      const methodParam = methodFilter ? `&method=${encodeURIComponent(methodFilter)}` : '';
      const d = await api.get(
        `/v1/quickbase/qb-customers-browse?client_id=${clientId}&view=${view}&limit=${PAGE_SIZE}&offset=${off}&sort_by=${backendSort}&sort_desc=${sortDesc}${searchParam}${methodParam}`
      ) as { items: BrowseRow[]; total: number };
      setRows(d.items || []);
      setBrowseTotal(d.total || 0);
    } catch { /* silent */ }
    setLoading(false);
  }, [clientId, view, page, sortBy, sortDesc, debouncedSearch, methodFilter]);

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
      if (override && override.id !== row.sb_company_id) params.set('sb_company_id', override.id);
      await api.post(`/v1/quickbase/match-candidates/${row.candidate_id}/review?${params}`);
      notify.success(`Linked "${row.qb_name}" -> "${targetName}"`);
      setRows(prev => prev.filter(r => r.candidate_id !== row.candidate_id));
      setBrowseTotal(prev => prev - 1);
      setRowSelections(prev => { const n = { ...prev }; delete n[row.candidate_id!]; return n; });
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

  const handleUnmatch = async (row: BrowseRow) => {
    if (!row.qb_record_id || !clientId) return;
    setSavingRow(row.id);
    try {
      await api.post(`/v1/quickbase/unmatch-company?client_id=${clientId}&qb_record_id=${row.qb_record_id}`);
      notify.success(`Unmatched "${row.qb_name}"`);
      setRows(prev => prev.filter(r => r.id !== row.id));
      setBrowseTotal(prev => prev - 1);
      loadHealth();
    } catch {
      notify.error('Failed to unmatch');
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
      notify.success(reset ? 'Full re-match started (clearing all matches first)' : 'Re-match started (unmatched only)');
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
    setSearchTerm('');
    setDebouncedSearch('');
    setMethodFilter('');
  };

  const scoreVariant = (score: number): 'success' | 'warning' | 'info' | 'neutral' => {
    if (score >= 85) return 'success';
    if (score >= 75) return 'warning';
    if (score >= 65) return 'info';
    return 'neutral';
  };

  const handleSort = (field: string) => {
    if (sortBy === field) setSortDesc(!sortDesc);
    else { setSortBy(field); setSortDesc(true); }
    setPage(1);
  };

  const totalPages = Math.ceil(browseTotal / PAGE_SIZE);
  const rev = data?.revenue;
  const co = data?.companies;
  const ct = data?.contacts;
  const em = data?.emails;

  const tabs: { key: ViewType; label: string; count: number }[] = [
    { key: 'candidates', label: 'Candidates', count: rev?.buckets.staged.count ?? 0 },
    { key: 'matched', label: 'Matched', count: co?.matched_qb_customers ?? 0 },
    { key: 'unmatched', label: 'Unmatched', count: co?.unmatched_qb_customers ?? 0 },
  ];

  // -- Render ---------------------------------------------------------------------------------

  return (
    <PageShell>
      <PageHeader
        title="QB Cleanup Dashboard"
        actions={
          <>
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
                  <button className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 transition-colors rounded-md"
                    onClick={() => handleRematch(true)}>
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
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </button>
          </>
        }
      />

      {!clientId && (
        <div className="rounded-lg border bg-white shadow-sm p-8 text-center mt-10">
          <p className="text-sm text-slate-500">Select a client above to view match data</p>
        </div>
      )}

      {clientId && data && !data.qb_configured && (
        <div className="rounded-lg border bg-white shadow-sm p-8 text-center mt-10">
          <p className="text-sm text-slate-500">
            QuickBase is not configured for this client. Set up QB integration on the{' '}
            <a href="/manage/quickbase" className="text-blue-600 hover:underline">QB Config</a> page first.
          </p>
        </div>
      )}

      {clientId && (!data || data.qb_configured) && (
        <>
          {healthLoading ? (
            <ContentSkeleton rows={4} className="mb-5" />
          ) : rev && co && ct && em ? (
            <>
              {/* Row 1: Revenue Progress Bar */}
              <div className="rounded-lg border bg-white shadow-sm p-5 mb-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-emerald-600" />
                    <h3 className="text-sm font-semibold text-slate-800">Revenue Match Coverage</h3>
                  </div>
                  <span className="text-sm font-medium text-slate-600">
                    {formatCurrencyCompact(rev.matched)} / {formatCurrencyCompact(rev.total)}
                  </span>
                </div>
                <div className="relative h-5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${rev.match_rate_pct >= 95 ? 'bg-emerald-500' : 'bg-amber-500'}`}
                    style={{ width: `${Math.min(rev.match_rate_pct, 100)}%` }}
                  />
                  <div className="absolute inset-y-0 w-0.5 bg-slate-800 z-10" style={{ left: '95%' }} title="95% target" />
                </div>
                <div className="flex justify-between mt-1.5">
                  <span className="text-xs font-medium text-slate-600">{rev.match_rate_pct}% matched</span>
                  <span className="text-xs text-slate-500">
                    95% target
                    {rev.match_rate_pct < 95 && (
                      <span className="ml-1 text-amber-600">
                        ({formatCurrencyCompact(Math.max(0, rev.total * 0.95 - rev.matched))} gap)
                      </span>
                    )}
                  </span>
                </div>
              </div>

              {/* Row 2: Pipeline Flow - QB -> Companies -> Contacts -> Emails */}
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] gap-3 mb-4 items-stretch">
                <PipelineCard
                  icon={<TrendingUp className="h-4 w-4 text-emerald-600" />}
                  label="QB Customers"
                  matched={co.matched_qb_customers}
                  matchedLabel="Matched to SB"
                  total={co.total_qb_customers}
                  color="emerald"
                  secondaryValue={co.unmatched_qb_customers}
                  secondaryLabel={`unmatched (${formatCurrencyCompact(rev.unmatched)} revenue)`}
                />
                <PipelineArrow />
                <PipelineCard
                  icon={<Building2 className="h-4 w-4 text-blue-600" />}
                  label="SB Companies"
                  matched={co.qb_anchored_sb}
                  matchedLabel="QB-anchored"
                  total={co.total_sb_companies}
                  color="blue"
                  secondaryValue={co.contaminated_sb}
                  secondaryLabel="contaminated (>1 QB match)"
                />
                <PipelineArrow />
                <PipelineCard
                  icon={<Users className="h-4 w-4 text-violet-600" />}
                  label="Contacts"
                  matched={ct.with_qb_company}
                  matchedLabel="QB-linked company"
                  total={ct.total}
                  color="violet"
                  secondaryValue={ct.with_non_qb_company}
                  secondaryLabel="linked to non-QB company"
                />
                <PipelineArrow />
                <PipelineCard
                  icon={<Mail className="h-4 w-4 text-amber-600" />}
                  label="Emails"
                  matched={em.with_qb_company}
                  matchedLabel="QB-linked company"
                  total={em.total}
                  color="amber"
                  secondaryValue={em.no_company}
                  secondaryLabel="no company link"
                />
              </div>

              {/* Row 3: Match Method Breakdown + Unmatched Buckets */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                {/* Method breakdown */}
                <div className="rounded-lg border bg-white shadow-sm p-4">
                  <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-3">Match Methods</h4>
                  <div className="space-y-2">
                    {Object.entries(rev.method_breakdown)
                      .sort(([,a], [,b]) => b.revenue - a.revenue)
                      .map(([method, { count, revenue }]) => (
                        <div key={method} className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-slate-700">{METHOD_LABELS[method] || method}</span>
                            <span className="text-slate-400">{count.toLocaleString()}</span>
                          </div>
                          <span className="text-slate-600 font-medium">{formatCurrencyCompact(revenue)}</span>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Unmatched buckets + alerts */}
                <div className="rounded-lg border bg-white shadow-sm p-4">
                  <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-3">Unmatched Breakdown</h4>
                  <div className="space-y-2.5">
                    {rev.buckets.staged.count > 0 && (
                      <button onClick={() => switchView('candidates')}
                        className="w-full flex items-center justify-between text-xs p-2 rounded-md bg-purple-50 hover:bg-purple-100 transition-colors text-left">
                        <div>
                          <span className="font-medium text-purple-700">Staged for review</span>
                          <span className="text-purple-500 ml-1.5">{rev.buckets.staged.count}</span>
                        </div>
                        <span className="font-medium text-purple-700">{formatCurrencyCompact(rev.buckets.staged.revenue)}</span>
                      </button>
                    )}
                    {rev.buckets.email_linked.count > 0 && (
                      <button onClick={() => switchView('unmatched')}
                        className="w-full flex items-center justify-between text-xs p-2 rounded-md bg-amber-50 hover:bg-amber-100 transition-colors text-left">
                        <div>
                          <span className="font-medium text-amber-700">Has email link (fixable)</span>
                          <span className="text-amber-500 ml-1.5">{rev.buckets.email_linked.count}</span>
                        </div>
                        <span className="font-medium text-amber-700">{formatCurrencyCompact(rev.buckets.email_linked.revenue)}</span>
                      </button>
                    )}
                    {rev.buckets.no_link.count > 0 && (
                      <div className="flex items-center justify-between text-xs p-2 rounded-md bg-slate-50">
                        <div>
                          <span className="font-medium text-slate-600">No link (manual)</span>
                          <span className="text-slate-400 ml-1.5">{rev.buckets.no_link.count}</span>
                        </div>
                        <span className="font-medium text-slate-600">{formatCurrencyCompact(rev.buckets.no_link.revenue)}</span>
                      </div>
                    )}
                    {co.contaminated_sb > 0 && (
                      <div className="flex items-center gap-1.5 text-xs p-2 rounded-md bg-red-50">
                        <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                        <span className="text-red-700 font-medium">{co.contaminated_sb.toLocaleString()} contaminated companies</span>
                        <span className="text-red-500 ml-auto">needs decontamination</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : null}

          {/* Browse Table */}
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center gap-1 px-4 py-3 border-b border-slate-100">
              {tabs.map(tab => (
                <button key={tab.key}
                  className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    view === tab.key ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'
                  }`}
                  onClick={() => switchView(tab.key)}>
                  {tab.label}
                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                    view === tab.key ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'
                  }`}>{tab.count.toLocaleString()}</span>
                </button>
              ))}
              <div className="flex-1" />
              {view === 'matched' && (
                <select
                  value={methodFilter}
                  onChange={(e) => { setMethodFilter(e.target.value); setPage(1); }}
                  className="text-xs rounded-md border border-slate-200 bg-white text-slate-700 px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-slate-300"
                >
                  <option value="">All methods</option>
                  <option value="email_lookup">Email</option>
                  <option value="contact_chain">Contact chain</option>
                  <option value="exact_name">Name</option>
                  <option value="domain_root">Domain</option>
                  <option value="fuzzy">Fuzzy</option>
                  <option value="manual">Manual</option>
                  <option value="qb_anchored_link">QB link</option>
                  <option value="qb_anchored_create">QB create</option>
                </select>
              )}
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search by name..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-48 pl-7 pr-2 py-1.5 text-xs rounded-md border border-slate-200 bg-white text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-300"
                />
              </div>
              <span className="text-xs text-slate-400">{browseTotal.toLocaleString()} {view === 'candidates' ? 'candidates' : 'customers'}</span>
            </div>

            {loading ? (
              <ContentSkeleton rows={6} />
            ) : rows.length === 0 ? (
              <div className="py-12 text-center text-sm text-slate-400">
                {view === 'candidates' ? 'No candidates to review -- run Re-Match to generate'
                  : view === 'matched' ? 'No matched QB customers yet'
                  : 'All QB customers are matched'}
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-slate-100">
                        <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[200px]">QB Customer</th>
                        <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-right w-[110px] cursor-pointer select-none"
                          onClick={() => handleSort('qb_total_revenue')}>
                          <span className="inline-flex items-center justify-end">
                            QB Revenue <SortIcon field="qb_total_revenue" sortBy={sortBy} sortDesc={sortDesc} />
                          </span>
                        </th>
                        {view === 'candidates' && (
                          <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-center w-[70px] cursor-pointer select-none"
                            onClick={() => handleSort('match_score')}>
                            <span className="inline-flex items-center justify-center">
                              Score <SortIcon field="match_score" sortBy={sortBy} sortDesc={sortDesc} />
                            </span>
                          </th>
                        )}
                        {view === 'matched' && (
                          <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-center w-[100px]">Method</th>
                        )}
                        {view !== 'unmatched' && (
                          <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[280px]">
                            {view === 'candidates' ? 'Map to SB Company' : 'SB Company'}
                          </th>
                        )}
                        {view !== 'unmatched' && (
                          <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-center w-[70px] cursor-pointer select-none"
                            onClick={() => handleSort('sb_total_emails')}>
                            <span className="inline-flex items-center justify-center">
                              Emails <SortIcon field="sb_total_emails" sortBy={sortBy} sortDesc={sortDesc} />
                            </span>
                          </th>
                        )}
                        {(view === 'candidates' || view === 'matched') && (
                          <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[80px]" />
                        )}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {rows.map((row) => (
                        <tr key={row.candidate_id || row.id} className="hover:bg-slate-50/50 transition-colors">
                          <td className="px-4 py-2 text-sm font-medium text-slate-900 truncate max-w-[200px]">{row.qb_name}</td>
                          <td className="px-4 py-2 text-sm text-right">
                            {row.qb_total_revenue != null
                              ? <span className="text-slate-700">{formatCurrency(Number(row.qb_total_revenue))}</span>
                              : <span className="text-slate-400">-</span>}
                          </td>
                          {view === 'candidates' && (
                            <td className="px-4 py-2 text-center">
                              <StatusBadge variant={scoreVariant(row.match_score ?? 0)} size="sm">
                                {row.match_score?.toFixed(0)}%
                              </StatusBadge>
                            </td>
                          )}
                          {view === 'matched' && (
                            <td className="px-4 py-2 text-center">
                              <StatusBadge variant={scoreVariant(row.match_score ?? 0)} size="sm">
                                {METHOD_LABELS[row.match_method || ''] || row.match_method || '--'}
                              </StatusBadge>
                            </td>
                          )}
                          {view === 'candidates' && (
                            <td className="px-4 py-2">
                              <CompanySearchSelect clientId={clientId}
                                defaultValue={rowSelections[row.candidate_id!]?.id || row.sb_company_id || ''}
                                defaultLabel={rowSelections[row.candidate_id!]?.name || row.sb_company_name || ''}
                                onChange={(id, name) => setRowSelections(prev => ({ ...prev, [row.candidate_id!]: { id, name } }))} />
                              {!rowSelections[row.candidate_id!] && (
                                <div className="mt-1">
                                  <DomainChips domains={row.sb_email_domains} website={row.sb_website} />
                                </div>
                              )}
                            </td>
                          )}
                          {view === 'matched' && (
                            <td className="px-4 py-2 text-sm text-slate-700 max-w-[280px]">
                              <div className="truncate">{row.sb_company_name || '--'}</div>
                              {row.sb_company_name && (
                                <div className="mt-1">
                                  <DomainChips domains={row.sb_email_domains} website={row.sb_website} />
                                </div>
                              )}
                            </td>
                          )}
                          {view !== 'unmatched' && (
                            <td className="px-4 py-2 text-center text-sm">
                              {row.sb_total_emails ? (
                                <a href={`/emails/all?company_id=${row.sb_company_id}`} target="_blank" rel="noreferrer"
                                  className="text-blue-600 hover:underline">{row.sb_total_emails}</a>
                              ) : <span className="text-slate-400">0</span>}
                            </td>
                          )}
                          {view === 'candidates' && (
                            <td className="px-4 py-2">
                              <div className="flex items-center gap-1">
                                <button
                                  className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50 transition-colors"
                                  disabled={savingRow === row.candidate_id}
                                  onClick={() => handleConfirm(row)}>
                                  {savingRow === row.candidate_id
                                    ? <Spinner className="h-3 w-3 animate-spin" />
                                    : <CheckCircle2 className="h-3 w-3" />}
                                  Confirm
                                </button>
                                <button
                                  className="rounded-md px-2 py-1 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                                  disabled={savingRow === row.candidate_id}
                                  onClick={() => handleSkip(row.candidate_id!)}>
                                  Skip
                                </button>
                              </div>
                            </td>
                          )}
                          {view === 'matched' && (
                            <td className="px-4 py-2 text-center">
                              <button
                                className="rounded-md px-2 py-1 text-xs text-red-500 hover:text-red-700 hover:bg-red-50 disabled:opacity-50 transition-colors"
                                disabled={savingRow === row.id}
                                onClick={() => handleUnmatch(row)}
                                title="Remove this match">
                                {savingRow === row.id ? <Spinner className="h-3 w-3 animate-spin" /> : '✕'}
                              </button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {totalPages > 1 && (
                  <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
                    <span className="text-xs text-slate-500">{browseTotal.toLocaleString()} {view === 'candidates' ? 'candidates' : 'customers'}</span>
                    <div className="flex items-center gap-1">
                      <button className="rounded-md px-2.5 py-1 text-xs border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
                        disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
                      <span className="text-xs text-slate-500 px-2">{page} / {totalPages}</span>
                      <button className="rounded-md px-2.5 py-1 text-xs border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
                        disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
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
