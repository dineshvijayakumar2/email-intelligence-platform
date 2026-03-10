import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Skeleton, Tag, Table, Alert, Select, Space } from 'antd';
import {
  TeamOutlined,
  BankOutlined,
  MessageOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  MailOutlined,
} from '@ant-design/icons';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { useNavigate } from 'react-router-dom';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { MetricCard } from '../../components/analytics/MetricCard';
import { ChartCard } from '../../components/analytics/ChartCard';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import {
  dashboardAnalyticsApi,
  formatRelativeTime,
  formatResponseTime,
} from '../../services/analyticsService';
import type { DashboardSummary } from '../../types/analytics';

const { Text } = Typography;

const ENGAGEMENT_COLORS = ['#52c41a', '#faad14', '#f5222d'];
const THREAD_COLORS: Record<string, string> = {
  Active: '#13c2c2',
  Awaiting: '#1890ff',
  Overdue: '#f5222d',
};

const PERIOD_OPTIONS = [
  { value: 0, label: 'All Time' },
  { value: 7, label: 'Last 7 Days' },
  { value: 30, label: 'Last 30 Days' },
  { value: 90, label: 'Last 90 Days' },
  { value: 180, label: 'Last 6 Months' },
  { value: 365, label: 'Last 1 Year' },
];

export const AnalyticsDashboard: React.FC = () => {
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState<string>('');
  const [periodDays, setPeriodDays] = useState<number>(0);
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!clientId) return;
    loadData();
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, [clientId, periodDays]);

  const loadData = async () => {
    if (!clientId) return;
    setLoading(true);
    const result = await dashboardAnalyticsApi.getSummary(clientId, periodDays || undefined);
    if (isMountedRef.current) {
      setData(result);
      setLoading(false);
    }
  };

  // Chart data
  const engagementPieData = data ? [
    { name: 'Active', value: data.active_contacts, color: '#52c41a' },
    { name: 'Quiet', value: data.quiet_contacts, color: '#faad14' },
    { name: 'At Risk', value: data.at_risk_contacts, color: '#f5222d' },
  ].filter(d => d.value > 0) : [];

  const threadBarData = data ? [
    { status: 'Active', count: data.active_threads, fill: THREAD_COLORS.Active },
    { status: 'Awaiting', count: data.awaiting_response_threads, fill: THREAD_COLORS.Awaiting },
    { status: 'Overdue', count: data.overdue_threads, fill: THREAD_COLORS.Overdue },
  ] : [];

  const topContactColumns = [
    {
      title: 'Contact',
      key: 'name',
      render: (_: any, r: any) => (
        <div>
          <Text strong>{r.full_name || r.email_address}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
    },
    {
      title: 'Score',
      dataIndex: 'engagement_score',
      key: 'score',
      width: 80,
      render: (v: number) => <EngagementBadge score={v} />,
    },
    {
      title: 'Emails',
      dataIndex: 'total_emails',
      key: 'emails',
      width: 70,
      render: (v: number, r: any) => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/emails?contact_id=${r.id}&name=${encodeURIComponent(r.full_name || r.email_address)}`); }} style={{ color: '#667eea' }}>
          {v || 0}
        </a>
      ),
    },
  ];

  const topCompanyColumns = [
    {
      title: 'Company',
      dataIndex: 'company_name',
      key: 'name',
    },
    {
      title: 'Score',
      dataIndex: 'engagement_score',
      key: 'score',
      width: 80,
      render: (v: number) => <EngagementBadge score={v} />,
    },
    {
      title: 'Contacts',
      dataIndex: 'contact_count',
      key: 'contacts',
      width: 80,
      render: (v: number, r: any) => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/analytics/contacts?company=${encodeURIComponent(r.company_name)}`); }} style={{ color: '#667eea' }}>
          {v ?? 0}
        </a>
      ),
    },
  ];

  const atRiskColumns = [
    {
      title: 'Contact',
      key: 'name',
      render: (_: any, r: any) => (
        <div>
          <Text>{r.full_name || r.email_address}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
    },
    {
      title: 'Days Silent',
      dataIndex: 'days_since_contact',
      key: 'days',
      width: 100,
      render: (v: number) => <Tag color={v > 90 ? 'red' : 'orange'}>{v}d</Tag>,
    },
  ];

  const periodLabel = PERIOD_OPTIONS.find(p => p.value === periodDays)?.label || 'All Time';

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Header */}
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Space>
          <Text type="secondary">Engagement analytics overview</Text>
          <Select
            value={periodDays}
            onChange={setPeriodDays}
            options={PERIOD_OPTIONS}
            style={{ width: 160 }}
            size="small"
          />
        </Space>
        <ClientSelector value={clientId} onChange={setClientId} />
      </div>

      {!clientId ? (
        <Alert message="Select a client to view analytics" type="info" showIcon />
      ) : (
        <>
          {/* Metric Cards */}
          <Row gutter={[16, 16]} className="fade-in-up stagger-1">
            <Col xs={12} sm={8} lg={4}>
              <MetricCard
                title="Contacts"
                value={data?.total_contacts}
                prefix={<TeamOutlined />}
                loading={loading}
                onClick={() => navigate('/analytics/contacts')}
              />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <MetricCard
                title="Companies"
                value={data?.total_companies}
                prefix={<BankOutlined />}
                loading={loading}
                onClick={() => navigate('/analytics/companies')}
              />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <MetricCard
                title={periodDays ? `Emails (${periodLabel})` : 'Total Emails'}
                value={data?.total_emails}
                prefix={<MailOutlined />}
                loading={loading}
              />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <MetricCard
                title="Active Threads"
                value={data?.active_threads}
                prefix={<MessageOutlined />}
                loading={loading}
                onClick={() => navigate('/analytics/threads?status=active')}
              />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <MetricCard
                title="Overdue Threads"
                value={data?.overdue_threads}
                prefix={<WarningOutlined />}
                loading={loading}
                onClick={() => navigate('/analytics/threads?status=overdue')}
              />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <MetricCard
                title="Avg Response"
                value={formatResponseTime(data?.avg_response_time_hours)}
                prefix={<ClockCircleOutlined />}
                loading={loading}
                onClick={() => navigate('/analytics/response-times')}
              />
            </Col>
          </Row>

          {/* Charts Row */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-2">
            <Col xs={24} lg={12}>
              <ChartCard title={`Contact Engagement${periodDays ? ` (${periodLabel})` : ''}`} loading={loading} height={280}>
                {engagementPieData.length > 0 ? (
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie
                        data={engagementPieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={100}
                        paddingAngle={3}
                        dataKey="value"
                        label={({ name, value }) => `${name}: ${value}`}
                      >
                        {engagementPieData.map((entry, i) => (
                          <Cell key={i} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                    <Text type="secondary">No contact data yet</Text>
                  </div>
                )}
              </ChartCard>
            </Col>
            <Col xs={24} lg={12}>
              <ChartCard title={`Thread Status${periodDays ? ` (${periodLabel})` : ''}`} loading={loading} height={280}>
                {threadBarData.some(d => d.count > 0) ? (
                  <ResponsiveContainer>
                    <BarChart data={threadBarData}>
                      <XAxis dataKey="status" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {threadBarData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                    <Text type="secondary">No thread data yet</Text>
                  </div>
                )}
              </ChartCard>
            </Col>
          </Row>

          {/* Tables Row */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-3">
            <Col xs={24} lg={8}>
              <div className="glass-table-container" style={{ padding: 16 }}>
                <a
                  onClick={() => navigate('/analytics/contacts')}
                  style={{ fontSize: 16, fontWeight: 600, display: 'block', marginBottom: 12, color: '#667eea', cursor: 'pointer' }}
                >
                  Top Engaged Contacts
                </a>
                {loading ? <Skeleton active /> : (
                  <Table
                    columns={topContactColumns}
                    dataSource={data?.top_engaged_contacts || []}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    onRow={(record) => ({
                      onClick: () => navigate(`/analytics/contacts/${record.id}`),
                      style: { cursor: 'pointer' },
                    })}
                  />
                )}
              </div>
            </Col>
            <Col xs={24} lg={8}>
              <div className="glass-table-container" style={{ padding: 16 }}>
                <a
                  onClick={() => navigate('/analytics/companies')}
                  style={{ fontSize: 16, fontWeight: 600, display: 'block', marginBottom: 12, color: '#667eea', cursor: 'pointer' }}
                >
                  Top Engaged Companies
                </a>
                {loading ? <Skeleton active /> : (
                  <Table
                    columns={topCompanyColumns}
                    dataSource={data?.top_engaged_companies || []}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    onRow={(record) => ({
                      onClick: () => navigate(`/analytics/companies/${record.id}`),
                      style: { cursor: 'pointer' },
                    })}
                  />
                )}
              </div>
            </Col>
            <Col xs={24} lg={8}>
              <div className="glass-table-container" style={{ padding: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <WarningOutlined style={{ color: '#f5222d' }} />
                  <a
                    onClick={() => navigate('/analytics/contacts')}
                    style={{ fontSize: 16, fontWeight: 600, color: '#667eea', cursor: 'pointer' }}
                  >
                    At-Risk Contacts
                  </a>
                </div>
                {loading ? <Skeleton active /> : (
                  <Table
                    columns={atRiskColumns}
                    dataSource={data?.at_risk_contacts_list || []}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    onRow={(record) => ({
                      onClick: () => navigate(`/analytics/contacts/${record.id}`),
                      style: { cursor: 'pointer' },
                    })}
                  />
                )}
              </div>
            </Col>
          </Row>

          {/* Footer info */}
          <div className="fade-in-up stagger-3" style={{ marginTop: 16, textAlign: 'right' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Last extraction: {formatRelativeTime(data?.last_extraction_date)} |
              Last contact: {formatRelativeTime(data?.last_contact_date)} |
              Avg engagement: {data?.avg_engagement_score != null ? Math.round(data.avg_engagement_score) : 'N/A'}/100
            </Text>
          </div>
        </>
      )}
    </div>
  );
};
