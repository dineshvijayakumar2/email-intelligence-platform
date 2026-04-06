/**
 * AI Usage & Monitoring Page — Sprint 3
 *
 * Real-time cost tracking, monitoring metrics, and AI control switches.
 * Admin-level controls for budget caps, kill switches, and feature toggles.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Row, Col, Statistic, Switch, InputNumber, Button, Table, Select,
  Tag, Space, Progress, Alert, Divider, Tooltip, Badge, Typography,
  Spin, message, Form, Input, Checkbox, Empty, Skeleton, Collapse,
} from 'antd';
import {
  DollarOutlined, ThunderboltOutlined, WarningOutlined,
  ReloadOutlined, PauseCircleOutlined, PlayCircleOutlined,
  ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ExclamationCircleOutlined, SyncOutlined, MailOutlined,
  BankOutlined, ToolOutlined, SearchOutlined,
} from '@ant-design/icons';
import * as vectorApi from '../../services/vectorService';
import { controlsApi, intelligenceApi } from '../../services/aiService';
import { modelsApi } from '../../services/strategicDigestService';
import { MailboxSelector } from '../../components/MailboxSelector';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import api from '../../services/apiClient';
import { formatTime } from '../../utils/dateUtils';
import {
  useAICosts, useAIMonitoring, useAIControls, useAIRecentLogs,
  useAIModels, useAIApiKeys, useClientAISettings,
} from '../../hooks/queries';
import type { UsageSummary, MonitoringStats, AIControlSettings, UsageLogEntry } from '../../types/ai';
import type { AIModel } from '../../types/strategic-digest';

const { Title, Text } = Typography;

const UsagePage: React.FC = () => {
  const [clientId, setClientId] = useState(() => localStorage.getItem('analytics_client_id') || '');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [apiKeysForm] = Form.useForm();
  const [apiKeysSaving, setApiKeysSaving] = useState(false);

  // Re-analyze state
  const [reanalyzeMailbox, setReanalyzeMailbox] = useState<string[]>([]);
  const [reanalyzeVersion, setReanalyzeVersion] = useState('v1.2');
  const [reanalyzeMax, setReanalyzeMax] = useState(500);
  const [reanalyzeIncludeFailed, setReanalyzeIncludeFailed] = useState(false);
  const [reanalyzeLoading, setReanalyzeLoading] = useState(false);

  // All data via TanStack Query — auto-refresh every 60s when enabled
  const costsQuery = useAICosts(clientId, 30);
  const monitoringQuery = useAIMonitoring(clientId);
  const controlsQuery = useAIControls();
  const logsQuery = useAIRecentLogs(30);
  const modelsQuery = useAIModels();
  const apiKeysQuery = useAIApiKeys(clientId);
  const clientSettingsQuery = useClientAISettings(clientId);

  const costs = costsQuery.data || null;
  const monitoring = monitoringQuery.data || null;
  const controls = controlsQuery.data || null;
  const recentLogs = logsQuery.data?.items || [];
  const models = modelsQuery.data?.models || [];
  const apiKeys = apiKeysQuery.data || null;
  const loading = costsQuery.isLoading;

  // Derive model selections from client settings → controls → defaults
  const clientSettings = clientSettingsQuery.data || {};
  const cheapModel = clientSettings['ai_cheap_model'] || controls?.cheap_model || 'haiku';
  const strategicModel = clientSettings['ai_strategic_model'] || controls?.strategic_model || 'sonnet';

  // Manual refresh handler
  const loadData = () => {
    costsQuery.refetch();
    monitoringQuery.refetch();
    controlsQuery.refetch();
    logsQuery.refetch();
    apiKeysQuery.refetch();
    clientSettingsQuery.refetch();
  };

  // Control update handler
  const handleControlChange = async (key: string, value: any) => {
    try {
      const result = await controlsApi.update({ [key]: value });
      if (result?.settings) {
        controlsQuery.refetch();
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
      loadData();
    }
  };

  const handleApiKeysSave = async () => {
    const values = apiKeysForm.getFieldsValue();
    if (!values.anthropic_api_key && !values.google_api_key && !values.openai_api_key) {
      message.warning('Enter at least one key to update');
      return;
    }
    setApiKeysSaving(true);
    try {
      const result = await api.put<any>('/v1/ai/api-keys', { ...values, client_id: clientId || undefined });
      message.success(`Keys updated: ${result.updated?.join(', ')}`);
      apiKeysForm.resetFields();
      apiKeysQuery.refetch();
    } catch (err: any) {
      message.error(err?.message || 'Failed to update keys');
    } finally {
      setApiKeysSaving(false);
    }
  };

  const handleReanalyze = async () => {
    const mailboxId = reanalyzeMailbox[0];
    if (!mailboxId) { message.warning('Select a mailbox'); return; }
    if (!reanalyzeVersion.trim()) { message.warning('Enter a prompt version to target'); return; }
    setReanalyzeLoading(true);
    try {
      const result = await intelligenceApi.reanalyze(mailboxId, reanalyzeVersion, reanalyzeMax, reanalyzeIncludeFailed);
      if (result?.status === 'no_candidates') {
        message.info(result.message);
      } else if (result) {
        message.success(`${result.message} — ${result.emails_queued} emails queued`);
      }
    } catch (err: any) {
      message.error(err?.message || 'Re-analysis failed');
    } finally {
      setReanalyzeLoading(false);
    }
  };

  const handleModelChange = async (type: 'cheap' | 'strategic', value: string) => {
    const newCheap = type === 'cheap' ? value : cheapModel;
    const newStrategic = type === 'strategic' ? value : strategicModel;
    try {
      await modelsApi.updateDefaults(newCheap, newStrategic, clientId || undefined);
      clientSettingsQuery.refetch();
      message.success(`${type === 'cheap' ? 'Fast' : 'Strategic'} model set to ${value}`);
    } catch (err) {
      message.error('Failed to update model');
    }
  };

  const showSkeleton = loading || !costs;

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
      render: (val: string) => val ? formatTime(val) : '-',
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
        : <Tooltip title={r.error_detail || r.error_type || 'Failed'}><CloseCircleOutlined style={{ color: '#ff4d4f' }} /></Tooltip>,
    },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>AI Usage & Monitoring</Title>
        <Space>
          <ClientSelector value={clientId} onChange={setClientId} />
          <Text type="secondary">Auto-refresh</Text>
          <Switch
            checked={autoRefresh}
            onChange={setAutoRefresh}
            checkedChildren="ON"
            unCheckedChildren="OFF"
            size="small"
          />
          <Button icon={<ReloadOutlined />} onClick={loadData}>
            Refresh
          </Button>
        </Space>
      </div>

      {/* Credit Balance / API Error Alert */}
      {monitoring && monitoring.total_failures_24h > 0 && monitoring.api_failure_rate > 50 && (
        <Alert
          message="API Errors Detected"
          description="High API failure rate in the last 24 hours. This may indicate insufficient Anthropic credits or an API key issue. Check your Anthropic account balance and update the API key if needed."
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

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

      {!clientId && (
        <Card className="glass-card" style={{ marginBottom: 24 }}><Empty description="Select a client to view AI usage" /></Card>
      )}

      {/* Row 1: Key Metrics */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card className="glass-card" size="small">
            {showSkeleton ? <Skeleton active paragraph={{ rows: 1 }} /> : (
              <Statistic
                title="Total Spend (30d)"
                value={costs?.total_cost_usd || 0}
                prefix={<DollarOutlined />}
                precision={4}
                valueStyle={{ color: '#667eea' }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card className="glass-card" size="small">
            {showSkeleton ? <Skeleton active paragraph={{ rows: 2 }} /> : (
              <>
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
              </>
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card className="glass-card" size="small">
            {showSkeleton ? <Skeleton active paragraph={{ rows: 1 }} /> : (
              <>
                <Statistic
                  title="Requests (24h)"
                  value={monitoring?.total_requests_24h || 0}
                  prefix={<ThunderboltOutlined />}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {monitoring?.total_failures_24h || 0} failures
                </Text>
              </>
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card className="glass-card" size="small">
            {showSkeleton ? <Skeleton active paragraph={{ rows: 1 }} /> : (() => {
              const dailyRemaining = Math.max((controls?.daily_budget_usd || 0) - (controls?.session_spend_usd || 0), 0);
              const monthlyRemaining = Math.max((controls?.monthly_budget_usd || 0) - (costs?.total_cost_usd || 0), 0);
              const dailyPct = controls?.daily_budget_usd ? (dailyRemaining / controls.daily_budget_usd) * 100 : 100;
              const creditColor = dailyPct <= 10 ? '#ff4d4f' : dailyPct <= 30 ? '#faad14' : '#52c41a';
              return (
                <>
                  <Statistic
                    title="Daily Credit Remaining"
                    value={dailyRemaining}
                    prefix={<DollarOutlined />}
                    precision={4}
                    valueStyle={{ color: creditColor }}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Monthly: ${monthlyRemaining.toFixed(2)} / ${controls?.monthly_budget_usd?.toFixed(2) || '0'}
                  </Text>
                </>
              );
            })()}
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

            {/* Model Selection */}
            {models.length > 0 && (
              <>
                <Title level={5} style={{ marginBottom: 12, marginTop: 0 }}>AI Model Selection</Title>
                <Row gutter={16}>
                  <Col span={12}>
                    <Text type="secondary" style={{ fontSize: 12 }}>Fast tasks (email analysis, insights)</Text>
                    <Select
                      value={cheapModel}
                      onChange={(v) => handleModelChange('cheap', v)}
                      style={{ width: '100%', marginTop: 4 }}
                      disabled={!controls?.ai_enabled}
                    >
                      {models.map(m => (
                        <Select.Option key={m.name} value={m.name} disabled={!m.available}>
                          {m.label} {m.cost_input_per_mtok === 0 ? '(free)' : `($${m.cost_input_per_mtok}/MTok)`}
                        </Select.Option>
                      ))}
                    </Select>
                  </Col>
                  <Col span={12}>
                    <Text type="secondary" style={{ fontSize: 12 }}>Strategic tasks (digest, reports)</Text>
                    <Select
                      value={strategicModel}
                      onChange={(v) => handleModelChange('strategic', v)}
                      style={{ width: '100%', marginTop: 4 }}
                      disabled={!controls?.ai_enabled}
                    >
                      {models.map(m => (
                        <Select.Option key={m.name} value={m.name} disabled={!m.available}>
                          {m.label} {m.cost_input_per_mtok === 0 ? '(free)' : `($${m.cost_input_per_mtok}/MTok)`}
                        </Select.Option>
                      ))}
                    </Select>
                  </Col>
                </Row>
                <Divider style={{ margin: '12px 0' }} />
              </>
            )}

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

            <Divider style={{ margin: '12px 0' }} />

            {/* API Keys */}
            <Title level={5} style={{ marginBottom: 12, marginTop: 0 }}>API Keys</Title>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text>Anthropic (Claude)</Text>
                <Text type={apiKeys?.anthropic_set ? 'success' : 'danger'}>
                  {apiKeys?.anthropic_set ? apiKeys.anthropic_masked : 'Not set'}
                </Text>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text>Google (Gemini)</Text>
                <Text type={apiKeys?.google_set ? 'success' : 'secondary'}>
                  {apiKeys?.google_set ? apiKeys.google_masked : 'Not set'}
                </Text>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text>OpenAI (GPT-4o)</Text>
                <Text type={apiKeys?.openai_set ? 'success' : 'secondary'}>
                  {apiKeys?.openai_set ? apiKeys.openai_masked : 'Not set'}
                </Text>
              </div>
            </div>
            <Form form={apiKeysForm} layout="vertical">
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label="Anthropic API Key" name="anthropic_api_key" style={{ marginBottom: 8 }}>
                    <Input.Password placeholder="sk-ant-..." size="small" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="Google API Key" name="google_api_key" style={{ marginBottom: 8 }}>
                    <Input.Password placeholder="AIza..." size="small" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="OpenAI API Key" name="openai_api_key" style={{ marginBottom: 8 }}>
                    <Input.Password placeholder="sk-..." size="small" />
                  </Form.Item>
                </Col>
              </Row>
            </Form>
            <Button size="small" loading={apiKeysSaving} onClick={handleApiKeysSave}>
              Update Keys
            </Button>
            <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
              Runtime only — add to .env for persistence
            </Text>
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

      {/* Row 3: Re-analyze */}
      <Card
        title={<Space><SyncOutlined />Re-analyze Emails</Space>}
        className="glass-card"
        style={{ marginBottom: 24 }}
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          Reset emails analyzed with an older prompt version so they are re-processed with the current prompt.
          Runs in the background — check Recent API Calls below for progress.
        </Text>
        <Row gutter={16} align="bottom">
          <Col xs={24} sm={8} md={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>Mailbox</Text>
            <div style={{ marginTop: 4 }}>
              <MailboxSelector value={reanalyzeMailbox} onChange={setReanalyzeMailbox} mode="single" />
            </div>
          </Col>
          <Col xs={24} sm={6} md={4}>
            <Text type="secondary" style={{ fontSize: 12 }}>Old prompt version</Text>
            <Input
              value={reanalyzeVersion}
              onChange={(e) => setReanalyzeVersion(e.target.value)}
              placeholder="e.g. v1.3"
              style={{ width: '100%', marginTop: 4 }}
            />
          </Col>
          <Col xs={24} sm={6} md={4}>
            <Text type="secondary" style={{ fontSize: 12 }}>Max emails</Text>
            <InputNumber
              value={reanalyzeMax}
              min={10}
              max={5000}
              step={100}
              style={{ width: '100%', marginTop: 4 }}
              onChange={(v) => setReanalyzeMax(v || 500)}
            />
          </Col>
          <Col xs={24} sm={4} md={3} style={{ paddingTop: 20 }}>
            <Checkbox
              checked={reanalyzeIncludeFailed}
              onChange={(e) => setReanalyzeIncludeFailed(e.target.checked)}
            >
              Include failed
            </Checkbox>
          </Col>
          <Col xs={24} sm={24} md={4} style={{ paddingTop: 20 }}>
            <Button
              type="primary"
              icon={<SyncOutlined />}
              loading={reanalyzeLoading}
              onClick={handleReanalyze}
              disabled={!reanalyzeMailbox[0]}
            >
              Start Re-analysis
            </Button>
          </Col>
        </Row>
      </Card>

      {/* Row 4: Recent API Calls */}
      <Card title="Recent API Calls" className="glass-card" style={{ marginBottom: 24 }}>
        {showSkeleton ? <Skeleton active paragraph={{ rows: 5 }} /> : (
          <Table
            dataSource={recentLogs}
            columns={logColumns}
            rowKey={(r) => r.id || `${r.created_at}-${Math.random()}`}
            size="small"
            pagination={{ pageSize: 15, size: 'small' }}
            scroll={{ x: 900 }}
          />
        )}
      </Card>

      {/* Row 5: Embedding Coverage & Management */}
      <EmbeddingManagement clientId={clientId} />

    </div>
  );
};


// ---------------------------------------------------------------------------
// Embedding Coverage & Management (moved from Semantic Search page)
// ---------------------------------------------------------------------------

const EmbeddingManagement: React.FC<{ clientId: string }> = ({ clientId }) => {
  const [stats, setStats] = useState<vectorApi.VectorStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [reembedStatus, setReembedStatus] = useState<vectorApi.ReembedStatus | null>(null);
  const [backfillRunning, setBackfillRunning] = useState(false);
  const [backfillTotal, setBackfillTotal] = useState(0);
  const backfillCancelRef = useRef(false);

  const loadStats = useCallback(async () => {
    if (!clientId) return; // Don't query without client_id
    setStatsLoading(true);
    try {
      const s = await vectorApi.getVectorStats(clientId);
      setStats(s);
    } catch { /* keep previous */ } finally {
      setStatsLoading(false);
    }
  }, [clientId]);

  // Load stats + check for in-progress embedding when clientId is available
  useEffect(() => {
    if (!clientId) return;
    loadStats();
    // Check if embedding is already running (survives page navigation)
    vectorApi.getReembedStatus(clientId).then(status => {
      if (status?.status === 'running') {
        setReembedStatus(status);
      }
    }).catch(() => {});
  }, [clientId, loadStats]);

  // Poll reembed status + live stats refresh while embedding is running
  useEffect(() => {
    if (reembedStatus?.status !== 'running') return;
    let pollCount = 0;
    const interval = setInterval(async () => {
      try {
        const status = await vectorApi.getReembedStatus(clientId);
        setReembedStatus(status);
        pollCount++;
        // Refresh stats every 5 polls (~15s) for live count updates
        if (pollCount % 5 === 0 && clientId) {
          vectorApi.getVectorStats(clientId).then(s => setStats(s)).catch(() => {});
        }
        if (status.status !== 'running') {
          clearInterval(interval);
          loadStats();
          if (status.status === 'complete') message.success(`Embedding complete: ${status.result?.total_embedded} records`);
          else if (status.status === 'error') message.error(`Embedding failed: ${status.error}`);
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(interval);
  }, [reembedStatus?.status, clientId, loadStats]);

  const handleReembed = async (tables?: string[]) => {
    try {
      const resp = await vectorApi.triggerReembed(clientId, tables);
      if (resp.status === 'already_running') message.info('Embedding already in progress');
      else message.success(`Embedding ${tables ? tables.join(' + ') : 'all tables'} in background`);
      setReembedStatus({ status: 'running', started_at: Date.now() / 1000 });
    } catch (err: any) {
      message.error(err?.message || 'Failed to start embedding');
    }
  };

  const handleStopReembed = async () => {
    try {
      await vectorApi.stopReembed(clientId);
      message.info('Stopping — already embedded records are kept');
      // Immediately update UI — don't wait for the background task to finish
      setReembedStatus(prev => prev ? { ...prev, status: 'stopped' } : null);
      loadStats();
    } catch (err: any) {
      message.error(err?.message || 'Failed to stop');
    }
  };

  const handleBackfill = async () => {
    setBackfillRunning(true);
    setBackfillTotal(0);
    backfillCancelRef.current = false;
    let total = 0;
    try {
      while (!backfillCancelRef.current) {
        const resp = await vectorApi.backfillSearchText(2000);
        if (!resp) break;
        total += resp.updated || 0;
        setBackfillTotal(total);
        if (resp.done || resp.updated === 0) {
          message.success(`Search index built: ${total.toLocaleString()} emails indexed`);
          break;
        }
      }
      if (backfillCancelRef.current) message.info(`Stopped — ${total.toLocaleString()} indexed`);
    } catch (err: any) {
      message.error(err?.message || 'Backfill failed');
    } finally {
      setBackfillRunning(false);
    }
  };

  if (!clientId) return null;

  return (
    <Card
      title={<Space><ThunderboltOutlined style={{ color: '#667eea' }} /> Embedding Coverage & Management</Space>}
      className="glass-card"
    >
      {statsLoading ? <Skeleton active paragraph={{ rows: 3 }} /> : stats ? (
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
              <Button icon={<SearchOutlined />} onClick={handleBackfill}>Build Search Index</Button>
            )}
            {reembedStatus?.status === 'complete' && reembedStatus.result && (
              <Text type="success"><CheckCircleOutlined /> {reembedStatus.result.total_embedded} embedded</Text>
            )}
          </Space>
        </>
      ) : (
        <Empty description="Select a client to view embedding stats" />
      )}
    </Card>
  );
};

export default UsagePage;
