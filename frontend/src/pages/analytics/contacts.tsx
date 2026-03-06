import React, { useState, useEffect, useRef } from 'react';
import { Typography, Tabs, Tag, Space, Slider, Switch, Select, Alert, Input, Button } from 'antd';
import type { TableProps } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import {
  contactsApi,
  formatRelativeTime,
  contactTypeConfig,
} from '../../services/analyticsService';
import type {
  ContactAnalytics,
  TopEngagedContact,
  AtRiskContact,
  ContactTypeGrouping,
  ContactType,
} from '../../types/analytics';

const { Text } = Typography;
const PAGE_SIZE = 20;

const CONTACT_TYPE_OPTIONS = [
  { value: '', label: 'All Types' },
  { value: 'person', label: 'Person' },
  { value: 'automated', label: 'Automated' },
  { value: 'shared', label: 'Shared' },
  { value: 'mailing_list', label: 'Mailing List' },
  { value: 'internal', label: 'Internal' },
  { value: 'unknown', label: 'Unknown' },
];

export const ContactsAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [activeTab, setActiveTab] = useState(() => searchParams.get('dm') === 'true' ? 'dm' : 'all');
  const [loading, setLoading] = useState(false);

  // All contacts state
  const [contacts, setContacts] = useState<ContactAnalytics[]>([]);
  const [contactsTotal, setContactsTotal] = useState(0);
  const [contactsPage, setContactsPage] = useState(1);
  const [minScore, setMinScore] = useState<number>(0);
  const [sliderScore, setSliderScore] = useState<number>(0);
  const [dmOnly, setDmOnly] = useState(() => searchParams.get('dm') === 'true');
  const [contactType, setContactType] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('engagement_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [search, setSearch] = useState<string>(() => searchParams.get('company') || '');

  // Top engaged state
  const [topEngaged, setTopEngaged] = useState<TopEngagedContact[]>([]);
  const [topLoading, setTopLoading] = useState(false);

  // At risk state
  const [atRisk, setAtRisk] = useState<AtRiskContact[]>([]);
  const [atRiskLoading, setAtRiskLoading] = useState(false);

  // Decision makers state
  const [dms, setDms] = useState<ContactAnalytics[]>([]);
  const [dmsTotal, setDmsTotal] = useState(0);
  const [dmsPage, setDmsPage] = useState(1);
  const [dmsLoading, setDmsLoading] = useState(false);

  // By type state
  const [typeGroups, setTypeGroups] = useState<ContactTypeGrouping[]>([]);
  const [typeLoading, setTypeLoading] = useState(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!clientId) return;
    loadTab(activeTab);
  }, [clientId, activeTab, contactsPage, dmsPage, minScore, dmOnly, contactType, sortBy, sortDir, search]);

  const loadTab = async (tab: string) => {
    if (!clientId) return;
    switch (tab) {
      case 'all':
        setLoading(true);
        const allResult = await contactsApi.list({
          client_id: clientId,
          limit: PAGE_SIZE,
          offset: (contactsPage - 1) * PAGE_SIZE,
          min_engagement_score: minScore > 0 ? minScore : undefined,
          is_decision_maker: dmOnly ? true : undefined,
          contact_type: contactType ? (contactType as ContactType) : undefined,
          sort_by: sortBy,
          sort_dir: sortDir,
          search: search || undefined,
        });
        if (isMountedRef.current) {
          setContacts(allResult.contacts);
          setContactsTotal(allResult.total);
          setLoading(false);
        }
        break;
      case 'top':
        setTopLoading(true);
        const topResult = await contactsApi.topEngaged(clientId, 50);
        if (isMountedRef.current) { setTopEngaged(topResult); setTopLoading(false); }
        break;
      case 'atrisk':
        setAtRiskLoading(true);
        const riskResult = await contactsApi.atRisk(clientId);
        if (isMountedRef.current) { setAtRisk(riskResult); setAtRiskLoading(false); }
        break;
      case 'dm':
        setDmsLoading(true);
        const dmResult = await contactsApi.decisionMakers(clientId, PAGE_SIZE, (dmsPage - 1) * PAGE_SIZE);
        if (isMountedRef.current) { setDms(dmResult.contacts); setDmsTotal(dmResult.total); setDmsLoading(false); }
        break;
      case 'type':
        setTypeLoading(true);
        const typeResult = await contactsApi.byType(clientId);
        if (isMountedRef.current) { setTypeGroups(typeResult); setTypeLoading(false); }
        break;
    }
  };

  const getSortOrder = (field: string): 'ascend' | 'descend' | null => {
    if (sortBy !== field) return null;
    return sortDir === 'asc' ? 'ascend' : 'descend';
  };

  const handleTableChange: TableProps<ContactAnalytics>['onChange'] = (_pagination, _filters, sorter) => {
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
      title: 'Type',
      dataIndex: 'contact_type',
      key: 'type',
      width: 110,
      render: (v: ContactType) => {
        const cfg = contactTypeConfig[v] || contactTypeConfig.unknown;
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
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
      render: (v: number) => v || 0,
    },
    {
      title: 'Received',
      dataIndex: 'total_emails_received',
      key: 'total_emails_received',
      width: 80,
      sorter: true,
      sortOrder: getSortOrder('total_emails_received'),
      render: (v: number) => v || 0,
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
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 120, render: (v: number) => <EngagementBadge score={v} /> },
    { title: 'Last Contact', dataIndex: 'last_contacted_at', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  const typeColumns = [
    {
      title: 'Type',
      dataIndex: 'contact_type',
      key: 'type',
      render: (v: ContactType) => {
        const cfg = contactTypeConfig[v] || contactTypeConfig.unknown;
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    { title: 'Count', dataIndex: 'count', key: 'count', width: 100 },
    { title: 'Avg Score', dataIndex: 'avg_engagement_score', key: 'score', width: 100, render: (v: number) => <EngagementBadge score={v} /> },
  ];

  const handleRowClick = (record: any) => {
    navigate(`/analytics/contacts/${record.id}`);
  };

  const companyDrilldown = searchParams.get('company');

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {companyDrilldown && (
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>
          Back to {companyDrilldown}
        </Button>
      )}
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">
          {companyDrilldown
            ? `Contacts for ${companyDrilldown}${dmOnly ? ' (Decision Makers)' : ''}`
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
                <Space style={{ marginBottom: 16 }} wrap>
                  <Input.Search
                    placeholder="Search name, email, company..."
                    allowClear
                    defaultValue={search}
                    onSearch={(v) => { setSearch(v); setContactsPage(1); }}
                    style={{ width: 240 }}
                    size="small"
                  />
                  <Text>Type:</Text>
                  <Select
                    value={contactType}
                    onChange={v => { setContactType(v); setContactsPage(1); }}
                    options={CONTACT_TYPE_OPTIONS}
                    style={{ width: 140 }}
                    size="small"
                  />
                  <Text>Min Score:</Text>
                  <Slider value={sliderScore} onChange={setSliderScore} onChangeComplete={v => { setMinScore(v); setSliderScore(v); setContactsPage(1); }} min={0} max={100} style={{ width: 120 }} />
                  <Text>Decision Makers:</Text>
                  <Switch checked={dmOnly} onChange={v => { setDmOnly(v); setContactsPage(1); }} size="small" />
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
                data={topEngaged}
                total={topEngaged.length}
                loading={topLoading}
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
                data={atRisk}
                total={atRisk.length}
                loading={atRiskLoading}
                onRowClick={handleRowClick}
                rowKey="id"
              />
            ),
          },
          {
            key: 'dm',
            label: `Decision Makers (${dmsTotal})`,
            children: (
              <>
                {dmsTotal === 0 && !dmsLoading && clientId && (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="No decision makers detected"
                    description="Decision makers are contacts with C-level, VP, or Director titles. These are auto-detected from email signatures and job titles during extraction. If your contacts don't have professional titles in their email data, this section will be empty."
                  />
                )}
                <AnalyticsTable<ContactAnalytics>
                  columns={allColumns}
                  data={dms}
                  total={dmsTotal}
                  loading={dmsLoading}
                  pageSize={PAGE_SIZE}
                  currentPage={dmsPage}
                  onPageChange={(p) => setDmsPage(p)}
                  onRowClick={handleRowClick}
                  rowKey="id"
                  emptyText="No decision makers found. Decision makers are auto-detected from job titles (C-level, VP, Director)."
                />
              </>
            ),
          },
          {
            key: 'type',
            label: 'By Type',
            children: (
              <AnalyticsTable<ContactTypeGrouping>
                columns={typeColumns}
                data={typeGroups}
                total={typeGroups.length}
                loading={typeLoading}
                rowKey="contact_type"
              />
            ),
          },
        ]} />
      </div>
    </div>
  );
};
