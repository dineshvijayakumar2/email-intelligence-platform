import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  useReactTable,
  getCoreRowModel,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { DataTable } from '../../components/DataTable';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import {
  useCompanies,
  useCompanyFilterOptions,
} from '../../hooks/queries';
import { formatRelativeTime } from '../../services/analyticsService';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { Search, X } from 'lucide-react';
import type { CompanyAnalytics } from '../../types/analytics';

const PAGE_SIZE = 25;
const col = createColumnHelper<CompanyAnalytics>();

export const CompaniesAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const [clientId, setClientId] = useState(() => localStorage.getItem('analytics_client_id') || '');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [qbMatched, setQbMatched] = useState(false);
  const [tierFilter, setTierFilter] = useState('');
  const [amFilter, setAmFilter] = useState('');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'engagement_score', desc: true }]);

  // Debounce search
  const searchTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => { setDebouncedSearch(search); setPage(1); }, 400);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [search]);

  const sortBy = sorting[0]?.id || 'engagement_score';
  const sortDir = sorting[0]?.desc ? 'desc' : 'asc';

  const companiesQuery = useCompanies({
    client_id: clientId,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    qb_matched: qbMatched || undefined,
    qb_tier: tierFilter || undefined,
    qb_account_manager: amFilter || undefined,
    search: debouncedSearch || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
  });

  const filterOptionsQuery = useCompanyFilterOptions(clientId);

  const tierOptions = useMemo(() => {
    const tiers = filterOptionsQuery.data?.tiers || [];
    return tiers.map(t => {
      const m = t.match(/Level\s*(\d)/i);
      return { value: t, label: m ? `L${m[1]}` : t };
    });
  }, [filterOptionsQuery.data]);

  const amOptions = useMemo(() => {
    return filterOptionsQuery.data?.account_managers || [];
  }, [filterOptionsQuery.data]);

  const companies = companiesQuery.data?.companies || [];
  const total = companiesQuery.data?.total || 0;

  const columns = useMemo(() => [
    col.accessor('company_name', {
      header: 'Company',
      size: 200,
      cell: info => <span className="font-medium text-slate-900 truncate">{info.getValue()}</span>,
    }),
    col.accessor('qb_tier', {
      header: 'Tier',
      size: 55,
      cell: info => {
        const v = info.getValue();
        if (!v) return <span className="text-slate-300">—</span>;
        const m = v.match(/Level\s*(\d)/i);
        const short = m ? `L${m[1]}` : v.slice(0, 4);
        return <StatusBadge variant="purple" size="sm">{short}</StatusBadge>;
      },
    }),
    col.accessor('qb_total_revenue', {
      header: 'Revenue',
      size: 100,
      meta: { align: 'right' },
      cell: info => {
        const v = info.getValue();
        return v != null
          ? <span className="tabular-nums font-medium">${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
          : <span className="text-slate-300">—</span>;
      },
    }),
    col.accessor('qb_account_manager', {
      header: 'AM',
      size: 110,
      cell: info => <span className="text-slate-600">{info.getValue() || '—'}</span>,
    }),
    col.accessor('engagement_score', {
      header: 'Score',
      size: 100,
      cell: info => <EngagementBadge score={info.getValue() ?? 0} />,
    }),
    col.accessor('total_emails', {
      header: 'Emails',
      size: 70,
      meta: { align: 'right' },
      cell: info => (
        <button onClick={(e) => { e.stopPropagation(); navigate(`/emails?company_id=${info.row.original.id}`); }}
          className="text-primary hover:underline tabular-nums">{info.getValue() || 0}</button>
      ),
    }),
    col.accessor('contact_count', {
      header: 'Contacts',
      size: 75,
      meta: { align: 'right' },
      cell: info => (
        <button onClick={(e) => { e.stopPropagation(); navigate(`/customers/contacts?company_id=${info.row.original.id}&client_id=${clientId}`); }}
          className="text-primary hover:underline tabular-nums">{info.getValue() ?? 0}</button>
      ),
    }),
    col.accessor('last_contact_date', {
      header: 'Last Contact',
      size: 100,
      cell: info => <span className="text-slate-500 text-xs">{formatRelativeTime(info.getValue())}</span>,
    }),
  ], [clientId, navigate]);

  const table = useReactTable({
    data: companies,
    columns,
    state: { sorting },
    onSortingChange: (updater) => {
      setSorting(typeof updater === 'function' ? updater(sorting) : updater);
      setPage(1);
    },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    enableSortingRemoval: false,
  });

  const hasFilters = qbMatched || !!tierFilter || !!amFilter || !!debouncedSearch;

  const clearFilters = () => {
    setSearch(''); setDebouncedSearch(''); setTierFilter(''); setAmFilter(''); setQbMatched(false); setPage(1);
  };

  return (
    <PageShell>
      <PageHeader
        title="Companies"
        description="Explore company engagement, relationship health, and risk indicators"
        actions={<ClientSelector value={clientId} onChange={setClientId} />}
      />

      {/* Filter bar */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search company..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary w-48"
          />
        </div>
        <select
          value={tierFilter}
          onChange={e => { setTierFilter(e.target.value); setPage(1); }}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          <option value="">All Tiers</option>
          {tierOptions.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <select
          value={amFilter}
          onChange={e => { setAmFilter(e.target.value); setPage(1); }}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          <option value="">All AMs</option>
          {amOptions.map(am => <option key={am} value={am}>{am}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
          <input
            type="checkbox"
            checked={qbMatched}
            onChange={e => { setQbMatched(e.target.checked); setPage(1); }}
            className="rounded border-slate-300"
          />
          QB only
        </label>
        {hasFilters && (
          <button onClick={clearFilters} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <X className="h-3 w-3" /> Clear
          </button>
        )}
        <span className="text-xs text-slate-400 ml-auto tabular-nums">{total.toLocaleString()} companies</span>
      </div>

      {/* Table */}
      <DataTable<CompanyAnalytics>
        table={table}
        total={total}
        loading={companiesQuery.isLoading}
        pageSize={PAGE_SIZE}
        currentPage={page}
        onPageChange={setPage}
        onRowClick={(r) => navigate(`/customers/${r.id}`)}
      />
    </PageShell>
  );
};
