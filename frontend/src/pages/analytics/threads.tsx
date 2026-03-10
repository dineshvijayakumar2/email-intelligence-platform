import React, { useState, useEffect, useRef } from 'react';
import { Typography, Tag, Space, Select, Button, Input } from 'antd';
import type { TableProps } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { LeftOutlined } from '@ant-design/icons';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { threadsApi, formatRelativeTime, threadStatusConfig } from '../../services/analyticsService';
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
  const isMountedRef = useRef(true);

  // Drilldown mode: when navigated from contact/company detail pages
  const drilldownContactId = searchParams.get('contact_id');
  const drilldownCompanyId = searchParams.get('company_id');
  const drilldownLabel = searchParams.get('name') || '';
  const isDrilldownMode = !!(drilldownContactId || drilldownCompanyId);

  const [clientId, setClientId] = useState('');
  const [threads, setThreads] = useState<ThreadStatusSummary[]>([]);
  const [threadsTotal, setThreadsTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>(() => searchParams.get('status') || '');
  const [search, setSearch] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('last_message_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  // Drilldown mode: load threads for contact/company
  useEffect(() => {
    if (!isDrilldownMode) return;
    const loadDrilldown = async () => {
      setLoading(true);
      try {
        const result = drilldownContactId
          ? await threadsApi.byContact(drilldownContactId, 200)
          : await threadsApi.byCompany(drilldownCompanyId!, 200);
        if (isMountedRef.current) {
          setThreads(result.threads);
          setThreadsTotal(result.total);
        }
      } catch (error) {
        console.error('Error loading drilldown threads:', error);
      } finally {
        if (isMountedRef.current) setLoading(false);
      }
    };
    loadDrilldown();
  }, [isDrilldownMode, drilldownContactId, drilldownCompanyId]);

  // Normal mode: load threads with filters
  useEffect(() => {
    if (isDrilldownMode) return;
    if (!clientId) return;
    loadThreads();
  }, [clientId, page, statusFilter, search, sortBy, sortDir]);

  const loadThreads = async () => {
    setLoading(true);
    try {
      const result = await threadsApi.list({
        client_id: clientId,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        status: statusFilter || undefined,
        search: search || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      if (isMountedRef.current) {
        setThreads(result.threads);
        setThreadsTotal(result.total);
      }
    } catch (error) {
      console.error('Error loading threads:', error);
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  };

  const handleThreadClick = (record: ThreadStatusSummary) => {
    const name = encodeURIComponent(record.subject || record.thread_id?.slice(0, 20) || 'Thread');
    navigate(`/emails?thread_id=${encodeURIComponent(record.thread_id)}&name=${name}`);
  };

  const getSortOrder = (field: string): 'ascend' | 'descend' | null => {
    if (sortBy !== field) return null;
    return sortDir === 'asc' ? 'ascend' : 'descend';
  };

  const handleTableChange: TableProps<ThreadStatusSummary>['onChange'] = (_pagination, _filters, sorter) => {
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
      title: 'Subject',
      dataIndex: 'subject',
      key: 'subject',
      ellipsis: true,
      sorter: !isDrilldownMode,
      sortOrder: isDrilldownMode ? undefined : getSortOrder('subject'),
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
      sorter: !isDrilldownMode,
      sortOrder: isDrilldownMode ? undefined : getSortOrder('status'),
      render: (v: ThreadStatus) => { const cfg = threadStatusConfig[v] || { label: v, color: 'default' }; return <Tag color={cfg.color}>{cfg.label}</Tag>; },
    },
    {
      title: 'Messages',
      dataIndex: 'total_messages',
      key: 'message_count',
      width: 90,
      sorter: !isDrilldownMode,
      sortOrder: isDrilldownMode ? undefined : getSortOrder('message_count'),
    },
    {
      title: 'Last Message',
      dataIndex: 'last_message_date',
      key: 'last_message_at',
      width: 110,
      sorter: !isDrilldownMode,
      sortOrder: isDrilldownMode ? undefined : getSortOrder('last_message_at'),
      render: (v: string) => formatRelativeTime(v),
    },
    {
      title: 'Days',
      dataIndex: 'days_since_last_message',
      key: 'days_since_last_email',
      width: 70,
      sorter: !isDrilldownMode,
      sortOrder: isDrilldownMode ? undefined : getSortOrder('days_since_last_email'),
    },
  ];

  // Drilldown mode: simplified view with back button
  if (isDrilldownMode) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <div className="fade-in-up" style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <Button type="text" icon={<LeftOutlined />} onClick={() => navigate(-1)} style={{ color: '#667eea' }}>Back</Button>
          <Text strong style={{ fontSize: 16 }}>Threads for {drilldownLabel}</Text>
          <Tag color="purple">{threadsTotal} thread{threadsTotal !== 1 ? 's' : ''}</Tag>
        </div>
        <div className="fade-in-up stagger-1">
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
      </div>
    );
  }

  const statusLabel = THREAD_STATUS_OPTIONS.find(o => o.value === statusFilter)?.label;

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">
          {statusFilter
            ? `${statusLabel} — ${threadsTotal} thread${threadsTotal !== 1 ? 's' : ''}`
            : `All Threads (${threadsTotal})`}
        </Text>
        <ClientSelector value={clientId} onChange={setClientId} />
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
          <Text>Status:</Text>
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
