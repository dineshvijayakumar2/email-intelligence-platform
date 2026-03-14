/**
 * Smart Inbox — AI Intelligence Inbox Page (Session 6)
 *
 * Primary intelligence view:
 * - Mailbox selector + "Analyze New Emails" button
 * - Filter bar: bucket chips, intent/urgency/sentiment dropdowns, confidence slider
 * - Table with bucket tags, urgency, subject, sender, sentiment, summary, date
 * - Detail drawer: full classification, entities, suggested action, feedback
 *
 * All business logic server-side — frontend only displays + confidence gating.
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Row, Col, Typography, Button, Table, Tag, Space, Select,
  Drawer, Descriptions, message, Empty,
} from 'antd';
import type { TableProps } from 'antd';
import {
  ReloadOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { formatDate, localDateToISOStart, formatDateForApi } from '../../utils/dateUtils';
import { MailboxSelector } from '../../components/MailboxSelector';
import { ActionBucketTag } from '../../components/ai/ActionBucketTag';
import { FeedbackButtons } from '../../components/ai/FeedbackButtons';
import { intelligenceApi, bucketApi } from '../../services/aiService';
import type {
  IntelligenceResult, IntelligenceFilterParams,
  BucketSummary, IntentType, UrgencyLevel, SentimentType, BucketType,
} from '../../types/ai';

const { Text } = Typography;

// Urgency color map
const URGENCY_COLORS: Record<string, string> = {
  critical: 'red', high: 'volcano', medium: 'orange', low: 'blue', none: 'default',
};

// Sentiment color map
const SENTIMENT_COLORS: Record<string, string> = {
  very_positive: 'green', positive: 'cyan', neutral: 'default',
  negative: 'orange', very_negative: 'red',
};

// Intent labels
const INTENT_LABELS: Record<string, string> = {
  action_required: 'Action Required', fyi_update: 'FYI', meeting_scheduling: 'Meeting',
  question: 'Question', complaint: 'Complaint', positive_feedback: 'Positive',
  pricing_inquiry: 'Pricing', feature_request: 'Feature', expansion_signal: 'Expansion',
  churn_risk: 'Churn Risk', follow_up: 'Follow-up', introduction: 'Intro', other: 'Other',
};

export const InboxPage: React.FC = () => {
  const isMountedRef = useRef(true);

  // Selection
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';

  // Data
  const [items, setItems] = useState<IntelligenceResult[]>([]);
  const [bucketSummary, setBucketSummary] = useState<BucketSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);

  // Filters
  const [filters, setFilters] = useState<IntelligenceFilterParams>({});

  // Analysis date range (days lookback)
  const [analysisRange, setAnalysisRange] = useState<number>(7);

  // Drawer
  const [drawerItem, setDrawerItem] = useState<IntelligenceResult | null>(null);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!mailboxId) return;
    const loadAll = async () => {
      setLoading(true);
      const [listResult, summary] = await Promise.all([
        intelligenceApi.list(mailboxId, { ...filters, page, page_size: pageSize }),
        bucketApi.getSummary(mailboxId),
      ]);
      if (!isMountedRef.current) return;
      setItems(listResult.items || []);
      setBucketSummary(summary);
      setLoading(false);
    };
    loadAll();
  }, [mailboxId, page, filters]);

  const loadData = async () => {
    setLoading(true);
    const result = await intelligenceApi.list(mailboxId, {
      ...filters,
      page,
      page_size: pageSize,
    });
    if (isMountedRef.current) {
      setItems(result.items || []);
      setLoading(false);
    }
  };

  const handleAnalyze = async () => {
    if (!mailboxId) return;
    setAnalyzing(true);
    // Compute timezone-aware date_from from the selected lookback range
    const fromDate = new Date();
    fromDate.setDate(fromDate.getDate() - analysisRange);
    const dateFrom = localDateToISOStart(formatDateForApi(fromDate));
    const result = await intelligenceApi.analyze(mailboxId, {
      max_emails: 500,
      date_from: dateFrom,
    });
    setAnalyzing(false);
    if (result) {
      message.success(result.message || 'Analysis started');
    } else {
      message.error('Failed to start analysis');
    }
  };

  const handleFilterChange = (key: string, value: any) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
    setPage(1);
  };

  const handleBucketClick = (bucket: BucketType) => {
    if (filters.primary_bucket === bucket) {
      handleFilterChange('primary_bucket', undefined);
    } else {
      handleFilterChange('primary_bucket', bucket);
    }
  };

  const handleTableFilters = (_pagination: any, tableFilters: any) => {
    // Sync column filters with our filter state
    const newFilters = { ...filters };
    if (tableFilters.urgency) {
      newFilters.urgency = tableFilters.urgency[0] as UrgencyLevel;
    } else {
      newFilters.urgency = undefined;
    }
    if (tableFilters.intent) {
      newFilters.intent = tableFilters.intent[0] as IntentType;
    } else {
      newFilters.intent = undefined;
    }
    if (tableFilters.sentiment) {
      newFilters.sentiment = tableFilters.sentiment[0] as SentimentType;
    } else {
      newFilters.sentiment = undefined;
    }
    if (tableFilters.bucket) {
      newFilters.primary_bucket = tableFilters.bucket[0] as BucketType;
    } else {
      newFilters.primary_bucket = undefined;
    }
    setFilters(newFilters);
    setPage(1);
  };

  const BUCKET_FILTER_OPTIONS = [
    { text: 'Response Urgency', value: 'response_urgency' },
    { text: 'Deal at Risk', value: 'deal_at_risk' },
    { text: 'Retention Risk', value: 'retention_risk' },
    { text: 'Revenue Opportunity', value: 'revenue_opportunity' },
    { text: 'New Relationship', value: 'new_relationship' },
    { text: 'Account Neglect', value: 'account_neglect' },
  ];

  const columns: TableProps<IntelligenceResult>['columns'] = [
    {
      title: 'Bucket',
      key: 'bucket',
      width: 160,
      filters: BUCKET_FILTER_OPTIONS,
      filteredValue: filters.primary_bucket ? [filters.primary_bucket] : null,
      filterMultiple: false,
      render: (_: any, r: IntelligenceResult) => {
        if (!r.action_buckets?.length) return <Tag>None</Tag>;
        return (
          <Space size={4} wrap>
            {r.action_buckets.slice(0, 2).map((b, i) => (
              <ActionBucketTag
                key={i}
                bucket={b.bucket}
                confidence={b.confidence}
                justification={b.justification}
              />
            ))}
          </Space>
        );
      },
    },
    {
      title: 'Urgency',
      dataIndex: 'urgency',
      key: 'urgency',
      width: 90,
      filters: ['critical', 'high', 'medium', 'low', 'none'].map(v => ({ text: v, value: v })),
      filteredValue: filters.urgency ? [filters.urgency] : null,
      filterMultiple: false,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) => {
        const order = ['critical', 'high', 'medium', 'low', 'none'];
        return order.indexOf(a.urgency || 'none') - order.indexOf(b.urgency || 'none');
      },
      render: (v: string) => v ? <Tag color={URGENCY_COLORS[v] || 'default'}>{v}</Tag> : null,
    },
    {
      title: 'Subject',
      key: 'subject',
      ellipsis: true,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) =>
        (a.email_subject || '').localeCompare(b.email_subject || ''),
      render: (_: any, r: IntelligenceResult) => (
        <a onClick={() => setDrawerItem(r)}>{r.email_subject || '(no subject)'}</a>
      ),
    },
    {
      title: 'Sender',
      key: 'sender',
      width: 180,
      ellipsis: true,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) =>
        (a.email_sender_name || a.email_sender || '').localeCompare(b.email_sender_name || b.email_sender || ''),
      render: (_: any, r: IntelligenceResult) => r.email_sender_name || r.email_sender || '',
    },
    {
      title: 'Intent',
      dataIndex: 'intent',
      key: 'intent',
      width: 120,
      filters: Object.entries(INTENT_LABELS).map(([k, v]) => ({ text: v, value: k })),
      filteredValue: filters.intent ? [filters.intent] : null,
      filterMultiple: false,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) =>
        (a.intent || '').localeCompare(b.intent || ''),
      render: (v: string) => v ? <Tag>{INTENT_LABELS[v] || v}</Tag> : null,
    },
    {
      title: 'Sentiment',
      dataIndex: 'sentiment',
      key: 'sentiment',
      width: 110,
      filters: ['very_positive', 'positive', 'neutral', 'negative', 'very_negative'].map(v => ({ text: v.replace('_', ' '), value: v })),
      filteredValue: filters.sentiment ? [filters.sentiment] : null,
      filterMultiple: false,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) => {
        const order = ['very_positive', 'positive', 'neutral', 'negative', 'very_negative'];
        return order.indexOf(a.sentiment || 'neutral') - order.indexOf(b.sentiment || 'neutral');
      },
      render: (v: string) => v ? <Tag color={SENTIMENT_COLORS[v] || 'default'}>{v?.replace('_', ' ')}</Tag> : null,
    },
    {
      title: 'Date',
      key: 'date',
      width: 100,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) =>
        (a.email_date || '').localeCompare(b.email_date || ''),
      render: (_: any, r: IntelligenceResult) => {
        if (!r.email_date) return null;
        return <Text type="secondary">{formatDate(r.email_date)}</Text>;
      },
    },
  ];

  // Signal summary bar (AM-centric v3)
  const bucketChips = bucketSummary ? [
    { key: 'response_urgency', label: 'Response Urgency', count: bucketSummary.response_urgency, color: 'red' },
    { key: 'deal_at_risk', label: 'Deal at Risk', count: bucketSummary.deal_at_risk, color: 'orange' },
    { key: 'retention_risk', label: 'Retention Risk', count: bucketSummary.retention_risk, color: 'red' },
    { key: 'revenue_opportunity', label: 'Revenue Opp.', count: bucketSummary.revenue_opportunity, color: 'green' },
    { key: 'new_relationship', label: 'New Relationship', count: bucketSummary.new_relationship, color: 'blue' },
    { key: 'account_neglect', label: 'Account Neglect', count: bucketSummary.account_neglect, color: 'gold' },
  ] : [];

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Header */}
      <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 16 }}>
        <Col flex="auto">
          <MailboxSelector
            value={mailboxIds}
            onChange={setMailboxIds}
            mode="single"
            placeholder="Select a mailbox"
            style={{ width: 350 }}
          />
        </Col>
        <Col>
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={loadData}
              disabled={!mailboxId}
            >
              Refresh
            </Button>
            <Select
              value={analysisRange}
              onChange={setAnalysisRange}
              style={{ width: 130 }}
              options={[
                { value: 7, label: 'Last 7 days' },
                { value: 14, label: 'Last 14 days' },
                { value: 30, label: 'Last 30 days' },
                { value: 90, label: 'Last 90 days' },
              ]}
            />
            <Button
              type="primary"
              icon={<RocketOutlined />}
              onClick={handleAnalyze}
              loading={analyzing}
              disabled={!mailboxId}
            >
              Analyze New Emails
            </Button>
          </Space>
        </Col>
      </Row>

      {/* Bucket summary chips */}
      {bucketChips.length > 0 && (
        <div className="glass-card fade-in-up" style={{ padding: '12px 16px', marginBottom: 16 }}>
          <Space size={8} wrap>
            <Text strong style={{ marginRight: 8 }}>Buckets:</Text>
            {bucketChips.map((chip) => (
              <Tag
                key={chip.key}
                color={filters.primary_bucket === chip.key ? chip.color : undefined}
                style={{
                  cursor: 'pointer',
                  borderStyle: filters.primary_bucket === chip.key ? 'solid' : 'dashed',
                  opacity: chip.count === 0 ? 0.4 : 1,
                }}
                onClick={() => handleBucketClick(chip.key as BucketType)}
              >
                {chip.label}: {chip.count}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {/* Main table */}
      {!mailboxId ? (
        <div className="glass-card" style={{ padding: 60, textAlign: 'center' }}>
          <Empty description="Select a mailbox to view AI intelligence" />
        </div>
      ) : (
        <div className="glass-card fade-in-up" style={{ padding: 0 }}>
          <Table<IntelligenceResult>
            columns={columns}
            dataSource={items}
            loading={loading}
            rowKey={(r) => r.id || r.email_id || Math.random().toString()}
            pagination={{
              current: page,
              pageSize,
              onChange: setPage,
              showSizeChanger: false,
              showTotal: (total) => `${total} results`,
            }}
            size="small"
            scroll={{ x: 1100 }}
            onChange={handleTableFilters}
            onRow={(record) => ({
              onClick: () => setDrawerItem(record),
              style: { cursor: 'pointer' },
            })}
          />
        </div>
      )}

      {/* Detail drawer */}
      <Drawer
        title={drawerItem?.email_subject || 'Email Intelligence'}
        open={!!drawerItem}
        onClose={() => setDrawerItem(null)}
        width={560}
      >
        {drawerItem && <IntelligenceDetail item={drawerItem} />}
      </Drawer>
    </div>
  );
};

// ============================================================================
// Detail panel inside drawer
// ============================================================================

const IntelligenceDetail: React.FC<{ item: IntelligenceResult }> = ({ item }) => {
  const [bodyView, setBodyView] = useState<'html' | 'text'>(item.email_body_html ? 'html' : 'text');
  const recipients = (item.email_recipients || [])
    .map((r: any) => typeof r === 'string' ? r : r?.email || r?.name || '')
    .filter(Boolean);

  const hasHtml = !!item.email_body_html;
  const hasText = !!item.email_body;

  return (
    <div>
      {/* Email Header */}
      <Descriptions column={1} size="small" style={{ marginBottom: 12 }}>
        <Descriptions.Item label="From">
          <Text strong>{item.email_sender_name || item.email_sender}</Text>
          {item.email_sender_name && <Text type="secondary"> &lt;{item.email_sender}&gt;</Text>}
        </Descriptions.Item>
        {recipients.length > 0 && (
          <Descriptions.Item label="To">
            <Text type="secondary">{recipients.join(', ')}</Text>
          </Descriptions.Item>
        )}
        <Descriptions.Item label="Date">
          {item.email_date ? formatDate(item.email_date) : 'N/A'}
        </Descriptions.Item>
      </Descriptions>

      {/* View toggle */}
      {hasHtml && hasText && (
        <Space size={4} style={{ marginBottom: 8 }}>
          <Button size="small" type={bodyView === 'html' ? 'primary' : 'default'} onClick={() => setBodyView('html')}>HTML</Button>
          <Button size="small" type={bodyView === 'text' ? 'primary' : 'default'} onClick={() => setBodyView('text')}>Plain Text</Button>
        </Space>
      )}

      {/* Email Body */}
      {hasHtml && bodyView === 'html' ? (
        <iframe
          srcDoc={`<!DOCTYPE html><html><head><meta charset="UTF-8"><base target="_blank"><style>
            html, body { margin: 0; padding: 0; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.6; color: #333; padding: 16px; }
            img { max-width: 100%; height: auto; }
            a { color: #667eea; }
            blockquote { border-left: 3px solid #d9d9d9; padding-left: 16px; margin-left: 0; color: #666; }
            pre { background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }
          </style></head><body>${item.email_body_html}</body></html>`}
          style={{ width: '100%', minHeight: 300, border: '1px solid #f0f0f0', borderRadius: 6, marginBottom: 16 }}
          sandbox="allow-same-origin"
        />
      ) : hasText ? (
        <div style={{
          marginBottom: 16, padding: 12, background: '#fafafa', borderRadius: 6,
          border: '1px solid #f0f0f0', maxHeight: 400, overflowY: 'auto',
          whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6,
        }}>
          {item.email_body}
        </div>
      ) : (
        <div style={{ marginBottom: 16, padding: 12, background: '#fafafa', borderRadius: 6, border: '1px solid #f0f0f0' }}>
          <Text type="secondary">No email content available</Text>
        </div>
      )}

      {/* AI Classification */}
      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12, marginBottom: 12 }}>
        <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>AI Classification</Text>
        <Space wrap size={6}>
          <Tag>{INTENT_LABELS[item.intent || ''] || item.intent}</Tag>
          <Tag color={URGENCY_COLORS[item.urgency || ''] || 'default'}>{item.urgency}</Tag>
          <Tag color={SENTIMENT_COLORS[item.sentiment || ''] || 'default'}>{item.sentiment?.replace('_', ' ')}</Tag>
          {item.confidence != null && <Tag>Confidence: {Math.round(item.confidence * 100)}%</Tag>}
        </Space>
      </div>

      {/* Buckets */}
      {item.action_buckets?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Text strong>Action Buckets:</Text>
          <div style={{ marginTop: 4 }}>
            <Space wrap>
              {item.action_buckets.map((b, i) => (
                <ActionBucketTag key={i} bucket={b.bucket} confidence={b.confidence} justification={b.justification} />
              ))}
            </Space>
          </div>
        </div>
      )}

      {/* Suggested Action */}
      {item.suggested_action && (
        <div style={{ marginBottom: 12 }}>
          <Text strong>Suggested Action:</Text>
          <p style={{ margin: '4px 0' }}>{item.suggested_action}</p>
        </div>
      )}

      {/* Key Topics */}
      {item.key_topics?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Text strong>Key Topics:</Text>
          <div style={{ marginTop: 4 }}>
            <Space wrap>
              {item.key_topics.map((t, i) => <Tag key={i}>{t}</Tag>)}
            </Space>
          </div>
        </div>
      )}

      {/* Entities */}
      {(item.competitors_mentioned?.length > 0 || item.products_mentioned?.length > 0 || item.buying_signals?.length > 0) && (
        <Descriptions column={1} size="small" bordered style={{ marginBottom: 12 }}>
          {item.competitors_mentioned?.length > 0 && (
            <Descriptions.Item label="Competitors">
              <Space wrap>{item.competitors_mentioned.map((c, i) => <Tag key={i} color="volcano">{c}</Tag>)}</Space>
            </Descriptions.Item>
          )}
          {item.products_mentioned?.length > 0 && (
            <Descriptions.Item label="Products">
              <Space wrap>{item.products_mentioned.map((p, i) => <Tag key={i} color="blue">{p}</Tag>)}</Space>
            </Descriptions.Item>
          )}
          {item.buying_signals?.length > 0 && (
            <Descriptions.Item label="Buying Signals">
              <Space wrap>{item.buying_signals.map((s, i) => <Tag key={i} color="green">{s}</Tag>)}</Space>
            </Descriptions.Item>
          )}
        </Descriptions>
      )}

      {/* Feedback */}
      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
        <Text strong style={{ marginBottom: 8, display: 'block' }}>Was this classification correct?</Text>
        <FeedbackButtons
          emailId={item.email_id || ''}
          currentFeedback={item.human_feedback || undefined}
        />
      </div>
    </div>
  );
};

export default InboxPage;
