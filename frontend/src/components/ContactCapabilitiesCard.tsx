import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Spin, Typography, Space, Button, Tooltip } from 'antd';
import { ReloadOutlined, UserOutlined } from '@ant-design/icons';
import { companiesApi } from '../services/analyticsService';

const { Text } = Typography;

const TAG_COLORS: Record<string, string> = {
  'Flat Sheets': '#3B82F6',
  'Soft Cover Books': '#10B981',
  'Hard Cover Books': '#8B5CF6',
  'Wide Format': '#F59E0B',
  'Embellishment': '#EC4899',
  'Specialty Finishing': '#EF4444',
  'Design Services': '#6366F1',
  'Display / Installation': '#14B8A6',
};

interface Props {
  companyId: string;
}

const ContactCapabilitiesCard: React.FC<Props> = ({ companyId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = (force = false) => {
    setLoading(true);
    companiesApi.getContactCapabilities(companyId, force)
      .then(setData)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [companyId]);

  if (loading) return <Card className="glass-card" title="Contact Capabilities"><Spin /></Card>;
  if (!data?.contacts?.length) {
    return (
      <Card className="glass-card" title="Contact Capabilities">
        <Text type="secondary">No contact capability data — requires classified operations with contact_email</Text>
      </Card>
    );
  }

  const columns = [
    {
      title: 'Contact',
      dataIndex: 'contact_name',
      key: 'name',
      width: 180,
      ellipsis: true,
      render: (v: string, r: any) => (
        <Tooltip title={r.contact_email}>
          <Space size={4}>
            <UserOutlined style={{ fontSize: 11, color: '#999' }} />
            <span>{v || r.contact_email}</span>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: 'Primary',
      dataIndex: 'primary_capability',
      key: 'primary',
      width: 140,
      render: (v: string) => v ? (
        <Tag color={TAG_COLORS[v] || 'blue'} style={{ fontSize: 11 }}>{v}</Tag>
      ) : '—',
    },
    {
      title: 'Capabilities',
      dataIndex: 'capabilities',
      key: 'caps',
      render: (caps: any[]) => (
        <Space size={2} wrap>
          {caps.map((c: any) => (
            <Tooltip key={c.tag} title={`${c.order_count} orders, $${Number(c.total_revenue).toLocaleString()}, last: ${c.last_order || '—'}`}>
              <Tag
                color={TAG_COLORS[c.tag] || 'default'}
                style={{ fontSize: 10, padding: '0 4px', cursor: 'help' }}
              >
                {c.tag} ({c.order_count})
              </Tag>
            </Tooltip>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <Card
      className="glass-card"
      title={<Space><UserOutlined />Contact Capabilities</Space>}
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => load(true)}>Refresh</Button>}
    >
      <Table
        dataSource={data.contacts}
        columns={columns}
        rowKey="contact_email"
        size="small"
        pagination={false}
        scroll={{ y: 300 }}
      />
      {data.computed_at && (
        <Text type="secondary" style={{ fontSize: 11, marginTop: 8, display: 'block' }}>
          Computed: {new Date(data.computed_at).toLocaleString()}
        </Text>
      )}
    </Card>
  );
};

export default ContactCapabilitiesCard;
