/**
 * QB Match Review -- Map QB customers to SB companies via searchable selector.
 * Fuzzy candidates are pre-suggested; user can type to search all SB companies (server-side).
 * Zero antd -- Tailwind CSS + Lucide icons.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  CheckCircle2, RefreshCw, Search, ChevronDown, ChevronUp, ArrowUpDown,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { StatusBadge } from '@/components/ui/status-badge';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { notify } from '@/lib/toast';
import { useClient } from '../../contexts/ClientContext';
import api from '../../services/apiClient';
import { formatCurrency } from '../../utils/numberFormat';

const PAGE_SIZE = 30;

interface MatchCandidate {
  id: string;
  sb_company_id: string;
  sb_company_name: string;
  qb_record_id: string;
  qb_customer_id: string;
  qb_name: string;
  match_score: number;
  match_method: string;
  reviewed: boolean;
  accepted: boolean | null;
  qb_total_revenue?: number;
  sb_total_emails?: number;
}

interface HealthData {
  qb_configured: boolean;
  qb_customers: { total: number; matched: number; unmatched: number; match_rate_pct: number };
  qb_contacts: { total: number; matched: number; unmatched: number; match_rate_pct: number };
  company_enrichment: { total: number; enriched: number; not_enriched: number; coverage_pct: number };
  active_companies: { total: number; with_qb_data: number; coverage_pct: number };
  qb_unique_emails?: { total: number; valid: number };
  match_methods?: { email_lookup: number; name_based: number };
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

  // Close dropdown when clicking outside
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

// -- Main page ---------------------------------------------------------------------------------

export default function QuickbaseMatchesPage() {
  const { clientId } = useClient();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const [candidates, setCandidates] = useState<MatchCandidate[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState('match_score');
  const [sortDesc, setSortDesc] = useState(true);

  const [rematchLoading, setRematchLoading] = useState(false);
  const [rowSelections, setRowSelections] = useState<Record<string, { id: string; name: string }>>({});
  const [savingRow, setSavingRow] = useState<string | null>(null);
  const [rematchMenuOpen, setRematchMenuOpen] = useState(false);
  const rematchRef = useRef<HTMLDivElement>(null);

  // Close rematch dropdown on outside click
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

  const loadCandidates = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    try {
      const offset = (page - 1) * PAGE_SIZE;
      const data = await api.get(
        `/v1/quickbase/match-candidates?client_id=${clientId}&reviewed=false&limit=${PAGE_SIZE}&offset=${offset}&sort_by=${sortBy}&sort_desc=${sortDesc}`
      ) as { candidates: MatchCandidate[]; total: number };
      setCandidates(data.candidates || []);
      setTotal(data.total || 0);
    } catch { /* silent */ }
    setLoading(false);
  }, [clientId, page, sortBy, sortDesc]);

  useEffect(() => { loadHealth(); }, [loadHealth]);
  useEffect(() => { loadCandidates(); }, [loadCandidates]);

  // -- Actions --------------------------------------------------------------------------------

  const handleConfirm = async (candidate: MatchCandidate) => {
    const override = rowSelections[candidate.id];
    const targetName = override?.name || candidate.sb_company_name;
    setSavingRow(candidate.id);
    try {
      const params = new URLSearchParams({ accepted: 'true' });
      if (override && override.id !== candidate.sb_company_id) {
        params.set('sb_company_id', override.id);
      }
      await api.post(`/v1/quickbase/match-candidates/${candidate.id}/review?${params}`);
      notify.success(`Linked "${candidate.qb_name}" \u2192 "${targetName}"`);
      setCandidates(prev => prev.filter(c => c.id !== candidate.id));
      setTotal(prev => prev - 1);
      setRowSelections(prev => { const n = { ...prev }; delete n[candidate.id]; return n; });
      // Update matched count optimistically instead of re-fetching
      setHealth(prev => prev ? {
        ...prev,
        qb_customers: { ...prev.qb_customers, matched: prev.qb_customers.matched + 1, unmatched: prev.qb_customers.unmatched - 1, match_rate_pct: prev.qb_customers.total ? Math.round((prev.qb_customers.matched + 1) / prev.qb_customers.total * 1000) / 10 : 0 },
      } : prev);
    } catch {
      notify.error('Failed to save mapping');
    }
    setSavingRow(null);
  };

  const handleSkip = async (candidateId: string) => {
    setSavingRow(candidateId);
    try {
      await api.post(`/v1/quickbase/match-candidates/${candidateId}/review?accepted=false`);
      setCandidates(prev => prev.filter(c => c.id !== candidateId));
      setTotal(prev => prev - 1);
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

  const scoreVariant = (score: number): 'success' | 'warning' | 'info' | 'neutral' => {
    if (score >= 95) return 'success';
    if (score >= 90) return 'success';
    if (score >= 85) return 'warning';
    return 'info';
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

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // -- Render ---------------------------------------------------------------------------------

  return (
    <PageShell>
      <PageHeader
        title="QB \u2194 Company Match Review"
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
              onClick={() => { loadHealth(); loadCandidates(); }}
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
          {/* Match Health Stats */}
          {healthLoading ? (
            <ContentSkeleton rows={2} className="mb-5" />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
              {/* QB Customers Matched */}
              <div className="rounded-lg border bg-white shadow-sm p-4">
                <p className="text-xs font-medium text-slate-500 mb-1">QB Customers Matched</p>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-2xl font-semibold text-green-700">
                    {health?.qb_customers.matched || 0}
                  </span>
                  <span className="text-sm text-slate-400">/ {health?.qb_customers.total || 0}</span>
                </div>
                <p className="text-xs text-slate-400 mt-1">{health?.qb_customers.match_rate_pct || 0}% match rate</p>
              </div>

              {/* Email-Matched */}
              <div className="rounded-lg border bg-white shadow-sm p-4">
                <p className="text-xs font-medium text-slate-500 mb-1">Email-Matched</p>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-2xl font-semibold text-blue-600">
                    {health?.match_methods?.email_lookup || 0}
                  </span>
                  <span className="text-sm text-slate-400">/ {health?.qb_customers.total || 0} QB customers</span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  {health?.match_methods?.name_based || 0} name-based | {health?.qb_unique_emails?.valid || 0} QB emails
                </p>
              </div>

              {/* QB Contacts Matched */}
              <div className="rounded-lg border bg-white shadow-sm p-4">
                <p className="text-xs font-medium text-slate-500 mb-1">QB Contacts Matched</p>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-2xl font-semibold text-green-700">
                    {health?.qb_contacts.matched || 0}
                  </span>
                  <span className="text-sm text-slate-400">/ {health?.qb_contacts.total || 0}</span>
                </div>
                <p className="text-xs text-slate-400 mt-1">{health?.qb_contacts.match_rate_pct || 0}% match rate</p>
              </div>

              {/* Fuzzy Candidates */}
              <div className="rounded-lg border bg-white shadow-sm p-4">
                <p className="text-xs font-medium text-slate-500 mb-1">Fuzzy Candidates</p>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-2xl font-semibold text-purple-600">
                    {total}
                  </span>
                  <span className="text-sm text-slate-400">to review</span>
                </div>
                <p className="text-xs text-slate-400 mt-1">{health?.qb_customers.unmatched || 0} still unmatched</p>
              </div>
            </div>
          )}

          {/* Candidates table */}
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-slate-800">Fuzzy Match Candidates</h3>
                {total > 0 && (
                  <StatusBadge variant="purple" size="sm">{total}</StatusBadge>
                )}
              </div>
            </div>

            {loading ? (
              <ContentSkeleton rows={6} />
            ) : candidates.length === 0 ? (
              <div className="py-12 text-center text-sm text-slate-400">
                No fuzzy candidates -- run Re-Match to generate
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-slate-100">
                        <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[180px]">
                          QB Customer
                        </th>
                        <th
                          className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-right w-[100px] cursor-pointer select-none"
                          onClick={() => handleSort('qb_total_revenue')}
                        >
                          <span className="inline-flex items-center justify-end">
                            QB Revenue
                            <SortIcon field="qb_total_revenue" sortBy={sortBy} sortDesc={sortDesc} />
                          </span>
                        </th>
                        <th
                          className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-center w-[70px] cursor-pointer select-none"
                          onClick={() => handleSort('match_score')}
                        >
                          <span className="inline-flex items-center justify-center">
                            Score
                            <SortIcon field="match_score" sortBy={sortBy} sortDesc={sortDesc} />
                          </span>
                        </th>
                        <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[280px]">
                          Map to SB Company
                        </th>
                        <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 text-center w-[70px]">
                          Emails
                        </th>
                        <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-600 w-[150px]" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {candidates.map((record) => (
                        <tr key={record.id} className="hover:bg-slate-50/50 transition-colors">
                          {/* QB Customer */}
                          <td className="px-4 py-2 text-sm font-medium text-slate-900 truncate max-w-[180px]">
                            {record.qb_name}
                          </td>

                          {/* QB Revenue */}
                          <td className="px-4 py-2 text-sm text-right">
                            {record.qb_total_revenue != null
                              ? <span className="text-slate-700">{formatCurrency(Number(record.qb_total_revenue))}</span>
                              : <span className="text-slate-400">-</span>
                            }
                          </td>

                          {/* Score */}
                          <td className="px-4 py-2 text-center">
                            <StatusBadge variant={scoreVariant(record.match_score)} size="sm">
                              {record.match_score?.toFixed(0)}%
                            </StatusBadge>
                          </td>

                          {/* Map to SB Company */}
                          <td className="px-4 py-2">
                            <CompanySearchSelect
                              clientId={clientId}
                              defaultValue={rowSelections[record.id]?.id || record.sb_company_id}
                              defaultLabel={rowSelections[record.id]?.name || record.sb_company_name}
                              onChange={(id, name) => setRowSelections(prev => ({ ...prev, [record.id]: { id, name } }))}
                            />
                          </td>

                          {/* Emails */}
                          <td className="px-4 py-2 text-center text-sm">
                            {record.sb_total_emails ? (
                              <a
                                href={`/emails/all?company_id=${record.sb_company_id}`}
                                target="_blank"
                                rel="noreferrer"
                                className="text-blue-600 hover:underline"
                              >
                                {record.sb_total_emails}
                              </a>
                            ) : (
                              <span className="text-slate-400">0</span>
                            )}
                          </td>

                          {/* Actions */}
                          <td className="px-4 py-2">
                            <div className="flex items-center gap-1">
                              <button
                                className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50 transition-colors"
                                disabled={savingRow === record.id}
                                onClick={() => handleConfirm(record)}
                              >
                                {savingRow === record.id ? (
                                  <Spinner className="h-3 w-3 animate-spin" />
                                ) : (
                                  <CheckCircle2 className="h-3 w-3" />
                                )}
                                Confirm
                              </button>
                              <button
                                className="rounded-md px-2 py-1 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                                disabled={savingRow === record.id}
                                onClick={() => handleSkip(record.id)}
                              >
                                Skip
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
                    <span className="text-xs text-slate-500">{total} candidates</span>
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
