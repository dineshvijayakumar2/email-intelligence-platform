import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Tag, Table, Progress, Alert } from 'antd';
import {
  CheckCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { MetricCard } from '../../components/analytics/MetricCard';
import { ChartCard } from '../../components/analytics/ChartCard';
import {
  dataHealthApi,
  type MailboxHealth,
  type DataHealthResponse,
  type ExtractionJobHealth,
} from '../../services/analyticsService';

const { Text } = Typography;

const THREAD_COLORS: Record<string, string> = {
  complete: '#52c41a',
  awaiting_response: '#1890ff',
  awaiting_our_response: '#fa8c16',
  overdue: '#f5222d',
  dropped: '#999',
  ongoing: '#13c2c2',
  unknown: '#d9d9d9',
};

function lagTag(hours: number | null) {
  if (hours == null) return <Tag>Never</Tag>;
  if (hours < 2) return <Tag color="green">{hours}h ago</Tag>;
  if (hours < 24) return <Tag color="orange">{hours}h ago</Tag>;
  return <Tag color="red">{Math.round(hours / 24)}d ago</Tag>;
}

function statusTag(status: string) {
  const map: Record<string, string> = {
    active: 'green', connected: 'green', syncing: 'blue',
    error: 'red', disconnected: 'red', pending: 'orange',
  };
  return <Tag color={map[status] || 'default'}>{status}</Tag>;
}

function jobStatusTag(status: string) {
  if (status === 'completed') return <Tag icon={<CheckCircleOutlined />} color="success">Completed</Tag>;
  if (status === 'failed') return <Tag icon={<CloseCircleOutlined />} color="error">Failed</Tag>;
  if (status === 'processing') return <Tag icon={<SyncOutlined spin />} color="processing">Running</Tag>;
  return <Tag color="default">{status}</Tag>;
}

export const DataHealthDashboard: React.FC = () => {
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [data, setData] = useState<DataHealthResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    const load = async () => {
      setLoading(true);
      try {
        const result = await dataHealthApi.get(clientId);
        if (isMountedRef.current) setData(result);
      } catch {
        // silent
      } finally {
        if (isMountedRef.current) setLoading(false);
      }
    };
    load();
  }, [clientId]);

  const mailboxColumns = [
    { title: 'Email', dataIndex: 'email_address', key: 'email', ellipsis: true },
    { title: 'Provider', dataIndex: 'provider', key: 'provider', width: 100, render: (v: string) => <Tag>{v}</Tag> },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 110, render: (v: string) => statusTag(v) },
    { title: 'Last Sync', key: 'sync_lag', width: 120, render: (_: any, r: MailboxHealth) => lagTag(r.sync_lag_hours) },
    { title: 'Last Extraction', key: 'ext_lag', width: 140, render: (_: any, r: MailboxHealth) => lagTag(r.extraction_lag_hours) },
  ];

  const jobColumns = [
    { title: 'Status', dataIndex: 'status', key: 'status', width: 120, render: (v: string) => jobStatusTag(v) },
    { title: 'Mode', dataIndex: 'extraction_mode', key: 'mode', width: 110, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: 'Progress', key: 'progress', width: 160,
      render: (_: any, r: ExtractionJobHealth) => {
        if (!r.total_emails) return '-';
        const pct = Math.round(((r.processed_emails || 0) / r.total_emails) * 100);
        return <Progress percent={pct} size="small" />;
      },
    },
    {
      title: 'Started', dataIndex: 'started_at', key: 'started', width: 160,
      render: (v: string | null) => v ? new Date(v).toLocaleString() : '-',
    },
    {
      title: 'Errors', dataIndex: 'errors', key: 'errors', ellipsis: true,
      render: (v: any[] | null) => v && v.length > 0 ? <Text type="danger" style={{ fontSize: 12 }}>{v.length} error(s)</Text> : '-',
    },
  ];

  const coveragePct = data?.identity_resolution?.coverage_percent ?? 0;
  const coverageColor = coveragePct >= 90 ? '#52c41a' : coveragePct >= 70 ? '#faad14' : '#f5222d';

  const pieData = (data?.thread_distribution || []).map((t) => ({
    name: t.status.replace(/_/g, ' '),
    value: t.count,
    fill: THREAD_COLORS[t.status] || '#d9d9d9',
  }));

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">Data health — sync status, identity resolution, thread confidence, extraction jobs</Text>
        <ClientSelector value={clientId} onChange={setClientId} />
      </div>

      {/* Summary cards */}
      <Row gutter={[16, 16]} className="fade-in-up stagger-1">
        <Col xs={12} sm={6}>
          <MetricCard
            title="Mailboxes"
            value={data?.mailbox_health?.length ?? 0}
            prefix={<DatabaseOutlined />}
            loading={loading}
          />
        </Col>
        <Col xs={12} sm={6}>
          <MetricCard
            title="Identity Coverage"
            value={`${coveragePct}%`}
            loading={loading}
            valueStyle={{ color: coverageColor }}
          />
        </Col>
        <Col xs={12} sm={6}>
          <MetricCard
            title="Missing Weekdays (30d)"
            value={data?.missing_weekday_count ?? 0}
            loading={loading}
            prefix={data?.missing_weekday_count ? <WarningOutlined /> : <CheckCircleOutlined />}
            valueStyle={{ color: (data?.missing_weekday_count ?? 0) > 5 ? '#f5222d' : (data?.missing_weekday_count ?? 0) > 0 ? '#faad14' : '#52c41a' }}
          />
        </Col>
        <Col xs={12} sm={6}>
          <MetricCard
            title="Total Emails"
            value={data?.identity_resolution?.total_emails ?? 0}
            loading={loading}
          />
        </Col>
      </Row>

      {/* Identity resolution bar */}
      {data && (
        <div className="glass-card fade-in-up stagger-1" style={{ padding: 20, marginTop: 16 }}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>Identity Resolution</Text>
          <Progress
            percent={coveragePct}
            strokeColor={coverageColor}
            format={() => `${data.identity_resolution.resolved_emails.toLocaleString()} / ${data.identity_resolution.total_emails.toLocaleString()} emails linked`}
          />
          {data.identity_resolution.unresolved_emails > 0 && (
            <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
              {data.identity_resolution.unresolved_emails.toLocaleString()} emails not linked to any contact
            </Text>
          )}
        </div>
      )}

      {/* Mailbox health + Thread distribution */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-2">
        <Col xs={24} lg={14}>
          <div className="glass-table-container" style={{ padding: 16 }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Mailbox Health</Text>
            <Table
              columns={mailboxColumns}
              dataSource={data?.mailbox_health || []}
              rowKey="mailbox_id"
              size="small"
              pagination={false}
              loading={loading}
            />
          </div>
        </Col>
        <Col xs={24} lg={10}>
          <ChartCard title="Thread Status Distribution" loading={loading} height={280}>
            {pieData.length > 0 ? (
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={(e) => `${e.name}: ${e.value}`}>
                    {pieData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <Text type="secondary">No thread data</Text>
            )}
          </ChartCard>
        </Col>
      </Row>

      {/* Missing weekdays alert */}
      {data && data.missing_weekdays.length > 0 && (
        <Alert
          type="warning"
          showIcon
          className="fade-in-up stagger-2"
          style={{ marginTop: 16 }}
          message={`${data.missing_weekdays.length} weekday(s) with no email data in the last 30 days`}
          description={data.missing_weekdays.join(', ')}
        />
      )}

      {/* Recent extraction jobs */}
      <div className="glass-table-container fade-in-up stagger-3" style={{ padding: 16, marginTop: 16 }}>
        <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Recent Extraction Jobs</Text>
        <Table
          columns={jobColumns}
          dataSource={data?.recent_extraction_jobs || []}
          rowKey="id"
          size="small"
          pagination={false}
          loading={loading}
        />
      </div>
    </div>
  );
};
