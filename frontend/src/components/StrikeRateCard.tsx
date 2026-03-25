import React, { useState, useEffect } from 'react';
import { Card, Table, Statistic, Row, Col, Tag, Spin, Typography, Space, Button } from 'antd';
import { ReloadOutlined, RiseOutlined, FallOutlined } from '@ant-design/icons';
import { companiesApi } from '../services/analyticsService';

const { Text } = Typography;

interface Props {
  companyId: string;
}

const StrikeRateCard: React.FC<Props> = ({ companyId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = (force = false) => {
    setLoading(true);
    companiesApi.getStrikeRate(companyId, force)
      .then(setData)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [companyId]);

  if (loading) return <Card className="glass-card" title="Strike Rate"><Spin /></Card>;
  if (!data || !data.company_total?.total_quotes) {
    return (
      <Card className="glass-card" title="Strike Rate">
        <Text type="secondary">No quote data available</Text>
      </Card>
    );
  }

  const { company_total, by_contact, by_year } = data;
  const rateColor = company_total.strike_rate_pct >= 60 ? '#52c41a'
    : company_total.strike_rate_pct >= 40 ? '#faad14' : '#ff4d4f';

  const contactColumns = [
    { title: 'Contact', dataIndex: 'contact_name', key: 'name', ellipsis: true,
      render: (v: string, r: any) => v || r.contact_email },
    { title: 'Quotes', dataIndex: 'total_quotes', key: 'quotes', width: 70, align: 'right' as const },
    { title: 'Jobs', dataIndex: 'converted', key: 'converted', width: 60, align: 'right' as const },
    { title: 'Rate', dataIndex: 'strike_rate_pct', key: 'rate', width: 70, align: 'right' as const,
      render: (v: number) => (
        <Text style={{ color: v >= 60 ? '#52c41a' : v >= 40 ? '#faad14' : '#ff4d4f' }}>
          {v}%
        </Text>
      ),
    },
  ];

  return (
    <Card
      className="glass-card"
      title={<Space><RiseOutlined />Strike Rate</Space>}
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => load(true)}>Refresh</Button>}
    >
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={8}>
          <Statistic title="Conversion Rate" value={company_total.strike_rate_pct} suffix="%" valueStyle={{ color: rateColor, fontSize: 28 }} />
        </Col>
        <Col xs={8}>
          <Statistic title="Total Quotes" value={company_total.total_quotes} />
        </Col>
        <Col xs={8}>
          <Statistic title="Converted to Jobs" value={company_total.converted} />
        </Col>
      </Row>

      {by_year && by_year.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ fontSize: 12, marginBottom: 8, display: 'block' }}>Year-over-Year</Text>
          <Space wrap>
            {by_year.map((y: any) => (
              <Tag key={y.year} color={y.strike_rate_pct >= 60 ? 'green' : y.strike_rate_pct >= 40 ? 'orange' : 'red'}>
                {y.year}: {y.strike_rate_pct}% ({y.converted}/{y.total_quotes})
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {by_contact && by_contact.length > 0 && (
        <>
          <Text strong style={{ fontSize: 12, marginBottom: 8, display: 'block' }}>Per Contact</Text>
          <Table
            dataSource={by_contact}
            columns={contactColumns}
            rowKey="contact_email"
            size="small"
            pagination={false}
            scroll={{ y: 200 }}
          />
        </>
      )}

      {data.computed_at && (
        <Text type="secondary" style={{ fontSize: 11, marginTop: 8, display: 'block' }}>
          Computed: {new Date(data.computed_at).toLocaleString()}
        </Text>
      )}
    </Card>
  );
};

export default StrikeRateCard;
