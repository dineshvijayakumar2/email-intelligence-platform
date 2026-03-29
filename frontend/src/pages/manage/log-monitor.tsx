/**
 * Live Log Monitor — Real-time backend log viewer with filtering.
 * Polls /api/v1/logs/recent every 3s. Classifies by service, level, mailbox.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Table, Tag, Space, Typography, Select, Input, Switch, Button, Badge,
} from 'antd';
import {
  ReloadOutlined, PauseCircleOutlined, PlayCircleOutlined,
  ClearOutlined,
} from '@ant-design/icons';
import api from '../../services/apiClient';

const { Title, Text } = Typography;
const { Search } = Input;

interface LogEntry {
  ts: string;
  level: string;
  service: string;
  message: string;
  mailbox_id?: string;
  client_id?: string;
  job_id?: string;
  step?: string;
}

const levelColors: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'blue',
  WARNING: 'gold',
  ERROR: 'red',
  CRITICAL: 'magenta',
};

const POLL_OPTIONS = [
  { value: 1000, label: '1s' },
  { value: 3000, label: '3s' },
  { value: 5000, label: '5s' },
  { value: 10000, label: '10s' },
  { value: 30000, label: '30s' },
];

export default function LogMonitorPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [pollInterval, setPollInterval] = useState(3000);

  // Filters
  const [levelFilter, setLevelFilter] = useState<string | undefined>(undefined);
  const [serviceFilter, setServiceFilter] = useState<string | undefined>(undefined);
  const [mailboxFilter, setMailboxFilter] = useState<string | undefined>(undefined);
  const [clientFilter, setClientFilter] = useState<string | undefined>(undefined);
  const [searchFilter, setSearchFilter] = useState('');
  const [services, setServices] = useState<string[]>([]);

  // Unique mailbox/client IDs seen in logs (for filter dropdowns)
  const [seenMailboxes, setSeenMailboxes] = useState<string[]>([]);
  const [seenClients, setSeenClients] = useState<string[]>([]);

  // Name lookups: id → label
  const [mailboxNames, setMailboxNames] = useState<Record<string, string>>({});
  const [clientNames, setClientNames] = useState<Record<string, string>>({});

  const tableRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load services (static, no DB) immediately; context names (DB) lazily with timeout
  useEffect(() => {
    api.get('/v1/logs/services').then((data: any) => {
      setServices(data?.services || []);
    }).catch(() => {});
    // Context names are nice-to-have — don't block if Supabase is busy
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 5000); // 5s timeout
    api.get('/v1/logs/context', { signal: ctrl.signal } as any).then((data: any) => {
      setMailboxNames(data?.mailboxes || {});
      setClientNames(data?.clients || {});
    }).catch(() => {});
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, []);

  // Use refs for seen IDs to avoid stale closures in fetchLogs
  const seenMbRef = useRef(new Set<string>());
  const seenClRef = useRef(new Set<string>());

  const fetchLogs = useCallback(async () => {
    if (paused) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (levelFilter) params.set('level', levelFilter);
      if (serviceFilter) params.set('service', serviceFilter);
      if (mailboxFilter) params.set('mailbox_id', mailboxFilter);
      if (clientFilter) params.set('client_id', clientFilter);
      if (searchFilter) params.set('search', searchFilter);
      const data = await api.get(`/v1/logs/recent?${params}`) as { logs: LogEntry[] };
      const entries = data.logs || [];
      setLogs(entries);

      // Track unique mailbox/client IDs for filter dropdowns
      let mbChanged = false, clChanged = false;
      for (const e of entries) {
        if (e.mailbox_id && !seenMbRef.current.has(e.mailbox_id)) {
          seenMbRef.current.add(e.mailbox_id); mbChanged = true;
        }
        if (e.client_id && !seenClRef.current.has(e.client_id)) {
          seenClRef.current.add(e.client_id); clChanged = true;
        }
      }
      if (mbChanged) setSeenMailboxes(Array.from(seenMbRef.current));
      if (clChanged) setSeenClients(Array.from(seenClRef.current));
    } catch { /* silent */ }
    setLoading(false);
  }, [paused, levelFilter, serviceFilter, mailboxFilter, clientFilter, searchFilter]);

  // Initial load + polling at configurable interval
  useEffect(() => {
    fetchLogs();
    pollRef.current = setInterval(fetchLogs, pollInterval);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchLogs, pollInterval]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && tableRef.current) {
      const tableBody = tableRef.current.querySelector('.ant-table-body');
      if (tableBody) tableBody.scrollTop = 0; // newest at top
    }
  }, [logs, autoScroll]);

  // Count by level
  const errorCount = logs.filter(l => l.level === 'ERROR' || l.level === 'CRITICAL').length;
  const warnCount = logs.filter(l => l.level === 'WARNING').length;

  const columns = [
    {
      title: 'Time',
      dataIndex: 'ts',
      key: 'ts',
      width: 90,
      render: (v: string) => {
        const d = new Date(v);
        return <Text style={{ fontSize: 11, fontFamily: 'monospace' }}>{d.toLocaleTimeString()}</Text>;
      },
    },
    {
      title: 'Level',
      dataIndex: 'level',
      key: 'level',
      width: 75,
      render: (v: string) => <Tag color={levelColors[v] || 'default'} style={{ fontSize: 11 }}>{v}</Tag>,
    },
    {
      title: 'Service',
      dataIndex: 'service',
      key: 'service',
      width: 110,
      ellipsis: true,
      render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text>,
    },
    {
      title: 'Message',
      dataIndex: 'message',
      key: 'message',
      ellipsis: false,
      render: (v: string, record: LogEntry) => (
        <div>
          <Text style={{ fontSize: 12 }}>{v}</Text>
          {(record.mailbox_id || record.job_id || record.step) && (
            <div style={{ marginTop: 2 }}>
              {record.step && <Tag style={{ fontSize: 10 }}>Step {record.step}</Tag>}
              {record.job_id && <Tag style={{ fontSize: 10 }} color="geekblue">Job: {record.job_id.slice(0, 8)}</Tag>}
              {record.mailbox_id && <Tag style={{ fontSize: 10 }} color="cyan">{mailboxNames[record.mailbox_id] || `MB: ${record.mailbox_id.slice(0, 8)}`}</Tag>}
              {record.client_id && <Tag style={{ fontSize: 10 }} color="green">{clientNames[record.client_id] || `Client: ${record.client_id.slice(0, 8)}`}</Tag>}
            </div>
          )}
        </div>
      ),
    },
  ];

  return (
    <div style={{ padding: '16px 24px', maxWidth: 1600, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>Live Log Monitor</Title>
          {errorCount > 0 && <Badge count={errorCount} style={{ backgroundColor: '#ff4d4f' }} />}
          {warnCount > 0 && <Badge count={warnCount} style={{ backgroundColor: '#faad14' }} />}
          {paused && <Tag color="orange">Paused</Tag>}
        </Space>
        <Space>
          <Select
            placeholder="Level"
            allowClear
            size="small"
            style={{ width: 100 }}
            value={levelFilter}
            onChange={setLevelFilter}
            options={['ERROR', 'WARNING', 'INFO', 'DEBUG'].map(l => ({ value: l, label: l }))}
          />
          <Select
            placeholder="Service"
            allowClear
            showSearch
            size="small"
            style={{ width: 140 }}
            value={serviceFilter}
            onChange={setServiceFilter}
            options={services.map(s => ({ value: s, label: s }))}
          />
          {seenMailboxes.length > 0 && (
            <Select
              placeholder="Mailbox"
              allowClear
              showSearch
              optionFilterProp="label"
              size="small"
              style={{ width: 180 }}
              value={mailboxFilter}
              onChange={setMailboxFilter}
              options={seenMailboxes.map(id => ({
                value: id,
                label: mailboxNames[id] || id.slice(0, 8) + '…',
              }))}
            />
          )}
          {seenClients.length > 0 && (
            <Select
              placeholder="Client"
              allowClear
              showSearch
              optionFilterProp="label"
              size="small"
              style={{ width: 140 }}
              value={clientFilter}
              onChange={setClientFilter}
              options={seenClients.map(id => ({
                value: id,
                label: clientNames[id] || id.slice(0, 8) + '…',
              }))}
            />
          )}
          <Search
            placeholder="Search messages..."
            size="small"
            style={{ width: 200 }}
            allowClear
            onSearch={setSearchFilter}
            enterButton={false}
          />
          <Select
            size="small"
            style={{ width: 80 }}
            value={pollInterval}
            onChange={setPollInterval}
            options={POLL_OPTIONS}
          />
          <Button
            size="small"
            icon={paused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
            onClick={() => setPaused(!paused)}
            type={paused ? 'primary' : 'default'}
          >
            {paused ? 'Resume' : 'Pause'}
          </Button>
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchLogs}>Refresh</Button>
          <Button size="small" icon={<ClearOutlined />} onClick={() => setLogs([])}>Clear</Button>
          <Switch
            checkedChildren="Auto-scroll"
            unCheckedChildren="Manual"
            checked={autoScroll}
            onChange={setAutoScroll}
            size="small"
          />
        </Space>
      </div>

      <div ref={tableRef}>
        <Card size="small" bodyStyle={{ padding: 0 }}>
          <Table
            dataSource={logs}
            columns={columns}
            rowKey={(_, idx) => `${idx}`}
            loading={loading && logs.length === 0}
            size="small"
            pagination={false}
            scroll={{ y: 'calc(100vh - 200px)' }}
            rowClassName={(record) =>
              record.level === 'ERROR' || record.level === 'CRITICAL'
                ? 'log-row-error'
                : record.level === 'WARNING'
                ? 'log-row-warn'
                : ''
            }
          />
        </Card>
      </div>

      <style>{`
        .log-row-error td { background: rgba(255, 77, 79, 0.08) !important; }
        .log-row-warn td { background: rgba(250, 173, 20, 0.06) !important; }
      `}</style>
    </div>
  );
}
