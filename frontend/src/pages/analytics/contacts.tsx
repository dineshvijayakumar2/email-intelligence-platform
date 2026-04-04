import React, { useState } from 'react';
import { Typography, Tabs, Tag, Space, Switch, Input, Button } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import { LifecycleBadge } from '../../components/analytics/LifecycleBadge';
import {
  useContacts,
  useTopEngagedContacts,
  useAtRiskContacts,
} from '../../hooks/queries';
import { formatRelativeTime } from '../../services/analyticsService';
import type {
  ContactAnalytics,
  TopEngagedContact,
  AtRiskContact,
} from '../../types/analytics';
import { formatCurrency } from '../../utils/numberFormat';

const { Text } = Typography;
const PAGE_SIZE = 20;

export const ContactsAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [clientId, setClientId] = useState(() => searchParams.get('client_id') || localStorage.getItem('analytics_client_id') || '');
  const [activeTab, setActiveTab] = useState('all');

  // Filter state
  const [contactsPage, setContactsPage] = useState(1);
  const [sortBy, setSortBy] = useState<string>('engagement_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [search, setSearch] = useState<string>('');
  const [qbLinked, setQbLinked] = useState(false);
  const companyIdFilter = searchParams.get('company_id') || '';

  // Data queries
  const contactsQuery = useContacts({
    client_id: clientId,
    company_id: companyIdFilter || undefined,
    limit: PAGE_SIZE,
    offset: (contactsPage - 1) * PAGE_SIZE,
    qb_linked: qbLinked || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    search: search || undefined,
  });

  const topQuery = useTopEngagedContacts(clientId);
  const atRiskQuery = useAtRiskContacts(clientId);

  // Derived data
  const contacts = contactsQuery.data?.contacts || [];
  const contactsTotal = contactsQuery.data?.total || 0;
  const loading = contactsQuery.isLoading;

  const getSortOrder = (field: string): 'ascend' | 'descend' | null => {
    if (sortBy !== field) return null;
    return sortDir === 'asc' ? 'ascend' : 'descend';
  };

  const handleTableChange = (_pagination: any, _filters: any, sorter: any) => {
    if (!sorter || Array.isArray(sorter)) return;
    const field = (sorter.columnKey ?? sorter.field) as string | undefined;
    if (field && sorter.order) {
      setSortBy(field);
      setSortDir(sorter.order === 'ascend' ? 'asc' : 'desc');
      setContactsPage(1);
    } else if (!sorter.order) {
      setSortBy('engagement_score');
      setSortDir('desc');
      setContactsPage(1);
    }
  };

  const allColumns = [
    {
      title: 'Contact',
      key: 'full_name',
      dataIndex: 'full_name',
      sorter: true,
      sortOrder: getSortOrder('full_name'),
      render: (_: any, r: ContactAnalytics) => (
        <div>
          <Text strong>{r.full_name || r.email_address}</Text>
          {r.full_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.email_address}</Text></div>}
        </div>
      ),
    },
    {
      title: 'Company',
      dataIndex: 'company_name',
      key: 'company_name',
      sorter: true,
      sortOrder: getSortOrder('company_name'),
      render: (v: string) => v || <Text type="secondary">-</Text>,
    },
    {
      title: 'Customer Type',
      dataIndex: 'qb_customer_type',
      key: 'qb_customer_type',
      width: 120,
      render: (v: string | null) => <LifecycleBadge tier={v} />,
    },
    {
      title: 'Tier',
      dataIndex: 'qb_tier',
      key: 'qb_tier',
      width: 70,
      render: (v: string | null) => {
        if (!v) return null;
        const colorMap: Record<string, string> = { A: 'green', B: 'blue', C: 'orange' };
        return <Tag color={colorMap[v] || 'default'}>{v}</Tag>;
      },
    },
    {
      title: 'Score',
      dataIndex: 'engagement_score',
      key: 'engagement_score',
      width: 140,
      sorter: true,
      sortOrder: getSortOrder('engagement_score'),
      render: (v: number) => <EngagementBadge score={v} showBar size="small" />,
    },
    {
      title: 'Sent',
      dataIndex: 'total_emails_sent',
      key: 'total_emails_sent',
      width: 70,
      sorter: true,
      sortOrder: getSortOrder('total_emails_sent'),
      render: (v: number, r: ContactAnalytics) => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/emails?contact_id=${r.id}`); }} style={{ color: '#667eea' }}>
          {v || 0}
        </a>
      ),
    },
    {
      title: 'Received',
      dataIndex: 'total_emails_received',
      key: 'total_emails_received',
      width: 80,
      sorter: true,
      sortOrder: getSortOrder('total_emails_received'),
      render: (v: number, r: ContactAnalytics) => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/emails?contact_id=${r.id}`); }} style={{ color: '#667eea' }}>
          {v || 0}
        </a>
      ),
    },
    {
      title: 'Last Contact',
      dataIndex: 'last_contacted_at',
      key: 'last_contacted_at',
      width: 110,
      sorter: true,
      sortOrder: getSortOrder('last_contacted_at'),
      render: (v: string) => formatRelativeTime(v),
    },
  ];

  const topColumns = [
    {
      title: 'Contact',
      key: 'name',
      render: (_: any, r: TopEngagedContact) => (
        <div>
          <Text strong>{r.full_name || r.email_address}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
    },
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 120, render: (v: number) => <EngagementBadge score={v} /> },
    { title: 'Emails', dataIndex: 'total_emails', key: 'emails', width: 80 },
    { title: 'Last Contact', dataIndex: 'last_contacted_at', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  const atRiskColumns = [
    {
      title: 'Contact',
      key: 'name',
      render: (_: any, r: AtRiskContact) => (
        <div>
          <Text strong>{r.full_name || r.email_address}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
    },
    { title: 'Days Silent', dataIndex: 'days_since_contact', key: 'days', width: 100, render: (v: number) => <Tag color={v > 90 ? 'red' : 'orange'}>{v}d</Tag> },
    {
      title: 'Tier',
      dataIndex: 'qb_tier',
      key: 'qb_tier',
      width: 70,
      render: (v: string | null) => {
        if (!v) return null;
        const colorMap: Record<string, string> = { A: 'green', B: 'blue', C: 'orange' };
        return <Tag color={colorMap[v] || 'default'}>{v}</Tag>;
      },
    },
    {
      title: 'Revenue',
      dataIndex: 'qb_total_revenue',
      key: 'qb_total_revenue',
      width: 110,
      render: (v: number | null) => formatCurrency(v, 'AUD', 2),
    },
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 120, render: (v: number) => <EngagementBadge score={v} /> },
    { title: 'Last Contact', dataIndex: 'last_contacted_at', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  const handleRowClick = (record: any) => {
    navigate(`/customers/contacts/${record.id}`);
  };

  const isCompanyDrilldown = !!companyIdFilter;

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {isCompanyDrilldown && (
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>
          Back
        </Button>
      )}
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">
          {isCompanyDrilldown
            ? 'Contacts for this company'
            : 'Explore contacts, engagement scores, and relationship health'}
        </Text>
        <ClientSelector value={clientId} onChange={setClientId} />
      </div>

      <div className="fade-in-up stagger-1">
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'all',
            label: `All Contacts (${contactsTotal})`,
            children: (
              <>
                <Space style={{ marginBottom: 12 }} wrap>
                  <Input.Search
                    placeholder="Search name, email, company..."
                    allowClear
                    defaultValue={search}
                    onSearch={(v) => { setSearch(v); setContactsPage(1); }}
                    style={{ width: 240 }}
                    size="small"
                  />
                  <Switch checked={qbLinked} onChange={v => { setQbLinked(v); setContactsPage(1); }} size="small" />
                  <Text type="secondary" style={{ fontSize: 12 }}>QB Linked</Text>
                </Space>
                <AnalyticsTable<ContactAnalytics>
                  columns={allColumns}
                  data={contacts}
                  total={contactsTotal}
                  loading={loading}
                  pageSize={PAGE_SIZE}
                  currentPage={contactsPage}
                  onPageChange={(p) => setContactsPage(p)}
                  onRowClick={handleRowClick}
                  onChange={handleTableChange}
                  rowKey="id"
                />
              </>
            ),
          },
          {
            key: 'top',
            label: 'Top Engaged',
            children: (
              <AnalyticsTable<TopEngagedContact>
                columns={topColumns}
                data={topQuery.data || []}
                total={(topQuery.data || []).length}
                loading={topQuery.isLoading}
                onRowClick={handleRowClick}
                rowKey="id"
              />
            ),
          },
          {
            key: 'atrisk',
            label: 'At Risk',
            children: (
              <AnalyticsTable<AtRiskContact>
                columns={atRiskColumns}
                data={atRiskQuery.data || []}
                total={(atRiskQuery.data || []).length}
                loading={atRiskQuery.isLoading}
                onRowClick={handleRowClick}
                rowKey="id"
              />
            ),
          },
        ]} />
      </div>
    </div>
  );
};
