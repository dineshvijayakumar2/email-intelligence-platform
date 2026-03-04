/**
 * AI Usage & Monitoring Page — Sprint 3
 *
 * Real-time cost tracking, monitoring metrics, and AI control switches.
 * Admin-level controls for budget caps, kill switches, and feature toggles.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Switch, InputNumber, Button, Table,
  Tag, Space, Progress, Alert, Divider, Tooltip, Badge, Typography,
  Spin, message,
} from 'antd';
import {
  DollarOutlined, ThunderboltOutlined, WarningOutlined,
  ReloadOutlined, PauseCircleOutlined, PlayCircleOutlined,
  ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { usageApi, controlsApi, invalidateCache } from '../../services/aiService';
import type { UsageSummary, MonitoringStats, AIControlSettings, UsageLogEntry } from '../../types/ai';

const { Title, Text } = Typography;

const UsagePage: React.FC = () => {
  const isMountedRef = useRef(true);
  const [loading, setLoading] = useState(true);
  const [costs, setCosts] = useState<UsageSummary | null>(null);
  const [monitoring, setMonitoring] = useState<MonitoringStats | null>(null);
  const [controls, setControls] = useState<AIControlSettings | null>(null);
  const [recentLogs, setRecentLogs] = useState<UsageLogEntry[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Load all data
  const loadData = useCallback(async () => {
    try {
      const [costsData, monData, ctrlData, logsData] = await Promise.all([
        usageApi.getCosts(undefined, 30),
        usageApi.getMonitoring(),
        controlsApi.get(),
        usageApi.getRecent(30),
      ]);
      if (!isMountedRef.current) return;
      setCosts(costsData);
      setMonitoring(monData);
      setControls(ctrlData);
      setRecentLogs(logsData.items);
    } catch (err) {
      console.error('Failed to load usage data:', err);
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    loadData();
    return () => { isMountedRef.current = false; };
  }, [loadData]);

  // Auto-refresh every 10s
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      invalidateCache('usage');
      loadData();
    }, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadData]);

  // Control update handler
  const handleControlChange = async (key: string, value: any) => {
    try {
      const result = await controlsApi.update({ [key]: value });
      if (result?.settings) {
        setControls(result.settings);
        message.success(`Updated ${key.replace(/_/g, ' ')}`);
      }
    } catch {
      message.error('Failed to update setting');
    }
  };

  const handleResetSpend = async () => {
    const result = await controlsApi.resetSessionSpend();
    if (result) {
      message.success(`Session spend reset (was $${result.previous_spend_usd})`);
      invalidateCache('usage');
      loadData();
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    );
  }

  const budgetUsedPct = controls
    ? Math.min((controls.session_spend_usd / controls.daily_budget_usd) * 100, 100)
    : 0;

  const budgetColor = budgetUsedPct >= 90 ? '#ff4d4f' : budgetUsedPct >= 70 ? '#faad14' : '#52c41a';

  // Recent logs table columns
  const logColumns = [
    {
      title: 'Time',
      dataIndex: 'created_at',
      key: 'time',
      width: 160,
      render: (val: string) => val ? new Date(val).toLocaleTimeString() : '-',
    },
    {
      title: 'Operation',
      dataIndex: 'operation',
      key: 'operation',
      width: 140,
      render: (val: string) => <Tag>{val || 'unknown'}</Tag>,
    },
    {
      title: 'Model',
      dataIndex: 'model',
      key: 'model',
      width: 200,
      render: (val: string) => {
        const short = val?.includes('haiku') ? 'Haiku' : val?.includes('sonnet') ? 'Sonnet' : val || '-';
        return <Tag color={short === 'Haiku' ? 'blue' : 'purple'}>{short}</Tag>;
      },
    },
    {
      title: 'Tokens (in/out)',
      key: 'tokens',
      width: 140,
      render: (_: any, r: UsageLogEntry) => (
        <span>{(r.input_tokens || 0).toLocaleString()} / {(r.output_tokens || 0).toLocaleString()}</span>
      ),
    },
    {
      title: 'Cost',
      dataIndex: 'estimated_cost_usd',
      key: 'cost',
      width: 100,
      render: (val: number) => <Text strong>${(val || 0).toFixed(4)}</Text>,
    },
    {
      title: 'Latency',
      dataIndex: 'processing_time_ms',
      key: 'latency',
      width: 90,
      render: (val: number) => val ? `${(val / 1000).toFixed(1)}s` : '-',
    },
    {
      title: 'Status',
      dataIndex: 'success',
      key: 'success',
      width: 80,
      render: (val: boolean, r: UsageLogEntry) => val
        ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
        : <Tooltip title={r.error_type || 'Failed'}><CloseCircleOutlined style={{ color: '#ff4d4f' }} /></Tooltip>,
    },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>AI Usage & Monitoring</Title>
        <Space>
          <Text type="secondary">Auto-refresh</Text>
          <Switch
            checked={autoRefresh}
            onChange={setAutoRefresh}
            checkedChildren="ON"
            unCheckedChildren="OFF"
            size="small"
          />
          <Button icon={<ReloadOutlined />} onClick={() => { invalidateCache('usage'); loadData(); }}>
            Refresh
          </Button>
        </Space>
      </div>

      {/* Budget Alert */}
      {controls && controls.session_spend_usd >= controls.daily_budget_usd * 0.8 && (
        <Alert
          message="Budget Warning"
          description={`Session spend ($${controls.session_spend_usd.toFixed(4)}) is approaching the daily budget cap ($${controls.daily_budget_usd.toFixed(2)}). API calls will be blocked when the cap is reached.`}
          type={controls.session_spend_usd >= controls.daily_budget_usd ? 'error' : 'warning'}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Row 1: Key Metrics */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card className="glass-card" size="small">
            <Statistic
              title="Total Spend (30d)"
              value={costs?.total_cost_usd || 0}
              prefix={<DollarOutlined />}
              precision={4}
              valueStyle={{ color: '#667eea' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card className="glass-card" size="small">
            <Statistic
              title="Session Spend"
              value={controls?.session_spend_usd || 0}
              prefix={<DollarOutlined />}
              precision={4}
              valueStyle={{ color: budgetColor }}
            />
            <Progress
              percent={Math.round(budgetUsedPct)}
              strokeColor={budgetColor}
              size="small"
              format={(pct) => `${pct}% of $${controls?.daily_budget_usd || 0}`}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card className="glass-card" size="small">
            <Statistic
              title="Requests (24h)"
              value={monitoring?.total_requests_24h || 0}
              prefix={<ThunderboltOutlined />}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {monitoring?.total_failures_24h || 0} failures
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card className="glass-card" size="small">
            <Statistic
              title="Cost / 1K Emails"
              value={monitoring?.cost_per_1000_emails || 0}
              prefix={<DollarOutlined />}
              precision={4}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              Avg latency: {(costs?.avg_latency_ms || 0).toFixed(0)}ms
            </Text>
          </Card>
        </Col>
      </Row>

      {/* Row 2: Controls + Monitoring */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {/* AI Controls */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                {controls?.ai_enabled
                  ? <Badge status="success" text="AI Controls" />
                  : <Badge status="error" text="AI Controls (DISABLED)" />
                }
              </Space>
            }
            className="glass-card"
            extra={
              <Button size="small" onClick={handleResetSpend}>
                Reset Spend
              </Button>
            }
          >
            {/* Master Kill Switch */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, padding: '12px 16px', background: controls?.ai_enabled ? 'rgba(82,196,26,0.06)' : 'rgba(255,77,79,0.06)', borderRadius: 8 }}>
              <div>
                <Text strong style={{ fontSize: 15 }}>Master AI Switch</Text>
                <br />
                <Text type="secondary" style={{ fontSize: 12 }}>Disables ALL AI API calls immediately</Text>
              </div>
              <Switch
                checked={controls?.ai_enabled ?? false}
                onChange={(val) => handleControlChange('ai_enabled', val)}
                checkedChildren={<PlayCircleOutlined />}
                unCheckedChildren={<PauseCircleOutlined />}
              />
            </div>

            <Divider style={{ margin: '12px 0' }} />

            {/* Feature Toggles */}
            <Title level={5} style={{ marginBottom: 12, marginTop: 0 }}>Feature Toggles</Title>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text>Email Analysis (Haiku)</Text>
                <Switch
                  checked={controls?.email_analysis_enabled ?? false}
                  onChange={(val) => handleControlChange('email_analysis_enabled', val)}
                  size="small"
                  disabled={!controls?.ai_enabled}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text>Daily Digest (Sonnet)</Text>
                <Switch
                  checked={controls?.digest_enabled ?? false}
                  onChange={(val) => handleControlChange('digest_enabled', val)}
                  size="small"
                  disabled={!controls?.ai_enabled}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text>Relationship Summaries (Sonnet)</Text>
                <Switch
                  checked={controls?.relationship_summary_enabled ?? false}
                  onChange={(val) => handleControlChange('relationship_summary_enabled', val)}
                  size="small"
                  disabled={!controls?.ai_enabled}
                />
              </div>
            </div>

            <Divider style={{ margin: '12px 0' }} />

            {/* Budget Controls */}
            <Title level={5} style={{ marginBottom: 12, marginTop: 0 }}>Budget Limits</Title>
            <Row gutter={16}>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12 }}>Daily Cap (USD)</Text>
                <InputNumber
                  value={controls?.daily_budget_usd}
                  min={0.01}
                  max={100}
                  step={0.5}
                  prefix="$"
                  style={{ width: '100%', marginTop: 4 }}
                  onBlur={(e) => {
                    const val = parseFloat(e.target.value.replace('$', ''));
                    if (!isNaN(val) && val > 0) handleControlChange('daily_budget_usd', val);
                  }}
                />
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12 }}>Monthly Cap (USD)</Text>
                <InputNumber
                  value={controls?.monthly_budget_usd}
                  min={1}
                  max={500}
                  step={1}
                  prefix="$"
                  style={{ width: '100%', marginTop: 4 }}
                  onBlur={(e) => {
                    const val = parseFloat(e.target.value.replace('$', ''));
                    if (!isNaN(val) && val > 0) handleControlChange('monthly_budget_usd', val);
                  }}
                />
              </Col>
            </Row>

            <Divider style={{ margin: '12px 0' }} />

            {/* Batch Controls */}
            <Title level={5} style={{ marginBottom: 12, marginTop: 0 }}>Processing Limits</Title>
            <Row gutter={16}>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12 }}>Emails per batch</Text>
                <InputNumber
                  value={controls?.batch_size}
                  min={1}
                  max={25}
                  step={1}
                  style={{ width: '100%', marginTop: 4 }}
                  onBlur={(e) => {
                    const val = parseInt(e.target.value);
                    if (!isNaN(val) && val > 0) handleControlChange('batch_size', val);
                  }}
                />
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12 }}>Max emails per run</Text>
                <InputNumber
                  value={controls?.max_emails_per_run}
                  min={10}
                  max={5000}
                  step={50}
                  style={{ width: '100%', marginTop: 4 }}
                  onBlur={(e) => {
                    const val = parseInt(e.target.value);
                    if (!isNaN(val) && val > 0) handleControlChange('max_emails_per_run', val);
                  }}
                />
              </Col>
            </Row>
          </Card>
        </Col>

        {/* Monitoring Health */}
        <Col xs={24} lg={12}>
          <Card title="Health Monitoring (24h)" className="glass-card">
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Statistic
                  title="API Failure Rate"
                  value={(monitoring?.api_failure_rate || 0) * 100}
                  suffix="%"
                  precision={1}
                  prefix={monitoring && monitoring.api_failure_rate > 0.1
                    ? <WarningOutlined style={{ color: '#ff4d4f' }} />
                    : <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  }
                  valueStyle={{
                    color: monitoring && monitoring.api_failure_rate > 0.1 ? '#ff4d4f' : '#52c41a',
                  }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="Parse Failure Rate"
                  value={(monitoring?.parse_failure_rate || 0) * 100}
                  suffix="%"
                  precision={1}
                  prefix={monitoring && monitoring.parse_failure_rate > 0.05
                    ? <ExclamationCircleOutlined style={{ color: '#faad14' }} />
                    : <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  }
                  valueStyle={{
                    color: monitoring && monitoring.parse_failure_rate > 0.05 ? '#faad14' : '#52c41a',
                  }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="Avg Retry Count"
                  value={monitoring?.avg_retry_count || 0}
                  precision={2}
                  prefix={<ClockCircleOutlined />}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="Total Failures (24h)"
                  value={monitoring?.total_failures_24h || 0}
                  valueStyle={{
                    color: (monitoring?.total_failures_24h || 0) > 0 ? '#ff4d4f' : '#52c41a',
                  }}
                />
              </Col>
            </Row>

            <Divider style={{ margin: '16px 0' }} />

            {/* Cost Breakdown */}
            <Title level={5} style={{ marginTop: 0, marginBottom: 12 }}>Cost by Operation (30d)</Title>
            {costs?.by_operation && Object.entries(costs.by_operation).length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {Object.entries(costs.by_operation).map(([op, data]) => (
                  <div key={op} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Tag>{op}</Tag>
                    <Space>
                      <Text type="secondary">{data.count} calls</Text>
                      <Text strong>${data.cost.toFixed(4)}</Text>
                    </Space>
                  </div>
                ))}
              </div>
            ) : (
              <Text type="secondary">No usage data yet</Text>
            )}

            <Divider style={{ margin: '16px 0' }} />

            <Title level={5} style={{ marginTop: 0, marginBottom: 12 }}>Cost by Model (30d)</Title>
            {costs?.by_model && Object.entries(costs.by_model).length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {Object.entries(costs.by_model).map(([model, data]) => {
                  const short = model.includes('haiku') ? 'Haiku' : model.includes('sonnet') ? 'Sonnet' : model;
                  return (
                    <div key={model} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Tag color={short === 'Haiku' ? 'blue' : 'purple'}>{short}</Tag>
                      <Space>
                        <Text type="secondary">{data.count} calls</Text>
                        <Text strong>${data.cost.toFixed(4)}</Text>
                      </Space>
                    </div>
                  );
                })}
              </div>
            ) : (
              <Text type="secondary">No usage data yet</Text>
            )}
          </Card>
        </Col>
      </Row>

      {/* Row 3: Recent API Calls */}
      <Card title="Recent API Calls" className="glass-card">
        <Table
          dataSource={recentLogs}
          columns={logColumns}
          rowKey={(r) => r.id || `${r.created_at}-${Math.random()}`}
          size="small"
          pagination={{ pageSize: 15, size: 'small' }}
          scroll={{ x: 900 }}
        />
      </Card>
    </div>
  );
};

export default UsagePage;
