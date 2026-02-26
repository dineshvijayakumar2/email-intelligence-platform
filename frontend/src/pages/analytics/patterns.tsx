import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Tabs, Tag, Progress } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { patternsApi, formatRelativeTime, formatRatio } from '../../services/analyticsService';
import type { InitiationPattern, FrequencyPattern, EngagementTrend } from '../../types/analytics';

const { Text } = Typography;

export const CommunicationPatterns: React.FC = () => {
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [activeTab, setActiveTab] = useState('initiation');

  const [initiation, setInitiation] = useState<InitiationPattern[]>([]);
  const [initLoading, setInitLoading] = useState(false);

  const [frequency, setFrequency] = useState<FrequencyPattern[]>([]);
  const [freqLoading, setFreqLoading] = useState(false);

  const [trends, setTrends] = useState<EngagementTrend[]>([]);
  const [trendsLoading, setTrendsLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    loadTab(activeTab);
  }, [clientId, activeTab]);

  const loadTab = async (tab: string) => {
    switch (tab) {
      case 'initiation':
        setInitLoading(true);
        const initResult = await patternsApi.initiation(clientId);
        if (isMountedRef.current) { setInitiation(initResult); setInitLoading(false); }
        break;
      case 'frequency':
        setFreqLoading(true);
        const freqResult = await patternsApi.frequency(clientId);
        if (isMountedRef.current) { setFrequency(freqResult); setFreqLoading(false); }
        break;
      case 'trends':
        setTrendsLoading(true);
        const trendsResult = await patternsApi.engagementTrends(clientId);
        if (isMountedRef.current) { setTrends(trendsResult); setTrendsLoading(false); }
        break;
    }
  };

  const initiationColumns = [
    {
      title: 'Contact', key: 'name',
      render: (_: any, r: InitiationPattern) => (
        <div>
          <Text strong>{r.contact_name || r.contact_email}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
    },
    {
      title: 'Initiation', key: 'ratio', width: 180,
      render: (_: any, r: InitiationPattern) => (
        <div>
          <Progress
            percent={Math.round(r.initiation_ratio * 100)}
            size="small"
            strokeColor={r.initiation_ratio > 0.6 ? '#52c41a' : r.initiation_ratio > 0.3 ? '#faad14' : '#f5222d'}
            format={() => `Us: ${formatRatio(r.initiation_ratio)}`}
            style={{ width: 140 }}
          />
        </div>
      ),
    },
    { title: 'Total Threads', dataIndex: 'total_threads', key: 'threads', width: 110 },
    { title: 'By Us', dataIndex: 'threads_initiated_by_us', key: 'byUs', width: 70 },
    { title: 'By Them', dataIndex: 'threads_initiated_by_them', key: 'byThem', width: 80 },
  ];

  const frequencyColumns = [
    {
      title: 'Contact', key: 'name',
      render: (_: any, r: FrequencyPattern) => (
        <div>
          <Text strong>{r.contact_name || r.contact_email}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
    },
    { title: 'Total Emails', dataIndex: 'total_emails', key: 'total', width: 100 },
    { title: '/Week', dataIndex: 'emails_per_week', key: 'week', width: 80, render: (v: number) => v?.toFixed(1) ?? '-' },
    { title: '/Month', dataIndex: 'emails_per_month', key: 'month', width: 80, render: (v: number) => v?.toFixed(1) ?? '-' },
    { title: 'Days Active', dataIndex: 'days_active', key: 'active', width: 100 },
    { title: 'First Contact', dataIndex: 'first_contact_date', key: 'first', width: 110, render: (v: string) => formatRelativeTime(v) },
    { title: 'Last Contact', dataIndex: 'last_contact_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  const trendIcon = (trend: string) => {
    if (trend === 'increasing') return <ArrowUpOutlined style={{ color: '#52c41a' }} />;
    if (trend === 'decreasing') return <ArrowDownOutlined style={{ color: '#f5222d' }} />;
    return <MinusOutlined style={{ color: '#999' }} />;
  };

  const trendColor = (trend: string) => {
    if (trend === 'increasing') return 'green';
    if (trend === 'decreasing') return 'red';
    return 'default';
  };

  const trendsColumns = [
    {
      title: 'Contact', key: 'name',
      render: (_: any, r: EngagementTrend) => (
        <div>
          <Text strong>{r.contact_name || r.contact_email}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
    },
    {
      title: 'Engagement', dataIndex: 'current_engagement_score', key: 'score', width: 110,
      render: (v: number) => (
        <Progress percent={v} size="small" strokeColor={v >= 70 ? '#52c41a' : v >= 40 ? '#faad14' : '#f5222d'} style={{ width: 80 }} />
      ),
    },
    {
      title: 'Trend', dataIndex: 'trend', key: 'trend', width: 120,
      render: (v: string) => <Tag icon={trendIcon(v)} color={trendColor(v)}>{v}</Tag>,
    },
    { title: 'Last 30d', dataIndex: 'last_30_days_emails', key: 'last30', width: 90 },
    { title: 'Prev 30d', dataIndex: 'previous_30_days_emails', key: 'prev30', width: 90 },
    {
      title: 'Change', dataIndex: 'change_percentage', key: 'change', width: 90,
      render: (v: number) => (
        <Text style={{ color: v > 0 ? '#52c41a' : v < 0 ? '#f5222d' : '#999' }}>
          {v > 0 ? '+' : ''}{v}%
        </Text>
      ),
    },
  ];

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">Communication patterns — who initiates, how often, and engagement trends</Text>
        <ClientSelector value={clientId} onChange={setClientId} />
      </div>
      <div className="fade-in-up stagger-1">
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'initiation', label: 'Thread Initiation',
            children: <AnalyticsTable columns={initiationColumns} data={initiation} total={initiation.length} loading={initLoading} rowKey="contact_id" />,
          },
          {
            key: 'frequency', label: 'Communication Frequency',
            children: <AnalyticsTable columns={frequencyColumns} data={frequency} total={frequency.length} loading={freqLoading} rowKey="contact_id" />,
          },
          {
            key: 'trends', label: 'Engagement Trends',
            children: <AnalyticsTable columns={trendsColumns} data={trends} total={trends.length} loading={trendsLoading} rowKey="contact_id" />,
          },
        ]} />
      </div>
    </div>
  );
};
