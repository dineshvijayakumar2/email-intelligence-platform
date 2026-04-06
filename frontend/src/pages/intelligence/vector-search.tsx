/**
 * Semantic Search Page — Hybrid search with vector + keyword + temporal parsing.
 * Thread-grouped email results with expandable conversation context.
 * Embedding management moved to AI Usage page.
 */

import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Card, Input, Tag, Space, Typography, Button, Row, Col,
  message, Select, Tooltip,
} from 'antd';
import {
  SearchOutlined,
  MailOutlined, BankOutlined, ToolOutlined,
  ClockCircleOutlined, FilterOutlined,
} from '@ant-design/icons';
import * as vectorApi from '../../services/vectorService';
import type { HybridResult } from '../../services/vectorService';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { formatRelativeDate } from '../../utils/dateUtils';

const { Title, Text, Paragraph } = Typography;
const { Search } = Input;

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
  const [response, setResponse] = useState<vectorApi.HybridSearchResponse | null>(() => {
    try {
      const cached = sessionStorage.getItem('semantic_search_result');
      const cachedQuery = sessionStorage.getItem('semantic_search_query');
      if (cached && cachedQuery === searchParams.get('q')) {
        const parsed = JSON.parse(cached);
        // Validate it has the current response shape (threads, not results)
        if (parsed && 'threads' in parsed) return parsed;
      }
    } catch { /* ignore */ }
    return null;
  });
  const [sourceFilter, setSourceFilter] = useState(() => searchParams.get('source') || '');
  const [clientId, setClientId] = useState<string | undefined>(
    localStorage.getItem('analytics_client_id') || undefined
  );
  const initialSearchDone = useRef(false);

  // Search handler — uses hybrid search
  const handleSearch = async (q: string) => {
    if (!q || q.trim().length < 3) {
      message.warning('Query must be at least 3 characters');
      return;
    }
    setSearching(true);
    setQuery(q);
    const next = new URLSearchParams(searchParams);
    next.set('q', q);
    if (sourceFilter) next.set('source', sourceFilter); else next.delete('source');
    setSearchParams(next, { replace: true });
    try {
      const r = await vectorApi.hybridSearch(q, clientId, undefined, 50, 0.5);
      setResponse(r);
      try {
        sessionStorage.setItem('semantic_search_result', JSON.stringify(r));
        sessionStorage.setItem('semantic_search_query', q);
      } catch { /* storage full */ }
      if (r.total === 0) {
        message.info('No results found. Try a different query.');
      }
    } catch (err: any) {
      message.error(err?.message || 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  // Auto-search on mount if URL has a query and no cached result
  useEffect(() => {
    if (initialSearchDone.current) return;
    if (response) { initialSearchDone.current = true; return; }
    const urlQuery = searchParams.get('q');
    if (urlQuery && urlQuery.trim().length >= 3) {
      initialSearchDone.current = true;
      handleSearch(urlQuery);
    }
  }, []);

  // Expanded thread state
  const [expandedThreads, setExpandedThreads] = useState<Set<string>>(new Set());
  const toggleThread = (threadId: string) => {
    setExpandedThreads(prev => {
      const next = new Set(prev);
      if (next.has(threadId)) next.delete(threadId); else next.add(threadId);
      return next;
    });
  };

  // Filtered threads and other results
  const filteredThreads = useMemo(() => {
    if (!response) return [];
    if (sourceFilter && sourceFilter !== 'email') return [];
    return response.threads || [];
  }, [response, sourceFilter]);

  const filteredOther = useMemo(() => {
    if (!response) return [];
    if (!sourceFilter) return response.other_results || [];
    return (response.other_results || []).filter(r => r.source_type === sourceFilter);
  }, [response, sourceFilter]);

  // Source counts
  const sourceCounts = useMemo(() => {
    if (!response) return { email: 0, company: 0, operation: 0 };
    return {
      email: (response.threads || []).length,
      company: (response.other_results || []).filter(r => r.source_type === 'company').length,
      operation: (response.other_results || []).filter(r => r.source_type === 'operation').length,
    };
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

      {/* Thread-grouped email results */}
      {filteredThreads.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          {(!sourceFilter || sourceFilter === 'email') && (
            <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>
              <MailOutlined style={{ color: '#667eea', marginRight: 6 }} />
              Email Threads ({filteredThreads.length})
            </Text>
          )}
          {filteredThreads.map(thread => (
            <Card
              key={thread.thread_id}
              className="glass-card"
              size="small"
              style={{ marginBottom: 8, borderLeft: '3px solid #667eea' }}
            >
              <div
                style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}
                onClick={() => toggleThread(thread.thread_id)}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text strong ellipsis={{ tooltip: thread.subject }} style={{ fontSize: 14 }}>
                    {thread.subject || '(No subject)'}
                  </Text>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 2 }}>
                    <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>
                      {thread.total_emails} email{thread.total_emails !== 1 ? 's' : ''}
                    </Tag>
                    {thread.matched_count > 1 && (
                      <Tag color="purple" style={{ margin: 0, fontSize: 11 }}>
                        {thread.matched_count} matched
                      </Tag>
                    )}
                    <Tooltip title={`Vector: ${thread.vector_score} | Keyword: ${thread.keyword_score} | Recency: ${thread.recency_score}`}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        Score: {(thread.score * 10000).toFixed(0)}
                      </Text>
                    </Tooltip>
                  </div>
                </div>
                <Button
                  type="text"
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/emails?thread_id=${encodeURIComponent(thread.thread_id)}&name=${encodeURIComponent(thread.subject || 'Thread')}`);
                  }}
                  style={{ color: '#667eea', fontSize: 12 }}
                >
                  Open Thread
                </Button>
                <Text type="secondary" style={{ fontSize: 18 }}>
                  {expandedThreads.has(thread.thread_id) ? '▾' : '▸'}
                </Text>
              </div>

              {expandedThreads.has(thread.thread_id) && (
                <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 8 }}>
                  {thread.emails.map((email, idx) => (
                    <div
                      key={email.id}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '6px 8px', borderRadius: 4, marginBottom: 2,
                        background: email.is_match ? 'rgba(102,126,234,0.08)' : 'transparent',
                        cursor: 'pointer',
                      }}
                      onClick={() => navigate(`/emails?email_id=${email.id}&name=${encodeURIComponent(email.subject || 'Email')}`)}
                    >
                      <Text type="secondary" style={{ fontSize: 11, width: 20, textAlign: 'center', flexShrink: 0 }}>
                        {idx + 1}
                      </Text>
                      <Tag
                        color={email.is_outbound ? 'green' : 'default'}
                        style={{ margin: 0, fontSize: 10, padding: '0 4px', width: 32, textAlign: 'center' }}
                      >
                        {email.is_outbound ? 'OUT' : 'IN'}
                      </Tag>
                      <Text style={{ fontSize: 12, width: 140, flexShrink: 0 }} ellipsis>
                        {email.sender_name || email.sender_email || '?'}
                      </Text>
                      <Text
                        style={{ fontSize: 12, flex: 1, color: email.is_match ? '#667eea' : undefined }}
                        ellipsis
                      >
                        {email.is_match && '● '}{email.subject || '(No subject)'}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 11, flexShrink: 0 }}>
                        {email.sent_date ? formatRelativeDate(email.sent_date) : '-'}
                      </Text>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Non-email results (companies, operations) */}
      {filteredOther.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>
            <BankOutlined style={{ color: '#52c41a', marginRight: 6 }} />
            Companies & Operations ({filteredOther.length})
          </Text>
          {filteredOther.map(r => (
            <Card
              key={r.id}
              className="glass-card"
              size="small"
              style={{
                marginBottom: 6,
                cursor: r.source_type === 'company' ? 'pointer' : 'default',
                borderLeft: `3px solid ${r.source_type === 'company' ? '#52c41a' : '#faad14'}`,
              }}
              onClick={r.source_type === 'company' ? () => navigate(`/customers/${r.id}`) : undefined}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Tag color={SOURCE_COLORS[r.source_type] || 'default'} style={{ margin: 0 }}>
                  {SOURCE_ICONS[r.source_type]} {r.source_type === 'company' ? 'Company' : 'Operation'}
                </Tag>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text strong ellipsis={{ tooltip: r.title }}>{r.title}</Text>
                  <div><Text type="secondary" style={{ fontSize: 11 }}>{r.snippet}</Text></div>
                </div>
                <Tooltip title={`Vector: ${r.vector_score} | Keyword: ${r.keyword_score} | Recency: ${r.recency_score}`}>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    Score: {(r.score * 10000).toFixed(0)}
                  </Text>
                </Tooltip>
              </div>
            </Card>
          ))}
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
    </div>
  );
};

export default VectorSearchPage;
