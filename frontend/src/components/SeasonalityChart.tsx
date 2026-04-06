import React, { useState, useEffect } from 'react';
import { Card, Tag, Spin, Typography, Space, Button, Table } from 'antd';
import { ReloadOutlined, CalendarOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { companiesApi } from '../services/analyticsService';

const { Text } = Typography;
const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

interface Props { companyId: string; }

const SeasonalityChart: React.FC<Props> = ({ companyId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = (force = false) => {
    setLoading(true);
    companiesApi.getSeasonality(companyId, force)
      .then(setData)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [companyId]);

  if (loading) return <Card className="glass-card" size="small" title={<Text strong style={{ fontSize: 13 }}>Seasonality</Text>}><Spin size="small" /></Card>;
  if (!data?.monthly?.length) {
    return <Card className="glass-card" size="small" title={<Text strong style={{ fontSize: 13 }}>Seasonality</Text>}>
      <Text type="secondary" style={{ fontSize: 12 }}>No ordering history</Text>
    </Card>;
  }

  const peakSet = new Set(data.peak_months || []);
  const troughSet = new Set(data.trough_months || []);

  return (
    <Card
      className="glass-card" size="small"
      title={<Text strong style={{ fontSize: 13 }}>Seasonality <Text type="secondary" style={{ fontSize: 11, fontWeight: 400 }}>{data.total_orders} orders</Text></Text>}
      extra={<Button size="small" type="text" icon={<ReloadOutlined />} onClick={() => load(true)} />}
      bodyStyle={{ padding: 0 }}
    >
      <Table
        dataSource={data.monthly}
        rowKey="month"
        size="small"
        pagination={false}
        columns={[
          {
            title: 'Month', dataIndex: 'month', width: 80,
            render: (v: number) => (
              <Space size={4}>
                <Text style={{ fontSize: 12 }}>{MONTHS[v]}</Text>
                {peakSet.has(v) && <ArrowUpOutlined style={{ color: '#52c41a', fontSize: 10 }} />}
                {troughSet.has(v) && <ArrowDownOutlined style={{ color: '#999', fontSize: 10 }} />}
              </Space>
            ),
          },
          { title: 'Orders', dataIndex: 'order_count', width: 65, align: 'right' as const,
            render: (v: number) => <Text style={{ fontSize: 12 }}>{v}</Text> },
          { title: 'Revenue', dataIndex: 'revenue', align: 'right' as const,
            render: (v: number) => <Text style={{ fontSize: 12 }}>${Number(v).toLocaleString()}</Text> },
        ]}
        summary={() => data.quarterly?.length > 0 ? (
          <Table.Summary fixed>
            {data.quarterly.map((q: any) => (
              <Table.Summary.Row key={q.quarter}>
                <Table.Summary.Cell index={0}><Text strong style={{ fontSize: 12 }}>Q{q.quarter}</Text></Table.Summary.Cell>
                <Table.Summary.Cell index={1} align="right"><Text strong style={{ fontSize: 12 }}>{q.order_count}</Text></Table.Summary.Cell>
                <Table.Summary.Cell index={2} align="right"><Text strong style={{ fontSize: 12 }}>${Number(q.revenue).toLocaleString()}</Text></Table.Summary.Cell>
              </Table.Summary.Row>
            ))}
          </Table.Summary>
        ) : undefined}
      />
    </Card>
  );
};

export default SeasonalityChart;
