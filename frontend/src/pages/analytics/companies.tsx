import React, { useState, useEffect, useRef } from 'react';
import { Typography, Tabs, Tag, Space, Switch, Input, Select } from 'antd';
import type { TableProps } from 'antd';
import { useNavigate } from 'react-router-dom';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { AnalyticsTable } from '../../components/analytics/AnalyticsTable';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import api from '../../services/apiClient';
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
  const [clientId, setClientId] = useState(() => localStorage.getItem('analytics_client_id') || '');
  const [activeTab, setActiveTab] = useState('all');
  const [loading, setLoading] = useState(false);

  const [companies, setCompanies] = useState<CompanyAnalytics[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [qbMatched, setQbMatched] = useState(false);
  const [tierFilter, setTierFilter] = useState('');
  const [amFilter, setAmFilter] = useState('');
  const [sortBy, setSortBy] = useState<string>('engagement_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Dynamic filter options from backend
  const [tierOptions, setTierOptions] = useState<{ value: string; label: string }[]>([]);
  const [amOptions, setAmOptions] = useState<{ value: string; label: string }[]>([]);

  const [topEngaged, setTopEngaged] = useState<TopEngagedCompany[]>([]);
  const [topLoading, setTopLoading] = useState(false);
  const [atRisk, setAtRisk] = useState<AtRiskCompany[]>([]);
  const [atRiskLoading, setAtRiskLoading] = useState(false);
  const [statusGroups, setStatusGroups] = useState<EngagementStatusGrouping[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  // Fetch filter options when client changes
  useEffect(() => {
    if (!clientId) return;
    api.get<{ tiers: string[]; account_managers: string[] }>(
      `/v1/analytics/companies/filter-options?client_id=${clientId}`
    ).then(data => {
      if (!isMountedRef.current) return;
      setTierOptions([
        { value: '', label: 'All Tiers' },
        ...(data?.tiers || []).map(t => {
          const m = t.match(/Level\s*(\d)/i);
          return { value: t, label: m ? `L${m[1]} — ${t.replace(/Level\s*\d\s*[-–]?\s*/, '')}` : t };
        }),
      ]);
      setAmOptions([
        { value: '', label: 'All AMs' },
        ...(data?.account_managers || []).map(am => ({ value: am, label: am })),
      ]);
    }).catch(() => {});
  }, [clientId]);

  useEffect(() => {
    if (!clientId) return;
    loadTab(activeTab);
  }, [clientId, activeTab, page, search, qbMatched, tierFilter, amFilter, sortBy, sortDir]);

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
          qb_tier: tierFilter || undefined,
          qb_account_manager: amFilter || undefined,
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

  const hasFilters = qbMatched || !!tierFilter || !!amFilter || !!search;

  const allColumns = [
    {
      title: 'Company', dataIndex: 'company_name', key: 'company_name', width: 200, ellipsis: true,
      sorter: true, sortOrder: getSortOrder('company_name'),
    },
    {
      title: 'Tier', dataIndex: 'qb_tier', key: 'qb_tier', width: 55,
      sorter: true, sortOrder: getSortOrder('qb_tier'),
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
      sorter: true, sortOrder: getSortOrder('qb_total_revenue'),
      render: (v: number | null) => v != null ? `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '-',
    },
    {
      title: 'AM', dataIndex: 'qb_account_manager', key: 'qb_account_manager', width: 110, ellipsis: true,
      sorter: true, sortOrder: getSortOrder('qb_account_manager'),
      render: (v: string | null) => v || '-',
    },
    {
      title: 'Score', dataIndex: 'engagement_score', key: 'engagement_score', width: 100,
      sorter: true, sortOrder: getSortOrder('engagement_score'),
      render: (v: number) => <EngagementBadge score={v} />,
    },
    {
      title: 'Emails', dataIndex: 'total_emails', key: 'total_emails', width: 70, align: 'right' as const,
      sorter: true, sortOrder: getSortOrder('total_emails'),
      render: (v: number, r: CompanyAnalytics) => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/emails?company_id=${r.id}`); }} style={{ color: '#667eea' }}>{v || 0}</a>
      ),
    },
    {
      title: 'Contacts', dataIndex: 'contact_count', key: 'contact_count', width: 75, align: 'right' as const,
      sorter: true, sortOrder: getSortOrder('contact_count'),
      render: (v: number, r: CompanyAnalytics) => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/customers/contacts?company_id=${r.id}&client_id=${clientId}`); }} style={{ color: '#667eea' }}>{v ?? 0}</a>
      ),
    },
    {
      title: 'Last Contact', dataIndex: 'last_contact_date', key: 'last_contact_date', width: 100,
      sorter: true, sortOrder: getSortOrder('last_contact_date'),
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
      title: 'Tier', dataIndex: 'qb_tier', key: 'qb_tier', width: 55,
      render: (v: string | null) => {
        if (!v) return null;
        const m = v.match(/Level\s*(\d)/i);
        const short = m ? `L${m[1]}` : v;
        const colors: Record<string, string> = { L1: 'default', L2: 'blue', L3: 'green', L4: 'gold', L8: 'cyan' };
        return <Tag color={colors[short] || 'default'}>{short}</Tag>;
      },
    },
    { title: 'Revenue', dataIndex: 'qb_total_revenue', key: 'qb_total_revenue', width: 100, render: (v: number | null) => formatCurrency(v) },
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
            label: `All Companies (${total})`,
            children: (
              <>
                <Space style={{ marginBottom: 12 }} wrap size={[8, 8]}>
                  <Input.Search
                    placeholder="Search company..."
                    allowClear
                    onSearch={(v) => { setSearch(v); setPage(1); }}
                    style={{ width: 200 }}
                    size="small"
                  />
                  <Select
                    value={tierFilter}
                    onChange={v => { setTierFilter(v); setPage(1); }}
                    options={tierOptions}
                    style={{ width: 140 }}
                    size="small"
                    popupMatchSelectWidth={false}
                  />
                  <Select
                    value={amFilter}
                    onChange={v => { setAmFilter(v); setPage(1); }}
                    options={amOptions}
                    style={{ width: 150 }}
                    size="small"
                    showSearch
                    filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
                    popupMatchSelectWidth={false}
                  />
                  <Switch checked={qbMatched} onChange={v => { setQbMatched(v); setPage(1); }} size="small" />
                  <Text type="secondary" style={{ fontSize: 12 }}>QB only</Text>
                  {hasFilters && (
                    <a onClick={() => { setSearch(''); setTierFilter(''); setAmFilter(''); setQbMatched(false); setPage(1); }} style={{ fontSize: 12 }}>
                      Clear all
                    </a>
                  )}
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
