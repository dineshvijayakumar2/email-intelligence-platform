/**
 * Semantic Search — Hybrid search with thread-grouped results.
 * Zero antd. Tailwind + Lucide + shadcn.
 */

import React, { useState, useEffect, useRef, useMemo } from 'react';
import * as vectorApi from '../../services/vectorService';
import type { HybridResult } from '../../services/vectorService';
import { useClient } from '../../contexts/ClientContext';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { formatRelativeDate } from '../../utils/dateUtils';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { cn } from '@/lib/utils';
import {
  Search, Mail, Building2, Wrench, Clock, Filter, ChevronDown,
  ChevronRight, ArrowRight,
} from 'lucide-react';
import { toast } from '@/lib/toast';

const SUGGESTED_PROMPTS = [
  'wide format printing banner',
  'delayed delivery complaint',
  'soft cover book binding',
  'embellishment foil stamping',
  'quote follow-up overdue',
  'what happened last quarter',
  'rush job urgent turnaround',
  'high value customer retention risk',
];

const SOURCE_OPTIONS = [
  { value: '', label: 'All Sources' },
  { value: 'email', label: 'Emails' },
  { value: 'company', label: 'Companies' },
  { value: 'operation', label: 'Operations' },
];

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  email: <Mail className="h-3.5 w-3.5 text-primary" />,
  company: <Building2 className="h-3.5 w-3.5 text-success" />,
  operation: <Wrench className="h-3.5 w-3.5 text-warning" />,
};

const VectorSearchPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { clientId } = useClient();
  const [query, setQuery] = useState(() => searchParams.get('q') || '');
  const [searching, setSearching] = useState(false);
  const [response, setResponse] = useState<vectorApi.HybridSearchResponse | null>(() => {
    try {
      const cached = sessionStorage.getItem('semantic_search_result');
      const cachedQuery = sessionStorage.getItem('semantic_search_query');
      if (cached && cachedQuery === searchParams.get('q')) {
        const parsed = JSON.parse(cached);
        if (parsed && 'threads' in parsed) return parsed;
      }
    } catch {}
    return null;
  });
  const [sourceFilter, setSourceFilter] = useState(() => searchParams.get('source') || '');
  const initialSearchDone = useRef(false);

  const handleSearch = async (q: string) => {
    if (!q || q.trim().length < 3) {
      toast.warning('Query must be at least 3 characters');
      return;
    }
    setSearching(true);
    setQuery(q);
    const next = new URLSearchParams(searchParams);
    next.set('q', q);
    if (sourceFilter) next.set('source', sourceFilter); else next.delete('source');
    setSearchParams(next, { replace: true });
    try {
      const r = await vectorApi.hybridSearch(q, clientId, undefined, 50, 0.5);
      setResponse(r);
      try {
        sessionStorage.setItem('semantic_search_result', JSON.stringify(r));
        sessionStorage.setItem('semantic_search_query', q);
      } catch {}
      if (r.total === 0) toast.info('No results found. Try a different query.');
    } catch (err: any) {
      toast.error(err?.message || 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  useEffect(() => {
    if (initialSearchDone.current) return;
    if (response) { initialSearchDone.current = true; return; }
    const urlQuery = searchParams.get('q');
    if (urlQuery && urlQuery.trim().length >= 3) {
      initialSearchDone.current = true;
      handleSearch(urlQuery);
    }
  }, []);

  const [expandedThreads, setExpandedThreads] = useState<Set<string>>(new Set());
  const toggleThread = (id: string) => {
    setExpandedThreads(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const filteredThreads = useMemo(() => {
    if (!response) return [];
    if (sourceFilter && sourceFilter !== 'email') return [];
    return response.threads || [];
  }, [response, sourceFilter]);

  const filteredOther = useMemo(() => {
    if (!response) return [];
    if (!sourceFilter) return response.other_results || [];
    return (response.other_results || []).filter(r => r.source_type === sourceFilter);
  }, [response, sourceFilter]);

  const sourceCounts = useMemo(() => {
    if (!response) return { email: 0, company: 0, operation: 0 };
    return {
      email: (response.threads || []).length,
      company: (response.other_results || []).filter(r => r.source_type === 'company').length,
      operation: (response.other_results || []).filter(r => r.source_type === 'operation').length,
    };
  }, [response]);

  return (
    <PageShell>
      <PageHeader title="Semantic Search" description="Hybrid search — AI understanding + keyword precision + time awareness" />

      {/* Search bar */}
      <div className="rounded-lg border bg-white shadow-sm p-4 mb-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search with natural language... e.g. 'what happened with Acme last quarter'"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch(query)}
              className="w-full h-10 pl-10 pr-4 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
          </div>
          <button
            onClick={() => handleSearch(query)}
            disabled={searching}
            className="h-10 px-5 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50 transition-colors inline-flex items-center gap-2"
          >
            <Search className="h-4 w-4" />
            {searching ? 'Searching...' : 'Search'}
          </button>
        </div>
        <div className="flex gap-1.5 mt-3 flex-wrap">
          <span className="text-xs text-slate-400 mr-1">Try:</span>
          {SUGGESTED_PROMPTS.map(p => (
            <button key={p} onClick={() => handleSearch(p)}
              className="px-2 py-0.5 text-xs rounded-full border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-700 transition-colors">
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Info bar */}
      {response && (
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <span className="text-sm font-bold text-slate-900">{response.total} results</span>
            {response.cleaned_query !== response.query && (
              <span className="text-xs text-slate-400">Cleaned: "{response.cleaned_query}"</span>
            )}
            {(response.date_from || response.date_to) && (
              <StatusBadge variant="info" size="sm">
                <Clock className="h-3 w-3 mr-1 inline" />
                {response.date_from || '...'} → {response.date_to || 'now'}
              </StatusBadge>
            )}
            <span className="text-xs text-slate-400">Vector: {response.total_vector_hits} | Keyword: {response.total_keyword_hits}</span>
          </div>
          <select
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value)}
            className="h-7 px-2 text-xs rounded border border-slate-200 bg-white"
          >
            {SOURCE_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>
                {o.label}{o.value && response ? ` (${sourceCounts[o.value as keyof typeof sourceCounts] || 0})` : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Thread results */}
      {filteredThreads.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
            <Mail className="h-3.5 w-3.5 inline mr-1" />Email Threads ({filteredThreads.length})
          </h3>
          {filteredThreads.map(thread => (
            <div key={thread.thread_id} className="rounded-lg border bg-white shadow-sm mb-2 overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-slate-50" onClick={() => toggleThread(thread.thread_id)}>
                {expandedThreads.has(thread.thread_id) ? <ChevronDown className="h-3.5 w-3.5 text-slate-400 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-400 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium text-slate-900 truncate block">{thread.subject || '(No subject)'}</span>
                  <div className="flex gap-2 mt-0.5">
                    <span className="text-xs text-slate-400">{thread.total_emails} email{thread.total_emails !== 1 ? 's' : ''}</span>
                    {thread.matched_count > 1 && <span className="text-xs text-slate-400">{thread.matched_count} matched</span>}
                  </div>
                </div>
                <button onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/emails?thread_id=${encodeURIComponent(thread.thread_id)}&name=${encodeURIComponent(thread.subject || 'Thread')}`);
                }} className="text-xs text-primary hover:underline shrink-0">Open Thread</button>
              </div>
              {expandedThreads.has(thread.thread_id) && (
                <div className="border-t divide-y divide-slate-50">
                  {thread.emails.map((email, idx) => (
                    <div key={email.id}
                      className={cn('flex items-center gap-3 px-4 py-1.5 cursor-pointer hover:bg-slate-50 text-sm', email.is_match && 'bg-primary/[0.03]')}
                      onClick={() => navigate(`/emails?email_id=${email.id}&name=${encodeURIComponent(email.subject || 'Email')}`)}>
                      <span className="text-xs text-slate-400 w-5 text-center tabular-nums">{idx + 1}</span>
                      <span className={cn('text-[10px] font-medium w-7', email.is_outbound ? 'text-success' : 'text-slate-400')}>{email.is_outbound ? 'OUT' : 'IN'}</span>
                      <span className="text-slate-600 w-32 truncate text-xs">{email.sender_name || email.sender_email || '?'}</span>
                      <span className={cn('flex-1 truncate text-xs', email.is_match ? 'text-primary font-medium' : 'text-slate-600')}>
                        {email.is_match && '● '}{email.subject || '(No subject)'}
                      </span>
                      <span className="text-xs text-slate-400 shrink-0">{email.sent_date ? formatRelativeDate(email.sent_date) : '—'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Non-email results */}
      {filteredOther.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
            <Building2 className="h-3.5 w-3.5 inline mr-1" />Companies & Operations ({filteredOther.length})
          </h3>
          {filteredOther.map(r => (
            <div key={r.id}
              className={cn('rounded-lg border bg-white shadow-sm px-4 py-3 mb-2', r.source_type === 'company' && 'cursor-pointer hover:bg-slate-50')}
              onClick={r.source_type === 'company' ? () => navigate(`/customers/${r.id}`) : undefined}>
              <div className="flex items-center gap-3">
                {SOURCE_ICONS[r.source_type]}
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium text-slate-900">{r.title}</span>
                  <p className="text-xs text-slate-400 truncate">{r.snippet}</p>
                </div>
                <span className="text-xs text-slate-400 tabular-nums">Score: {(r.score * 10000).toFixed(0)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty states */}
      {response && response.total === 0 && (
        <div className="text-center py-16">
          <Search className="h-12 w-12 text-slate-200 mx-auto mb-3" />
          <p className="text-sm text-slate-500">No results found for "{query}"</p>
          <p className="text-xs text-slate-400 mt-1">Try a broader query or different keywords</p>
        </div>
      )}
      {!response && !searching && (
        <div className="text-center py-20">
          <Search className="h-16 w-16 text-slate-200 mx-auto mb-4" />
          <p className="text-slate-500">Search your portfolio with natural language</p>
          <p className="text-xs text-slate-400 mt-1">AI understanding + keyword matching + time awareness</p>
        </div>
      )}
    </PageShell>
  );
};

export default VectorSearchPage;
