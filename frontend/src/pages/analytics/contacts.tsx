import React, { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  useReactTable, getCoreRowModel, createColumnHelper, type SortingState,
} from '@tanstack/react-table';
import { DataTable } from '../../components/DataTable';
import { LifecycleBadge } from '../../components/analytics/LifecycleBadge';
import { useContacts } from '../../hooks/queries';
import { formatRelativeTime } from '../../services/analyticsService';
import { useClient } from '../../contexts/ClientContext';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { Search, X, ArrowLeft, FileText } from 'lucide-react';
import type { ContactAnalytics } from '../../types/analytics';

const PAGE_SIZE = 25;
const col = createColumnHelper<ContactAnalytics>();

// These match the raw QB `customer_status` values stored in
// customer_contacts.qb_customer_type. The "Active" option matches any
// value starting with "Active" (Active A Customer, Active B Customer, etc).
const LIFECYCLE_OPTIONS = [
  { value: '', label: 'All Types' },
  { value: 'Active', label: 'Active Customers' },
  { value: 'Prospect', label: 'Prospects' },
  { value: 'New Customer', label: 'New Customers' },
  { value: 'Dormant', label: 'Dormant' },
  { value: 'At Risk', label: 'At Risk' },
];

export const ContactsAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { clientId } = useClient();

  const [contactsPage, setContactsPage] = useState(1);
  const [sorting, setSorting] = useState<SortingState>([{ id: 'last_contacted_at', desc: true }]);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [qbLinked, setQbLinked] = useState(false);
  const [lifecycleFilter, setLifecycleFilter] = useState('');
  const companyIdFilter = searchParams.get('company_id') || '';
  const companyName = searchParams.get('name') || '';
  const isCompanyDrilldown = !!companyIdFilter;

  const searchTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => { setDebouncedSearch(search); setContactsPage(1); }, 400);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [search]);

  const sortBy = sorting[0]?.id || 'last_contacted_at';
  const sortDir = sorting[0]?.desc ? 'desc' : 'asc';

  const contactsQuery = useContacts({
    client_id: clientId,
    company_id: companyIdFilter || undefined,
    limit: PAGE_SIZE,
    offset: (contactsPage - 1) * PAGE_SIZE,
    qb_linked: qbLinked || undefined,
    customer_type: lifecycleFilter || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    search: debouncedSearch || undefined,
  });

  const contacts = contactsQuery.data?.contacts || [];
  const contactsTotal = contactsQuery.data?.total || 0;

  const columns = useMemo(() => [
    col.accessor('full_name', {
      header: 'Contact', minSize: 200, meta: { wrap: true },
      cell: info => {
        const r = info.row.original;
        return (
          <div>
            <span className="font-medium text-slate-900">{r.full_name || r.email_address}</span>
            {r.full_name && <div className="text-xs text-slate-400 truncate">{r.email_address}</div>}
            {r.job_title && <div className="text-[11px] text-slate-400">{r.job_title}</div>}
          </div>
        );
      },
    }),
    ...(!isCompanyDrilldown ? [col.accessor('company_name', {
      header: 'Company', minSize: 120, meta: { wrap: true },
      cell: info => <span className="text-slate-600">{info.getValue() || '—'}</span>,
    })] : []),
    col.accessor('qb_customer_type', {
      header: 'Type', size: 130,
      cell: info => <LifecycleBadge tier={info.getValue()} />,
    }),
    col.accessor('engagement_score', {
      header: 'Engagement', size: 85, meta: { align: 'right' },
      cell: info => {
        const v = info.getValue();
        if (v == null) return <span className="text-slate-300">—</span>;
        return <span className="tabular-nums text-slate-700">{Math.round(v)}</span>;
      },
    }),
    col.accessor('total_emails_sent', {
      header: 'Sent', size: 60, meta: { align: 'right' },
      cell: info => <span className="tabular-nums text-slate-700">{info.getValue() || 0}</span>,
    }),
    col.accessor('total_emails_received', {
      header: 'Recv', size: 60, meta: { align: 'right' },
      cell: info => <span className="tabular-nums text-slate-700">{info.getValue() || 0}</span>,
    }),
    col.accessor('qb_quotes_count', {
      header: 'Quotes', size: 70, meta: { align: 'right' },
      cell: info => {
        const v = info.getValue();
        if (!v) return <span className="text-slate-300">—</span>;
        return (
          <span className="inline-flex items-center gap-0.5 tabular-nums text-slate-700">
            <FileText className="h-3 w-3 text-slate-400" />{v}
          </span>
        );
      },
    }),
    col.accessor('last_contacted_at', {
      header: 'Last Contact', size: 100,
      cell: info => <span className="text-xs text-slate-500">{formatRelativeTime(info.getValue())}</span>,
    }),
  ], [navigate, isCompanyDrilldown]);

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

  const hasFilters = qbLinked || !!debouncedSearch || !!lifecycleFilter;

  return (
    <PageShell>
      {isCompanyDrilldown && (
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 mb-4">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
      )}

      <PageHeader
        title={isCompanyDrilldown ? `Contacts${companyName ? ` — ${decodeURIComponent(companyName)}` : ''}` : 'Contacts'}
        description={isCompanyDrilldown ? `${contactsTotal} contact${contactsTotal !== 1 ? 's' : ''} for this company` : 'Explore contacts and communication patterns'}
      />

      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input type="text" placeholder="Search name, email..." value={search} onChange={e => setSearch(e.target.value)}
            className="h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary w-56" />
        </div>
        <select
          value={lifecycleFilter}
          onChange={e => { setLifecycleFilter(e.target.value); setContactsPage(1); }}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          {LIFECYCLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
          <input type="checkbox" checked={qbLinked} onChange={e => { setQbLinked(e.target.checked); setContactsPage(1); }} className="rounded border-slate-300" />
          QB Linked
        </label>
        {hasFilters && (
          <button onClick={() => { setSearch(''); setDebouncedSearch(''); setQbLinked(false); setLifecycleFilter(''); setContactsPage(1); }}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><X className="h-3 w-3" />Clear</button>
        )}
        <span className="text-xs text-slate-400 ml-auto tabular-nums">{contactsTotal.toLocaleString('en-AU')} contacts</span>
      </div>

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
