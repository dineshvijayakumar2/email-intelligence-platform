import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Tabs, Tag, Space, Slider, Switch } from 'antd';
import { useNavigate } from 'react-router-dom';
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

export const ContactsAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [activeTab, setActiveTab] = useState('all');
  const [loading, setLoading] = useState(false);

  // All contacts state
  const [contacts, setContacts] = useState<ContactAnalytics[]>([]);
  const [contactsTotal, setContactsTotal] = useState(0);
  const [contactsPage, setContactsPage] = useState(1);
  const [minScore, setMinScore] = useState<number>(0);
  const [dmOnly, setDmOnly] = useState(false);

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
  }, [clientId, activeTab, contactsPage, dmsPage, minScore, dmOnly]);

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

  const allColumns = [
    {
      title: 'Contact',
      key: 'name',
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
      key: 'company',
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
      key: 'score',
      width: 100,
      render: (v: number) => <EngagementBadge score={v} showBar size="small" />,
    },
    {
      title: 'Emails',
      key: 'emails',
      width: 80,
      render: (_: any, r: ContactAnalytics) => (r.total_emails_sent || 0) + (r.total_emails_received || 0),
    },
    {
      title: 'Last Contact',
      dataIndex: 'last_contacted_at',
      key: 'lastContact',
      width: 110,
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
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 80, render: (v: number) => <EngagementBadge score={v} /> },
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
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 80, render: (v: number) => <EngagementBadge score={v} /> },
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

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">Explore contacts, engagement scores, and relationship health</Text>
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
                  <Text>Min Score:</Text>
                  <Slider value={minScore} onChange={v => { setMinScore(v); setContactsPage(1); }} min={0} max={100} style={{ width: 120 }} />
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
            label: 'Decision Makers',
            children: (
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
              />
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
