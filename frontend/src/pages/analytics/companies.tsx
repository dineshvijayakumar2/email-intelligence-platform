import React, { useState, useEffect, useRef } from 'react';
import { Typography, Tabs, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import {
  companiesApi,
  formatRelativeTime,
  engagementStatusConfig,
} from '../../services/analyticsService';
import type {
  CompanyAnalytics,
  TopEngagedCompany,
  AtRiskCompany,
  EngagementStatusGrouping,
  EngagementStatus,
} from '../../types/analytics';

const { Text } = Typography;
const PAGE_SIZE = 20;

export const CompaniesAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [activeTab, setActiveTab] = useState('all');
  const [loading, setLoading] = useState(false);

  const [companies, setCompanies] = useState<CompanyAnalytics[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const [topEngaged, setTopEngaged] = useState<TopEngagedCompany[]>([]);
  const [topLoading, setTopLoading] = useState(false);

  const [atRisk, setAtRisk] = useState<AtRiskCompany[]>([]);
  const [atRiskLoading, setAtRiskLoading] = useState(false);

  const [statusGroups, setStatusGroups] = useState<EngagementStatusGrouping[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    loadTab(activeTab);
  }, [clientId, activeTab, page]);

  const loadTab = async (tab: string) => {
    if (!clientId) return;
    switch (tab) {
      case 'all':
        setLoading(true);
        const allResult = await companiesApi.list({ client_id: clientId, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
        if (isMountedRef.current) { setCompanies(allResult.companies); setTotal(allResult.total); setLoading(false); }
        break;
      case 'top':
        setTopLoading(true);
        const topResult = await companiesApi.topEngaged(clientId, 50);
        if (isMountedRef.current) { setTopEngaged(topResult); setTopLoading(false); }
        break;
      case 'atrisk':
        setAtRiskLoading(true);
        const riskResult = await companiesApi.atRisk(clientId);
        if (isMountedRef.current) { setAtRisk(riskResult); setAtRiskLoading(false); }
        break;
      case 'status':
        setStatusLoading(true);
        const statusResult = await companiesApi.byEngagement(clientId);
        if (isMountedRef.current) { setStatusGroups(statusResult); setStatusLoading(false); }
        break;
    }
  };

  const allColumns = [
    { title: 'Company', dataIndex: 'company_name', key: 'name' },
    {
      title: 'Status', dataIndex: 'engagement_status', key: 'status', width: 100,
      render: (v: EngagementStatus) => { const cfg = engagementStatusConfig[v] || engagementStatusConfig.unknown; return <Tag color={cfg.color}>{cfg.label}</Tag>; },
    },
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 80, render: (v: number) => <EngagementBadge score={v} /> },
    { title: 'Emails', dataIndex: 'total_emails', key: 'emails', width: 80 },
    { title: 'Contacts', dataIndex: 'contact_count', key: 'contacts', width: 80 },
    { title: 'DMs', dataIndex: 'decision_maker_count', key: 'dms', width: 60 },
    { title: 'Last Contact', dataIndex: 'last_contact_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  const topColumns = [
    { title: 'Company', dataIndex: 'company_name', key: 'name' },
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 80, render: (v: number) => <EngagementBadge score={v} /> },
    { title: 'Emails', dataIndex: 'total_emails', key: 'emails', width: 80 },
    { title: 'Contacts', dataIndex: 'contact_count', key: 'contacts', width: 80 },
    { title: 'Last Contact', dataIndex: 'last_contact_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  const atRiskColumns = [
    { title: 'Company', dataIndex: 'company_name', key: 'name' },
    { title: 'Days Silent', dataIndex: 'days_since_contact', key: 'days', width: 100, render: (v: number) => <Tag color={v > 90 ? 'red' : 'orange'}>{v}d</Tag> },
    { title: 'Contacts', dataIndex: 'contact_count', key: 'contacts', width: 80 },
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 80, render: (v: number) => <EngagementBadge score={v} /> },
  ];

  const statusColumns = [
    {
      title: 'Status', dataIndex: 'engagement_status', key: 'status',
      render: (v: EngagementStatus) => { const cfg = engagementStatusConfig[v] || engagementStatusConfig.unknown; return <Tag color={cfg.color}>{cfg.label}</Tag>; },
    },
    { title: 'Count', dataIndex: 'count', key: 'count', width: 100 },
    { title: 'Avg Score', dataIndex: 'avg_engagement_score', key: 'score', width: 100, render: (v: number) => <EngagementBadge score={v} /> },
  ];

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Text type="secondary">Explore company engagement, relationship health, and risk indicators</Text>
        <ClientSelector value={clientId} onChange={setClientId} />
      </div>
      <div className="fade-in-up stagger-1">
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          { key: 'all', label: `All Companies (${total})`, children: <AnalyticsTable columns={allColumns} data={companies} total={total} loading={loading} pageSize={PAGE_SIZE} currentPage={page} onPageChange={setPage} onRowClick={(r) => navigate(`/analytics/companies/${r.id}`)} /> },
          { key: 'top', label: 'Top Engaged', children: <AnalyticsTable columns={topColumns} data={topEngaged} total={topEngaged.length} loading={topLoading} onRowClick={(r) => navigate(`/analytics/companies/${r.id}`)} /> },
          { key: 'atrisk', label: 'At Risk', children: <AnalyticsTable columns={atRiskColumns} data={atRisk} total={atRisk.length} loading={atRiskLoading} onRowClick={(r) => navigate(`/analytics/companies/${r.id}`)} /> },
          { key: 'status', label: 'By Engagement', children: <AnalyticsTable columns={statusColumns} data={statusGroups} total={statusGroups.length} loading={statusLoading} rowKey="engagement_status" /> },
        ]} />
      </div>
    </div>
  );
};
