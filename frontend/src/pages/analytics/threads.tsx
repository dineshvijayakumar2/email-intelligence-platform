import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Tabs, Tag, Space, Select } from 'antd';
import type { TableProps } from 'antd';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { ChartCard } from '../../components/analytics/ChartCard';
import { threadsApi, formatRelativeTime, threadStatusConfig } from '../../services/analyticsService';
import type { ThreadStatusSummary, OverdueThread, ThreadStatusCount, ThreadStatus } from '../../types/analytics';

const { Text } = Typography;
const PAGE_SIZE = 20;

const STATUS_COLORS: Record<string, string> = {
  complete: '#52c41a', awaiting_response: '#1890ff', awaiting_our_response: '#fa8c16',
  overdue: '#f5222d', dropped: '#999', ongoing: '#13c2c2',
};

const THREAD_STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'complete', label: 'Complete' },
  { value: 'awaiting_response', label: 'Awaiting Response' },
  { value: 'awaiting_our_response', label: 'Awaiting Our Response' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'dropped', label: 'Dropped' },
  { value: 'ongoing', label: 'Ongoing' },
];

export const ThreadAnalytics: React.FC = () => {
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [activeTab, setActiveTab] = useState('all');

  const [threads, setThreads] = useState<ThreadStatusSummary[]>([]);
  const [threadsTotal, setThreadsTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('last_message_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const [overdue, setOverdue] = useState<OverdueThread[]>([]);
  const [overdueLoading, setOverdueLoading] = useState(false);

  const [statusCounts, setStatusCounts] = useState<ThreadStatusCount[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    loadTab(activeTab);
  }, [clientId, activeTab, page, statusFilter, sortBy, sortDir]);

  const loadTab = async (tab: string) => {
    switch (tab) {
      case 'all':
        setLoading(true);
        const allResult = await threadsApi.list({
          client_id: clientId,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
          status: statusFilter ? (statusFilter as ThreadStatus) : undefined,
          sort_by: sortBy,
          sort_dir: sortDir,
        });
        if (isMountedRef.current) { setThreads(allResult.threads); setThreadsTotal(allResult.total); setLoading(false); }
        break;
      case 'overdue':
        setOverdueLoading(true);
        const odResult = await threadsApi.overdue(clientId);
        if (isMountedRef.current) { setOverdue(odResult); setOverdueLoading(false); }
        break;
      case 'status':
        setStatusLoading(true);
        const scResult = await threadsApi.byStatus(clientId);
        if (isMountedRef.current) { setStatusCounts(scResult); setStatusLoading(false); }
        break;
    }
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

  const allColumns = [
    {
      title: 'Subject',
      dataIndex: 'subject',
      key: 'subject',
      ellipsis: true,
      sorter: true,
      sortOrder: getSortOrder('subject'),
      render: (v: string, r: ThreadStatusSummary) => v || <Text type="secondary" style={{ fontSize: 12 }}>{r.thread_id?.slice(0, 16)}...</Text>,
    },
    { title: 'Contact', key: 'contact', render: (_: any, r: ThreadStatusSummary) => r.contact_name || r.contact_email || '-' },
    { title: 'Company', dataIndex: 'company_name', key: 'company', render: (v: string) => v || '-' },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 150,
      sorter: true,
      sortOrder: getSortOrder('status'),
      render: (v: ThreadStatus) => { const cfg = threadStatusConfig[v] || { label: v, color: 'default' }; return <Tag color={cfg.color}>{cfg.label}</Tag>; },
    },
    {
      title: 'Messages',
      dataIndex: 'total_messages',
      key: 'message_count',
      width: 90,
      sorter: true,
      sortOrder: getSortOrder('message_count'),
    },
    {
      title: 'Last Message',
      dataIndex: 'last_message_date',
      key: 'last_message_at',
      width: 110,
      sorter: true,
      sortOrder: getSortOrder('last_message_at'),
      render: (v: string) => formatRelativeTime(v),
    },
    {
      title: 'Days',
      dataIndex: 'days_since_last_message',
      key: 'days_since_last_email',
      width: 70,
      sorter: true,
      sortOrder: getSortOrder('days_since_last_email'),
    },
  ];

  const overdueColumns = [
    {
      title: 'Subject',
      dataIndex: 'subject',
      key: 'subject',
      ellipsis: true,
      render: (v: string, r: OverdueThread) => v || <Text type="secondary" style={{ fontSize: 12 }}>{r.thread_id?.slice(0, 16)}...</Text>,
    },
    { title: 'Contact', key: 'contact', render: (_: any, r: OverdueThread) => r.contact_name || r.contact_email || '-' },
    { title: 'Company', dataIndex: 'company_name', key: 'company', render: (v: string) => v || '-' },
    { title: 'Days Overdue', dataIndex: 'days_overdue', key: 'days', width: 110, render: (v: number) => <Tag color="red">{v}d overdue</Tag> },
    { title: 'Last Message', dataIndex: 'last_message_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  const chartData = statusCounts.map(sc => ({
    status: threadStatusConfig[sc.status]?.label || sc.status,
    count: sc.count,
    fill: STATUS_COLORS[sc.status] || '#999',
  }));

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">Email thread status tracking — active, overdue, and dropped conversations</Text>
        <ClientSelector value={clientId} onChange={setClientId} />
      </div>
      <div className="fade-in-up stagger-1">
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'all', label: `All Threads (${threadsTotal})`,
            children: (
              <>
                <Space style={{ marginBottom: 16 }} wrap>
                  <Text>Status:</Text>
                  <Select
                    value={statusFilter}
                    onChange={v => { setStatusFilter(v); setPage(1); }}
                    options={THREAD_STATUS_OPTIONS}
                    style={{ width: 200 }}
                    size="small"
                  />
                </Space>
                <AnalyticsTable<ThreadStatusSummary>
                  columns={allColumns}
                  data={threads}
                  total={threadsTotal}
                  loading={loading}
                  pageSize={PAGE_SIZE}
                  currentPage={page}
                  onPageChange={setPage}
                  onChange={handleTableChange}
                  rowKey="thread_id"
                />
              </>
            ),
          },
          {
            key: 'overdue', label: `Overdue (${overdue.length})`,
            children: <AnalyticsTable columns={overdueColumns} data={overdue} total={overdue.length} loading={overdueLoading} rowKey="thread_id" />,
          },
          {
            key: 'status', label: 'By Status',
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24}>
                  <ChartCard title="Thread Status Distribution" loading={statusLoading} height={300}>
                    <ResponsiveContainer>
                      <BarChart data={chartData}>
                        <XAxis dataKey="status" />
                        <YAxis />
                        <Tooltip />
                        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                          {chartData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </ChartCard>
                </Col>
              </Row>
            ),
          },
        ]} />
      </div>
    </div>
  );
};
