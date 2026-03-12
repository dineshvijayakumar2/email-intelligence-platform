/**
 * Quickbase Data Views — Browse synced QB cache tables.
 * Customers, Contacts, Quotes, Jobs, Sales Line Items.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Tabs, Table, Input, Button, Tag, Space, Typography, Statistic,
  Row, Col, Spin, Badge, Tooltip, message,
} from 'antd';
import {
  ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
} from '@ant-design/icons';
import api from '../../services/apiClient';

const { Title, Text } = Typography;
const { Search } = Input;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PageState {
  data: any[];
  total: number;
  loading: boolean;
  page: number;
  search: string;
}

const PAGE_SIZE = 50;

function emptyPage(): PageState {
  return { data: [], total: 0, loading: false, page: 1, search: '' };
}

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

const customerColumns = [
  { title: 'Name', dataIndex: 'customer_name', key: 'customer_name', width: 200, ellipsis: true },
  { title: 'Code', dataIndex: 'customer_code', key: 'customer_code', width: 90 },
  { title: 'Tier', dataIndex: 'customer_tier', key: 'customer_tier', width: 80,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Status', dataIndex: 'customer_status', key: 'customer_status', width: 100,
    render: (v: string) => v ? <Tag color={v === 'Active' ? 'green' : 'default'}>{v}</Tag> : '-' },
  { title: 'Account Manager', dataIndex: 'account_manager', key: 'account_manager', width: 160, ellipsis: true },
  { title: 'Industry', dataIndex: 'industry', key: 'industry', width: 140, ellipsis: true },
  { title: 'Total Invoiced', dataIndex: 'total_invoiced', key: 'total_invoiced', width: 130, align: 'right' as const,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'TY', dataIndex: 'invoiced_ty', key: 'invoiced_ty', width: 110, align: 'right' as const,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'LY', dataIndex: 'invoiced_ly', key: 'invoiced_ly', width: 110, align: 'right' as const,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Days Since Invoice', dataIndex: 'days_since_last_invoice', key: 'days_since_last_invoice', width: 130, align: 'right' as const,
    render: (v: number) => v != null ? <Text type={v > 180 ? 'danger' : v > 90 ? 'warning' : undefined}>{v}d</Text> : '-' },
  { title: 'Matched', dataIndex: 'matched_company_name', key: 'matched', width: 160, ellipsis: true,
    render: (v: string) => v
      ? <Tooltip title={v}><CheckCircleOutlined style={{ color: '#52c41a' }} /> {v}</Tooltip>
      : <Text type="secondary"><CloseCircleOutlined /> unmatched</Text> },
];

const contactColumns = [
  { title: 'First Name', dataIndex: 'first_name', key: 'first_name', width: 130 },
  { title: 'Surname', dataIndex: 'surname', key: 'surname', width: 140 },
  { title: 'Email', dataIndex: 'email', key: 'email', width: 220, ellipsis: true },
  { title: 'Phone', dataIndex: 'phone', key: 'phone', width: 140 },
  { title: 'Active', dataIndex: 'active', key: 'active', width: 70,
    render: (v: any) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#bbb' }} /> },
  { title: 'Recency (days)', dataIndex: 'contact_recency_days', key: 'contact_recency_days', width: 130, align: 'right' as const,
    render: (v: number) => v != null ? `${v}d` : '-' },
  { title: 'Quotes Accepted', dataIndex: 'quotes_accepted_count', key: 'quotes_accepted_count', width: 130, align: 'right' as const },
  { title: 'Last Quote', dataIndex: 'most_recent_quote_date', key: 'most_recent_quote_date', width: 130,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Matched', dataIndex: 'matched_contact_id', key: 'matched', width: 80,
    render: (v: string) => v
      ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
      : <Text type="secondary"><CloseCircleOutlined /></Text> },
];

const quoteColumns = [
  { title: 'Quote No', dataIndex: 'quote_no', key: 'quote_no', width: 110 },
  { title: 'Contact', dataIndex: 'contact_name', key: 'contact_name', width: 160, ellipsis: true },
  { title: 'Email', dataIndex: 'contact_email', key: 'contact_email', width: 200, ellipsis: true },
  { title: 'AM', dataIndex: 'quote_am_name', key: 'quote_am_name', width: 140, ellipsis: true },
  { title: 'Category', dataIndex: 'category', key: 'category', width: 120,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Sell (ex tax)', dataIndex: 'sell_ex_tax', key: 'sell_ex_tax', width: 120, align: 'right' as const,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Created', dataIndex: 'date_created', key: 'date_created', width: 110,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Accepted', dataIndex: 'date_accepted', key: 'date_accepted', width: 110,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Has Job', dataIndex: 'has_job', key: 'has_job', width: 80,
    render: (v: any) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : '-' },
  { title: 'Qty', dataIndex: 'total_quantity', key: 'total_quantity', width: 80, align: 'right' as const },
];

const jobColumns = [
  { title: 'Job No', dataIndex: 'job_no', key: 'job_no', width: 100 },
  { title: 'Quote No', dataIndex: 'quote_no', key: 'quote_no', width: 100 },
  { title: 'Status', dataIndex: 'job_status', key: 'job_status', width: 120,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Retail Sale', dataIndex: 'retail_sale', key: 'retail_sale', width: 120, align: 'right' as const,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Margin', dataIndex: 'invoiced_margin', key: 'invoiced_margin', width: 110, align: 'right' as const,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Margin %', dataIndex: 'margin_pct', key: 'margin_pct', width: 100, align: 'right' as const,
    render: (v: number) => v != null ? `${Number(v).toFixed(1)}%` : '-' },
  { title: 'Accepted', dataIndex: 'accepted_date', key: 'accepted_date', width: 110,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Due', dataIndex: 'due_date', key: 'due_date', width: 110,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Pieces', dataIndex: 'pieces_ordered', key: 'pieces_ordered', width: 80, align: 'right' as const },
  { title: 'Kinds', dataIndex: 'kinds_ordered', key: 'kinds_ordered', width: 80, align: 'right' as const },
];

const sliColumns = [
  { title: 'Invoice No', dataIndex: 'invoice_no', key: 'invoice_no', width: 110 },
  { title: 'Invoice ID', dataIndex: 'invoice_id', key: 'invoice_id', width: 100 },
  { title: 'Customer', dataIndex: 'customer_name', key: 'customer_name', width: 200, ellipsis: true },
  { title: 'Job No', dataIndex: 'job_no', key: 'job_no', width: 100 },
  { title: 'Job Title', dataIndex: 'job_title', key: 'job_title', width: 160, ellipsis: true },
  { title: 'AM', dataIndex: 'job_am_name', key: 'job_am_name', width: 140, ellipsis: true },
  { title: 'Product Group', dataIndex: 'product_group', key: 'product_group', width: 130,
    render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
  { title: 'Industry', dataIndex: 'industry', key: 'industry', width: 130, ellipsis: true },
  { title: 'Subtotal', dataIndex: 'subtotal', key: 'subtotal', width: 110, align: 'right' as const,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Total', dataIndex: 'total', key: 'total', width: 110, align: 'right' as const,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Date', dataIndex: 'inv_date', key: 'inv_date', width: 110,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
];

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

const QuickbaseDataPage: React.FC = () => {
  const [clientId, setClientId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('customers');
  const [qbSyncing, setQbSyncing] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);
  const [customers, setCustomers] = useState<PageState>(emptyPage());
  const [contacts, setContacts] = useState<PageState>(emptyPage());
  const [quotes, setQuotes] = useState<PageState>(emptyPage());
  const [jobs, setJobs] = useState<PageState>(emptyPage());
  const [sli, setSli] = useState<PageState>(emptyPage());
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;
    return () => { isMounted.current = false; };
  }, []);

  // Resolve clientId on mount
  useEffect(() => {
    (async () => {
      try {
        // 1. localStorage (set by ClientSelector on analytics pages)
        const stored = localStorage.getItem('analytics_client_id');
        if (stored) { setClientId(stored); return; }

        // 2. Assigned clients (client_manager role)
        const assigned = await api.get<any>('/auth/me/clients');
        const fromAssigned = Array.isArray(assigned) ? assigned[0]?.client_id : null;
        if (fromAssigned) { setClientId(fromAssigned); return; }

        // 3. Admin fallback
        const all = await api.get<any>('/clients/');
        setClientId(all?.clients?.[0]?.id || null);
      } catch { /* ignore */ }
    })();
  }, []);

  // Load last sync time
  useEffect(() => {
    if (!clientId) return;
    api.get<any>(`/v1/quickbase/sync-status?client_id=${clientId}`)
      .then(s => setLastSyncAt(s?.last_sync_at || null))
      .catch(() => {});
  }, [clientId]);

  const handleQBSync = async () => {
    if (!clientId) return;
    setQbSyncing(true);
    try {
      await api.post<any>(`/v1/quickbase/sync?client_id=${clientId}`);
      message.success('Quickbase sync started — data will update shortly');
      setTimeout(async () => {
        const s = await api.get<any>(`/v1/quickbase/sync-status?client_id=${clientId}`);
        setLastSyncAt(s?.last_sync_at || null);
      }, 3000);
    } catch (err: any) {
      message.error(err?.message || 'Sync failed');
    } finally {
      setQbSyncing(false);
    }
  };

  // Generic fetch helper
  const fetchTable = useCallback(async (
    tableKey: string,
    setter: React.Dispatch<React.SetStateAction<PageState>>,
    endpoint: string,
    responseKey: string,
    page: number,
    search: string,
    cid: string,
  ) => {
    setter(prev => ({ ...prev, loading: true }));
    const offset = (page - 1) * PAGE_SIZE;
    const params = new URLSearchParams({
      client_id: cid,
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (search) params.set('search', search);
    try {
      const resp = await api.get<any>(`/v1/quickbase/${endpoint}?${params}`);
      if (!isMounted.current) return;
      setter({ data: resp[responseKey] || [], total: resp.total || 0, loading: false, page, search });
    } catch (err: any) {
      if (!isMounted.current) return;
      message.error(`Failed to load ${tableKey}: ${err?.message || 'error'}`);
      setter(prev => ({ ...prev, loading: false }));
    }
  }, []);

  // Load the active tab when clientId is ready or tab changes
  useEffect(() => {
    if (!clientId) return;
    const load = (tab: string) => {
      switch (tab) {
        case 'customers': fetchTable('customers', setCustomers, 'customers', 'customers', 1, '', clientId); break;
        case 'contacts': fetchTable('contacts', setContacts, 'contacts', 'contacts', 1, '', clientId); break;
        case 'quotes': fetchTable('quotes', setQuotes, 'quotes', 'quotes', 1, '', clientId); break;
        case 'jobs': fetchTable('jobs', setJobs, 'jobs', 'jobs', 1, '', clientId); break;
        case 'sales_line_items': fetchTable('sli', setSli, 'sales-line-items', 'sales_line_items', 1, '', clientId); break;
      }
    };
    load(activeTab);
  }, [clientId, activeTab, fetchTable]);

  const makeTabContent = (
    state: PageState,
    setter: React.Dispatch<React.SetStateAction<PageState>>,
    endpoint: string,
    responseKey: string,
    columns: any[],
    tableKey: string,
  ) => {
    const handleSearch = (val: string) => {
      if (!clientId) return;
      fetchTable(tableKey, setter, endpoint, responseKey, 1, val, clientId);
    };
    const handlePageChange = (page: number) => {
      if (!clientId) return;
      fetchTable(tableKey, setter, endpoint, responseKey, page, state.search, clientId);
    };
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Search
            placeholder="Search..."
            allowClear
            style={{ width: 280 }}
            onSearch={handleSearch}
          />
          <Space>
            <Text type="secondary">{state.total.toLocaleString()} records</Text>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => clientId && fetchTable(tableKey, setter, endpoint, responseKey, state.page, state.search, clientId)}
            >
              Refresh
            </Button>
          </Space>
        </div>
        <Table
          dataSource={state.data}
          columns={columns}
          rowKey={(r) => r.id || r.qb_record_id || Math.random()}
          size="small"
          loading={state.loading}
          scroll={{ x: 'max-content' }}
          pagination={{
            current: state.page,
            pageSize: PAGE_SIZE,
            total: state.total,
            onChange: handlePageChange,
            showSizeChanger: false,
            showTotal: (total) => `${total} records`,
            size: 'small',
          }}
        />
      </div>
    );
  };

  if (!clientId) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    );
  }

  const tabItems = [
    {
      key: 'customers',
      label: <span>Customers <Badge count={customers.total} overflowCount={99999} color="#667eea" /></span>,
      children: makeTabContent(customers, setCustomers, 'customers', 'customers', customerColumns, 'customers'),
    },
    {
      key: 'contacts',
      label: <span>Contacts <Badge count={contacts.total} overflowCount={99999} color="#667eea" /></span>,
      children: makeTabContent(contacts, setContacts, 'contacts', 'contacts', contactColumns, 'contacts'),
    },
    {
      key: 'quotes',
      label: <span>Quotes <Badge count={quotes.total} overflowCount={99999} color="#667eea" /></span>,
      children: makeTabContent(quotes, setQuotes, 'quotes', 'quotes', quoteColumns, 'quotes'),
    },
    {
      key: 'jobs',
      label: <span>Jobs <Badge count={jobs.total} overflowCount={99999} color="#667eea" /></span>,
      children: makeTabContent(jobs, setJobs, 'jobs', 'jobs', jobColumns, 'jobs'),
    },
    {
      key: 'sales_line_items',
      label: <span>Sales Line Items <Badge count={sli.total} overflowCount={99999} color="#667eea" /></span>,
      children: makeTabContent(sli, setSli, 'sales-line-items', 'sales_line_items', sliColumns, 'sales_line_items'),
    },
  ];

  // Summary stats
  const syncedCounts = [
    { label: 'Customers', value: customers.total },
    { label: 'Contacts', value: contacts.total },
    { label: 'Quotes', value: quotes.total },
    { label: 'Jobs', value: jobs.total },
    { label: 'Sales Line Items', value: sli.total },
  ];

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
          <Button
            type="primary"
            icon={<SyncOutlined spin={qbSyncing} />}
            loading={qbSyncing}
            onClick={handleQBSync}
          >
            Sync Now
          </Button>
        </Space>
      </div>

      {/* Summary row */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {syncedCounts.map(s => (
          <Col key={s.label} xs={12} sm={8} md={4}>
            <Card className="glass-card" size="small">
              <Statistic title={s.label} value={s.value} />
            </Card>
          </Col>
        ))}
      </Row>

      <Card className="glass-card">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          type="line"
        />
      </Card>
    </div>
  );
};

export default QuickbaseDataPage;
