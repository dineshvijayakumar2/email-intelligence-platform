import React, { useState, useMemo } from 'react';
import { Typography, Tabs, Tag, Space, Switch, Input, Button } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftOutlined } from '@ant-design/icons';
import {
  useReactTable,
  getCoreRowModel,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { DataTable } from '../../components/DataTable';
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
const col = createColumnHelper<ContactAnalytics>();

export const ContactsAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [clientId, setClientId] = useState(() => searchParams.get('client_id') || localStorage.getItem('analytics_client_id') || '');
  const [activeTab, setActiveTab] = useState('all');

  const [contactsPage, setContactsPage] = useState(1);
  const [sorting, setSorting] = useState<SortingState>([{ id: 'engagement_score', desc: true }]);
  const [search, setSearch] = useState('');
  const [qbLinked, setQbLinked] = useState(false);
  const companyIdFilter = searchParams.get('company_id') || '';

  const sortBy = sorting[0]?.id || 'engagement_score';
  const sortDir = sorting[0]?.desc ? 'desc' : 'asc';

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

  const contacts = contactsQuery.data?.contacts || [];
  const contactsTotal = contactsQuery.data?.total || 0;

  const columns = useMemo(() => [
    col.accessor('full_name', {
      header: 'Contact',
      size: 200,
      cell: info => {
        const r = info.row.original;
        return (
          <div>
            <Text strong>{r.full_name || r.email_address}</Text>
            {r.full_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.email_address}</Text></div>}
          </div>
        );
      },
    }),
    col.accessor('company_name', {
      header: 'Company',
      cell: info => info.getValue() || <Text type="secondary">-</Text>,
    }),
    col.accessor('qb_customer_type', {
      header: 'Customer Type',
      size: 120,
      enableSorting: false,
      cell: info => <LifecycleBadge tier={info.getValue()} />,
    }),
    col.accessor('qb_tier', {
      header: 'Tier',
      size: 70,
      enableSorting: false,
      cell: info => {
        const v = info.getValue();
        if (!v) return null;
        const colorMap: Record<string, string> = { A: 'green', B: 'blue', C: 'orange' };
        return <Tag color={colorMap[v] || 'default'}>{v}</Tag>;
      },
    }),
    col.accessor('engagement_score', {
      header: 'Score',
      size: 140,
      cell: info => <EngagementBadge score={info.getValue() ?? 0} showBar size="small" />,
    }),
    col.accessor('total_emails_sent', {
      header: 'Sent',
      size: 70,
      meta: { align: 'right' },
      cell: info => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/emails?contact_id=${info.row.original.id}`); }} style={{ color: '#667eea' }}>
          {info.getValue() || 0}
        </a>
      ),
    }),
    col.accessor('total_emails_received', {
      header: 'Received',
      size: 80,
      meta: { align: 'right' },
      cell: info => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/emails?contact_id=${info.row.original.id}`); }} style={{ color: '#667eea' }}>
          {info.getValue() || 0}
        </a>
      ),
    }),
    col.accessor('last_contacted_at', {
      header: 'Last Contact',
      size: 110,
      cell: info => formatRelativeTime(info.getValue()),
    }),
  ], [navigate]);

  const table = useReactTable({
    data: contacts,
    columns,
    state: { sorting },
    onSortingChange: (updater) => {
      setSorting(typeof updater === 'function' ? updater(sorting) : updater);
      setContactsPage(1);
    },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    enableSortingRemoval: false,
  });

  // Top Engaged / At Risk tabs still use AnalyticsTable (Ant Design)
  const topColumns = [
    {
      title: 'Contact', key: 'name',
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
      title: 'Contact', key: 'name',
      render: (_: any, r: AtRiskContact) => (
        <div>
          <Text strong>{r.full_name || r.email_address}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
    },
    { title: 'Days Silent', dataIndex: 'days_since_contact', key: 'days', width: 100, render: (v: number) => <Tag color={v > 90 ? 'red' : 'orange'}>{v}d</Tag> },
    { title: 'Tier', dataIndex: 'qb_tier', key: 'qb_tier', width: 70, render: (v: string | null) => { if (!v) return null; const colorMap: Record<string, string> = { A: 'green', B: 'blue', C: 'orange' }; return <Tag color={colorMap[v] || 'default'}>{v}</Tag>; } },
    { title: 'Revenue', dataIndex: 'qb_total_revenue', key: 'qb_total_revenue', width: 110, render: (v: number | null) => formatCurrency(v, 'AUD', 2) },
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 120, render: (v: number) => <EngagementBadge score={v} /> },
    { title: 'Last Contact', dataIndex: 'last_contacted_at', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  const handleRowClick = (record: ContactAnalytics) => navigate(`/customers/contacts/${record.id}`);
  const isCompanyDrilldown = !!companyIdFilter;

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {isCompanyDrilldown && (
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>Back</Button>
      )}
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">
          {isCompanyDrilldown ? 'Contacts for this company' : 'Explore contacts, engagement scores, and relationship health'}
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
                  <Input.Search placeholder="Search name, email, company..." allowClear defaultValue={search} onSearch={(v) => { setSearch(v); setContactsPage(1); }} style={{ width: 240 }} size="small" />
                  <Switch checked={qbLinked} onChange={v => { setQbLinked(v); setContactsPage(1); }} size="small" />
                  <Text type="secondary" style={{ fontSize: 12 }}>QB Linked</Text>
                </Space>
                <DataTable<ContactAnalytics>
                  table={table}
                  total={contactsTotal}
                  loading={contactsQuery.isLoading}
                  pageSize={PAGE_SIZE}
                  currentPage={contactsPage}
                  onPageChange={setContactsPage}
                  onRowClick={handleRowClick}
                />
              </>
            ),
          },
          {
            key: 'top', label: 'Top Engaged',
            children: <AnalyticsTable<TopEngagedContact> columns={topColumns} data={topQuery.data || []} total={(topQuery.data || []).length} loading={topQuery.isLoading} onRowClick={(r) => navigate(`/customers/contacts/${r.id}`)} rowKey="id" />,
          },
          {
            key: 'atrisk', label: 'At Risk',
            children: <AnalyticsTable<AtRiskContact> columns={atRiskColumns} data={atRiskQuery.data || []} total={(atRiskQuery.data || []).length} loading={atRiskQuery.isLoading} onRowClick={(r) => navigate(`/customers/contacts/${r.id}`)} rowKey="id" />,
          },
        ]} />
      </div>
    </div>
  );
};
