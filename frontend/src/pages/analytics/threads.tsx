import React, { useState, useMemo } from 'react';
import { Typography, Tag, Space, Select, Button, Input } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { LeftOutlined } from '@ant-design/icons';
import {
  useReactTable,
  getCoreRowModel,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { MailboxSelector } from '../../components/MailboxSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { DataTable } from '../../components/DataTable';
import {
  useThreads,
  useThreadsByCompany,
  useThreadsByContact,
} from '../../hooks/queries';
import { formatRelativeTime, threadStatusConfig } from '../../services/analyticsService';
import type { ThreadStatusSummary, ThreadStatus } from '../../types/analytics';

const { Text } = Typography;
const PAGE_SIZE = 20;
const col = createColumnHelper<ThreadStatusSummary>();

const THREAD_STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'active', label: 'Active (Ongoing + Awaiting)' },
  { value: 'complete', label: 'Complete' },
  { value: 'awaiting_response', label: 'Awaiting Response' },
  { value: 'awaiting_our_response', label: 'Awaiting Our Response' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'dropped', label: 'Dropped' },
  { value: 'ongoing', label: 'Ongoing' },
];

export const ThreadAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const drilldownContactId = searchParams.get('contact_id');
  const drilldownCompanyId = searchParams.get('company_id');
  const drilldownLabel = searchParams.get('name') || '';
  const isDrilldownMode = !!(drilldownContactId || drilldownCompanyId);

  const [clientId, setClientId] = useState('');
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>(() => searchParams.get('status') || '');
  const [search, setSearch] = useState('');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'last_message_at', desc: true }]);

  const sortBy = sorting[0]?.id || 'last_message_at';
  const sortDir = sorting[0]?.desc ? 'desc' : 'asc';

  // Drilldown queries
  const companyThreadsQuery = useThreadsByCompany(isDrilldownMode && drilldownCompanyId ? drilldownCompanyId : undefined);
  const contactThreadsQuery = useThreadsByContact(isDrilldownMode && drilldownContactId ? drilldownContactId : undefined);

  // Normal mode query
  const normalThreadsQuery = useThreads(!isDrilldownMode ? {
    client_id: clientId,
    mailbox_id: mailboxId || undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    status: statusFilter || undefined,
    search: search || undefined,
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
      const statusMap: Record<string, string[]> = {
        'active': ['ongoing', 'awaiting_our_response'],
        'overdue': ['overdue'], 'complete': ['complete'], 'dropped': ['dropped'],
      };
      const allowed = statusMap[statusFilter] || [statusFilter];
      filtered = filtered.filter(t => allowed.includes(t.status));
    }
    if (search) {
      const term = search.toLowerCase();
      filtered = filtered.filter(t => (t.subject || '').toLowerCase().includes(term));
    }
    return filtered;
  }, [drilldownRaw, statusFilter, search]);

  const threads = isDrilldownMode ? drilldownFiltered : (normalThreadsQuery.data?.threads || []);
  const threadsTotal = isDrilldownMode ? drilldownFiltered.length : (normalThreadsQuery.data?.total || 0);
  const loading = isDrilldownMode
    ? (drilldownContactId ? contactThreadsQuery.isLoading : companyThreadsQuery.isLoading)
    : normalThreadsQuery.isLoading;

  const handleThreadClick = (record: ThreadStatusSummary) => {
    const name = encodeURIComponent(record.subject || record.thread_id?.slice(0, 20) || 'Thread');
    navigate(`/emails?thread_id=${encodeURIComponent(record.thread_id)}&name=${name}`);
  };

  // TanStack Table columns for normal mode
  const tanstackColumns = useMemo(() => [
    col.accessor('subject', {
      header: 'Subject',
      cell: info => {
        const r = info.row.original;
        return (
          <a onClick={(e) => { e.stopPropagation(); handleThreadClick(r); }} style={{ color: '#667eea' }}>
            {info.getValue() || <Text type="secondary" style={{ fontSize: 12 }}>{r.thread_id?.slice(0, 16)}...</Text>}
          </a>
        );
      },
    }),
    col.accessor('contact_name', {
      header: 'Contact',
      cell: info => info.getValue() || info.row.original.contact_email || '-',
    }),
    col.accessor('company_name', {
      header: 'Company',
      cell: info => info.getValue() || '-',
    }),
    col.accessor('status', {
      header: 'Status',
      size: 150,
      cell: info => {
        const v = info.getValue() as ThreadStatus;
        const cfg = threadStatusConfig[v] || { label: v, color: 'default' };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    }),
    col.accessor('total_messages', {
      id: 'message_count',
      header: 'Emails',
      size: 90,
    }),
    col.accessor('last_message_date', {
      id: 'last_message_at',
      header: 'Last Email',
      size: 110,
      cell: info => formatRelativeTime(info.getValue()),
    }),
    col.accessor('days_since_last_message', {
      header: 'Days',
      size: 70,
      id: 'days_since_last_email',
    }),
  ], [navigate]);

  const table = useReactTable({
    data: threads,
    columns: tanstackColumns,
    state: { sorting },
    onSortingChange: (updater) => {
      setSorting(typeof updater === 'function' ? updater(sorting) : updater);
      setPage(1);
    },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    enableSortingRemoval: false,
  });

  // Drilldown: Ant Design columns (simpler, no server-side sort)
  const drilldownColumns = [
    { title: 'Subject', dataIndex: 'subject', key: 'subject', ellipsis: true,
      render: (v: string, r: ThreadStatusSummary) => (
        <a onClick={(e: any) => { e.stopPropagation(); handleThreadClick(r); }} style={{ color: '#667eea' }}>
          {v || r.thread_id?.slice(0, 16) + '...'}
        </a>
      ),
    },
    { title: 'Contact', key: 'contact', render: (_: any, r: ThreadStatusSummary) => r.contact_name || r.contact_email || '-' },
    { title: 'Company', dataIndex: 'company_name', key: 'company', render: (v: string) => v || '-' },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 150,
      render: (v: ThreadStatus) => { const cfg = threadStatusConfig[v] || { label: v, color: 'default' }; return <Tag color={cfg.color}>{cfg.label}</Tag>; },
    },
    { title: 'Emails', dataIndex: 'total_messages', key: 'msgs', width: 90 },
    { title: 'Last Email', dataIndex: 'last_message_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
    { title: 'Days', dataIndex: 'days_since_last_message', key: 'days', width: 70 },
  ];

  if (isDrilldownMode) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <div className="fade-in-up" style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <Button type="text" icon={<LeftOutlined />} onClick={() => navigate(-1)} style={{ color: '#667eea' }}>Back</Button>
          <Text strong style={{ fontSize: 16 }}>Threads{drilldownLabel ? ` for ${drilldownLabel}` : ''}</Text>
          <Tag color="purple">{threadsTotal} thread{threadsTotal !== 1 ? 's' : ''}</Tag>
        </div>
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search placeholder="Search subject..." allowClear onSearch={v => setSearch(v)} style={{ width: 240 }} size="small" />
          <Select value={statusFilter} onChange={v => setStatusFilter(v)} options={THREAD_STATUS_OPTIONS} style={{ width: 240 }} size="small" />
        </Space>
        <AnalyticsTable<ThreadStatusSummary>
          columns={drilldownColumns}
          data={threads}
          total={threadsTotal}
          loading={loading}
          pageSize={PAGE_SIZE}
          currentPage={page}
          onPageChange={setPage}
          rowKey="thread_id"
          onRowClick={handleThreadClick}
        />
      </div>
    );
  }

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">All Threads ({threadsTotal})</Text>
        <Space>
          <ClientSelector value={clientId} onChange={setClientId} />
          <MailboxSelector value={mailboxIds} onChange={setMailboxIds} mode="single" placeholder="All mailboxes" style={{ width: 220 }} />
        </Space>
      </div>
      <div className="fade-in-up stagger-1">
        <Space style={{ marginBottom: 16 }} wrap>
          <Input.Search placeholder="Search thread subject..." allowClear onSearch={(v) => { setSearch(v); setPage(1); }} style={{ width: 240 }} size="small" />
          <Select value={statusFilter} onChange={v => { setStatusFilter(v); setPage(1); }} options={THREAD_STATUS_OPTIONS} style={{ width: 240 }} size="small" />
        </Space>
        <DataTable<ThreadStatusSummary>
          table={table}
          total={threadsTotal}
          loading={loading}
          pageSize={PAGE_SIZE}
          currentPage={page}
          onPageChange={setPage}
          onRowClick={handleThreadClick}
        />
      </div>
    </div>
  );
};
