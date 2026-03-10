import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Table, Typography, Tag, Input, Select, DatePicker, Button, Row, Col,
  Card, Statistic, Space, Tooltip, message, Dropdown,
} from 'antd';
import {
  SearchOutlined, ReloadOutlined, DownloadOutlined, FileTextOutlined,
  UserOutlined, ClockCircleOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import dayjs from 'dayjs';
import api from '../services/apiClient';
import { formatDateTime } from '../utils/dateUtils';

const { Text } = Typography;
const { RangePicker } = DatePicker;

// Types
interface AuditLogEntry {
  id: string;
  user_id: string | null;
  user_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

interface AuditLogResponse {
  data: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
}

interface AuditLogStats {
  total_entries: number;
  actions: { name: string; count: number }[];
  resource_types: { name: string; count: number }[];
  active_users: { email: string; count: number }[];
}

// Action → color/label mapping
const ACTION_COLORS: Record<string, string> = {
  login: 'blue',
  settings_change: 'cyan',
  role_change: 'gold',
  user_activate: 'green',
  user_deactivate: 'red',
  mailbox_create: 'green',
  mailbox_delete: 'red',
  sync: 'geekblue',
  analyze: 'purple',
  extract: 'volcano',
  digest_generate: 'magenta',
  client_assign: 'orange',
  client_unassign: 'orange',
  user_invite: 'lime',
};

const RESOURCE_COLORS: Record<string, string> = {
  mailbox: 'blue',
  user: 'gold',
  settings: 'cyan',
  ai_analysis: 'purple',
  extraction_job: 'volcano',
  client: 'orange',
  digest: 'magenta',
};

const AuditLogsPage: React.FC = () => {
  const isMountedRef = useRef(true);
  const [data, setData] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Filters
  const [actionFilter, setActionFilter] = useState<string | undefined>();
  const [resourceFilter, setResourceFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);

  // Stats
  const [stats, setStats] = useState<AuditLogStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { page, page_size: pageSize };
      if (actionFilter) params.action = actionFilter;
      if (resourceFilter) params.resource_type = resourceFilter;
      if (searchText) params.search = searchText;
      if (dateRange?.[0]) params.date_from = dateRange[0].format('YYYY-MM-DD');
      if (dateRange?.[1]) params.date_to = dateRange[1].format('YYYY-MM-DD');

      const qs = new URLSearchParams(
        Object.entries(params).map(([k, v]) => [k, String(v)])
      ).toString();

      const result = await api.get<AuditLogResponse>(`/auth/audit-logs?${qs}`);
      if (isMountedRef.current) {
        setData(result.data);
        setTotal(result.total);
      }
    } catch {
      // silent
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [page, pageSize, actionFilter, resourceFilter, searchText, dateRange]);

  const fetchStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const result = await api.get<AuditLogStats>('/auth/audit-logs/stats?days=30');
      if (isMountedRef.current) setStats(result);
    } catch {
      // silent
    } finally {
      if (isMountedRef.current) setStatsLoading(false);
    }
  }, []);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  // Derive filter options from stats
  const actionOptions = useMemo(() =>
    (stats?.actions || []).map(a => ({ value: a.name, label: `${a.name.replace(/_/g, ' ')} (${a.count})` })),
    [stats]
  );
  const resourceOptions = useMemo(() =>
    (stats?.resource_types || []).map(r => ({ value: r.name, label: `${r.name.replace(/_/g, ' ')} (${r.count})` })),
    [stats]
  );

  // Export helpers
  const exportData = useCallback((format: 'csv' | 'json') => {
    if (!data.length) { message.warning('No data to export'); return; }

    if (format === 'json') {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_logs_${new Date().toISOString().split('T')[0]}.json`;
      a.click();
      URL.revokeObjectURL(url);
      message.success(`Exported ${data.length} entries as JSON`);
      return;
    }

    // CSV
    const cols = ['created_at', 'action', 'resource_type', 'resource_id', 'user_email', 'details', 'ip_address'];
    const header = cols.join(',');
    const rows = data.map(row =>
      cols.map(col => {
        const val = row[col as keyof AuditLogEntry];
        if (val === null || val === undefined) return '';
        const str = typeof val === 'object' ? JSON.stringify(val) : String(val);
        if (str.includes(',') || str.includes('"') || str.includes('\n')) {
          return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
      }).join(',')
    );
    const csv = [header, ...rows].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit_logs_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    message.success(`Exported ${data.length} entries as CSV`);
  }, [data]);

  const columns: ColumnsType<AuditLogEntry> = [
    {
      title: 'Time', dataIndex: 'created_at', key: 'time', width: 180,
      render: (v: string) => (
        <Tooltip title={v}>
          <Text style={{ fontSize: 12 }}>{formatDateTime(v)}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Action', dataIndex: 'action', key: 'action', width: 150,
      render: (v: string) => <Tag color={ACTION_COLORS[v] || 'default'}>{v.replace(/_/g, ' ')}</Tag>,
    },
    {
      title: 'Resource', dataIndex: 'resource_type', key: 'resource_type', width: 130,
      render: (v: string) => <Tag color={RESOURCE_COLORS[v] || 'default'}>{v.replace(/_/g, ' ')}</Tag>,
    },
    {
      title: 'Resource ID', dataIndex: 'resource_id', key: 'resource_id', width: 160, ellipsis: true,
      render: (v: string | null) => v ? <Text copyable style={{ fontSize: 12 }}>{v.slice(0, 12)}...</Text> : '—',
    },
    {
      title: 'User', dataIndex: 'user_email', key: 'user_email', width: 200, ellipsis: true,
      render: (v: string | null) => v || <Text type="secondary">system</Text>,
    },
    {
      title: 'Details', dataIndex: 'details', key: 'details', ellipsis: true,
      render: (v: Record<string, unknown> | null) =>
        v && Object.keys(v).length > 0
          ? <Tooltip title={<pre style={{ margin: 0, fontSize: 11, maxHeight: 300, overflow: 'auto' }}>{JSON.stringify(v, null, 2)}</pre>}>
              <Text style={{ fontSize: 12 }}>{JSON.stringify(v).slice(0, 80)}{JSON.stringify(v).length > 80 ? '...' : ''}</Text>
            </Tooltip>
          : '—',
    },
  ];

  const handleTableChange = (pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1);
    setPageSize(pagination.pageSize || 50);
  };

  const handleReset = () => {
    setActionFilter(undefined);
    setResourceFilter(undefined);
    setSearchText('');
    setDateRange(null);
    setPage(1);
  };

  const exportMenuItems = [
    { key: 'csv', icon: <FileTextOutlined />, label: 'Export as CSV', onClick: () => exportData('csv') },
    { key: 'json', icon: <FileTextOutlined />, label: 'Export as JSON', onClick: () => exportData('json') },
  ];

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Summary Stats */}
      <Row gutter={[16, 16]} className="fade-in-up">
        <Col xs={12} sm={6}>
          <Card size="small" className="glass-card">
            <Statistic
              title="Total (30d)"
              value={stats?.total_entries ?? 0}
              prefix={<ClockCircleOutlined />}
              loading={statsLoading}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className="glass-card">
            <Statistic
              title="Action Types"
              value={stats?.actions?.length ?? 0}
              prefix={<ThunderboltOutlined />}
              loading={statsLoading}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className="glass-card">
            <Statistic
              title="Resource Types"
              value={stats?.resource_types?.length ?? 0}
              prefix={<FileTextOutlined />}
              loading={statsLoading}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className="glass-card">
            <Statistic
              title="Active Users"
              value={stats?.active_users?.length ?? 0}
              prefix={<UserOutlined />}
              loading={statsLoading}
            />
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <div className="glass-card fade-in-up stagger-1" style={{ padding: 16, marginTop: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} sm={6}>
            <Input
              placeholder="Search..."
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={e => { setSearchText(e.target.value); setPage(1); }}
              allowClear
            />
          </Col>
          <Col xs={12} sm={4}>
            <Select
              placeholder="Action"
              value={actionFilter}
              onChange={v => { setActionFilter(v); setPage(1); }}
              options={actionOptions}
              allowClear
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} sm={4}>
            <Select
              placeholder="Resource"
              value={resourceFilter}
              onChange={v => { setResourceFilter(v); setPage(1); }}
              options={resourceOptions}
              allowClear
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={24} sm={6}>
            <RangePicker
              value={dateRange as [dayjs.Dayjs, dayjs.Dayjs] | null}
              onChange={(dates) => { setDateRange(dates as [dayjs.Dayjs | null, dayjs.Dayjs | null] | null); setPage(1); }}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={24} sm={4}>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => { fetchLogs(); fetchStats(); }}>
                Refresh
              </Button>
              <Button onClick={handleReset}>Reset</Button>
              <Dropdown menu={{ items: exportMenuItems }} placement="bottomRight">
                <Button icon={<DownloadOutlined />}>Export</Button>
              </Dropdown>
            </Space>
          </Col>
        </Row>
      </div>

      {/* Table */}
      <div className="glass-table-container fade-in-up stagger-2" style={{ padding: 16, marginTop: 16 }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          size="small"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: ['25', '50', '100', '200'],
            showTotal: (t, range) => `${range[0]}-${range[1]} of ${t}`,
          }}
          onChange={handleTableChange}
          scroll={{ x: 1000 }}
        />
      </div>

      {/* Top users sidebar */}
      {stats && stats.active_users.length > 0 && (
        <div className="glass-card fade-in-up stagger-3" style={{ padding: 16, marginTop: 16 }}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>Most Active Users (30d)</Text>
          <Space wrap>
            {stats.active_users.map(u => (
              <Tag key={u.email} icon={<UserOutlined />} color="blue" style={{ cursor: 'pointer' }}
                onClick={() => { setSearchText(u.email); setPage(1); }}>
                {u.email.split('@')[0]} ({u.count})
              </Tag>
            ))}
          </Space>
        </div>
      )}
    </div>
  );
};

export default AuditLogsPage;
