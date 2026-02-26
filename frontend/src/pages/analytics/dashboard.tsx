import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Skeleton, Tag, Table, Alert } from 'antd';
import {
  TeamOutlined,
  BankOutlined,
  MessageOutlined,
  ClockCircleOutlined,
  WarningOutlined,
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
  threadStatusConfig,
} from '../../services/analyticsService';
import type { DashboardSummary } from '../../types/analytics';

const { Text } = Typography;

const ENGAGEMENT_COLORS = ['#52c41a', '#faad14', '#f5222d'];
const THREAD_COLORS: Record<string, string> = {
  complete: '#52c41a',
  awaiting_response: '#1890ff',
  awaiting_our_response: '#fa8c16',
  overdue: '#f5222d',
  dropped: '#999',
  ongoing: '#13c2c2',
};

export const AnalyticsDashboard: React.FC = () => {
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState<string>('');
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
  }, [clientId]);

  const loadData = async () => {
    if (!clientId) return;
    setLoading(true);
    const result = await dashboardAnalyticsApi.getSummary(clientId);
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
    { status: 'Active', count: data.active_threads, fill: THREAD_COLORS.ongoing },
    { status: 'Awaiting', count: data.awaiting_response_threads, fill: THREAD_COLORS.awaiting_response },
    { status: 'Overdue', count: data.overdue_threads, fill: THREAD_COLORS.overdue },
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

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Header */}
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">Engagement analytics overview — contacts, companies, threads, and response times</Text>
        <ClientSelector value={clientId} onChange={setClientId} />
      </div>

      {!clientId ? (
        <Alert message="Select a client to view analytics" type="info" showIcon />
      ) : (
        <>
          {/* Metric Cards */}
          <Row gutter={[16, 16]} className="fade-in-up stagger-1">
            <Col xs={12} sm={12} lg={6}>
              <MetricCard
                title="Total Contacts"
                value={data?.total_contacts}
                prefix={<TeamOutlined />}
                loading={loading}
              />
            </Col>
            <Col xs={12} sm={12} lg={6}>
              <MetricCard
                title="Total Companies"
                value={data?.total_companies}
                prefix={<BankOutlined />}
                loading={loading}
              />
            </Col>
            <Col xs={12} sm={12} lg={6}>
              <MetricCard
                title="Active Threads"
                value={data?.active_threads}
                prefix={<MessageOutlined />}
                loading={loading}
              />
            </Col>
            <Col xs={12} sm={12} lg={6}>
              <MetricCard
                title="Avg Response Time"
                value={formatResponseTime(data?.avg_response_time_hours)}
                prefix={<ClockCircleOutlined />}
                loading={loading}
              />
            </Col>
          </Row>

          {/* Charts Row */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-2">
            <Col xs={24} lg={12}>
              <ChartCard title="Contact Engagement" loading={loading} height={280}>
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
              <ChartCard title="Thread Status" loading={loading} height={280}>
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
                <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Top Engaged Contacts</Text>
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
                <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Top Engaged Companies</Text>
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
                  <Text strong style={{ fontSize: 16 }}>At-Risk Contacts</Text>
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
