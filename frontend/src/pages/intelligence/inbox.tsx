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
  Row, Col, Typography, Button, Table, Tag, Space, Select, Slider,
  Drawer, Descriptions, Alert, Spin, message, Statistic, Empty,
} from 'antd';
import type { TableProps } from 'antd';
import {
  ThunderboltOutlined, FilterOutlined, ReloadOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { MailboxSelector } from '../../components/MailboxSelector';
import { ActionBucketTag } from '../../components/ai/ActionBucketTag';
import { FeedbackButtons } from '../../components/ai/FeedbackButtons';
import { intelligenceApi, bucketApi } from '../../services/aiService';
import type {
  IntelligenceResult, IntelligenceFilterParams,
  BucketSummary, IntentType, UrgencyLevel, SentimentType, BucketType,
} from '../../types/ai';

const { Title, Text } = Typography;

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
    const result = await intelligenceApi.analyze(mailboxId, { max_emails: 500 });
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

  const columns: TableProps<IntelligenceResult>['columns'] = [
    {
      title: 'Bucket',
      key: 'bucket',
      width: 160,
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
      render: (v: string) => v ? <Tag color={URGENCY_COLORS[v] || 'default'}>{v}</Tag> : null,
    },
    {
      title: 'Subject',
      key: 'subject',
      ellipsis: true,
      render: (_: any, r: IntelligenceResult) => (
        <a onClick={() => setDrawerItem(r)}>{r.email_subject || '(no subject)'}</a>
      ),
    },
    {
      title: 'Sender',
      key: 'sender',
      width: 180,
      ellipsis: true,
      render: (_: any, r: IntelligenceResult) => r.email_sender_name || r.email_sender || '',
    },
    {
      title: 'Intent',
      dataIndex: 'intent',
      key: 'intent',
      width: 120,
      render: (v: string) => v ? <Tag>{INTENT_LABELS[v] || v}</Tag> : null,
    },
    {
      title: 'Sentiment',
      dataIndex: 'sentiment',
      key: 'sentiment',
      width: 110,
      render: (v: string) => v ? <Tag color={SENTIMENT_COLORS[v] || 'default'}>{v?.replace('_', ' ')}</Tag> : null,
    },
    {
      title: 'Score',
      dataIndex: 'business_signal_score',
      key: 'score',
      width: 70,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) =>
        (a.business_signal_score || 0) - (b.business_signal_score || 0),
      render: (v: number) => v > 0 ? <Text strong>{v}</Text> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Date',
      key: 'date',
      width: 100,
      render: (_: any, r: IntelligenceResult) => {
        if (!r.email_date) return null;
        const d = new Date(r.email_date);
        return <Text type="secondary">{d.toLocaleDateString()}</Text>;
      },
    },
  ];

  // Bucket summary bar
  const bucketChips = bucketSummary ? [
    { key: 'buying_signal', label: 'Buying Signal', count: bucketSummary.buying_signal, color: 'green' },
    { key: 'expansion_signal', label: 'Expansion', count: bucketSummary.expansion_signal, color: 'blue' },
    { key: 'churn_risk', label: 'Churn Risk', count: bucketSummary.churn_risk, color: 'red' },
    { key: 'competitor_threat', label: 'Competitor', count: bucketSummary.competitor_threat, color: 'volcano' },
    { key: 'missed_opportunity', label: 'Missed Opp.', count: bucketSummary.missed_opportunity, color: 'magenta' },
    { key: 'stakeholder_entry', label: 'Stakeholder', count: bucketSummary.stakeholder_entry, color: 'purple' },
    { key: 'silent_champion', label: 'Silent', count: bucketSummary.silent_champion, color: 'orange' },
    { key: 'unresolved_block', label: 'Blocked', count: bucketSummary.unresolved_block, color: 'gold' },
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

      {/* Filter bar */}
      <div className="glass-card fade-in-up" style={{ padding: '12px 16px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <FilterOutlined style={{ marginRight: 8 }} />
          </Col>
          <Col>
            <Select
              placeholder="Intent"
              allowClear
              style={{ width: 140 }}
              size="small"
              value={filters.intent}
              onChange={(v) => handleFilterChange('intent', v)}
              options={Object.entries(INTENT_LABELS).map(([k, v]) => ({ value: k, label: v }))}
            />
          </Col>
          <Col>
            <Select
              placeholder="Urgency"
              allowClear
              style={{ width: 120 }}
              size="small"
              value={filters.urgency}
              onChange={(v) => handleFilterChange('urgency', v)}
              options={['critical', 'high', 'medium', 'low', 'none'].map(v => ({ value: v, label: v }))}
            />
          </Col>
          <Col>
            <Select
              placeholder="Sentiment"
              allowClear
              style={{ width: 140 }}
              size="small"
              value={filters.sentiment}
              onChange={(v) => handleFilterChange('sentiment', v)}
              options={['very_positive', 'positive', 'neutral', 'negative', 'very_negative'].map(v => ({ value: v, label: v.replace('_', ' ') }))}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Min confidence:
            </Text>
          </Col>
          <Col>
            <Slider
              min={0}
              max={100}
              step={5}
              defaultValue={0}
              style={{ width: 120 }}
              tooltip={{ formatter: (v) => `${v}%` }}
              onChangeComplete={(v: number) => handleFilterChange('min_confidence', v > 0 ? v / 100 : undefined)}
            />
          </Col>
        </Row>
      </div>

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
  return (
    <div>
      {/* Classification */}
      <Descriptions title="Classification" column={2} size="small" bordered style={{ marginBottom: 16 }}>
        <Descriptions.Item label="Intent">
          <Tag>{INTENT_LABELS[item.intent || ''] || item.intent}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Urgency">
          <Tag color={URGENCY_COLORS[item.urgency || ''] || 'default'}>{item.urgency}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Sentiment">
          <Tag color={SENTIMENT_COLORS[item.sentiment || ''] || 'default'}>{item.sentiment?.replace('_', ' ')}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Confidence">
          {item.confidence != null ? `${Math.round(item.confidence * 100)}%` : 'N/A'}
        </Descriptions.Item>
        <Descriptions.Item label="Action Type" span={2}>
          {item.action_type?.replace(/_/g, ' ')}
        </Descriptions.Item>
        <Descriptions.Item label="Business Signal" span={2}>
          {item.business_signal?.replace(/_/g, ' ') || 'None'}
        </Descriptions.Item>
      </Descriptions>

      {/* Summary */}
      <div style={{ marginBottom: 16 }}>
        <Text strong>Summary:</Text>
        <p style={{ margin: '4px 0' }}>{item.summary}</p>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text strong>Suggested Action:</Text>
        <p style={{ margin: '4px 0' }}>{item.suggested_action}</p>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text strong>Justification:</Text>
        <p style={{ margin: '4px 0', color: '#999', fontSize: 12 }}>{item.justification}</p>
      </div>

      {/* Buckets */}
      {item.action_buckets?.length > 0 && (
        <div style={{ marginBottom: 16 }}>
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

      {/* Key Topics */}
      {item.key_topics?.length > 0 && (
        <div style={{ marginBottom: 16 }}>
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
        <Descriptions title="Entities" column={1} size="small" bordered style={{ marginBottom: 16 }}>
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
          {item.budget_signals && (
            <Descriptions.Item label="Budget">
              {item.budget_signals.amount || 'N/A'} — {item.budget_signals.timeframe || ''} — {item.budget_signals.context || ''}
            </Descriptions.Item>
          )}
        </Descriptions>
      )}

      {/* Signal Score */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Statistic title="Signal Score" value={item.business_signal_score || 0} suffix="/100" />
        </Col>
        <Col span={8}>
          <Statistic title="Confidence" value={item.confidence != null ? Math.round(item.confidence * 100) : 0} suffix="%" />
        </Col>
        <Col span={8}>
          <Statistic title="Model" value={item.model_used || 'N/A'} valueStyle={{ fontSize: 14 }} />
        </Col>
      </Row>

      {/* Feedback */}
      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 16 }}>
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
