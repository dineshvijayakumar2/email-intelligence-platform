import React, { useState } from 'react';
import { Card, Button, Spin, Tag, Typography, Space, List } from 'antd';
import { RobotOutlined } from '@ant-design/icons';
import { insightsApi } from '../services/strategicDigestService';
import type { AIInsight } from '../types/strategic-digest';

const { Text, Paragraph } = Typography;

interface AIInsightsCardProps {
  entityType: 'company' | 'contact' | 'thread';
  entityId: string;
  clientId?: string;
}

const riskColor = (level?: string): string => {
  if (!level) return 'default';
  const l = level.toLowerCase();
  if (l === 'low') return 'green';
  if (l === 'medium') return 'orange';
  if (l === 'high' || l === 'critical') return 'red';
  return 'default';
};

const trendColor = (trend?: string): string => {
  if (!trend) return 'default';
  const t = trend.toLowerCase();
  if (t === 'up' || t === 'increasing' || t === 'growing') return 'green';
  if (t === 'stable' || t === 'steady') return 'blue';
  if (t === 'down' || t === 'decreasing' || t === 'declining') return 'red';
  return 'default';
};

const importanceColor = (level?: string): string => {
  if (!level) return 'default';
  const l = level.toLowerCase();
  if (l === 'high' || l === 'critical') return 'red';
  if (l === 'medium') return 'orange';
  if (l === 'low') return 'green';
  return 'blue';
};

const BulletList: React.FC<{ items?: string[]; header: string }> = ({ items, header }) => {
  if (!items || items.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <Text strong>{header}</Text>
      <List
        size="small"
        dataSource={items}
        renderItem={(item) => (
          <List.Item style={{ padding: '4px 0', borderBottom: 'none' }}>
            <Text>&bull; {item}</Text>
          </List.Item>
        )}
      />
    </div>
  );
};

const CompanyInsight: React.FC<{ insight: AIInsight }> = ({ insight }) => (
  <Space direction="vertical" style={{ width: '100%' }} size="small">
    {insight.health_summary && <Paragraph style={{ marginBottom: 4 }}>{insight.health_summary}</Paragraph>}
    <Space wrap>
      {insight.revenue_risk && <span>Revenue Risk: <Tag color={riskColor(insight.revenue_risk)}>{insight.revenue_risk}</Tag></span>}
      {insight.engagement_trend && <span>Engagement Trend: <Tag color={trendColor(insight.engagement_trend)}>{insight.engagement_trend}</Tag></span>}
    </Space>
    <BulletList items={insight.key_observations} header="Key Observations" />
    <BulletList items={insight.recommended_actions} header="Recommended Actions" />
  </Space>
);

const ContactInsight: React.FC<{ insight: AIInsight }> = ({ insight }) => (
  <Space direction="vertical" style={{ width: '100%' }} size="small">
    {insight.engagement_summary && <Paragraph style={{ marginBottom: 4 }}>{insight.engagement_summary}</Paragraph>}
    {insight.importance_level && (
      <div>Importance: <Tag color={importanceColor(insight.importance_level)}>{insight.importance_level}</Tag></div>
    )}
    {insight.follow_up_suggestion && (
      <div style={{ marginTop: 8 }}>
        <Text strong>Follow-up Suggestion</Text>
        <Paragraph style={{ marginBottom: 0, marginTop: 4 }}>{insight.follow_up_suggestion}</Paragraph>
      </div>
    )}
    <BulletList items={insight.key_observations} header="Key Observations" />
  </Space>
);

const ThreadInsight: React.FC<{ insight: AIInsight }> = ({ insight }) => (
  <Space direction="vertical" style={{ width: '100%' }} size="small">
    {insight.thread_summary && <Paragraph style={{ marginBottom: 4 }}>{insight.thread_summary}</Paragraph>}
    <Space wrap>
      {insight.deal_probability != null && (
        <span>Deal Probability: <Tag color={insight.deal_probability >= 70 ? 'green' : insight.deal_probability >= 40 ? 'orange' : 'red'}>{insight.deal_probability}/100</Tag></span>
      )}
      {insight.risk_level && <span>Risk: <Tag color={riskColor(insight.risk_level)}>{insight.risk_level}</Tag></span>}
    </Space>
    <BulletList items={insight.key_signals} header="Key Signals" />
    {insight.recommended_action && (
      <div style={{ marginTop: 8 }}>
        <Text strong>Recommended Action</Text>
        <Paragraph style={{ marginBottom: 0, marginTop: 4 }}>{insight.recommended_action}</Paragraph>
      </div>
    )}
  </Space>
);

/** Fallback: render any key-value pairs from the insight when typed fields don't match */
const SKIP_KEYS = new Set(['_entity_type', '_entity_id', '_generated_at', '_model', '_ai_insight', 'error']);

const GenericInsight: React.FC<{ insight: Record<string, any> }> = ({ insight }) => (
  <Space direction="vertical" style={{ width: '100%' }} size="small">
    {Object.entries(insight)
      .filter(([k]) => !SKIP_KEYS.has(k))
      .map(([key, value]) => {
        const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        if (Array.isArray(value)) {
          return <BulletList key={key} items={value.map(String)} header={label} />;
        }
        if (typeof value === 'string') {
          // Long strings as paragraphs, short as tag
          if (value.length > 80) return <div key={key}><Text strong>{label}: </Text><Paragraph style={{ marginBottom: 4 }}>{value}</Paragraph></div>;
          return <div key={key}><Text strong>{label}: </Text><Tag>{value}</Tag></div>;
        }
        if (typeof value === 'number') {
          return <div key={key}><Text strong>{label}: </Text><Tag color="blue">{value}</Tag></div>;
        }
        return null;
      })}
  </Space>
);

/** Check if any typed insight field is present */
const hasTypedFields = (data: any): boolean =>
  !!(data?.health_summary || data?.engagement_summary || data?.thread_summary);

const AIInsightsCard: React.FC<AIInsightsCardProps> = ({ entityType, entityId, clientId }) => {
  const [insight, setInsight] = useState<AIInsight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await insightsApi[entityType](entityId, false, clientId) as any;
      if (!result) {
        setError('Request timed out — the AI model may be slow. Try again.');
        return;
      }
      const data: AIInsight = result?.insight ?? result?.data?.insight ?? result;
      if (data?.error) {
        setError(data.error);
      } else {
        setInsight(data);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to generate AI insight');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card
      style={{ marginTop: 16 }}
      className="glass-card"
      title={
        <Space>
          <RobotOutlined style={{ color: '#667eea' }} />
          <Text strong>AI Insights</Text>
        </Space>
      }
      extra={
        !insight && !loading ? (
          <Button type="primary" icon={<RobotOutlined />} onClick={handleAnalyze}>
            Analyze with AI
          </Button>
        ) : null
      }
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin size="large" />
          <div style={{ marginTop: 12 }}><Text type="secondary">Analyzing...</Text></div>
        </div>
      )}

      {error && !loading && (
        <Text type="danger">{error}</Text>
      )}

      {insight && !loading && (
        <>
          {hasTypedFields(insight) ? (
            <>
              {entityType === 'company' && <CompanyInsight insight={insight} />}
              {entityType === 'contact' && <ContactInsight insight={insight} />}
              {entityType === 'thread' && <ThreadInsight insight={insight} />}
            </>
          ) : (
            <GenericInsight insight={insight as any} />
          )}
          <div style={{ marginTop: 12, textAlign: 'right' }}>
            <Button size="small" onClick={handleAnalyze} loading={loading}>Refresh</Button>
          </div>
        </>
      )}

      {!insight && !loading && !error && (
        <Text type="secondary">Click "Analyze with AI" to generate insights for this {entityType}.</Text>
      )}
    </Card>
  );
};

export default AIInsightsCard;
