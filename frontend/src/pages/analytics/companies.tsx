import React, { useState, useMemo } from 'react';
import { Typography, Tabs, Tag, Space, Switch, Input, Select } from 'antd';
import { useNavigate } from 'react-router-dom';
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
import {
  useCompanies,
  useTopEngagedCompanies,
  useAtRiskCompanies,
  useCompanyEngagementGroups,
  useCompanyFilterOptions,
} from '../../hooks/queries';
import { formatRelativeTime, engagementStatusConfig } from '../../services/analyticsService';
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
const col = createColumnHelper<CompanyAnalytics>();

export const CompaniesAnalytics: React.FC = () => {
  const navigate = useNavigate();
  const [clientId, setClientId] = useState(() => localStorage.getItem('analytics_client_id') || '');
  const [activeTab, setActiveTab] = useState('all');

  // Filter + pagination state
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [qbMatched, setQbMatched] = useState(false);
  const [tierFilter, setTierFilter] = useState('');
  const [amFilter, setAmFilter] = useState('');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'engagement_score', desc: true }]);

  const sortBy = sorting[0]?.id || 'engagement_score';
  const sortDir = sorting[0]?.desc ? 'desc' : 'asc';

  // Data queries
  const companiesQuery = useCompanies({
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

  const topQuery = useTopEngagedCompanies(clientId);
  const atRiskQuery = useAtRiskCompanies(clientId);
  const statusQuery = useCompanyEngagementGroups(clientId);
  const filterOptionsQuery = useCompanyFilterOptions(clientId);

  // Dynamic filter options
  const tierOptions = useMemo(() => {
    const tiers = filterOptionsQuery.data?.tiers || [];
    return [
      { value: '', label: 'All Tiers' },
      ...tiers.map(t => {
        const m = t.match(/Level\s*(\d)/i);
        return { value: t, label: m ? `L${m[1]} — ${t.replace(/Level\s*\d\s*[-–]?\s*/, '')}` : t };
      }),
    ];
  }, [filterOptionsQuery.data]);

  const amOptions = useMemo(() => {
    const ams = filterOptionsQuery.data?.account_managers || [];
    return [{ value: '', label: 'All AMs' }, ...ams.map(am => ({ value: am, label: am }))];
  }, [filterOptionsQuery.data]);

  const companies = companiesQuery.data?.companies || [];
  const total = companiesQuery.data?.total || 0;

  // TanStack Table column definitions
  const columns = useMemo(() => [
    col.accessor('company_name', {
      header: 'Company',
      size: 200,
      cell: info => <Text ellipsis={{ tooltip: info.getValue() }}>{info.getValue()}</Text>,
    }),
    col.accessor('qb_tier', {
      header: 'Tier',
      size: 55,
      cell: info => {
        const v = info.getValue();
        if (!v) return null;
        const m = v.match(/Level\s*(\d)/i);
        const short = m ? `L${m[1]}` : v.slice(0, 4);
        const colors: Record<string, string> = { L1: 'default', L2: 'blue', L3: 'green', L4: 'gold', L8: 'cyan' };
        return <Tag color={colors[short] || 'default'}>{short}</Tag>;
      },
    }),
    col.accessor('qb_total_revenue', {
      header: 'Revenue',
      size: 100,
      meta: { align: 'right' },
      cell: info => {
        const v = info.getValue();
        return v != null ? `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '-';
      },
    }),
    col.accessor('qb_account_manager', {
      header: 'AM',
      size: 110,
      cell: info => info.getValue() || '-',
    }),
    col.accessor('engagement_score', {
      header: 'Score',
      size: 100,
      cell: info => <EngagementBadge score={info.getValue() ?? 0} />,
    }),
    col.accessor('total_emails', {
      header: 'Emails',
      size: 70,
      meta: { align: 'right' },
      cell: info => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/emails?company_id=${info.row.original.id}`); }} style={{ color: '#667eea' }}>
          {info.getValue() || 0}
        </a>
      ),
    }),
    col.accessor('contact_count', {
      header: 'Contacts',
      size: 75,
      meta: { align: 'right' },
      cell: info => (
        <a onClick={(e) => { e.stopPropagation(); navigate(`/customers/contacts?company_id=${info.row.original.id}&client_id=${clientId}`); }} style={{ color: '#667eea' }}>
          {info.getValue() ?? 0}
        </a>
      ),
    }),
    col.accessor('last_contact_date', {
      header: 'Last Contact',
      size: 100,
      cell: info => formatRelativeTime(info.getValue()),
    }),
  ], [clientId, navigate]);

  // TanStack Table instance — manualSorting since sort is server-side
  const table = useReactTable({
    data: companies,
    columns,
    state: { sorting },
    onSortingChange: (updater) => {
      const next = typeof updater === 'function' ? updater(sorting) : updater;
      setSorting(next);
      setPage(1);
    },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    enableSortingRemoval: false,
  });

  const hasFilters = qbMatched || !!tierFilter || !!amFilter || !!search;

  // Tabs that still use AnalyticsTable (Ant Design) — only the "All" tab uses TanStack Table
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
                <DataTable<CompanyAnalytics>
                  table={table}
                  total={total}
                  loading={companiesQuery.isLoading}
                  pageSize={PAGE_SIZE}
                  currentPage={page}
                  onPageChange={setPage}
                  onRowClick={(r) => navigate(`/customers/${r.id}`)}
                />
              </>
            ),
          },
          {
            key: 'top',
            label: 'Top Engaged',
            children: (
              <AnalyticsTable
                columns={topColumns}
                data={topQuery.data || []}
                total={(topQuery.data || []).length}
                loading={topQuery.isLoading}
                onRowClick={(r) => navigate(`/customers/${r.id}`)}
              />
            ),
          },
          {
            key: 'atrisk',
            label: 'At Risk',
            children: (
              <AnalyticsTable
                columns={atRiskColumns}
                data={atRiskQuery.data || []}
                total={(atRiskQuery.data || []).length}
                loading={atRiskQuery.isLoading}
                onRowClick={(r) => navigate(`/customers/${r.id}`)}
              />
            ),
          },
          {
            key: 'status',
            label: 'By Engagement',
            children: (
              <AnalyticsTable
                columns={statusColumns}
                data={statusQuery.data || []}
                total={(statusQuery.data || []).length}
                loading={statusQuery.isLoading}
                rowKey="engagement_status"
              />
            ),
          },
        ]} />
      </div>
    </div>
  );
};
