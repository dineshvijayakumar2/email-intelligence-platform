import React, { useState, useMemo } from 'react';
import { Typography, Tag, Space, Select, Button, Input } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { LeftOutlined } from '@ant-design/icons';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { MailboxSelector } from '../../components/MailboxSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import {
  useThreads,
  useThreadsByCompany,
  useThreadsByContact,
} from '../../hooks/queries';
import { formatRelativeTime, threadStatusConfig } from '../../services/analyticsService';
import type { ThreadStatusSummary, ThreadStatus } from '../../types/analytics';

const { Text } = Typography;
const PAGE_SIZE = 20;

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

  // Drilldown mode
  const drilldownContactId = searchParams.get('contact_id');
  const drilldownCompanyId = searchParams.get('company_id');
  const drilldownLabel = searchParams.get('name') || '';
  const isDrilldownMode = !!(drilldownContactId || drilldownCompanyId);

  const [clientId, setClientId] = useState('');
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>(() => searchParams.get('status') || '');
  const [search, setSearch] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('last_message_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Data queries — separate hooks for drilldown vs normal mode
  const companyThreadsQuery = useThreadsByCompany(
    isDrilldownMode && drilldownCompanyId ? drilldownCompanyId : undefined
  );
  const contactThreadsQuery = useThreadsByContact(
    isDrilldownMode && drilldownContactId ? drilldownContactId : undefined
  );
  const normalThreadsQuery = useThreads(
    !isDrilldownMode ? {
      client_id: clientId,
      mailbox_id: mailboxId || undefined,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      status: statusFilter || undefined,
      search: search || undefined,
      sort_by: sortBy,
      sort_dir: sortDir,
    } : { client_id: '' }  // disabled when in drilldown
  );

  // Derive data based on mode
  const drilldownRaw = drilldownContactId
    ? contactThreadsQuery.data?.threads || []
    : companyThreadsQuery.data?.threads || [];

  // Apply client-side filters to drilldown results
  const drilldownFiltered = useMemo(() => {
    let filtered = drilldownRaw;
    if (statusFilter) {
      const statusMap: Record<string, string[]> = {
        'active': ['ongoing', 'awaiting_our_response'],
        'overdue': ['overdue'],
        'complete': ['complete'],
        'dropped': ['dropped'],
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

  const getSortOrder = (field: string): 'ascend' | 'descend' | null => {
    if (sortBy !== field) return null;
    return sortDir === 'asc' ? 'ascend' : 'descend';
  };

  const handleTableChange = (_pagination: any, _filters: any, sorter: any) => {
    if (!sorter || Array.isArray(sorter)) return;
    if (sorter.field && sorter.order) {
      const field = (sorter.columnKey ?? sorter.field) as string;
      setSortBy(field);
      setSortDir(sorter.order === 'ascend' ? 'asc' : 'desc');
      setPage(1);
    } else if (!sorter.order) {
      setSortBy('last_message_at');
      setSortDir('desc');
      setPage(1);
    }
  };

  const columns = [
    {
      title: 'Subject', dataIndex: 'subject', key: 'subject', ellipsis: true,
      sorter: !isDrilldownMode, sortOrder: isDrilldownMode ? undefined : getSortOrder('subject'),
      render: (v: string, r: ThreadStatusSummary) => (
        <a onClick={(e) => { e.stopPropagation(); handleThreadClick(r); }} style={{ color: '#667eea' }}>
          {v || <Text type="secondary" style={{ fontSize: 12 }}>{r.thread_id?.slice(0, 16)}...</Text>}
        </a>
      ),
    },
    { title: 'Contact', key: 'contact', render: (_: any, r: ThreadStatusSummary) => r.contact_name || r.contact_email || '-' },
    { title: 'Company', dataIndex: 'company_name', key: 'company', render: (v: string) => v || '-' },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 150,
      sorter: !isDrilldownMode, sortOrder: isDrilldownMode ? undefined : getSortOrder('status'),
      render: (v: ThreadStatus) => { const cfg = threadStatusConfig[v] || { label: v, color: 'default' }; return <Tag color={cfg.color}>{cfg.label}</Tag>; },
    },
    {
      title: 'Emails', dataIndex: 'total_messages', key: 'message_count', width: 90,
      sorter: !isDrilldownMode, sortOrder: isDrilldownMode ? undefined : getSortOrder('message_count'),
    },
    {
      title: 'Last Email', dataIndex: 'last_message_date', key: 'last_message_at', width: 110,
      sorter: !isDrilldownMode, sortOrder: isDrilldownMode ? undefined : getSortOrder('last_message_at'),
      render: (v: string) => formatRelativeTime(v),
    },
    {
      title: 'Days', dataIndex: 'days_since_last_message', key: 'days_since_last_email', width: 70,
      sorter: !isDrilldownMode, sortOrder: isDrilldownMode ? undefined : getSortOrder('days_since_last_email'),
    },
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
          <Input.Search
            placeholder="Search subject..."
            allowClear
            onSearch={(v) => setSearch(v)}
            style={{ width: 240 }}
            size="small"
          />
          <Select
            value={statusFilter}
            onChange={v => setStatusFilter(v)}
            options={THREAD_STATUS_OPTIONS}
            style={{ width: 240 }}
            size="small"
          />
        </Space>
        <AnalyticsTable<ThreadStatusSummary>
          columns={columns}
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
          <Input.Search
            placeholder="Search thread subject..."
            allowClear
            onSearch={(v) => { setSearch(v); setPage(1); }}
            style={{ width: 240 }}
            size="small"
          />
          <Select
            value={statusFilter}
            onChange={v => { setStatusFilter(v); setPage(1); }}
            options={THREAD_STATUS_OPTIONS}
            style={{ width: 240 }}
            size="small"
          />
        </Space>
        <AnalyticsTable<ThreadStatusSummary>
          columns={columns}
          data={threads}
          total={threadsTotal}
          loading={loading}
          pageSize={PAGE_SIZE}
          currentPage={page}
          onPageChange={setPage}
          onChange={handleTableChange}
          rowKey="thread_id"
          onRowClick={handleThreadClick}
        />
      </div>
    </div>
  );
};
