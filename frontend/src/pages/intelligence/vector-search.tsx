/**
 * Semantic Search Page — Hybrid search with vector + keyword + temporal parsing.
 * Uses TanStack Table for results with sorting, filtering, source-type tabs.
 * Embedding management (stats, reembed, backfill) in collapsible panel.
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Card, Input, Tag, Space, Typography, Button, Row, Col,
  Statistic, Progress, Alert, message, Collapse, Badge, Spin,
  Select, Tooltip,
} from 'antd';
import {
  SearchOutlined, ThunderboltOutlined, ReloadOutlined,
  MailOutlined, BankOutlined, ToolOutlined,
  CheckCircleOutlined, SyncOutlined, ClockCircleOutlined,
  FilterOutlined,
} from '@ant-design/icons';
import {
  useReactTable,
  getCoreRowModel,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import { DataTable } from '../../components/DataTable';
import * as vectorApi from '../../services/vectorService';
import type { HybridResult } from '../../services/vectorService';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { useNavigate, useSearchParams } from 'react-router-dom';

const { Title, Text, Paragraph } = Typography;
const { Search } = Input;
const col = createColumnHelper<HybridResult>();

// ---------------------------------------------------------------------------
// Suggested prompts
// ---------------------------------------------------------------------------

const SUGGESTED_PROMPTS = [
  'wide format printing banner',
  'delayed delivery complaint',
  'soft cover book binding',
  'embellishment foil stamping',
  'quote follow-up overdue',
  'what happened last quarter',
  'rush job urgent turnaround',
  'high value customer retention risk',
];

const SOURCE_OPTIONS = [
  { value: '', label: 'All Sources' },
  { value: 'email', label: 'Emails' },
  { value: 'company', label: 'Companies' },
  { value: 'operation', label: 'Operations' },
];

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  email: <MailOutlined style={{ color: '#667eea' }} />,
  company: <BankOutlined style={{ color: '#52c41a' }} />,
  operation: <ToolOutlined style={{ color: '#faad14' }} />,
};

const SOURCE_COLORS: Record<string, string> = {
  email: 'blue',
  company: 'green',
  operation: 'gold',
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

const VectorSearchPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(() => searchParams.get('q') || '');
  const [searching, setSearching] = useState(false);
  const [response, setResponse] = useState<vectorApi.HybridSearchResponse | null>(null);
  const [sourceFilter, setSourceFilter] = useState(() => searchParams.get('source') || '');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'score', desc: true }]);
  const [clientId, setClientId] = useState<string | undefined>(
    localStorage.getItem('analytics_client_id') || undefined
  );
  const initialSearchDone = useRef(false);

  // Embedding stats
  const [stats, setStats] = useState<vectorApi.VectorStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [reembedStatus, setReembedStatus] = useState<vectorApi.ReembedStatus | null>(null);

  // Full-text search backfill
  const [backfillRunning, setBackfillRunning] = useState(false);
  const [backfillTotal, setBackfillTotal] = useState(0);
  const backfillCancelRef = useRef(false);

  // Load stats on mount and when client changes
  useEffect(() => {
    loadStats();
    setResponse(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const s = await vectorApi.getVectorStats(clientId);
      setStats(s);
    } catch { /* keep previous */ } finally {
      setStatsLoading(false);
    }
  }, [clientId]);

  // Poll reembed status
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
            message.success(`Embedding complete: ${status.result?.total_embedded} records`);
          } else if (status.status === 'error') {
            message.error(`Embedding failed: ${status.error}`);
          }
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(interval);
  }, [reembedStatus?.status, clientId, loadStats]);

  // Search handler — uses hybrid search
  const handleSearch = async (q: string) => {
    if (!q || q.trim().length < 3) {
      message.warning('Query must be at least 3 characters');
      return;
    }
    setSearching(true);
    setQuery(q);
    // Persist to URL so results survive navigation
    const next = new URLSearchParams(searchParams);
    next.set('q', q);
    if (sourceFilter) next.set('source', sourceFilter); else next.delete('source');
    setSearchParams(next, { replace: true });
    try {
      const r = await vectorApi.hybridSearch(q, clientId, undefined, 50, 0.5);
      setResponse(r);
      if (r.total === 0) {
        message.info('No results found. Try a different query.');
      }
    } catch (err: any) {
      message.error(err?.message || 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  // Auto-search on mount if URL has a query
  useEffect(() => {
    if (initialSearchDone.current) return;
    const urlQuery = searchParams.get('q');
    if (urlQuery && urlQuery.trim().length >= 3) {
      initialSearchDone.current = true;
      handleSearch(urlQuery);
    }
  }, []);

  const handleReembed = async (tables?: string[]) => {
    try {
      const resp = await vectorApi.triggerReembed(clientId, tables);
      if (resp.status === 'already_running') {
        message.info('Embedding already in progress');
      } else {
        message.success(`Embedding ${tables ? tables.join(' + ') : 'all tables'} in background`);
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

  const handleBackfillSearchText = async () => {
    setBackfillRunning(true);
    setBackfillTotal(0);
    backfillCancelRef.current = false;
    let totalUpdated = 0;
    try {
      while (!backfillCancelRef.current) {
        const resp = await vectorApi.backfillSearchText(2000);
        if (!resp) break;
        totalUpdated += resp.updated || 0;
        setBackfillTotal(totalUpdated);
        if (resp.done || resp.updated === 0) {
          message.success(`Search index built: ${totalUpdated.toLocaleString()} emails indexed`);
          break;
        }
      }
      if (backfillCancelRef.current) {
        message.info(`Backfill stopped — ${totalUpdated.toLocaleString()} indexed so far`);
      }
    } catch (err: any) {
      message.error(err?.message || 'Search text backfill failed');
    } finally {
      setBackfillRunning(false);
    }
  };

  // Filtered results
  const filteredResults = useMemo(() => {
    if (!response) return [];
    if (!sourceFilter) return response.results;
    return response.results.filter(r => r.source_type === sourceFilter);
  }, [response, sourceFilter]);

  // Row click handler
  const handleRowClick = (result: HybridResult) => {
    if (result.source_type === 'company') {
      navigate(`/customers/${result.id}`);
    } else if (result.source_type === 'email') {
      navigate(`/emails?email_id=${result.id}`);
    }
  };

  // TanStack Table columns
  const columns = useMemo(() => [
    col.accessor('source_type', {
      header: 'Source',
      size: 90,
      cell: info => {
        const t = info.getValue();
        return (
          <Tag color={SOURCE_COLORS[t] || 'default'} style={{ margin: 0 }}>
            {SOURCE_ICONS[t]} {t === 'email' ? 'Email' : t === 'company' ? 'Company' : 'Operation'}
          </Tag>
        );
      },
    }),
    col.accessor('title', {
      header: 'Title',
      size: 320,
      cell: info => {
        const r = info.row.original;
        const clickable = r.source_type === 'company' || r.source_type === 'email';
        return (
          <div>
            <Text
              strong
              ellipsis={{ tooltip: info.getValue() }}
              style={clickable ? { color: '#667eea', cursor: 'pointer' } : undefined}
              onClick={clickable ? (e) => { e.stopPropagation(); handleRowClick(r); } : undefined}
            >
              {info.getValue()}
            </Text>
            <div><Text type="secondary" style={{ fontSize: 11 }}>{r.snippet}</Text></div>
          </div>
        );
      },
    }),
    col.accessor('score', {
      header: 'Score',
      size: 80,
      cell: info => {
        const v = info.getValue();
        const pct = Math.min(v * 10000, 100);  // RRF scores are small — normalize for display
        return (
          <Tooltip title={`Vector: ${info.row.original.vector_score} | Keyword: ${info.row.original.keyword_score} | Recency: ${info.row.original.recency_score}`}>
            <Progress
              percent={Math.round(pct)}
              size="small"
              strokeColor={pct > 70 ? '#52c41a' : pct > 40 ? '#faad14' : '#667eea'}
              format={p => `${p}`}
              style={{ width: 60 }}
            />
          </Tooltip>
        );
      },
    }),
    col.accessor(r => r.metadata?.sent_date || r.metadata?.last_contact_date, {
      id: 'date',
      header: 'Date',
      size: 100,
      cell: info => {
        const v = info.getValue();
        return v ? new Date(v).toLocaleDateString() : '-';
      },
    }),
    col.accessor('vector_score', {
      header: 'Vector',
      size: 70,
      cell: info => {
        const v = info.getValue();
        return v > 0 ? (
          <Text style={{ color: v > 0.8 ? '#52c41a' : v > 0.7 ? '#faad14' : undefined, fontSize: 12 }}>
            {(v * 100).toFixed(0)}%
          </Text>
        ) : <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
      },
    }),
    col.accessor('keyword_score', {
      header: 'Keyword',
      size: 70,
      cell: info => {
        const v = info.getValue();
        return v > 0 ? (
          <Text style={{ color: '#667eea', fontSize: 12 }}>{v.toFixed(2)}</Text>
        ) : <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
      },
    }),
    col.accessor('recency_score', {
      header: 'Recency',
      size: 70,
      cell: info => {
        const v = info.getValue();
        return v < 1 ? (
          <Text style={{ fontSize: 12 }}>{(v * 100).toFixed(0)}%</Text>
        ) : <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
      },
    }),
  ], [navigate]);

  const table = useReactTable({
    data: filteredResults,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: false, // client-side sort on already-fetched results
  });

  const hasEmbeddings = stats && (
    stats.emails.embedded > 0 || stats.companies.embedded > 0 || stats.operations.embedded > 0
  );

  // Source counts
  const sourceCounts = useMemo(() => {
    if (!response) return { email: 0, company: 0, operation: 0 };
    const c = { email: 0, company: 0, operation: 0 };
    for (const r of response.results) c[r.source_type]++;
    return c;
  }, [response]);

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>Semantic Search</Title>
          <Paragraph type="secondary" style={{ margin: '4px 0 0 0' }}>
            Hybrid search with AI understanding + keyword precision + time awareness
          </Paragraph>
        </div>
        <ClientSelector value={clientId || ''} onChange={id => setClientId(id)} />
      </div>

      {/* Search bar */}
      <Card className="glass-card" style={{ marginBottom: 16 }}>
        <Search
          placeholder="Search with natural language... e.g. 'what happened with Acme last quarter', 'rush delivery complaints'"
          allowClear
          value={query}
          onChange={e => setQuery(e.target.value)}
          enterButton={<><SearchOutlined /> Search</>}
          size="large"
          loading={searching}
          onSearch={handleSearch}
          style={{ marginBottom: 12 }}
        />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <Text type="secondary" style={{ fontSize: 12, marginRight: 4 }}>Try:</Text>
          {SUGGESTED_PROMPTS.map(p => (
            <Tag key={p} style={{ cursor: 'pointer', fontSize: 11 }} onClick={() => handleSearch(p)}>{p}</Tag>
          ))}
        </div>
      </Card>

      {/* Temporal + source info bar */}
      {response && (
        <Card className="glass-card" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={16} align="middle">
            <Col flex="auto">
              <Space wrap size="middle">
                <Text strong>{response.total} results</Text>
                {response.cleaned_query !== response.query && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Cleaned: "{response.cleaned_query}"
                  </Text>
                )}
                {(response.date_from || response.date_to) && (
                  <Tag icon={<ClockCircleOutlined />} color="processing">
                    {response.date_from || '...'} → {response.date_to || 'now'}
                  </Tag>
                )}
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Vector: {response.total_vector_hits} | Keyword: {response.total_keyword_hits}
                </Text>
              </Space>
            </Col>
            <Col>
              <Space>
                <FilterOutlined />
                <Select
                  value={sourceFilter}
                  onChange={setSourceFilter}
                  style={{ width: 140 }}
                  size="small"
                  options={SOURCE_OPTIONS.map(o => ({
                    ...o,
                    label: (
                      <span>
                        {o.value ? SOURCE_ICONS[o.value] : null} {o.label}
                        {o.value && response ? ` (${sourceCounts[o.value as keyof typeof sourceCounts] || 0})` : ''}
                      </span>
                    ),
                  }))}
                />
              </Space>
            </Col>
          </Row>
        </Card>
      )}

      {/* Results table */}
      {response && filteredResults.length > 0 && (
        <div className="glass-table-container" style={{ marginBottom: 16 }}>
          <DataTable
            table={table}
            loading={searching}
            total={filteredResults.length}
            currentPage={1}
            pageSize={50}
            onPageChange={() => {}}
            onRowClick={handleRowClick}
          />
        </div>
      )}

      {/* No results */}
      {response && response.total === 0 && (
        <Card className="glass-card" style={{ textAlign: 'center', padding: 48, marginBottom: 16 }}>
          <SearchOutlined style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }} />
          <div><Text type="secondary">No results found for "{query}"</Text></div>
          <div style={{ marginTop: 8 }}><Text type="secondary" style={{ fontSize: 12 }}>Try a broader query or lower the similarity threshold</Text></div>
        </Card>
      )}

      {/* Empty state */}
      {!response && !searching && (
        <Card className="glass-card" style={{ textAlign: 'center', padding: 64, marginBottom: 16 }}>
          <SearchOutlined style={{ fontSize: 64, marginBottom: 16, opacity: 0.2 }} />
          <div style={{ fontSize: 16, marginBottom: 8 }}><Text type="secondary">Search your portfolio with natural language</Text></div>
          <div><Text type="secondary" style={{ fontSize: 13 }}>
            Combines AI understanding + keyword matching + time awareness for precise results
          </Text></div>
        </Card>
      )}

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
                            <Progress percent={pct} size="small" status={pct === 100 ? 'success' : 'active'}
                              strokeColor={pct === 100 ? '#52c41a' : '#667eea'} />
                          </Card>
                        </Col>
                      );
                    })}
                  </Row>
                  <Space wrap>
                    {reembedStatus?.status === 'running' ? (
                      <Button danger icon={<SyncOutlined spin />} onClick={handleStopReembed}>Stop Embedding</Button>
                    ) : (
                      <>
                        <Button type="primary" icon={<MailOutlined />} onClick={() => handleReembed(['emails'])}>Embed Emails</Button>
                        <Button icon={<BankOutlined />} onClick={() => handleReembed(['companies'])}>Embed Companies</Button>
                        <Button icon={<ToolOutlined />} onClick={() => handleReembed(['operations'])}>Embed Operations</Button>
                        <Button icon={<ThunderboltOutlined />} onClick={() => handleReembed()}>Embed All</Button>
                      </>
                    )}
                    <Button icon={<ReloadOutlined />} onClick={loadStats}>Refresh Stats</Button>
                    {backfillRunning ? (
                      <Button danger icon={<SyncOutlined spin />} onClick={() => { backfillCancelRef.current = true; }}>
                        Stop Indexing ({backfillTotal.toLocaleString()})
                      </Button>
                    ) : (
                      <Button icon={<SearchOutlined />} onClick={handleBackfillSearchText}>Build Search Index</Button>
                    )}
                    {reembedStatus?.status === 'complete' && reembedStatus.result && (
                      <Text type="success"><CheckCircleOutlined /> {reembedStatus.result.total_embedded} embedded</Text>
                    )}
                  </Space>
                </>
              ) : (
                <Alert
                  type="warning"
                  message="Could not load embedding stats"
                  action={<Button size="small" onClick={loadStats}>Refresh</Button>}
                />
              )}
            </div>
          ),
        }]}
        style={{ marginBottom: 24 }}
      />

      {stats && !hasEmbeddings && (
        <Alert
          type="warning" showIcon style={{ marginBottom: 24 }}
          message="No embeddings found"
          description="Click 'Embed All' above to generate embeddings. This is a one-time operation."
        />
      )}
    </div>
  );
};

export default VectorSearchPage;
