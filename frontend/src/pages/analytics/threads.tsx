import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Tabs, Tag } from 'antd';
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

export const ThreadAnalytics: React.FC = () => {
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [activeTab, setActiveTab] = useState('all');

  const [threads, setThreads] = useState<ThreadStatusSummary[]>([]);
  const [threadsTotal, setThreadsTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  const [overdue, setOverdue] = useState<OverdueThread[]>([]);
  const [overdueLoading, setOverdueLoading] = useState(false);

  const [statusCounts, setStatusCounts] = useState<ThreadStatusCount[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    loadTab(activeTab);
  }, [clientId, activeTab, page]);

  const loadTab = async (tab: string) => {
    switch (tab) {
      case 'all':
        setLoading(true);
        const allResult = await threadsApi.list({ client_id: clientId, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
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

  const allColumns = [
    { title: 'Subject', dataIndex: 'subject', key: 'subject', ellipsis: true },
    { title: 'Contact', key: 'contact', render: (_: any, r: ThreadStatusSummary) => r.contact_name || r.contact_email || '-' },
    { title: 'Company', dataIndex: 'company_name', key: 'company', render: (v: string) => v || '-' },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 150,
      render: (v: ThreadStatus) => { const cfg = threadStatusConfig[v] || { label: v, color: 'default' }; return <Tag color={cfg.color}>{cfg.label}</Tag>; },
    },
    { title: 'Messages', dataIndex: 'total_messages', key: 'msgs', width: 90 },
    { title: 'Last Message', dataIndex: 'last_message_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
    { title: 'Days', dataIndex: 'days_since_last_message', key: 'days', width: 70 },
  ];

  const overdueColumns = [
    { title: 'Subject', dataIndex: 'subject', key: 'subject', ellipsis: true },
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
            children: <AnalyticsTable columns={allColumns} data={threads} total={threadsTotal} loading={loading} pageSize={PAGE_SIZE} currentPage={page} onPageChange={setPage} rowKey="thread_id" />,
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
