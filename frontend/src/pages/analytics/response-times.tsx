import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Tag } from 'antd';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { ClockCircleOutlined } from '@ant-design/icons';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { MetricCard } from '../../components/analytics/MetricCard';
import { ChartCard } from '../../components/analytics/ChartCard';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { responseTimesApi, formatResponseTime } from '../../services/analyticsService';
import type { ResponseTimeStats, SlowestResponder } from '../../types/analytics';

const { Text } = Typography;

export const ResponseTimesAnalytics: React.FC = () => {
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [stats, setStats] = useState<ResponseTimeStats | null>(null);
  const [slowest, setSlowest] = useState<SlowestResponder[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    const load = async () => {
      setLoading(true);
      const [s, sl] = await Promise.all([
        responseTimesApi.stats(clientId),
        responseTimesApi.slowest(clientId),
      ]);
      if (isMountedRef.current) { setStats(s); setSlowest(sl); setLoading(false); }
    };
    load();
  }, [clientId]);

  const comparisonData = stats ? [
    { label: 'Our Avg', hours: stats.our_avg_response_time || 0 },
    { label: 'Their Avg', hours: stats.their_avg_response_time || 0 },
    { label: 'Overall Avg', hours: stats.avg_response_time_hours || 0 },
  ] : [];

  const slowestColumns = [
    {
      title: 'Contact', key: 'name',
      render: (_: any, r: SlowestResponder) => (
        <div>
          <Text strong>{r.contact_name || r.contact_email}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
    },
    { title: 'Avg Response', dataIndex: 'avg_response_time_hours', key: 'avg', width: 130, render: (v: number) => <Tag color="orange">{formatResponseTime(v)}</Tag> },
    { title: 'Responses', dataIndex: 'response_count', key: 'count', width: 100 },
  ];

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">Response time analytics — averages, medians, and slowest responders</Text>
        <ClientSelector value={clientId} onChange={setClientId} />
      </div>

      <Row gutter={[16, 16]} className="fade-in-up stagger-1">
        <Col xs={12} sm={6}><MetricCard title="Avg Response" value={formatResponseTime(stats?.avg_response_time_hours)} prefix={<ClockCircleOutlined />} loading={loading} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Median Response" value={formatResponseTime(stats?.median_response_time_hours)} loading={loading} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Fastest" value={formatResponseTime(stats?.min_response_time_hours)} loading={loading} valueStyle={{ color: '#52c41a' }} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Slowest" value={formatResponseTime(stats?.max_response_time_hours)} loading={loading} valueStyle={{ color: '#f5222d' }} /></Col>
      </Row>

      {(stats?.avg_business_hours_response_time_hours != null) && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-1">
          <Col xs={12} sm={6}><MetricCard title="Avg (Business Hours)" value={formatResponseTime(stats.avg_business_hours_response_time_hours)} prefix={<ClockCircleOutlined />} loading={loading} valueStyle={{ color: '#1890ff' }} /></Col>
          <Col xs={12} sm={6}><MetricCard title="Median (Business Hours)" value={formatResponseTime(stats.median_business_hours_response_time_hours)} loading={loading} valueStyle={{ color: '#1890ff' }} /></Col>
        </Row>
      )}

      <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-2">
        <Col xs={24} lg={12}>
          <ChartCard title="Response Time Comparison" loading={loading} height={280}>
            <ResponsiveContainer>
              <BarChart data={comparisonData}>
                <XAxis dataKey="label" />
                <YAxis label={{ value: 'Hours', angle: -90, position: 'insideLeft' }} />
                <Tooltip formatter={(v: number) => formatResponseTime(v)} />
                <Bar dataKey="hours" fill="#667eea" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </Col>
        <Col xs={24} lg={12}>
          <div className="glass-card" style={{ padding: 20 }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Auto-Reply Detection</Text>
            <Row gutter={16}>
              <Col span={12}>
                <MetricCard title="Auto-Replies" value={stats?.auto_reply_count ?? 0} loading={loading} />
              </Col>
              <Col span={12}>
                <MetricCard title="Auto-Reply %" value={stats?.auto_reply_percentage != null ? `${stats.auto_reply_percentage.toFixed(1)}%` : 'N/A'} loading={loading} />
              </Col>
            </Row>
          </div>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-3">
        <Col xs={24}>
          <div className="glass-table-container" style={{ padding: 16 }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Slowest Responders</Text>
            <AnalyticsTable columns={slowestColumns} data={slowest} total={slowest.length} loading={loading} rowKey="contact_id" />
          </div>
        </Col>
      </Row>
    </div>
  );
};
