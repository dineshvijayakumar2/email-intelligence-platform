/**
 * Quickbase Data Views — Browse synced QB cache tables.
 * TanStack Query for data fetching, server-side sort via column headers.
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Card, Tabs, Table, Input, Button, Tag, Space, Typography, Statistic,
  Row, Col, Spin, Badge, Tooltip, message, Dropdown, Pagination,
} from 'antd';
import {
  ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined,
  SyncOutlined, DownOutlined, SortAscendingOutlined,
} from '@ant-design/icons';
import api from '../../services/apiClient';
import { useQBTable, useQBSyncStatus } from '../../hooks/queries';

const { Title, Text } = Typography;
const { Search } = Input;

const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// Column definitions — each column's dataIndex is also its sort key
// ---------------------------------------------------------------------------

const customerColumns = [
  { title: 'Name', dataIndex: 'customer_name', key: 'customer_name', width: 200, ellipsis: true, sorter: true },
  { title: 'Code', dataIndex: 'customer_code', key: 'customer_code', width: 90, sorter: true },
  { title: 'Tier', dataIndex: 'customer_tier', key: 'customer_tier', width: 80, sorter: true,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Status', dataIndex: 'customer_status', key: 'customer_status', width: 100, sorter: true,
    render: (v: string) => v ? <Tag color={v === 'Active' ? 'green' : 'default'}>{v}</Tag> : '-' },
  { title: 'Account Manager', dataIndex: 'account_manager', key: 'account_manager', width: 160, ellipsis: true, sorter: true },
  { title: 'Industry', dataIndex: 'industry', key: 'industry', width: 140, ellipsis: true },
  { title: 'Total Invoiced', dataIndex: 'total_invoiced', key: 'total_invoiced', width: 130, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'TY', dataIndex: 'invoiced_ty', key: 'invoiced_ty', width: 110, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'LY', dataIndex: 'invoiced_ly', key: 'invoiced_ly', width: 110, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Days Since Invoice', dataIndex: 'days_since_last_invoice', key: 'days_since_last_invoice', width: 130, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? <Text type={v > 180 ? 'danger' : v > 90 ? 'warning' : undefined}>{v}d</Text> : '-' },
  { title: 'Matched', dataIndex: 'matched_company_name', key: 'matched', width: 160, ellipsis: true,
    render: (v: string) => v
      ? <Tooltip title={v}><CheckCircleOutlined style={{ color: '#52c41a' }} /> {v}</Tooltip>
      : <Text type="secondary"><CloseCircleOutlined /> unmatched</Text> },
];

const contactColumns = [
  { title: 'First Name', dataIndex: 'first_name', key: 'first_name', width: 130, sorter: true },
  { title: 'Surname', dataIndex: 'surname', key: 'surname', width: 140, sorter: true },
  { title: 'Email', dataIndex: 'email', key: 'email', width: 220, ellipsis: true, sorter: true },
  { title: 'Phone', dataIndex: 'phone', key: 'phone', width: 140 },
  { title: 'Active', dataIndex: 'active', key: 'active', width: 70,
    render: (v: any) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#bbb' }} /> },
  { title: 'Recency (days)', dataIndex: 'contact_recency_days', key: 'contact_recency_days', width: 130, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `${v}d` : '-' },
  { title: 'Quotes Accepted', dataIndex: 'quotes_accepted_count', key: 'quotes_accepted_count', width: 130, align: 'right' as const, sorter: true },
  { title: 'Last Quote', dataIndex: 'most_recent_quote_date', key: 'most_recent_quote_date', width: 130, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Matched', dataIndex: 'matched_contact_id', key: 'matched', width: 80,
    render: (v: string) => v
      ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
      : <Text type="secondary"><CloseCircleOutlined /></Text> },
];

const quoteColumns = [
  { title: 'Quote No', dataIndex: 'quote_no', key: 'quote_no', width: 110, sorter: true },
  { title: 'Contact', dataIndex: 'contact_name', key: 'contact_name', width: 160, ellipsis: true, sorter: true },
  { title: 'Email', dataIndex: 'contact_email', key: 'contact_email', width: 200, ellipsis: true },
  { title: 'AM', dataIndex: 'quote_am_name', key: 'quote_am_name', width: 140, ellipsis: true, sorter: true },
  { title: 'Category', dataIndex: 'category', key: 'category', width: 120,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Sell (ex tax)', dataIndex: 'sell_ex_tax', key: 'sell_ex_tax', width: 120, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Created', dataIndex: 'date_created', key: 'date_created', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Accepted', dataIndex: 'date_accepted', key: 'date_accepted', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Has Job', dataIndex: 'has_job', key: 'has_job', width: 80,
    render: (v: any) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : '-' },
  { title: 'Qty', dataIndex: 'total_quantity', key: 'total_quantity', width: 80, align: 'right' as const },
];

const jobColumns = [
  { title: 'Job No', dataIndex: 'job_no', key: 'job_no', width: 100, sorter: true },
  { title: 'Quote No', dataIndex: 'quote_no', key: 'quote_no', width: 100 },
  { title: 'Status', dataIndex: 'job_status', key: 'job_status', width: 120, sorter: true,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Retail Sale', dataIndex: 'retail_sale', key: 'retail_sale', width: 120, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Margin', dataIndex: 'invoiced_margin', key: 'invoiced_margin', width: 110, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Margin %', dataIndex: 'margin_pct', key: 'margin_pct', width: 100, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `${Number(v).toFixed(1)}%` : '-' },
  { title: 'Accepted', dataIndex: 'accepted_date', key: 'accepted_date', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Due', dataIndex: 'due_date', key: 'due_date', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Pieces', dataIndex: 'pieces_ordered', key: 'pieces_ordered', width: 80, align: 'right' as const },
  { title: 'Kinds', dataIndex: 'kinds_ordered', key: 'kinds_ordered', width: 80, align: 'right' as const },
  { title: 'Embellishments', key: 'embellishments', width: 220,
    render: (_: any, r: any) => {
      const flags = [
        { key: 'has_hot_foil', label: 'Hot Foil', color: 'red' },
        { key: 'has_spot_uv', label: 'Spot UV', color: 'blue' },
        { key: 'has_special_substrate', label: 'Special Sub', color: 'purple' },
        { key: 'has_digital_foil', label: 'Digital Foil', color: 'gold' },
        { key: 'has_de_emboss', label: 'De/Emboss', color: 'orange' },
        { key: 'has_raised_ink', label: 'Raised Ink', color: 'cyan' },
        { key: 'has_laser_cut', label: 'Laser Cut', color: 'volcano' },
        { key: 'has_white_ink', label: 'White Ink', color: 'geekblue' },
      ];
      const active = flags.filter(f => r[f.key] && r[f.key] !== '0' && String(r[f.key]).toLowerCase() !== 'no');
      if (!active.length) return <Text type="secondary" style={{ fontSize: 11 }}>-</Text>;
      return <Space size={2} wrap>{active.map(f => <Tag key={f.key} color={f.color} style={{ fontSize: 10, padding: '0 4px' }}>{f.label}</Tag>)}</Space>;
    } },
];

const sliColumns = [
  { title: 'Invoice No', dataIndex: 'invoice_no', key: 'invoice_no', width: 110, sorter: true },
  { title: 'Customer', dataIndex: 'customer_name', key: 'customer_name', width: 200, ellipsis: true, sorter: true },
  { title: 'Job No', dataIndex: 'job_no', key: 'job_no', width: 100, sorter: true },
  { title: 'Job Title', dataIndex: 'job_title', key: 'job_title', width: 160, ellipsis: true },
  { title: 'AM', dataIndex: 'job_am_name', key: 'job_am_name', width: 140, ellipsis: true },
  { title: 'Product Group', dataIndex: 'product_group', key: 'product_group', width: 130, sorter: true,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Industry', dataIndex: 'industry', key: 'industry', width: 130, ellipsis: true },
  { title: 'Subtotal', dataIndex: 'subtotal', key: 'subtotal', width: 110, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Total', dataIndex: 'total', key: 'total', width: 110, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Date', dataIndex: 'inv_date', key: 'inv_date', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
];

const operationsColumns = [
  { title: 'Operation', dataIndex: 'operation_name', key: 'operation_name', width: 200, ellipsis: true, sorter: true },
  { title: 'Department', dataIndex: 'department', key: 'department', width: 130, sorter: true,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Machine', dataIndex: 'machine', key: 'machine', width: 160, ellipsis: true, sorter: true },
  { title: 'Job No', dataIndex: 'job_no', key: 'job_no', width: 90 },
  { title: 'Customer', dataIndex: 'customer_name', key: 'customer_name', width: 180, ellipsis: true, sorter: true },
  { title: 'AM', dataIndex: 'am_job', key: 'am_job', width: 130, ellipsis: true },
  { title: 'Capability Tags', dataIndex: 'capability_tags', key: 'capability_tags', width: 200,
    render: (v: any) => {
      const tags = Array.isArray(v) ? v : (typeof v === 'string' && v ? v.split(',').map((s: string) => s.trim()) : []);
      if (!tags.length) return <Text type="secondary" style={{ fontSize: 11 }}>-</Text>;
      return <Space size={2} wrap>{tags.map((t: string) => <Tag key={t} color="blue" style={{ fontSize: 11 }}>{t}</Tag>)}</Space>;
    } },
  { title: 'Row Type', dataIndex: 'row_type', key: 'row_type', width: 110,
    render: (v: string) => {
      const colorMap: Record<string, string> = { production: 'green', outsource: 'orange', rush_charge: 'red', admin: 'default', logistics: 'cyan', costing: 'purple' };
      return v ? <Tag color={colorMap[v] || 'default'}>{v}</Tag> : '-';
    } },
  { title: 'Flags', key: 'flags', width: 120,
    render: (_: any, r: any) => (
      <Space size={2}>
        {r.am_rush && <Tag color="volcano" style={{ fontSize: 10, padding: '0 4px' }}>AM Rush</Tag>}
        {r.factory_rush && <Tag color="red" style={{ fontSize: 10, padding: '0 4px' }}>Factory Rush</Tag>}
        {r.has_outsource_component && <Tag color="orange" style={{ fontSize: 10, padding: '0 4px' }}>Outsource</Tag>}
      </Space>
    ) },
  { title: 'Date Accepted', dataIndex: 'date_accepted', key: 'date_accepted', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Cost+ Price', dataIndex: 'cost_plus_price', key: 'cost_plus_price', width: 110, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Profit %', dataIndex: 'profit_pct', key: 'profit_pct', width: 90, align: 'right' as const, sorter: true,
    render: (v: number) => v != null ? `${Number(v).toFixed(1)}%` : '-' },
];

const uniqueEmailColumns = [
  { title: 'Email', dataIndex: 'email', key: 'email', width: 250, ellipsis: true, sorter: true },
  { title: 'Customer Name', dataIndex: 'customer_name', key: 'customer_name', width: 200, ellipsis: true, sorter: true },
  { title: 'First Name', dataIndex: 'first_name', key: 'first_name', width: 120, sorter: true },
  { title: 'Last Name', dataIndex: 'last_name', key: 'last_name', width: 120, sorter: true },
  { title: 'QB Customer ID', dataIndex: 'qb_customer_id', key: 'qb_customer_id', width: 120 },
  { title: 'Type', dataIndex: 'customer_type', key: 'customer_type', width: 160,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Quality', dataIndex: 'quality', key: 'quality', width: 80, sorter: true,
    render: (v: string) => v ? <Tag color={v === 'good' ? 'green' : v === 'risky' ? 'gold' : v === 'bad' ? 'red' : 'default'}>{v}</Tag> : '-' },
  { title: 'Result', dataIndex: 'result', key: 'result', width: 90, sorter: true,
    render: (v: string) => v ? <Tag color={v === 'ok' ? 'green' : v === 'invalid' ? 'red' : 'default'}>{v}</Tag> : '-' },
  { title: 'Capabilities', dataIndex: 'capabilities_used', key: 'capabilities_used', width: 180, ellipsis: true },
  { title: 'Processes', dataIndex: 'processes_used', key: 'processes_used', width: 180, ellipsis: true },
  { title: 'Embellishments', dataIndex: 'embellishments_used', key: 'embellishments_used', width: 180, ellipsis: true },
];

// ---------------------------------------------------------------------------
// Table config
// ---------------------------------------------------------------------------

interface TableConfig {
  key: string;
  label: string;
  endpoint: string;
  responseKey: string;
  columns: any[];
}

const TABLE_CONFIGS: TableConfig[] = [
  { key: 'customers', label: 'Customers', endpoint: 'customers', responseKey: 'customers', columns: customerColumns },
  { key: 'contacts', label: 'Contacts', endpoint: 'contacts', responseKey: 'contacts', columns: contactColumns },
  { key: 'quotes', label: 'Quotes', endpoint: 'quotes', responseKey: 'quotes', columns: quoteColumns },
  { key: 'jobs', label: 'Jobs', endpoint: 'jobs', responseKey: 'jobs', columns: jobColumns },
  { key: 'sales_line_items', label: 'Sales Line Items', endpoint: 'sales-line-items', responseKey: 'sales_line_items', columns: sliColumns },
  { key: 'operations', label: 'Operations', endpoint: 'operations', responseKey: 'operations', columns: operationsColumns },
  { key: 'unique_emails', label: 'Unique Emails', endpoint: 'unique-emails', responseKey: 'unique_emails', columns: uniqueEmailColumns },
];

// ---------------------------------------------------------------------------
// Reusable QB Table Tab component
// ---------------------------------------------------------------------------

const QBTableTab: React.FC<{
  config: TableConfig;
  clientId: string;
  tableLogs: Record<string, { synced_at: string | null; status: string }>;
  onSync: (tableKey: string, full: boolean) => void;
  syncing: boolean;
}> = ({ config, clientId, tableLogs, onSync, syncing }) => {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [sortBy, setSortBy] = useState<string | undefined>();
  const [sortDir, setSortDir] = useState<string | undefined>();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce search
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => { setDebouncedSearch(search); setPage(1); }, 400);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [search]);

  const query = useQBTable({
    clientId,
    endpoint: config.endpoint,
    responseKey: config.responseKey,
    page,
    pageSize: PAGE_SIZE,
    search: debouncedSearch || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
  });

  const handleTableChange = (_pagination: any, _filters: any, sorter: any) => {
    if (sorter?.columnKey) {
      setSortBy(sorter.columnKey);
      setSortDir(sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined);
      setPage(1);
    } else {
      setSortBy(undefined);
      setSortDir(undefined);
    }
  };

  const log = tableLogs[config.key];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <Search
          placeholder={`Search ${config.label.toLowerCase()}...`}
          allowClear
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 280 }}
          size="small"
        />
        <Space wrap>
          {log?.synced_at && (
            <Tooltip title={`Status: ${log.status}`}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                Last sync: {new Date(log.synced_at).toLocaleString()}
              </Text>
            </Tooltip>
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>{(query.data?.total || 0).toLocaleString()} records</Text>
          <Dropdown.Button
            size="small"
            icon={<DownOutlined />}
            loading={syncing}
            onClick={() => onSync(config.key, false)}
            menu={{ items: [{ key: 'full', label: 'Full Sync (re-fetch all)', onClick: () => onSync(config.key, true) }] }}
          >
            <SyncOutlined spin={syncing} /> Sync
          </Dropdown.Button>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => query.refetch()}>Refresh</Button>
        </Space>
      </div>
      <Table
        dataSource={query.data?.items || []}
        columns={config.columns}
        rowKey={(r) => r.id || r.qb_record_id || Math.random()}
        size="small"
        loading={query.isLoading}
        scroll={{ x: 'max-content' }}
        onChange={handleTableChange}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total: query.data?.total || 0,
          onChange: p => setPage(p),
          showSizeChanger: false,
          showTotal: (total, range) => `${range[0]}-${range[1]} of ${total.toLocaleString()}`,
          size: 'small',
        }}
      />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

const QuickbaseDataPage: React.FC = () => {
  const [clientId, setClientId] = useState<string | null>(() => localStorage.getItem('analytics_client_id'));
  const [activeTab, setActiveTab] = useState('customers');
  const [qbSyncing, setQbSyncing] = useState(false);
  const [tableSyncing, setTableSyncing] = useState<Record<string, boolean>>({});

  // Resolve clientId on mount
  useEffect(() => {
    (async () => {
      try {
        const stored = localStorage.getItem('analytics_client_id');
        if (stored) { setClientId(stored); return; }
        const assigned = await api.get<any>('/auth/me/clients');
        const fromAssigned = Array.isArray(assigned) ? assigned[0]?.client_id : null;
        if (fromAssigned) { setClientId(fromAssigned); return; }
        const all = await api.get<any>('/clients/');
        setClientId(all?.clients?.[0]?.id || null);
      } catch { /* ignore */ }
    })();
  }, []);

  // Sync status via TanStack Query
  const syncStatusQuery = useQBSyncStatus(clientId);
  const syncStatus = syncStatusQuery.data;
  const lastSyncAt = syncStatus?.last_sync_at;
  const recordCounts: Record<string, number> = syncStatus?.record_counts || {};
  const tableLogs = useMemo(() => {
    const logs: Record<string, { synced_at: string | null; status: string }> = {};
    for (const log of (syncStatus?.table_logs || [])) {
      logs[log.table_name] = { synced_at: log.synced_at, status: log.status };
    }
    return logs;
  }, [syncStatus]);

  const scheduleRefresh = () => {
    setTimeout(() => syncStatusQuery.refetch(), 5000);
    setTimeout(() => syncStatusQuery.refetch(), 15000);
    setTimeout(() => syncStatusQuery.refetch(), 30000);
  };

  const handleQBSync = async (full = false) => {
    if (!clientId) return;
    setQbSyncing(true);
    try {
      const params = full ? `client_id=${clientId}&full=true` : `client_id=${clientId}`;
      await api.post<any>(`/v1/quickbase/sync?${params}`);
      message.success(full ? 'Full sync started' : 'Sync started');
      scheduleRefresh();
    } catch (err: any) {
      message.error(err?.message || 'Sync failed');
    } finally {
      setQbSyncing(false);
    }
  };

  const handleTableSync = async (tableKey: string, full: boolean) => {
    if (!clientId) return;
    setTableSyncing(prev => ({ ...prev, [tableKey]: true }));
    try {
      const params = new URLSearchParams({ client_id: clientId, tables: tableKey });
      if (full) params.set('full', 'true');
      await api.post<any>(`/v1/quickbase/sync?${params}`);
      message.success(`${full ? 'Full' : 'Incremental'} sync started for ${tableKey}`);
      scheduleRefresh();
    } catch (err: any) {
      message.error(err?.message || `Sync failed for ${tableKey}`);
    }
    setTimeout(() => setTableSyncing(prev => ({ ...prev, [tableKey]: false })), 2000);
  };

  if (!clientId) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    );
  }

  const tabItems = TABLE_CONFIGS.map(config => ({
    key: config.key,
    label: (
      <span>
        {config.label}{' '}
        <Badge count={recordCounts[config.key] || 0} overflowCount={999999} color="#667eea" />
      </span>
    ),
    children: (
      <QBTableTab
        config={config}
        clientId={clientId}
        tableLogs={tableLogs}
        onSync={handleTableSync}
        syncing={!!tableSyncing[config.key]}
      />
    ),
  }));

  return (
    <div style={{ padding: '24px', maxWidth: 1600, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>Quickbase Synced Data</Title>
        <Space>
          {lastSyncAt && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              Last sync: {new Date(lastSyncAt).toLocaleString()}
            </Text>
          )}
          <Dropdown.Button
            type="primary"
            icon={<DownOutlined />}
            loading={qbSyncing}
            onClick={() => handleQBSync(false)}
            menu={{ items: [{ key: 'full', label: 'Full Sync (re-fetch all)', onClick: () => handleQBSync(true) }] }}
          >
            <SyncOutlined spin={qbSyncing} /> Sync
          </Dropdown.Button>
        </Space>
      </div>

      {/* Summary row */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {TABLE_CONFIGS.map(config => {
          const log = tableLogs[config.key];
          const count = recordCounts[config.key] || 0;
          return (
            <Col key={config.key} xs={12} sm={8} md={4}>
              <Card className="glass-card" size="small">
                <Statistic title={config.label} value={count} />
                {log?.synced_at ? (
                  <Text type="secondary" style={{ fontSize: 10 }}>{new Date(log.synced_at).toLocaleString()}</Text>
                ) : count > 0 ? (
                  <Text type="secondary" style={{ fontSize: 10, opacity: 0.5 }}>Sync log unavailable</Text>
                ) : (
                  <Text type="secondary" style={{ fontSize: 10, opacity: 0.5 }}>Not synced</Text>
                )}
              </Card>
            </Col>
          );
        })}
      </Row>

      <Card className="glass-card">
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} type="line" />
      </Card>
    </div>
  );
};

export default QuickbaseDataPage;
