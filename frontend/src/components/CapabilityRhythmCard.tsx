import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Spin, Typography, Space, Button, Badge, Alert } from 'antd';
import { ReloadOutlined, ClockCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { companiesApi } from '../services/analyticsService';

const { Text } = Typography;

interface Props {
  companyId: string;
}

const STATUS_CONFIG: Record<string, { color: string; badge: 'success' | 'warning' | 'error' | 'default' }> = {
  on_track: { color: 'green', badge: 'success' },
  due_soon: { color: 'orange', badge: 'warning' },
  overdue: { color: 'red', badge: 'error' },
  insufficient_data: { color: 'default', badge: 'default' },
};

const CapabilityRhythmCard: React.FC<Props> = ({ companyId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = (force = false) => {
    setLoading(true);
    companiesApi.getCapabilityRhythm(companyId, force)
      .then(setData)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [companyId]);

  if (loading) return <Card className="glass-card" title="Ordering Rhythm"><Spin /></Card>;
  if (!data?.rhythms?.length) {
    return (
      <Card className="glass-card" title="Ordering Rhythm">
        <Text type="secondary">No classified operations with dates available</Text>
      </Card>
    );
  }

  const columns = [
    {
      title: 'Capability',
      dataIndex: 'capability',
      key: 'capability',
      width: 160,
      render: (v: string) => <Tag color="blue" style={{ fontSize: 11 }}>{v}</Tag>,
    },
    { title: 'Orders', dataIndex: 'order_count', key: 'orders', width: 65, align: 'right' as const },
    {
      title: 'Avg Interval',
      dataIndex: 'avg_interval_days',
      key: 'interval',
      width: 100,
      render: (v: number | null) => {
        if (v == null) return <Text type="secondary">—</Text>;
        const weeks = Math.round(v / 7);
        return weeks > 0 ? `~${weeks} weeks` : `${v} days`;
      },
    },
    {
      title: 'Last Order',
      dataIndex: 'last_order_date',
      key: 'last',
      width: 100,
      render: (v: string) => v ? new Date(v).toLocaleDateString() : '—',
    },
    {
      title: 'Days Since',
      dataIndex: 'days_since_last',
      key: 'since',
      width: 80,
      align: 'right' as const,
      render: (v: number, r: any) => (
        <Text type={r.overdue ? 'danger' : undefined}>{v != null ? `${v}d` : '—'}</Text>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (v: string, r: any) => {
        const cfg = STATUS_CONFIG[v] || STATUS_CONFIG.insufficient_data;
        return (
          <Badge
            status={cfg.badge}
            text={
              <Text style={{ fontSize: 11, color: r.overdue ? '#ff4d4f' : undefined }}>
                {v === 'overdue' ? `${r.overdue_days}d overdue` : v === 'due_soon' ? 'Due soon' : v === 'on_track' ? 'On track' : 'Low data'}
              </Text>
            }
          />
        );
      },
    },
  ];

  const overdueCount = data.alerts?.length || 0;

  return (
    <Card
      className="glass-card"
      title={
        <Space>
          <ClockCircleOutlined />
          Ordering Rhythm
          {overdueCount > 0 && <Tag color="red" icon={<WarningOutlined />}>{overdueCount} overdue</Tag>}
        </Space>
      }
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => load(true)}>Refresh</Button>}
    >
      {overdueCount > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={
            <span>
              {data.alerts.map((a: any) => (
                <Tag key={a.capability} color={a.severity === 'danger' ? 'red' : 'orange'} style={{ fontSize: 11 }}>
                  {a.capability}: {a.overdue_days}d overdue
                </Tag>
              ))}
            </span>
          }
        />
      )}
      <Table
        dataSource={data.rhythms}
        columns={columns}
        rowKey="capability"
        size="small"
        pagination={false}
        scroll={{ y: 300 }}
        rowClassName={(r: any) => r.overdue ? 'ant-table-row-danger' : ''}
      />
      {data.computed_at && (
        <Text type="secondary" style={{ fontSize: 11, marginTop: 8, display: 'block' }}>
          Computed: {new Date(data.computed_at).toLocaleString()}
        </Text>
      )}
    </Card>
  );
};

export default CapabilityRhythmCard;
