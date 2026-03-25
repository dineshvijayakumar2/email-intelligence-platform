import React, { useState, useEffect } from 'react';
import { Card, Tag, Spin, Typography, Space, Button, Row, Col, Statistic } from 'antd';
import { ReloadOutlined, CalendarOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { companiesApi } from '../services/analyticsService';

const { Text } = Typography;

interface Props {
  companyId: string;
}

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

  if (loading) return <Card className="glass-card" title="Seasonality"><Spin /></Card>;
  if (!data?.monthly?.length) {
    return (
      <Card className="glass-card" title="Seasonality">
        <Text type="secondary">No ordering history with dates available</Text>
      </Card>
    );
  }

  const maxCount = Math.max(...data.monthly.map((m: any) => m.order_count));

  return (
    <Card
      className="glass-card"
      title={<Space><CalendarOutlined />Seasonality</Space>}
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => load(true)}>Refresh</Button>}
    >
      <Row gutter={[16, 8]} style={{ marginBottom: 16 }}>
        <Col xs={8}>
          <Statistic title="Total Orders" value={data.total_orders} />
        </Col>
        <Col xs={8}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>Peak Months</Text>
            <div style={{ marginTop: 4 }}>
              {data.peak_months?.length > 0 ? (
                <Space size={4} wrap>
                  {data.peak_months.map((m: number) => (
                    <Tag key={m} color="green" icon={<ArrowUpOutlined />} style={{ fontSize: 11 }}>
                      {['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m]}
                    </Tag>
                  ))}
                </Space>
              ) : <Text type="secondary" style={{ fontSize: 11 }}>Even distribution</Text>}
            </div>
          </div>
        </Col>
        <Col xs={8}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>Quiet Months</Text>
            <div style={{ marginTop: 4 }}>
              {data.trough_months?.length > 0 ? (
                <Space size={4} wrap>
                  {data.trough_months.map((m: number) => (
                    <Tag key={m} color="default" icon={<ArrowDownOutlined />} style={{ fontSize: 11 }}>
                      {['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m]}
                    </Tag>
                  ))}
                </Space>
              ) : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>}
            </div>
          </div>
        </Col>
      </Row>

      {/* Simple bar chart */}
      <div style={{ display: 'flex', gap: 3, alignItems: 'flex-end', height: 100, marginBottom: 8 }}>
        {data.monthly.map((m: any) => {
          const height = maxCount > 0 ? (m.order_count / maxCount) * 100 : 0;
          const isPeak = data.peak_months?.includes(m.month);
          const isTrough = data.trough_months?.includes(m.month);
          return (
            <div
              key={m.month}
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 2,
              }}
              title={`${m.month_name}: ${m.order_count} orders, $${Number(m.revenue).toLocaleString()}`}
            >
              <Text style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)' }}>{m.order_count}</Text>
              <div
                style={{
                  width: '100%',
                  height: `${Math.max(height, 2)}%`,
                  backgroundColor: isPeak ? '#52c41a' : isTrough ? 'rgba(255,255,255,0.15)' : '#667eea',
                  borderRadius: 3,
                  transition: 'height 0.3s',
                }}
              />
              <Text style={{ fontSize: 9, color: 'rgba(255,255,255,0.5)' }}>
                {m.month_name?.substring(0, 3)}
              </Text>
            </div>
          );
        })}
      </div>

      {/* Quarterly summary */}
      {data.quarterly?.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Space wrap>
            {data.quarterly.map((q: any) => (
              <Tag key={q.quarter} style={{ fontSize: 11 }}>
                Q{q.quarter}: {q.order_count} orders (${Number(q.revenue).toLocaleString()})
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {data.computed_at && (
        <Text type="secondary" style={{ fontSize: 11, marginTop: 8, display: 'block' }}>
          Computed: {new Date(data.computed_at).toLocaleString()}
          {data.date_range && ` | Data: ${data.date_range.earliest} to ${data.date_range.latest}`}
        </Text>
      )}
    </Card>
  );
};

export default SeasonalityChart;
