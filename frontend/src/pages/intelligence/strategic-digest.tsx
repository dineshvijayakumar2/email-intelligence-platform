/**
 * Strategic Digest Page — Sprint 3
 *
 * Displays AI-generated strategic digest with executive summary,
 * AM performance, relationship health, pipeline, risks, opportunities,
 * competitive landscape, and action items.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Typography, Tag, Select, Button, Row, Col, Spin, Alert,
  Table, Space, Descriptions, Empty, Progress,
} from 'antd';
import {
  ThunderboltOutlined, ArrowUpOutlined, ArrowDownOutlined, MinusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { strategicDigestApi } from '../../services/strategicDigestService';
import type { StrategicDigest, PeriodType } from '../../types/strategic-digest';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { formatRelativeTime } from '../../utils/dateUtils';

const { Title, Text, Paragraph } = Typography;

const BUCKET_COLORS: Record<string, string> = {
  buying_signal: 'green', expansion_signal: 'blue', churn_risk: 'red',
  competitor_threat: 'volcano', missed_opportunity: 'orange',
  stakeholder_entry: 'purple', silent_champion: 'gold', unresolved_block: 'yellow',
};

const PERIOD_OPTIONS = [
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'ytd', label: 'Year to Date' },
];

const SEVERITY_TYPE: Record<string, 'error' | 'warning' | 'info'> = {
  critical: 'error',
  high: 'warning',
  medium: 'info',
};

function trendIcon(trend?: string) {
  if (!trend) return <MinusOutlined style={{ color: '#999' }} />;
  const t = trend.toLowerCase();
  if (t === 'up' || t === 'increasing' || t === 'improving') return <ArrowUpOutlined style={{ color: '#52c41a' }} />;
  if (t === 'down' || t === 'decreasing' || t === 'declining') return <ArrowDownOutlined style={{ color: '#f5222d' }} />;
  return <MinusOutlined style={{ color: '#999' }} />;
}

function fmtCurrency(val?: number) {
  if (val == null) return '-';
  return `$${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function fmtPct(val?: number) {
  if (val == null) return '-';
  return `${val >= 0 ? '+' : ''}${val.toFixed(1)}%`;
}

export default function StrategicDigestPage() {
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [periodType, setPeriodType] = useState<PeriodType>('monthly');
  const [digest, setDigest] = useState<StrategicDigest | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState<{ pct: number; message: string; phase: string } | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadDigest = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    setError('');
    try {
      const resp = await strategicDigestApi.get(clientId, periodType);
      if (!isMountedRef.current) return;
      setDigest(resp?.digest ?? null);
    } catch (err: any) {
      if (isMountedRef.current) setError(err?.message || 'Failed to load digest');
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [clientId, periodType]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (clientId) loadDigest();
  }, [clientId, periodType, loadDigest]);

  const stopPolling = () => {
    if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null; }
  };

  const handleGenerate = async () => {
    if (!clientId) return;
    setGenerating(true);
    setError('');
    setProgress({ pct: 0, phase: 'starting', message: 'Initialising…' });
    stopPolling();

    try {
      await strategicDigestApi.generate(clientId, periodType);
    } catch (err: any) {
      if (isMountedRef.current) {
        setError(err?.message || 'Failed to start generation');
        setGenerating(false);
        setProgress(null);
      }
      return;
    }

    // Poll progress + completion
    const poll = async () => {
      if (!isMountedRef.current) return;
      try {
        const prog = await strategicDigestApi.getProgress(clientId);
        if (isMountedRef.current) {
          setProgress({ pct: prog.pct, phase: prog.phase, message: prog.message });
        }

        if (prog.phase === 'completed') {
          // Load the finished digest
          try {
            const resp = await strategicDigestApi.get(clientId, periodType);
            if (isMountedRef.current) setDigest(resp?.digest ?? null);
          } catch { /* ignore */ }
          setGenerating(false);
          setProgress(null);
          return;
        }

        if (prog.phase === 'failed') {
          if (isMountedRef.current) setError(prog.message || 'Generation failed');
          setGenerating(false);
          setProgress(null);
          return;
        }
      } catch { /* keep polling */ }

      pollRef.current = setTimeout(poll, 4000);
    };

    pollRef.current = setTimeout(poll, 3000);
  };

  // Clean up poll on unmount
  useEffect(() => () => stopPolling(), []);

  // AM Performance columns
  const amColumns = [
    { title: 'Account Manager', dataIndex: 'account_manager', key: 'account_manager' },
    {
      title: 'Revenue', dataIndex: 'total_revenue', key: 'total_revenue',
      render: (v: number) => fmtCurrency(v),
    },
    {
      title: 'Change', dataIndex: 'revenue_change_pct', key: 'revenue_change_pct',
      render: (v: number) => {
        if (v == null) return '-';
        const color = v >= 0 ? '#52c41a' : '#f5222d';
        return <Text style={{ color }}>{fmtPct(v)}</Text>;
      },
    },
    {
      title: 'Conversion Rate', dataIndex: 'quote_conversion_rate', key: 'quote_conversion_rate',
      render: (v: number) => v != null ? `${(v * 100).toFixed(1)}%` : '-',
    },
    {
      title: 'Avg Response (hrs)', dataIndex: 'avg_response_time_hours', key: 'avg_response_time_hours',
      render: (v: number) => v != null ? v.toFixed(1) : '-',
    },
    {
      title: 'Retention', dataIndex: 'retention_rate', key: 'retention_rate',
      render: (v: number) => v != null ? `${(v * 100).toFixed(1)}%` : '-',
    },
  ];

  // Pipeline quote columns
  const quoteColumns = [
    { title: 'Quote #', dataIndex: 'quote_no', key: 'quote_no' },
    { title: 'Company', dataIndex: 'company', key: 'company' },
    { title: 'Amount', dataIndex: 'amount', key: 'amount', render: (v: number) => fmtCurrency(v) },
    { title: 'Date', dataIndex: 'date_created', key: 'date_created' },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (v: string) => <Tag>{v || '-'}</Tag> },
  ];

  // Action items columns
  const actionColumns = [
    {
      title: 'Priority', dataIndex: 'priority', key: 'priority', width: 80,
      render: (v: number) => (
        <Tag color={v <= 2 ? 'red' : v <= 3 ? 'orange' : 'blue'}>P{v}</Tag>
      ),
    },
    { title: 'Action', dataIndex: 'action', key: 'action' },
    { title: 'Company', dataIndex: 'company', key: 'company', render: (v: string) => v || '-' },
    {
      title: 'Bucket', dataIndex: 'bucket', key: 'bucket',
      render: (v: string) => v ? <Tag color={BUCKET_COLORS[v] || 'default'}>{v.replace(/_/g, ' ')}</Tag> : '-',
    },
  ];

  const amData = Array.isArray(digest?.am_performance) ? digest.am_performance : [];
  const pipeline = digest?.pipeline_intelligence;
  const risks = digest?.risk_alerts || [];
  const opportunities = digest?.opportunities || [];
  const competitive = digest?.competitive_landscape;
  const actionItems = digest?.action_items || [];
  const relationships = digest?.relationship_health || [];

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <Title level={3} style={{ margin: 0 }}>
          <ThunderboltOutlined style={{ color: '#667eea', marginRight: 8 }} />
          Strategic Digest
        </Title>
        <Space wrap>
          <ClientSelector value={clientId} onChange={setClientId} />
          <Select
            value={periodType}
            onChange={(v) => setPeriodType(v)}
            style={{ width: 140 }}
            options={PERIOD_OPTIONS}
          />
          <Button
            type="primary"
            onClick={handleGenerate}
            loading={generating}
            icon={<ReloadOutlined />}
          >
            Generate Digest
          </Button>
        </Space>
      </div>

      {error && <Alert message={error} type="warning" showIcon closable style={{ marginBottom: 16 }} />}

      {!clientId && (
        <Card className="glass-card">
          <Empty description="Select a client to view the strategic digest" />
        </Card>
      )}

      {loading && clientId && !generating && (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}><Text type="secondary">Loading digest…</Text></div>
        </div>
      )}

      {generating && clientId && (
        <Card className="glass-card" style={{ padding: '32px 48px' }}>
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <Text strong style={{ fontSize: 16 }}>
              {progress?.phase === 'ai_analysis' ? 'Running AI Analysis' :
               progress?.phase === 'am_performance' ? 'Building AM Performance' :
               progress?.phase === 'building_context' ? 'Building Relationship Context' :
               'Generating Strategic Digest'}
            </Text>
          </div>
          <Progress
            percent={progress?.pct ?? 0}
            status={progress?.phase === 'failed' ? 'exception' : 'active'}
            strokeColor={
              progress?.phase === 'ai_analysis' ? '#667eea' :
              progress?.phase === 'am_performance' ? '#52c41a' : '#1890ff'
            }
            style={{ marginBottom: 12 }}
          />
          <div style={{ textAlign: 'center' }}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              {progress?.message || 'Please wait — this may take several minutes for large accounts…'}
            </Text>
          </div>
          {(progress?.pct ?? 0) < 90 && progress?.phase === 'building_context' && (
            <div style={{ textAlign: 'center', marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                Tip: You can navigate away — generation continues in the background.
              </Text>
            </div>
          )}
        </Card>
      )}

      {!loading && !generating && clientId && !digest && !error && (
        <Card className="glass-card" style={{ textAlign: 'center', padding: 40 }}>
          <Empty description="No strategic digest available for this period.">
            <Button type="primary" onClick={handleGenerate} loading={generating}>
              Generate Digest Now
            </Button>
          </Empty>
        </Card>
      )}

      {!loading && !generating && digest && !error && (
        <>
          {/* Meta info */}
          <Card className="glass-card" size="small" style={{ marginBottom: 16 }}>
            <Space wrap size="large">
              <Text type="secondary">
                Period: {digest.period_start} to {digest.period_end}
              </Text>
              {digest.emails_analyzed != null && (
                <Text type="secondary">{digest.emails_analyzed} emails analyzed</Text>
              )}
              {digest.companies_analyzed != null && (
                <Text type="secondary">{digest.companies_analyzed} companies</Text>
              )}
              {digest.contacts_analyzed != null && (
                <Text type="secondary">{digest.contacts_analyzed} contacts</Text>
              )}
              {digest.created_at && (
                <Text type="secondary">Generated {formatRelativeTime(digest.created_at)}</Text>
              )}
              {digest.total_cost_usd != null && (
                <Text type="secondary">Cost: ${digest.total_cost_usd.toFixed(4)}</Text>
              )}
            </Space>
          </Card>

          {/* Section 1: Executive Summary */}
          <Card className="glass-card" title="Executive Summary" style={{ marginBottom: 16 }}>
            <Paragraph style={{ fontSize: 15, lineHeight: 1.8, marginBottom: 0 }}>
              {digest.executive_summary || 'No executive summary available.'}
            </Paragraph>
          </Card>

          {/* Section 2: AM Performance */}
          {amData.length > 0 && (
            <Card className="glass-card" title="Account Manager Performance" style={{ marginBottom: 16 }}>
              <Table
                dataSource={amData}
                columns={amColumns}
                rowKey="account_manager"
                pagination={false}
                size="small"
              />
            </Card>
          )}

          {/* Section 3: Relationship Health */}
          {relationships.length > 0 && (
            <Card className="glass-card" title="Relationship Health" style={{ marginBottom: 16 }}>
              <Row gutter={[12, 12]}>
                {relationships.map((r, idx) => (
                  <Col xs={24} sm={12} md={8} lg={6} key={r.company_id || idx}>
                    <Card
                      size="small"
                      hoverable
                      onClick={() => r.company_id ? navigate(`/analytics/company/${r.company_id}`) : undefined}
                      style={{ height: '100%' }}
                    >
                      <Text strong style={{ display: 'block', marginBottom: 4 }}>{r.company_name}</Text>
                      <Space wrap size={4} style={{ marginBottom: 8 }}>
                        {r.tier && <Tag color="blue">{r.tier}</Tag>}
                        {r.engagement_score != null && (
                          <Tag color={r.engagement_score >= 70 ? 'green' : r.engagement_score >= 40 ? 'orange' : 'red'}>
                            Score: {r.engagement_score}
                          </Tag>
                        )}
                      </Space>
                      <div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          Revenue: {fmtCurrency(r.revenue)} {trendIcon(r.revenue_trend)}
                        </Text>
                      </div>
                      {r.engagement_trend && (
                        <div>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            Engagement: {trendIcon(r.engagement_trend)}
                          </Text>
                        </div>
                      )}
                      {r.key_signal && (
                        <div style={{ marginTop: 4 }}>
                          <Text type="secondary" style={{ fontSize: 11, fontStyle: 'italic' }}>{r.key_signal}</Text>
                        </div>
                      )}
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>
          )}

          {/* Section 4: Pipeline Intelligence */}
          {pipeline && (
            <Card className="glass-card" title="Pipeline Intelligence" style={{ marginBottom: 16 }}>
              <Row gutter={24} style={{ marginBottom: 16 }}>
                <Col>
                  <Descriptions size="small" column={4}>
                    <Descriptions.Item label="Total Pipeline">{fmtCurrency(pipeline.total_pipeline_value)}</Descriptions.Item>
                    <Descriptions.Item label="Open Quotes">{pipeline.open_quotes ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="Active Jobs">{pipeline.active_jobs ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="Conversion Rate">
                      {pipeline.quote_conversion_rate != null ? `${(pipeline.quote_conversion_rate * 100).toFixed(1)}%` : '-'}
                    </Descriptions.Item>
                  </Descriptions>
                </Col>
              </Row>
              {pipeline.quotes && pipeline.quotes.length > 0 && (
                <Table
                  dataSource={pipeline.quotes}
                  columns={quoteColumns}
                  rowKey="quote_no"
                  pagination={false}
                  size="small"
                />
              )}
            </Card>
          )}

          {/* Section 5: Risk Alerts */}
          {risks.length > 0 && (
            <Card className="glass-card" title={`Risk Alerts (${risks.length})`} style={{ marginBottom: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                {risks.map((risk, idx) => (
                  <Alert
                    key={idx}
                    type={SEVERITY_TYPE[risk.severity] || 'info'}
                    showIcon
                    message={
                      <Space>
                        <Text strong>{risk.company_name}</Text>
                        <Tag color={risk.severity === 'critical' ? 'red' : risk.severity === 'high' ? 'orange' : 'blue'}>
                          {risk.severity}
                        </Tag>
                        <Text type="secondary">{risk.risk_type.replace(/_/g, ' ')}</Text>
                      </Space>
                    }
                    description={
                      <span>
                        {risk.description}
                        {risk.revenue_at_risk != null && (
                          <Text type="danger" style={{ marginLeft: 8 }}>
                            Revenue at risk: {fmtCurrency(risk.revenue_at_risk)}
                          </Text>
                        )}
                      </span>
                    }
                  />
                ))}
              </Space>
            </Card>
          )}

          {/* Section 6: Opportunities */}
          {opportunities.length > 0 && (
            <Card className="glass-card" title={`Opportunities (${opportunities.length})`} style={{ marginBottom: 16 }}>
              <Row gutter={[12, 12]}>
                {opportunities.map((opp, idx) => (
                  <Col xs={24} md={12} key={idx}>
                    <Card
                      size="small"
                      style={{ borderLeft: '3px solid #52c41a' }}
                    >
                      <Space wrap style={{ marginBottom: 8 }}>
                        <Tag color="green">{opp.opportunity_type.replace(/_/g, ' ')}</Tag>
                        <Text strong>{opp.company_name}</Text>
                        {opp.estimated_value != null && (
                          <Tag color="gold">{fmtCurrency(opp.estimated_value)}</Tag>
                        )}
                        {opp.confidence != null && (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {(opp.confidence * 100).toFixed(0)}% confidence
                          </Text>
                        )}
                      </Space>
                      <Paragraph style={{ marginBottom: 0, fontSize: 13 }}>{opp.description}</Paragraph>
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>
          )}

          {/* Section 7: Competitive Landscape */}
          {competitive && (
            <Card className="glass-card" title="Competitive Landscape" style={{ marginBottom: 16 }}>
              <Space style={{ marginBottom: 12 }}>
                <Text>Threat Level:</Text>
                <Tag color={
                  competitive.threat_level === 'high' ? 'red' :
                  competitive.threat_level === 'medium' ? 'orange' : 'green'
                }>
                  {competitive.threat_level || 'Unknown'}
                </Tag>
                {competitive.active_battles != null && (
                  <Text type="secondary">Active battles: {competitive.active_battles}</Text>
                )}
              </Space>
              {competitive.competitors && competitive.competitors.length > 0 ? (
                <Table
                  dataSource={competitive.competitors}
                  rowKey="name"
                  pagination={false}
                  size="small"
                  columns={[
                    { title: 'Competitor', dataIndex: 'name', key: 'name' },
                    { title: 'Mentions', dataIndex: 'mention_count', key: 'mention_count' },
                    {
                      title: 'Trend', dataIndex: 'trend', key: 'trend',
                      render: (v: string) => <span>{trendIcon(v)} {v || '-'}</span>,
                    },
                    {
                      title: 'Companies Mentioning', dataIndex: 'companies_mentioning', key: 'companies_mentioning',
                      render: (v: string[]) => v?.length ? v.join(', ') : '-',
                    },
                  ]}
                />
              ) : (
                <Empty description="No competitor data available" />
              )}
            </Card>
          )}

          {/* Section 8: Action Items */}
          {actionItems.length > 0 && (
            <Card className="glass-card" title={`Action Items (${actionItems.length})`} style={{ marginBottom: 16 }}>
              <Table
                dataSource={actionItems}
                columns={actionColumns}
                rowKey={(_, idx) => String(idx)}
                pagination={false}
                size="small"
              />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
