/**
 * Admin Data View Page
 *
 * Raw table browser for admins to inspect Supabase data.
 * Features: table selector, global search, column sorting,
 * server-side pagination, and CSV export.
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Table, Card, Select, Input, Button, Space, Typography, Tag,
  message, Empty, Tooltip,
} from 'antd';
import type { TableProps } from 'antd';
import {
  DatabaseOutlined, SearchOutlined, ReloadOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import { adminService, TableInfo, TableDataResponse } from '../services/adminService';

const { Title, Text } = Typography;

const PAGE_SIZE_OPTIONS = [25, 50, 100, 250];

const AdminDataViewPage: React.FC = () => {
  // NOTE: No isAdmin guard here — AdminRoute wrapper already handles auth/role check.
  // Adding one here would cause component unmount/remount during auth refreshes,
  // destroying all state.

  // Table list state
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [tablesLoading, setTablesLoading] = useState(true);

  // Selected table state
  const [selectedTable, setSelectedTable] = useState<string>('');
  const [tableData, setTableData] = useState<TableDataResponse | null>(null);
  const [loading, setLoading] = useState(false);

  // Query params
  const [searchText, setSearchText] = useState('');
  const [pageSize, setPageSize] = useState(50);
  const [currentPage, setCurrentPage] = useState(1);
  const [sortBy, setSortBy] = useState('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Refresh trigger (increment to force data reload)
  const [refreshKey, setRefreshKey] = useState(0);

  // Refs for debounce and preventing stale updates
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchIdRef = useRef(0);

  // Load table list on mount
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setTablesLoading(true);
      try {
        const result = await adminService.listTables();
        if (!cancelled && result?.tables?.length > 0) {
          setTables(result.tables);
        }
      } catch (err: any) {
        if (!cancelled) {
          console.error('[AdminDataView] Failed to load tables:', err);
          message.error(err?.message || 'Failed to load table list');
        }
      } finally {
        if (!cancelled) setTablesLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  // Load table data when params change (debounced search via separate effect)
  useEffect(() => {
    if (!selectedTable) return;

    const thisId = ++fetchIdRef.current;
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      try {
        const result = await adminService.getTableData(selectedTable, {
          search: searchText || undefined,
          sort_by: sortBy || undefined,
          sort_dir: sortDir,
          limit: pageSize,
          offset: (currentPage - 1) * pageSize,
        });
        if (!cancelled && fetchIdRef.current === thisId) {
          setTableData(result);
        }
      } catch (error: any) {
        if (!cancelled) message.error(error?.message || 'Failed to load table data');
      } finally {
        if (!cancelled && fetchIdRef.current === thisId) setLoading(false);
      }
    };

    // Debounce only when searchText changes; load immediately for other params
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(load, searchText ? 400 : 0);

    return () => {
      cancelled = true;
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTable, searchText, sortBy, sortDir, pageSize, currentPage, refreshKey]);

  // Handle table selection change
  const handleTableSelect = (tableName: string) => {
    setSelectedTable(tableName);
    setSearchText('');
    setCurrentPage(1);
    setSortBy('');
    setSortDir('desc');
    setTableData(null);
  };

  // Handle Ant Design Table sort change
  const handleTableChange: TableProps<Record<string, any>>['onChange'] = (
    _pagination, _filters, sorter
  ) => {
    if (!Array.isArray(sorter) && sorter.field) {
      setSortBy(String(sorter.field));
      setSortDir(sorter.order === 'ascend' ? 'asc' : 'desc');
      setCurrentPage(1);
    }
  };

  // Refresh handler
  const handleRefresh = async () => {
    setTablesLoading(true);
    try {
      const result = await adminService.listTables();
      if (result?.tables?.length > 0) setTables(result.tables);
    } catch (err: any) {
      console.error('[AdminDataView] Failed to refresh tables:', err);
      message.error(err?.message || 'Failed to refresh table list');
    } finally {
      setTablesLoading(false);
    }
    // Trigger data reload
    if (selectedTable) {
      setRefreshKey((k) => k + 1);
    }
  };

  // Generate columns dynamically from response
  const columns = useMemo(() => {
    if (!tableData?.columns?.length) return [];
    return tableData.columns.map((col) => ({
      title: col
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (c: string) => c.toUpperCase()),
      dataIndex: col,
      key: col,
      sorter: true,
      sortOrder:
        sortBy === col
          ? sortDir === 'asc'
            ? ('ascend' as const)
            : ('descend' as const)
          : undefined,
      ellipsis: true,
      width:
        col === 'id' ? 290
        : col.includes('_at') || col.includes('date') ? 185
        : col === 'email_address' || col === 'sender_email' ? 220
        : col === 'subject' ? 280
        : 160,
      render: (value: any) => {
        if (value === null || value === undefined) {
          return <Text type="secondary" style={{ fontStyle: 'italic', fontSize: 12 }}>null</Text>;
        }
        if (typeof value === 'boolean') {
          return <Tag color={value ? 'green' : 'default'}>{String(value)}</Tag>;
        }
        if (Array.isArray(value) || typeof value === 'object') {
          const str = JSON.stringify(value);
          return str.length > 80
            ? <Tooltip title={str}><Text code style={{ fontSize: 11 }}>{str.substring(0, 80)}...</Text></Tooltip>
            : <Text code style={{ fontSize: 11 }}>{str}</Text>;
        }
        const str = String(value);
        if (str.length > 100) {
          return <Tooltip title={str}>{str.substring(0, 100)}...</Tooltip>;
        }
        return str;
      },
    }));
  }, [tableData?.columns, sortBy, sortDir]);

  // CSV Export
  const handleExportCSV = () => {
    if (!tableData?.data?.length || !tableData?.columns?.length) {
      message.warning('No data to export');
      return;
    }

    const header = tableData.columns.join(',');
    const rows = tableData.data.map((row) =>
      tableData.columns
        .map((col) => {
          const val = row[col];
          if (val === null || val === undefined) return '';
          const str = typeof val === 'object' ? JSON.stringify(val) : String(val);
          if (str.includes(',') || str.includes('"') || str.includes('\n')) {
            return `"${str.replace(/"/g, '""')}"`;
          }
          return str;
        })
        .join(',')
    );

    const csv = [header, ...rows].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${selectedTable}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    message.success(`Exported ${tableData.data.length} rows to CSV`);
  };

  // Selected table info
  const selectedTableInfo = tables.find((t) => t.table_name === selectedTable);

  // Memoize select options to prevent unnecessary re-renders
  const selectOptions = useMemo(() =>
    tables.map((t) => ({
      value: t.table_name,
      label: `${t.display_name} (${t.row_count >= 0 ? t.row_count.toLocaleString() : '?'} rows)`,
    })),
    [tables]
  );

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Page Header */}
      <div style={{ marginBottom: 24 }}>
        <Title level={3} className="gradient-text" style={{ margin: 0 }}>
          <DatabaseOutlined style={{ marginRight: 8 }} />
          Admin Data View
        </Title>
        <Text type="secondary">
          Browse raw database tables &mdash; {tables.length} tables available
        </Text>
      </div>

      {/* Controls Card */}
      <Card className="glass-card-static" style={{ marginBottom: 24 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <Space wrap size="middle">
            {/* Table selector */}
            <Select
              style={{ width: 340 }}
              placeholder="Select a table..."
              value={selectedTable || undefined}
              onChange={handleTableSelect}
              loading={tablesLoading}
              showSearch
              optionFilterProp="label"
              options={selectOptions}
            />

            {/* Global search */}
            <Input
              placeholder={
                selectedTableInfo?.searchable
                  ? 'Search...'
                  : 'Search not available for this table'
              }
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => { setSearchText(e.target.value); setCurrentPage(1); }}
              style={{ width: 260 }}
              allowClear
              disabled={!selectedTable || !selectedTableInfo?.searchable}
            />
          </Space>

          <Space>
            <Button
              icon={<DownloadOutlined />}
              onClick={handleExportCSV}
              disabled={!tableData?.data?.length}
            >
              Export CSV
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefresh}
              loading={loading || tablesLoading}
            >
              Refresh
            </Button>
          </Space>
        </div>

        {/* Active filters summary */}
        {selectedTable && (
          <div style={{ marginTop: 12 }}>
            <Space size="small">
              <Tag color="blue">{selectedTableInfo?.display_name || selectedTable}</Tag>
              {tableData && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {tableData.total.toLocaleString()} total rows
                  {searchText && ` (filtered by "${searchText}")`}
                </Text>
              )}
            </Space>
          </div>
        )}
      </Card>

      {/* Data Table */}
      {selectedTable ? (
        <div className="glass-table-container">
          <Table
            columns={columns}
            dataSource={tableData?.data || []}
            rowKey={(record, index) => record.id || record.domain || String(index)}
            loading={loading}
            onChange={handleTableChange}
            scroll={{ x: 'max-content' }}
            size="small"
            pagination={{
              current: currentPage,
              pageSize: pageSize,
              total: tableData?.total || 0,
              showSizeChanger: true,
              pageSizeOptions: PAGE_SIZE_OPTIONS.map(String),
              onChange: (page, size) => {
                if (size !== pageSize) {
                  setPageSize(size);
                  setCurrentPage(1);
                } else {
                  setCurrentPage(page);
                }
              },
              showTotal: (total, range) =>
                `${range[0]}-${range[1]} of ${total.toLocaleString()} rows`,
              position: ['bottomRight'],
            }}
          />
        </div>
      ) : (
        <Card className="glass-card-static">
          <Empty
            image={<DatabaseOutlined style={{ fontSize: 48, color: '#ccc' }} />}
            description={
              <Text type="secondary" style={{ fontSize: 16 }}>
                Select a table from the dropdown above to browse data
              </Text>
            }
          />
        </Card>
      )}
    </div>
  );
};

export default AdminDataViewPage;
