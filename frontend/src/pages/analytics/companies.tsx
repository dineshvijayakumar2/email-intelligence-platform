import React, { useState, useEffect, useRef } from 'react';
import { Typography, Tabs, Tag, Space, Switch, Input } from 'antd';
import type { TableProps } from 'antd';
import { useNavigate } from 'react-router-dom';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import {
  companiesApi,
  formatRelativeTime,
  engagementStatusConfig,
} from '../../services/analyticsService';
import { formatCurrency } from '../../utils/numberFormat';
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
  const [search, setSearch] = useState<string>('');
  const [qbMatched, setQbMatched] = useState(false);
  const [sortBy, setSortBy] = useState<string>('engagement_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

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
  }, [clientId, activeTab, page, search, qbMatched, sortBy, sortDir]);

  const loadTab = async (tab: string) => {
    if (!clientId) return;
    switch (tab) {
      case 'all':
        setLoading(true);
        const allResult = await companiesApi.list({
          client_id: clientId,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
          qb_matched: qbMatched || undefined,
          search: search || undefined,
          sort_by: sortBy,
          sort_dir: sortDir,
        });
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

  const getSortOrder = (field: string): 'ascend' | 'descend' | null => {
    if (sortBy !== field) return null;
    return sortDir === 'asc' ? 'ascend' : 'descend';
  };

  const handleTableChange: TableProps<CompanyAnalytics>['onChange'] = (_pagination, _filters, sorter) => {
    if (!sorter || Array.isArray(sorter)) return;
    const field = (sorter.columnKey ?? sorter.field) as string | undefined;
    if (field && sorter.order) {
      setSortBy(field);
      setSortDir(sorter.order === 'ascend' ? 'asc' : 'desc');
      setPage(1);
    } else if (!sorter.order) {
      setSortBy('engagement_score');
      setSortDir('desc');
      setPage(1);
    }
  };

  const allColumns = [
    {
      title: 'Company',
      dataIndex: 'company_name',
      key: 'company_name',
      width: 200,
      ellipsis: true,
      sorter: true,
      sortOrder: getSortOrder('company_name'),
    },
    {
      title: 'Tier', dataIndex: 'qb_tier', key: 'qb_tier', width: 55,
      sorter: true,
      sortOrder: getSortOrder('qb_tier'),
      filters: [
        { text: 'L1 Retail', value: 'Level 1' },
        { text: 'L2 Growth', value: 'Level 2' },
        { text: 'L3 Major', value: 'Level 3' },
        { text: 'L4 Enterprise', value: 'Level 4' },
        { text: 'L8 Trade', value: 'Level 8' },
        { text: 'No Tier', value: '__none__' },
      ],
      onFilter: (value: any, record: any) => value === '__none__' ? !record.qb_tier : (record.qb_tier || '').includes(value),
      render: (v: string | null) => {
        if (!v) return null;
        const m = v.match(/Level\s*(\d)/i);
        const short = m ? `L${m[1]}` : v.slice(0, 4);
        const colors: Record<string, string> = { L1: 'default', L2: 'blue', L3: 'green', L4: 'gold', L8: 'cyan' };
        return <Tag color={colors[short] || 'default'}>{short}</Tag>;
      },
    },
    {
      title: 'Revenue', dataIndex: 'qb_total_revenue', key: 'qb_total_revenue', width: 100, align: 'right' as const,
      sorter: true,
      sortOrder: getSortOrder('qb_total_revenue'),
      render: (v: number | null) => v != null ? `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '-',
    },
    {
      title: 'AM', dataIndex: 'qb_account_manager', key: 'qb_account_manager', width: 110, ellipsis: true,
      sorter: true,
      sortOrder: getSortOrder('qb_account_manager'),
      filters: [
        { text: 'Colin Brown', value: 'Colin Brown' },
        { text: 'Dan Sutherland', value: 'Dan Sutherland' },
        { text: 'Daniel Hall', value: 'Daniel Hall' },
        { text: 'Ehab Kamel', value: 'Ehab Kamel' },
        { text: 'Jacky Chan', value: 'Jacky Chan' },
        { text: 'Kalani Evans', value: 'Kalani Evans' },
        { text: 'Kenneth Beck-Pedersen', value: 'Kenneth Beck-Pedersen' },
        { text: 'Linda D\'Arcy', value: 'Linda D\'Arcy' },
        { text: 'Mary Serratore-Howe', value: 'Mary Serratore-Howe' },
        { text: 'Nathan Brown', value: 'Nathan Brown' },
        { text: 'Nic Doyle', value: 'Nic Doyle' },
        { text: 'Peter Musarra', value: 'Peter Musarra' },
        { text: 'Prince Claudio', value: 'Prince Claudio' },
        { text: 'The Carbon8 Team', value: 'The Carbon8 Team' },
      ],
      onFilter: (value: any, record: any) => record.qb_account_manager === value,
      render: (v: string | null) => v || '-',
    },
    {
      title: 'Score', dataIndex: 'engagement_score', key: 'engagement_score', width: 100,
      sorter: true,
      sortOrder: getSortOrder('engagement_score'),
      render: (v: number) => <EngagementBadge score={v} />,
    },
    {
      title: 'Emails', dataIndex: 'total_emails', key: 'total_emails', width: 70, align: 'right' as const,
      sorter: true,
      sortOrder: getSortOrder('total_emails'),
      render: (v: number, r: CompanyAnalytics) => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/emails?company_id=${r.id}`); }} style={{ color: '#667eea' }}>
          {v || 0}
        </a>
      ),
    },
    {
      title: 'Contacts', dataIndex: 'contact_count', key: 'contact_count', width: 75, align: 'right' as const,
      sorter: true,
      sortOrder: getSortOrder('contact_count'),
      render: (v: number, r: CompanyAnalytics) => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/customers/contacts?company_id=${r.id}&client_id=${clientId}`); }} style={{ color: '#667eea' }}>
          {v ?? 0}
        </a>
      ),
    },
    {
      title: 'Last Contact', dataIndex: 'last_contact_date', key: 'last_contact_date', width: 100,
      sorter: true,
      sortOrder: getSortOrder('last_contact_date'),
      render: (v: string) => formatRelativeTime(v),
    },
  ];

  const topColumns = [
    { title: 'Company', dataIndex: 'company_name', key: 'name' },
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 120, render: (v: number) => <EngagementBadge score={v} /> },
    { title: 'Emails', dataIndex: 'total_emails', key: 'emails', width: 80 },
    { title: 'Contacts', dataIndex: 'contact_count', key: 'contacts', width: 80 },
    { title: 'Last Contact', dataIndex: 'last_contact_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  const atRiskColumns = [
    { title: 'Company', dataIndex: 'company_name', key: 'name' },
    {
      title: 'Tier', dataIndex: 'qb_tier', key: 'qb_tier', width: 60,
      render: (v: string | null) => {
        if (!v) return null;
        const colors: Record<string, string> = { A: 'green', B: 'blue', C: 'orange' };
        return <Tag color={colors[v] || 'default'}>{v}</Tag>;
      },
    },
    {
      title: 'Revenue TY', dataIndex: 'qb_total_revenue', key: 'qb_total_revenue', width: 110,
      render: (v: number | null) => formatCurrency(v),
    },
    { title: 'Days Silent', dataIndex: 'days_since_contact', key: 'days', width: 100, render: (v: number) => <Tag color={v > 90 ? 'red' : 'orange'}>{v}d</Tag> },
    { title: 'Contacts', dataIndex: 'contact_count', key: 'contacts', width: 80 },
    { title: 'Score', dataIndex: 'engagement_score', key: 'score', width: 120, render: (v: number) => <EngagementBadge score={v} /> },
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
          {
            key: 'all',
            label: `All Companies (${total})${qbMatched ? ' — QB Matched' : ''}`,
            children: (
              <>
                <Space style={{ marginBottom: 16 }} wrap>
                  <Input.Search
                    placeholder="Search company name..."
                    allowClear
                    onSearch={(v) => { setSearch(v); setPage(1); }}
                    style={{ width: 240 }}
                    size="small"
                  />
                  <Text>QB Matched:</Text>
                  <Switch checked={qbMatched} onChange={v => { setQbMatched(v); setPage(1); }} size="small" />
                </Space>
                <AnalyticsTable<CompanyAnalytics>
                  columns={allColumns}
                  data={companies}
                  total={total}
                  loading={loading}
                  pageSize={PAGE_SIZE}
                  currentPage={page}
                  onPageChange={setPage}
                  onRowClick={(r) => navigate(`/customers/${r.id}`)}
                  onChange={handleTableChange}
                  rowKey="id"
                />
              </>
            ),
          },
          { key: 'top', label: 'Top Engaged', children: <AnalyticsTable columns={topColumns} data={topEngaged} total={topEngaged.length} loading={topLoading} onRowClick={(r) => navigate(`/customers/${r.id}`)} /> },
          { key: 'atrisk', label: 'At Risk', children: <AnalyticsTable columns={atRiskColumns} data={atRisk} total={atRisk.length} loading={atRiskLoading} onRowClick={(r) => navigate(`/customers/${r.id}`)} /> },
          { key: 'status', label: 'By Engagement', children: <AnalyticsTable columns={statusColumns} data={statusGroups} total={statusGroups.length} loading={statusLoading} rowKey="engagement_status" /> },
        ]} />
      </div>
    </div>
  );
};
