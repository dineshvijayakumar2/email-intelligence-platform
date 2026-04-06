import React, { useState, useEffect } from 'react';
import { Card, Tag, Spin, Typography, Space, Button, Table, Row, Col } from 'antd';
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

  if (loading) return <Card className="glass-card" size="small" title={<Space size={6}><CalendarOutlined />Seasonality</Space>}><Spin size="small" /></Card>;
  if (!data?.monthly?.length) {
    return <Card className="glass-card" size="small" title={<Space size={6}><CalendarOutlined />Seasonality</Space>}>
      <Text type="secondary" style={{ fontSize: 12 }}>No ordering history</Text>
    </Card>;
  }

  const peakSet = new Set(data.peak_months || []);
  const troughSet = new Set(data.trough_months || []);

  const monthlyColumns = [
    {
      title: 'Month', dataIndex: 'month', key: 'month', width: 70,
      render: (v: number) => {
        const isPeak = peakSet.has(v);
        const isTrough = troughSet.has(v);
        return (
          <Space size={4}>
            <Text style={{ fontSize: 12 }}>{MONTHS[v]}</Text>
            {isPeak && <ArrowUpOutlined style={{ color: '#52c41a', fontSize: 10 }} />}
            {isTrough && <ArrowDownOutlined style={{ color: '#999', fontSize: 10 }} />}
          </Space>
        );
      },
    },
    {
      title: 'Orders', dataIndex: 'order_count', key: 'orders', width: 65, align: 'right' as const,
      render: (v: number) => <Text style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: 'Revenue', dataIndex: 'revenue', key: 'revenue', align: 'right' as const,
      render: (v: number) => <Text style={{ fontSize: 12 }}>${Number(v).toLocaleString()}</Text>,
    },
  ];

  const quarterlyColumns = [
    { title: 'Quarter', dataIndex: 'quarter', key: 'quarter', width: 70,
      render: (v: number) => <Text style={{ fontSize: 12 }}>Q{v}</Text> },
    { title: 'Orders', dataIndex: 'order_count', key: 'orders', width: 65, align: 'right' as const,
      render: (v: number) => <Text style={{ fontSize: 12 }}>{v}</Text> },
    { title: 'Revenue', dataIndex: 'revenue', key: 'revenue', align: 'right' as const,
      render: (v: number) => <Text style={{ fontSize: 12 }}>${Number(v).toLocaleString()}</Text> },
  ];

  return (
    <Card
      className="glass-card" size="small"
      title={<Space size={6}><CalendarOutlined />Seasonality <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>{data.total_orders} orders</Text></Space>}
      extra={<Button size="small" type="text" icon={<ReloadOutlined />} onClick={() => load(true)} />}
    >
      <Row gutter={[12, 12]}>
        {/* Monthly grid */}
        <Col xs={24} md={14}>
          <Table
            dataSource={data.monthly}
            columns={monthlyColumns}
            rowKey="month"
            size="small"
            pagination={false}
            showHeader={true}
          />
        </Col>

        {/* Quarterly grid */}
        {data.quarterly?.length > 0 && (
          <Col xs={24} md={10}>
            <Table
              dataSource={data.quarterly}
              columns={quarterlyColumns}
              rowKey="quarter"
              size="small"
              pagination={false}
              showHeader={true}
            />
            {data.date_range && (
              <Text type="secondary" style={{ fontSize: 10, display: 'block', marginTop: 4 }}>
                Data: {data.date_range.earliest} to {data.date_range.latest}
              </Text>
            )}
          </Col>
        )}
      </Row>
    </Card>
  );
};

export default SeasonalityChart;
