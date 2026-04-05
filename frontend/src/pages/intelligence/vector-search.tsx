/**
 * Vector Search Page — Semantic search across emails, companies, and operations.
 * Also includes embedding management (stats, reembed trigger).
 *
 * Sprint 4 S4.4 — /insights/search
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Input, Tabs, Table, Tag, Space, Typography, Button, Row, Col,
  Statistic, Progress, Alert, message, Collapse, Badge, Spin,
} from 'antd';
import {
  SearchOutlined, ThunderboltOutlined, ReloadOutlined,
  MailOutlined, BankOutlined, ToolOutlined,
  CheckCircleOutlined, SyncOutlined,
} from '@ant-design/icons';
import * as vectorApi from '../../services/vectorService';
import { ClientSelector } from '../../components/analytics/ClientSelector';

const { Title, Text, Paragraph } = Typography;
const { Search } = Input;

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

const emailColumns = [
  { title: 'Subject', dataIndex: 'subject', key: 'subject', width: 320, ellipsis: true },
  { title: 'From', dataIndex: 'sender_name', key: 'sender', width: 180, ellipsis: true,
    render: (v: string, r: any) => v || r.sender_email || '—' },
  { title: 'Direction', dataIndex: 'is_outbound', key: 'direction', width: 90,
    render: (v: boolean) => v ? <Tag color="blue">Outbound</Tag> : <Tag color="green">Inbound</Tag> },
  { title: 'Date', dataIndex: 'sent_date', key: 'sent_date', width: 110,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '—' },
  { title: 'Similarity', dataIndex: 'similarity', key: 'similarity', width: 90, align: 'right' as const,
    render: (v: number) => v != null ? (
      <Text strong style={{ color: v > 0.8 ? '#52c41a' : v > 0.7 ? '#faad14' : undefined }}>
        {(v * 100).toFixed(0)}%
      </Text>
    ) : '—' },
];

const companyColumns = [
  { title: 'Company', dataIndex: 'company_name', key: 'company_name', width: 220, ellipsis: true },
  { title: 'Industry', dataIndex: 'industry', key: 'industry', width: 160, ellipsis: true },
  { title: 'Tier', dataIndex: 'qb_tier', key: 'tier', width: 80,
    render: (v: string) => v ? <Tag>{v}</Tag> : '—' },
  { title: 'Revenue', dataIndex: 'qb_total_revenue', key: 'revenue', width: 120, align: 'right' as const,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '—' },
  { title: 'Similarity', dataIndex: 'similarity', key: 'similarity', width: 90, align: 'right' as const,
    render: (v: number) => v != null ? (
      <Text strong style={{ color: v > 0.8 ? '#52c41a' : v > 0.7 ? '#faad14' : undefined }}>
        {(v * 100).toFixed(0)}%
      </Text>
    ) : '—' },
];

const operationColumns = [
  { title: 'Operation', dataIndex: 'operation_name', key: 'operation_name', width: 220, ellipsis: true },
  { title: 'Department', dataIndex: 'department', key: 'department', width: 130,
    render: (v: string) => v ? <Tag>{v}</Tag> : '—' },
  { title: 'Machine', dataIndex: 'machine', key: 'machine', width: 160, ellipsis: true },
  { title: 'Customer', dataIndex: 'customer_name', key: 'customer_name', width: 180, ellipsis: true },
  { title: 'Capabilities', dataIndex: 'capability_tags', key: 'tags', width: 200,
    render: (v: string[]) => {
      if (!v || v.length === 0) return <Text type="secondary" style={{ fontSize: 11 }}>—</Text>;
      return <Space size={2} wrap>{v.map((t: string) => <Tag key={t} color="blue" style={{ fontSize: 11 }}>{t}</Tag>)}</Space>;
    } },
  { title: 'Similarity', dataIndex: 'similarity', key: 'similarity', width: 90, align: 'right' as const,
    render: (v: number) => v != null ? (
      <Text strong style={{ color: v > 0.8 ? '#52c41a' : v > 0.7 ? '#faad14' : undefined }}>
        {(v * 100).toFixed(0)}%
      </Text>
    ) : '—' },
];

// ---------------------------------------------------------------------------
// Suggested prompts
// ---------------------------------------------------------------------------

const SUGGESTED_PROMPTS = [
  'wide format printing banner',
  'delayed delivery complaint',
  'soft cover book binding',
  'embellishment foil stamping',
  'packaging design services',
  'quote follow-up overdue',
  'rush job urgent turnaround',
  'high value customer retention risk',
];

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

const VectorSearchPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<vectorApi.UnifiedSearchResult | null>(null);
  const [activeTab, setActiveTab] = useState('all');
  const [clientId, setClientId] = useState<string | undefined>(
    localStorage.getItem('analytics_client_id') || undefined
  );

  // Embedding stats
  const [stats, setStats] = useState<vectorApi.VectorStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [reembedStatus, setReembedStatus] = useState<vectorApi.ReembedStatus | null>(null);

  // Load stats on mount and when client changes
  useEffect(() => {
    loadStats();
    setResults(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const s = await vectorApi.getVectorStats(clientId);
      setStats(s);
    } catch {
      // Keep previous stats if available — don't wipe on transient failure
    } finally {
      setStatsLoading(false);
    }
  }, [clientId]);

  // Poll reembed status when running
  useEffect(() => {
    if (reembedStatus?.status !== 'running') return;
    const interval = setInterval(async () => {
      try {
        const status = await vectorApi.getReembedStatus(clientId);
        setReembedStatus(status);
        if (status.status !== 'running') {
          clearInterval(interval);
          loadStats();
          if (status.status === 'complete') {
            message.success(`Embedding complete: ${status.result?.total_embedded} records embedded`);
          } else if (status.status === 'error') {
            message.error(`Embedding failed: ${status.error}`);
          }
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(interval);
  }, [reembedStatus?.status, clientId, loadStats]);

  const handleSearch = async (q: string) => {
    if (!q || q.trim().length < 3) {
      message.warning('Query must be at least 3 characters');
      return;
    }
    setSearching(true);
    setQuery(q);
    try {
      const r = await vectorApi.searchAll(q, clientId, 0.6, 10);
      setResults(r);
      if (r.total === 0) {
        message.info('No results found. Try a different query or lower the similarity threshold.');
      }
    } catch (err: any) {
      message.error(err?.message || 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  const handleReembed = async (tables?: string[]) => {
    try {
      const resp = await vectorApi.triggerReembed(clientId, tables);
      if (resp.status === 'already_running') {
        message.info('Embedding already in progress');
      } else {
        const label = tables ? tables.join(' + ') : 'all tables';
        message.success(`Embedding ${label} in background`);
      }
      setReembedStatus({ status: 'running', started_at: Date.now() / 1000 });
    } catch (err: any) {
      message.error(err?.message || 'Failed to start embedding');
    }
  };

  const handleStopReembed = async () => {
    try {
      await vectorApi.stopReembed(clientId);
      message.info('Stopping embedding — already embedded records are kept');
    } catch (err: any) {
      message.error(err?.message || 'Failed to stop embedding');
    }
  };

  // Full-text search backfill
  const [backfillRunning, setBackfillRunning] = useState(false);
  const [backfillTotal, setBackfillTotal] = useState(0);
  const backfillCancelRef = useRef(false);

  const handleBackfillSearchText = async () => {
    setBackfillRunning(true);
    setBackfillTotal(0);
    backfillCancelRef.current = false;
    let totalUpdated = 0;

    try {
      while (!backfillCancelRef.current) {
        const resp = await vectorApi.backfillSearchText(10000);
        totalUpdated += resp.updated;
        setBackfillTotal(totalUpdated);
        if (resp.done) {
          message.success(`Search index built: ${totalUpdated.toLocaleString()} emails indexed`);
          break;
        }
      }
      if (backfillCancelRef.current) {
        message.info(`Backfill stopped — ${totalUpdated.toLocaleString()} emails indexed so far`);
      }
    } catch (err: any) {
      message.error(err?.message || 'Search text backfill failed');
    } finally {
      setBackfillRunning(false);
    }
  };

  const hasEmbeddings = stats && (
    stats.emails.embedded > 0 || stats.companies.embedded > 0 || stats.operations.embedded > 0
  );

  const tabItems = results ? [
    {
      key: 'all',
      label: <span>All Results <Badge count={results.total} overflowCount={999} color="#667eea" /></span>,
      children: (
        <div>
          {results.emails.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <Text strong style={{ fontSize: 14 }}><MailOutlined /> Emails ({results.emails.length})</Text>
              <Table dataSource={results.emails} columns={emailColumns} rowKey="id"
                size="small" pagination={false} scroll={{ x: 'max-content' }} style={{ marginTop: 8 }} />
            </div>
          )}
          {results.companies.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <Text strong style={{ fontSize: 14 }}><BankOutlined /> Companies ({results.companies.length})</Text>
              <Table dataSource={results.companies} columns={companyColumns} rowKey="id"
                size="small" pagination={false} scroll={{ x: 'max-content' }} style={{ marginTop: 8 }} />
            </div>
          )}
          {results.operations.length > 0 && (
            <div>
              <Text strong style={{ fontSize: 14 }}><ToolOutlined /> Operations ({results.operations.length})</Text>
              <Table dataSource={results.operations} columns={operationColumns} rowKey="id"
                size="small" pagination={false} scroll={{ x: 'max-content' }} style={{ marginTop: 8 }} />
            </div>
          )}
          {results.total === 0 && (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'rgba(255,255,255,0.3)' }}>
              <SearchOutlined style={{ fontSize: 48, marginBottom: 16 }} />
              <div>No results found for "{query}"</div>
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'emails',
      label: <span>Emails <Badge count={results.emails.length} color="#667eea" /></span>,
      children: <Table dataSource={results.emails} columns={emailColumns} rowKey="id"
        size="small" pagination={{ pageSize: 20 }} scroll={{ x: 'max-content' }} />,
    },
    {
      key: 'companies',
      label: <span>Companies <Badge count={results.companies.length} color="#667eea" /></span>,
      children: <Table dataSource={results.companies} columns={companyColumns} rowKey="id"
        size="small" pagination={{ pageSize: 20 }} scroll={{ x: 'max-content' }} />,
    },
    {
      key: 'operations',
      label: <span>Operations <Badge count={results.operations.length} color="#667eea" /></span>,
      children: <Table dataSource={results.operations} columns={operationColumns} rowKey="id"
        size="small" pagination={{ pageSize: 20 }} scroll={{ x: 'max-content' }} />,
    },
  ] : [];

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>Semantic Search</Title>
          <Paragraph type="secondary" style={{ margin: '4px 0 0 0' }}>
            Search across emails, companies, and operations using natural language
          </Paragraph>
        </div>
        <ClientSelector value={clientId || ''} onChange={id => setClientId(id)} />
      </div>

      {/* Search bar */}
      <Card className="glass-card" style={{ marginBottom: 24 }}>
        <Search
          placeholder="Ask anything about your portfolio... e.g. 'wide format printing', 'deal at risk', 'rush delivery'"
          allowClear
          enterButton={<><SearchOutlined /> Search</>}
          size="large"
          loading={searching}
          onSearch={handleSearch}
          style={{ marginBottom: 12 }}
        />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <Text type="secondary" style={{ fontSize: 12, marginRight: 4 }}>Try:</Text>
          {SUGGESTED_PROMPTS.map(p => (
            <Tag
              key={p}
              style={{ cursor: 'pointer', fontSize: 11 }}
              onClick={() => handleSearch(p)}
            >
              {p}
            </Tag>
          ))}
        </div>
      </Card>

      {/* Embedding Stats + Management */}
      <Collapse
        items={[{
          key: 'embeddings',
          label: (
            <Space>
              <ThunderboltOutlined />
              <span>Embedding Coverage</span>
              {stats && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {(stats.emails.embedded + stats.companies.embedded + stats.operations.embedded).toLocaleString()} /
                  {' '}{(stats.emails.total + stats.companies.total + stats.operations.total).toLocaleString()} records
                </Text>
              )}
            </Space>
          ),
          children: (
            <div>
              {statsLoading ? <Spin /> : stats ? (
                <>
                  <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                    {[
                      { label: 'Emails', icon: <MailOutlined />, data: stats.emails },
                      { label: 'Companies', icon: <BankOutlined />, data: stats.companies },
                      { label: 'Operations', icon: <ToolOutlined />, data: stats.operations },
                    ].map(s => {
                      const pct = s.data.total > 0 ? Math.round((s.data.embedded / s.data.total) * 100) : 0;
                      return (
                        <Col key={s.label} xs={24} sm={8}>
                          <Card size="small" className="glass-card">
                            <Statistic
                              title={<Space>{s.icon} {s.label}</Space>}
                              value={s.data.embedded}
                              suffix={<Text type="secondary">/ {s.data.total.toLocaleString()}</Text>}
                            />
                            <Progress
                              percent={pct}
                              size="small"
                              status={pct === 100 ? 'success' : 'active'}
                              strokeColor={pct === 100 ? '#52c41a' : '#667eea'}
                            />
                          </Card>
                        </Col>
                      );
                    })}
                  </Row>
                  <Space wrap>
                    {reembedStatus?.status === 'running' ? (
                      <Button
                        danger
                        icon={<SyncOutlined spin />}
                        onClick={handleStopReembed}
                      >
                        Stop Embedding
                      </Button>
                    ) : (
                      <>
                        <Button
                          type="primary"
                          icon={<MailOutlined />}
                          onClick={() => handleReembed(['emails'])}
                        >
                          Embed Emails
                        </Button>
                        <Button
                          icon={<BankOutlined />}
                          onClick={() => handleReembed(['companies'])}
                        >
                          Embed Companies
                        </Button>
                        <Button
                          icon={<ToolOutlined />}
                          onClick={() => handleReembed(['operations'])}
                        >
                          Embed Operations
                        </Button>
                        <Button
                          icon={<ThunderboltOutlined />}
                          onClick={() => handleReembed()}
                        >
                          Embed All
                        </Button>
                      </>
                    )}
                    <Button icon={<ReloadOutlined />} onClick={loadStats}>Refresh Stats</Button>
                    {backfillRunning ? (
                      <Button danger icon={<SyncOutlined spin />} onClick={() => { backfillCancelRef.current = true; }}>
                        Stop Indexing ({backfillTotal.toLocaleString()})
                      </Button>
                    ) : (
                      <Button icon={<SearchOutlined />} onClick={handleBackfillSearchText}>
                        Build Search Index
                      </Button>
                    )}
                    {reembedStatus?.status === 'complete' && reembedStatus.result && (
                      <Text type="success">
                        <CheckCircleOutlined /> {reembedStatus.result.total_embedded} embedded
                      </Text>
                    )}
                    {reembedStatus?.status === 'stopped' && reembedStatus.result && (
                      <Text type="warning">
                        Stopped — {reembedStatus.result.total_embedded} embedded so far
                      </Text>
                    )}
                  </Space>
                </>
              ) : (
                <Alert
                  type="warning"
                  message="Could not load embedding stats"
                  description="The backend may be busy or temporarily unavailable. Click Refresh to retry."
                  action={<Button size="small" onClick={loadStats}>Refresh</Button>}
                />
              )}
            </div>
          ),
        }]}
        style={{ marginBottom: 24 }}
      />

      {/* No embeddings warning */}
      {stats && !hasEmbeddings && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 24 }}
          message="No embeddings found"
          description="Click 'Embed All Records' above to generate embeddings. This is a one-time operation (~$0.15 cost)."
        />
      )}

      {/* Results */}
      {results && (
        <Card className="glass-card">
          <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} type="line" />
        </Card>
      )}

      {/* Empty state */}
      {!results && !searching && (
        <div style={{
          textAlign: 'center',
          padding: '64px 0',
          color: 'rgba(255,255,255,0.25)',
        }}>
          <SearchOutlined style={{ fontSize: 64, marginBottom: 16 }} />
          <div style={{ fontSize: 16, marginBottom: 8 }}>Search your portfolio with natural language</div>
          <div style={{ fontSize: 13 }}>
            Find emails, companies, and operations by meaning — not just keywords
          </div>
        </div>
      )}
    </div>
  );
};

export default VectorSearchPage;
