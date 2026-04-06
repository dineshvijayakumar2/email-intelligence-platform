import React, { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  useReactTable,
  getCoreRowModel,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { DataTable } from '../../components/DataTable';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import { LifecycleBadge } from '../../components/analytics/LifecycleBadge';
import {
  useContacts,
} from '../../hooks/queries';
import { formatRelativeTime } from '../../services/analyticsService';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { Search, X, ArrowLeft } from 'lucide-react';
import type { ContactAnalytics } from '../../types/analytics';

const PAGE_SIZE = 25;
const col = createColumnHelper<ContactAnalytics>();

export const ContactsAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [clientId, setClientId] = useState(() => searchParams.get('client_id') || localStorage.getItem('analytics_client_id') || '');

  const [contactsPage, setContactsPage] = useState(1);
  const [sorting, setSorting] = useState<SortingState>([{ id: 'engagement_score', desc: true }]);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [qbLinked, setQbLinked] = useState(false);
  const companyIdFilter = searchParams.get('company_id') || '';
  const isCompanyDrilldown = !!companyIdFilter;

  // Debounce search
  const searchTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => { setDebouncedSearch(search); setContactsPage(1); }, 400);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [search]);

  const sortBy = sorting[0]?.id || 'engagement_score';
  const sortDir = sorting[0]?.desc ? 'desc' : 'asc';

  const contactsQuery = useContacts({
    client_id: clientId,
    company_id: companyIdFilter || undefined,
    limit: PAGE_SIZE,
    offset: (contactsPage - 1) * PAGE_SIZE,
    qb_linked: qbLinked || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    search: debouncedSearch || undefined,
  });

  const contacts = contactsQuery.data?.contacts || [];
  const contactsTotal = contactsQuery.data?.total || 0;

  const columns = useMemo(() => [
    col.accessor('full_name', {
      header: 'Contact',
      size: 200,
      cell: info => {
        const r = info.row.original;
        return (
          <div>
            <span className="font-medium text-slate-900">{r.full_name || r.email_address}</span>
            {r.full_name && <div className="text-xs text-slate-400">{r.email_address}</div>}
          </div>
        );
      },
    }),
    col.accessor('company_name', {
      header: 'Company',
      cell: info => <span className="text-slate-600">{info.getValue() || '—'}</span>,
    }),
    col.accessor('qb_customer_type', {
      header: 'Type',
      size: 120,
      enableSorting: false,
      cell: info => <LifecycleBadge tier={info.getValue()} />,
    }),
    col.accessor('qb_tier', {
      header: 'Tier',
      size: 60,
      enableSorting: false,
      cell: info => {
        const v = info.getValue();
        if (!v) return <span className="text-slate-300">—</span>;
        return <StatusBadge variant="purple" size="sm">{v}</StatusBadge>;
      },
    }),
    col.accessor('engagement_score', {
      header: 'Score',
      size: 140,
      cell: info => <EngagementBadge score={info.getValue() ?? 0} showBar size="small" />,
    }),
    col.accessor('total_emails_sent', {
      header: 'Sent',
      size: 70,
      meta: { align: 'right' },
      cell: info => (
        <button onClick={(e) => { e.stopPropagation(); navigate(`/emails?contact_id=${info.row.original.id}`); }}
          className="text-primary hover:underline tabular-nums">{info.getValue() || 0}</button>
      ),
    }),
    col.accessor('total_emails_received', {
      header: 'Received',
      size: 80,
      meta: { align: 'right' },
      cell: info => (
        <button onClick={(e) => { e.stopPropagation(); navigate(`/emails?contact_id=${info.row.original.id}`); }}
          className="text-primary hover:underline tabular-nums">{info.getValue() || 0}</button>
      ),
    }),
    col.accessor('last_contacted_at', {
      header: 'Last Contact',
      size: 110,
      cell: info => <span className="text-xs text-slate-500">{formatRelativeTime(info.getValue())}</span>,
    }),
  ], [navigate]);

  const table = useReactTable({
    data: contacts,
    columns,
    state: { sorting },
    onSortingChange: (updater) => {
      setSorting(typeof updater === 'function' ? updater(sorting) : updater);
      setContactsPage(1);
    },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    enableSortingRemoval: false,
  });

  const hasFilters = qbLinked || !!debouncedSearch;

  return (
    <PageShell>
      {isCompanyDrilldown && (
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 mb-4">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
      )}

      <PageHeader
        title="Contacts"
        description={isCompanyDrilldown ? 'Contacts for this company' : 'Explore contacts, engagement scores, and relationship health'}
        actions={<ClientSelector value={clientId} onChange={setClientId} />}
      />

      {/* Filter bar */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search name, email, company..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary w-56"
          />
        </div>
        <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
          <input
            type="checkbox"
            checked={qbLinked}
            onChange={e => { setQbLinked(e.target.checked); setContactsPage(1); }}
            className="rounded border-slate-300"
          />
          QB Linked
        </label>
        {hasFilters && (
          <button onClick={() => { setSearch(''); setDebouncedSearch(''); setQbLinked(false); setContactsPage(1); }}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <X className="h-3 w-3" /> Clear
          </button>
        )}
        <span className="text-xs text-slate-400 ml-auto tabular-nums">{contactsTotal.toLocaleString()} contacts</span>
      </div>

      {/* Table */}
      <DataTable<ContactAnalytics>
        table={table}
        total={contactsTotal}
        loading={contactsQuery.isLoading}
        pageSize={PAGE_SIZE}
        currentPage={contactsPage}
        onPageChange={setContactsPage}
        onRowClick={(r) => navigate(`/customers/contacts/${r.id}`)}
      />
    </PageShell>
  );
};
