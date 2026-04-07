import React, { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  useReactTable, getCoreRowModel, createColumnHelper, type SortingState,
} from '@tanstack/react-table';
import { DataTable } from '../../components/DataTable';
import { useThreads, useThreadsByCompany, useThreadsByContact } from '../../hooks/queries';
import { formatRelativeTime, threadStatusConfig } from '../../services/analyticsService';
import type { ThreadStatusSummary, ThreadStatus } from '../../types/analytics';
import { useClient } from '../../contexts/ClientContext';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { Search, ArrowLeft, X } from 'lucide-react';

const PAGE_SIZE = 25;
const col = createColumnHelper<ThreadStatusSummary>();

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'active', label: 'Active' },
  { value: 'complete', label: 'Complete' },
  { value: 'awaiting_our_response', label: 'Awaiting Our Response' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'dropped', label: 'Dropped' },
  { value: 'ongoing', label: 'Ongoing' },
];

const statusVariant = (s: string) => {
  if (s === 'overdue') return 'danger';
  if (s === 'awaiting_our_response') return 'warning';
  if (s === 'ongoing' || s === 'active') return 'info';
  if (s === 'complete') return 'success';
  return 'neutral';
};

export const ThreadAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { clientId } = useClient();

  const drilldownContactId = searchParams.get('contact_id');
  const drilldownCompanyId = searchParams.get('company_id');
  const drilldownLabel = searchParams.get('name') || '';
  const isDrilldownMode = !!(drilldownContactId || drilldownCompanyId);

  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState(() => searchParams.get('status') || '');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'last_message_at', desc: true }]);

  // Debounce search
  const searchTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => { setDebouncedSearch(search); setPage(1); }, 400);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [search]);

  const sortBy = sorting[0]?.id || 'last_message_at';
  const sortDir = sorting[0]?.desc ? 'desc' : 'asc';

  // Drilldown queries
  const companyThreadsQuery = useThreadsByCompany(isDrilldownMode && drilldownCompanyId ? drilldownCompanyId : undefined);
  const contactThreadsQuery = useThreadsByContact(isDrilldownMode && drilldownContactId ? drilldownContactId : undefined);

  // Normal mode query
  const normalThreadsQuery = useThreads(!isDrilldownMode ? {
    client_id: clientId,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    status: statusFilter || undefined,
    search: debouncedSearch || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
  } : { client_id: '' });

  // Drilldown: client-side filter
  const drilldownRaw = drilldownContactId
    ? contactThreadsQuery.data?.threads || []
    : companyThreadsQuery.data?.threads || [];

  const drilldownFiltered = useMemo(() => {
    let filtered = drilldownRaw;
    if (statusFilter) {
      const statusMap: Record<string, string[]> = { active: ['ongoing', 'awaiting_our_response'], overdue: ['overdue'], complete: ['complete'], dropped: ['dropped'] };
      const allowed = statusMap[statusFilter] || [statusFilter];
      filtered = filtered.filter(t => allowed.includes(t.status));
    }
    if (debouncedSearch) {
      const term = debouncedSearch.toLowerCase();
      filtered = filtered.filter(t => (t.subject || '').toLowerCase().includes(term));
    }
    return filtered;
  }, [drilldownRaw, statusFilter, debouncedSearch]);

  const threads = isDrilldownMode ? drilldownFiltered : (normalThreadsQuery.data?.threads || []);
  const threadsTotal = isDrilldownMode ? drilldownFiltered.length : (normalThreadsQuery.data?.total || 0);
  const loading = isDrilldownMode
    ? (drilldownContactId ? contactThreadsQuery.isLoading : companyThreadsQuery.isLoading)
    : normalThreadsQuery.isLoading;

  const handleThreadClick = (record: ThreadStatusSummary) => {
    const name = encodeURIComponent(record.subject || record.thread_id?.slice(0, 20) || 'Thread');
    navigate(`/emails?thread_id=${encodeURIComponent(record.thread_id)}&name=${name}`);
  };

  const columns = useMemo(() => [
    col.accessor('subject', {
      header: 'Subject',
      cell: info => {
        const r = info.row.original;
        return (
          <button onClick={(e) => { e.stopPropagation(); handleThreadClick(r); }} className="text-primary hover:underline text-left truncate">
            {info.getValue() || <span className="text-slate-400">{r.thread_id?.slice(0, 16)}...</span>}
          </button>
        );
      },
    }),
    col.accessor('contact_name', { header: 'Contact',
      cell: info => <span className="text-slate-600">{info.getValue() || info.row.original.contact_email || '—'}</span>,
    }),
    col.accessor('company_name', { header: 'Company',
      cell: info => <span className="text-slate-600">{info.getValue() || '—'}</span>,
    }),
    col.accessor('status', { header: 'Status', size: 140,
      cell: info => {
        const v = info.getValue() as ThreadStatus;
        const cfg = threadStatusConfig[v] || { label: v };
        return <StatusBadge variant={statusVariant(v) as any} size="sm">{cfg.label}</StatusBadge>;
      },
    }),
    col.accessor('total_messages', { id: 'message_count', header: 'Emails', size: 70, meta: { align: 'right' },
      cell: info => <span className="tabular-nums">{info.getValue()}</span>,
    }),
    col.accessor('last_message_date', { id: 'last_message_at', header: 'Last Email', size: 100,
      cell: info => <span className="text-xs text-slate-500">{formatRelativeTime(info.getValue())}</span>,
    }),
    col.accessor('days_since_last_message', { header: 'Days', size: 60, id: 'days_since_last_email', meta: { align: 'right' },
      cell: info => <span className="tabular-nums text-slate-600">{info.getValue()}</span>,
    }),
  ], [navigate]);

  const table = useReactTable({
    data: threads,
    columns,
    state: { sorting },
    onSortingChange: (updater) => {
      setSorting(typeof updater === 'function' ? updater(sorting) : updater);
      setPage(1);
    },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: !isDrilldownMode,
    enableSortingRemoval: false,
  });

  const hasFilters = !!statusFilter || !!debouncedSearch;

  return (
    <PageShell>
      {isDrilldownMode && (
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 mb-4">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
      )}

      <PageHeader
        title={isDrilldownMode ? `Threads${drilldownLabel ? ` for ${drilldownLabel}` : ''}` : 'Threads'}
        description={isDrilldownMode ? `${threadsTotal} thread${threadsTotal !== 1 ? 's' : ''}` : `All conversation threads (${threadsTotal})`}
      />

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search subject..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary w-52"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {hasFilters && (
          <button onClick={() => { setSearch(''); setDebouncedSearch(''); setStatusFilter(''); setPage(1); }}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <X className="h-3 w-3" /> Clear
          </button>
        )}
        <span className="text-xs text-slate-400 ml-auto tabular-nums">{threadsTotal.toLocaleString('en-AU')} threads</span>
      </div>

      <DataTable<ThreadStatusSummary>
        table={table}
        total={threadsTotal}
        loading={loading}
        pageSize={PAGE_SIZE}
        currentPage={page}
        onPageChange={setPage}
        onRowClick={handleThreadClick}
      />
    </PageShell>
  );
};
