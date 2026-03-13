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
import type { StrategicDigest, PeriodType, LifecycleTier } from '../../types/strategic-digest';
import { LIFECYCLE_CONFIG, SIGNAL_CONFIG } from '../../types/strategic-digest';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { formatRelativeTime } from '../../utils/dateUtils';

const { Title, Text, Paragraph } = Typography;

function lifecycleBadge(tier?: LifecycleTier | string) {
  if (!tier) return null;
  const cfg = LIFECYCLE_CONFIG[tier as LifecycleTier];
  return <Tag color={cfg?.color || 'default'}>{cfg?.label || tier.replace(/_/g, ' ')}</Tag>;
}

function signalTag(type?: string) {
  if (!type) return null;
  const cfg = SIGNAL_CONFIG[type as keyof typeof SIGNAL_CONFIG];
  return <Tag color={cfg?.color || 'default'}>{cfg?.label || type.replace(/_/g, ' ')}</Tag>;
}

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
  const [cancelling, setCancelling] = useState(false);
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
    setCancelling(false);
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
          setCancelling(false);
          return;
        }

        if (prog.phase === 'cancelled') {
          setGenerating(false);
          setProgress(null);
          setCancelling(false);
          return;
        }
      } catch { /* keep polling */ }

      pollRef.current = setTimeout(poll, 4000);
    };

    pollRef.current = setTimeout(poll, 3000);
  };

  const handleCancel = async () => {
    if (!clientId || cancelling) return;
    setCancelling(true);
    try {
      await strategicDigestApi.cancel(clientId);
    } catch { /* ignore — poll will detect cancelled phase */ }
  };

  // Clean up poll on unmount
  useEffect(() => () => stopPolling(), []);

  // AM Efficiency columns (v2 — mailbox-based)
  const amColumns = [
    { title: 'Account Manager', dataIndex: 'am_name', key: 'am_name',
      render: (v: string) => <Text strong>{v || '-'}</Text> },
    {
      title: 'BH Response', dataIndex: 'avg_bh_response_hours', key: 'avg_bh_response_hours',
      render: (v: number) => {
        if (v == null) return '-';
        const color = v <= 4 ? '#52c41a' : v <= 8 ? '#fa8c16' : '#f5222d';
        return <Text style={{ color }}>{v.toFixed(1)}h</Text>;
      },
    },
    {
      title: 'Response Rate', dataIndex: 'response_rate_pct', key: 'response_rate_pct',
      render: (v: number) => {
        if (v == null) return '-';
        const color = v >= 80 ? '#52c41a' : v >= 60 ? '#fa8c16' : '#f5222d';
        return <Text style={{ color }}>{v.toFixed(0)}%</Text>;
      },
    },
    {
      title: 'After Hours', dataIndex: 'after_hours_pct', key: 'after_hours_pct',
      render: (v: number) => {
        if (v == null) return '-';
        const color = v > 30 ? '#fa8c16' : '#52c41a';
        return <Text style={{ color }}>{v.toFixed(0)}%</Text>;
      },
    },
    {
      title: 'Revenue', dataIndex: 'revenue_attributed', key: 'revenue_attributed',
      render: (v: number) => fmtCurrency(v),
    },
    {
      title: 'Quote Conv.', dataIndex: 'quote_conversion_rate', key: 'quote_conversion_rate',
      render: (v: number) => v != null ? `${v.toFixed(0)}%` : '-',
    },
    {
      title: 'At Risk', dataIndex: 'accounts_at_risk', key: 'accounts_at_risk',
      render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : <Tag color="green">0</Tag>,
    },
    {
      title: 'Note', dataIndex: 'performance_note', key: 'performance_note',
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v || '-'}</Text>,
    },
  ];

  // Action items columns
  const actionColumns = [
    {
      title: 'Priority', dataIndex: 'priority', key: 'priority', width: 85,
      render: (v: string) => {
        const color = v === 'urgent' ? 'red' : v === 'high' ? 'orange' : 'blue';
        return <Tag color={color}>{typeof v === 'string' ? v.toUpperCase() : `P${v}`}</Tag>;
      },
    },
    {
      title: 'Signal', dataIndex: 'signal_type', key: 'signal_type', width: 160,
      render: (v: string) => signalTag(v),
    },
    { title: 'Action', dataIndex: 'action', key: 'action' },
    { title: 'Owner', dataIndex: 'owner', key: 'owner', width: 120, render: (v: string) => v || '-' },
    { title: 'Company', dataIndex: 'company', key: 'company', width: 140, render: (v: string) => v || '-' },
    {
      title: 'Due', dataIndex: 'deadline_suggestion', key: 'deadline_suggestion', width: 110,
      render: (v: string) => v ? <Tag>{v}</Tag> : '-',
    },
    {
      title: 'Context', dataIndex: 'context', key: 'context',
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v || '-'}</Text>,
    },
  ];

  // AM performance: v2 stores as {summary: [...], ...}; v1 was an array
  const amRaw = digest?.am_performance;
  const amData: any[] = Array.isArray(amRaw)
    ? amRaw
    : (amRaw as any)?.summary || [];
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
          <div style={{ textAlign: 'center', marginTop: 20 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              You can navigate away — generation continues in the background.
            </Text>
            <div style={{ marginTop: 12 }}>
              <Button
                danger
                size="small"
                loading={cancelling || progress?.phase === 'cancelling'}
                onClick={handleCancel}
                disabled={progress?.phase === 'cancelling'}
              >
                {progress?.phase === 'cancelling' ? 'Cancelling…' : 'Cancel'}
              </Button>
            </div>
          </div>
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
                      style={{
                        height: '100%',
                        borderLeft: r.lifecycle_tier === 'at_risk' ? '3px solid #fa8c16' :
                                    r.lifecycle_tier === 'dormant' ? '3px solid #999' :
                                    r.lifecycle_tier === 'champion' ? '3px solid #fadb14' : undefined,
                      }}
                    >
                      <Text strong style={{ display: 'block', marginBottom: 4 }}>{r.company_name}</Text>
                      <Space wrap size={4} style={{ marginBottom: 6 }}>
                        {lifecycleBadge(r.lifecycle_tier)}
                        {r.tier && <Tag color="blue" style={{ fontSize: 11 }}>{r.tier}</Tag>}
                      </Space>
                      {r.am_owner && (
                        <div style={{ marginBottom: 4 }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>AM: {r.am_owner}</Text>
                        </div>
                      )}
                      {r.signal && (
                        <div style={{ marginBottom: 4 }}>
                          <Text type="secondary" style={{ fontSize: 12, fontStyle: 'italic' }}>{r.signal}</Text>
                        </div>
                      )}
                      {r.recommended_action && (
                        <div style={{ marginTop: 4 }}>
                          <Text style={{ fontSize: 11, color: '#1890ff' }}>→ {r.recommended_action}</Text>
                        </div>
                      )}
                      {r.revenue_impact_estimate && (
                        <div style={{ marginTop: 4 }}>
                          <Tag color="gold" style={{ fontSize: 11 }}>{r.revenue_impact_estimate}</Tag>
                        </div>
                      )}
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>
          )}

          {/* Section 4: Pipeline Intelligence + Lifecycle Breakdown */}
          {pipeline && (
            <Card className="glass-card" title="Pipeline & Customer Lifecycle" style={{ marginBottom: 16 }}>
              {pipeline.lifecycle_breakdown && Object.keys(pipeline.lifecycle_breakdown).length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <Text strong style={{ display: 'block', marginBottom: 8 }}>Customer Lifecycle Distribution</Text>
                  <Space wrap>
                    {(Object.entries(pipeline.lifecycle_breakdown) as [LifecycleTier, number][])
                      .filter(([, count]) => count > 0)
                      .map(([tier, count]) => (
                        <Tag key={tier} color={LIFECYCLE_CONFIG[tier]?.color || 'default'} style={{ fontSize: 13, padding: '2px 10px' }}>
                          {LIFECYCLE_CONFIG[tier]?.label || tier}: {count}
                        </Tag>
                      ))}
                  </Space>
                </div>
              )}
              <Descriptions size="small" column={3} style={{ marginBottom: 12 }}>
                {pipeline.active_quotes_value != null && (
                  <Descriptions.Item label="Active Quotes Value">{fmtCurrency(pipeline.active_quotes_value)}</Descriptions.Item>
                )}
                {pipeline.conversion_trend && (
                  <Descriptions.Item label="Conversion Trend">
                    {trendIcon(pipeline.conversion_trend)} {pipeline.conversion_trend}
                  </Descriptions.Item>
                )}
              </Descriptions>
              {pipeline.stalled_quotes && pipeline.stalled_quotes.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <Text strong style={{ display: 'block', marginBottom: 6 }}>Stalled Quotes</Text>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {pipeline.stalled_quotes.map((q, i) => (
                      <Alert key={i} type="warning" message={q} showIcon style={{ padding: '4px 12px' }} />
                    ))}
                  </Space>
                </div>
              )}
              {pipeline.new_relationships_this_period && pipeline.new_relationships_this_period.length > 0 && (
                <div>
                  <Text strong style={{ display: 'block', marginBottom: 6 }}>New Relationships</Text>
                  <Space wrap>
                    {pipeline.new_relationships_this_period.map((r, i) => (
                      <Tag key={i} color="blue">{r}</Tag>
                    ))}
                  </Space>
                </div>
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
                      <Space wrap>
                        <Text strong>{risk.affected_company || risk.company_name}</Text>
                        <Tag color={risk.severity === 'critical' ? 'red' : risk.severity === 'high' ? 'orange' : 'blue'}>
                          {risk.severity}
                        </Tag>
                        {signalTag(risk.type) || <Tag>{(risk.risk_type || risk.type || '').replace(/_/g, ' ')}</Tag>}
                        {risk.am_owner && <Text type="secondary">AM: {risk.am_owner}</Text>}
                        {risk.days_overdue != null && risk.days_overdue > 0 && (
                          <Tag color="red">{risk.days_overdue}d overdue</Tag>
                        )}
                      </Space>
                    }
                    description={
                      <span>
                        {risk.description}
                        {risk.recommended_action && (
                          <div style={{ marginTop: 4 }}>
                            <Text style={{ color: '#1890ff', fontSize: 12 }}>→ {risk.recommended_action}</Text>
                          </div>
                        )}
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
                    <Card size="small" style={{ borderLeft: '3px solid #52c41a' }}>
                      <Space wrap style={{ marginBottom: 8 }}>
                        <Tag color="green">{(opp.type || opp.opportunity_type || '').replace(/_/g, ' ')}</Tag>
                        <Text strong>{opp.company_name}</Text>
                        {lifecycleBadge(opp.lifecycle_tier)}
                        {opp.estimated_value && <Tag color="gold">{opp.estimated_value}</Tag>}
                      </Space>
                      <Paragraph style={{ marginBottom: 4, fontSize: 13 }}>{opp.description}</Paragraph>
                      {opp.next_step && (
                        <Text style={{ fontSize: 12, color: '#1890ff' }}>→ {opp.next_step}</Text>
                      )}
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>
          )}

          {/* Section 7: Competitive Landscape */}
          {competitive && (competitive.competitor_mentions?.length || competitive.price_sensitivity_signals?.length) ? (
            <Card className="glass-card" title="Competitive Landscape" style={{ marginBottom: 16 }}>
              {competitive.competitor_mentions?.length ? (
                <div style={{ marginBottom: 12 }}>
                  <Text strong style={{ display: 'block', marginBottom: 6 }}>Competitor Mentions</Text>
                  <Space wrap>{competitive.competitor_mentions.map((c, i) => <Tag key={i} color="volcano">{c}</Tag>)}</Space>
                </div>
              ) : null}
              {competitive.price_sensitivity_signals?.length ? (
                <div style={{ marginBottom: 12 }}>
                  <Text strong style={{ display: 'block', marginBottom: 6 }}>Price Sensitivity</Text>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {competitive.price_sensitivity_signals.map((s, i) => (
                      <Text key={i} type="secondary" style={{ fontSize: 13 }}>• {s}</Text>
                    ))}
                  </Space>
                </div>
              ) : null}
              {competitive.win_loss_insights?.length ? (
                <div>
                  <Text strong style={{ display: 'block', marginBottom: 6 }}>Win/Loss Insights</Text>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {competitive.win_loss_insights.map((s, i) => (
                      <Text key={i} type="secondary" style={{ fontSize: 13 }}>• {s}</Text>
                    ))}
                  </Space>
                </div>
              ) : null}
            </Card>
          ) : null}

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
