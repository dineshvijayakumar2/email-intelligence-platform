import React, { useState } from 'react';
import { Card, Button, Spin, Tag, Typography, Space, List } from 'antd';
import { RobotOutlined } from '@ant-design/icons';
import { insightsApi } from '../services/strategicDigestService';
import type { AIInsight } from '../types/strategic-digest';

const { Text, Paragraph } = Typography;

interface AIInsightsCardProps {
  entityType: 'company' | 'contact' | 'thread';
  entityId: string;
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

const AIInsightsCard: React.FC<AIInsightsCardProps> = ({ entityType, entityId }) => {
  const [insight, setInsight] = useState<AIInsight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await insightsApi[entityType](entityId) as any;
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
          {entityType === 'company' && <CompanyInsight insight={insight} />}
          {entityType === 'contact' && <ContactInsight insight={insight} />}
          {entityType === 'thread' && <ThreadInsight insight={insight} />}
          <div style={{ marginTop: 12, textAlign: 'right' }}>
            <Button size="small" onClick={handleAnalyze}>Refresh</Button>
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
