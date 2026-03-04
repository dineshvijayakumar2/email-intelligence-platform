import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Table, Tag, Button, Tabs, Alert, Card, Tooltip, Spin, message, Empty } from 'antd';
import {
  FilterOutlined, ImportOutlined, InfoCircleOutlined,
  WarningOutlined, CheckCircleOutlined, SwapOutlined,
} from '@ant-design/icons';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { MetricCard } from '../../components/analytics/MetricCard';
import {
  rulesApi, clearRulesCache, getSignalColor, getSignalLabel,
} from '../../services/rulesService';
import type {
  RulesAnalyticsResponse, MailboxRulesMetrics, RulesInsight, UnifiedRule,
} from '../../services/rulesService';

const { Title, Text, Paragraph } = Typography;

// ============================================================================
// SIGNAL TAG COMPONENT
// ============================================================================

const SignalTag: React.FC<{ signal: string }> = ({ signal }) => (
  <Tag color={getSignalColor(signal)} style={{ borderRadius: 4 }}>
    {getSignalLabel(signal)}
  </Tag>
);

// ============================================================================
// MAIN PAGE
// ============================================================================

export const EmailRulesPage: React.FC = () => {
  const isMountedRef = useRef(true);
  const [clientId, setClientId] = useState('');
  const [analytics, setAnalytics] = useState<RulesAnalyticsResponse | null>(null);
  const [insights, setInsights] = useState<RulesInsight[]>([]);
  const [allRules, setAllRules] = useState<UnifiedRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState<string | null>(null); // mailbox_id being imported

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  // Load analytics + insights when client changes
  useEffect(() => {
    if (!clientId) return;
    const load = async () => {
      setLoading(true);

      // Step 1: Get initial analytics to find LIVE mailboxes
      const initialAnalytics = await rulesApi.analytics(clientId);
      if (!isMountedRef.current) return;

      // Step 2: Auto-import rules for LIVE-connected mailboxes
      const liveMailboxes = (initialAnalytics?.mailboxes || []).filter(mb => mb.live_connection);
      if (liveMailboxes.length > 0) {
        await Promise.allSettled(
          liveMailboxes.map(mb => rulesApi.importRules(mb.mailbox_id))
        );
        if (!isMountedRef.current) return;
        // Clear cache so we get fresh data after import
        clearRulesCache();
      }

      // Step 3: Load fresh analytics + insights (after import)
      const [analyticsData, insightsData] = await Promise.all([
        liveMailboxes.length > 0 ? rulesApi.analytics(clientId) : Promise.resolve(initialAnalytics),
        rulesApi.insights(clientId),
      ]);
      if (!isMountedRef.current) return;
      setAnalytics(analyticsData);
      setInsights(insightsData?.insights || []);

      // Step 4: Collect all rules from each mailbox
      const rules: UnifiedRule[] = [];
      for (const mb of analyticsData?.mailboxes || []) {
        if (mb.total_rules > 0) {
          const resp = await rulesApi.list(mb.mailbox_id);
          rules.push(...(resp?.items || []));
        }
      }
      if (isMountedRef.current) {
        setAllRules(rules);
        setLoading(false);
      }
    };
    load();
  }, [clientId]);

  // Import rules for a single mailbox
  const handleImport = async (mailboxId: string) => {
    setImporting(mailboxId);
    try {
      const result = await rulesApi.importRules(mailboxId);
      message.success(`Imported ${result.imported_count} rules from ${result.source}`);
      clearRulesCache();
      // Reload
      setClientId((prev) => { setClientId(''); return prev; }); // force re-fetch
      setTimeout(() => setClientId(clientId), 100);
    } catch {
      message.error('Failed to import rules. Check mail server connection.');
    } finally {
      setImporting(null);
    }
  };

  // Import all mailboxes
  const handleImportAll = async () => {
    if (!analytics) return;
    for (const mb of analytics.mailboxes) {
      if (mb.live_connection) {
        await handleImport(mb.mailbox_id);
      }
    }
  };

  // ======== COMPARISON TABLE COLUMNS ========
  const comparisonColumns = [
    {
      title: 'Mailbox',
      key: 'mailbox',
      render: (_: any, r: MailboxRulesMetrics) => (
        <div>
          <Text strong>{r.mailbox_email || 'Unknown'}</Text>
          <div>
            <Tag color={r.live_connection === 'gmail' ? 'red' : r.live_connection === 'outlook' ? 'blue' : 'default'} style={{ fontSize: 10 }}>
              {r.live_connection === 'gmail' ? 'Gmail' : r.live_connection === 'outlook' ? 'Outlook' : r.mailbox_type || 'Archive'}
            </Tag>
          </div>
        </div>
      ),
    },
    { title: 'Total', dataIndex: 'total_rules', key: 'total_rules', sorter: (a: MailboxRulesMetrics, b: MailboxRulesMetrics) => a.total_rules - b.total_rules },
    { title: 'Active', dataIndex: 'active_rules', key: 'active_rules' },
    {
      title: 'High Value', dataIndex: 'high_value_count', key: 'high_value',
      render: (v: number) => v > 0 ? <Tag color="green">{v}</Tag> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Escalation', dataIndex: 'escalation_count', key: 'escalation',
      render: (v: number) => v > 0 ? <Tag color="blue">{v}</Tag> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Low Priority', dataIndex: 'low_priority_count', key: 'low_priority',
      render: (v: number) => v > 0 ? <Tag color="orange">{v}</Tag> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Segmentation', dataIndex: 'segmentation_count', key: 'segmentation',
      render: (v: number) => v > 0 ? <Tag color="purple">{v}</Tag> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Forwards', dataIndex: 'forward_count', key: 'forward',
      render: (v: number) => v > 0 ? <Tag color="cyan">{v}</Tag> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Domains Covered', key: 'domains',
      render: (_: any, r: MailboxRulesMetrics) => r.covered_domains.length || 0,
    },
    {
      title: 'Action', key: 'action',
      render: (_: any, r: MailboxRulesMetrics) => (
        <Button
          size="small"
          icon={<ImportOutlined />}
          loading={importing === r.mailbox_id}
          onClick={() => handleImport(r.mailbox_id)}
          disabled={!r.live_connection}
        >
          Import
        </Button>
      ),
    },
  ];

  // ======== ALL RULES TABLE COLUMNS ========
  const rulesColumns = [
    {
      title: 'Source', key: 'source', width: 80,
      render: (_: any, r: UnifiedRule) => (
        <Tag color={r.source_type === 'gmail' ? 'red' : 'blue'}>
          {r.source_type === 'gmail' ? 'Gmail' : 'Outlook'}
        </Tag>
      ),
    },
    {
      title: 'Mailbox', dataIndex: 'mailbox_email', key: 'mailbox', width: 200,
      render: (v: string) => <Text ellipsis={{ tooltip: v }} style={{ maxWidth: 180 }}>{v}</Text>,
    },
    { title: 'Rule Name', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: 'Signal', key: 'signal', width: 120,
      render: (_: any, r: UnifiedRule) => <SignalTag signal={r.engagement_signal} />,
      filters: [
        { text: 'High Value', value: 'high_value' },
        { text: 'Escalation', value: 'escalation' },
        { text: 'Low Priority', value: 'low_priority' },
        { text: 'Segmentation', value: 'segmentation' },
        { text: 'Neutral', value: 'neutral' },
      ],
      onFilter: (value: any, record: UnifiedRule) => record.engagement_signal === value,
    },
    {
      title: 'Conditions', key: 'conditions',
      render: (_: any, r: UnifiedRule) => {
        const parts: string[] = [];
        if (r.conditions.from_addresses.length) parts.push(`From: ${r.conditions.from_addresses.join(', ')}`);
        if (r.conditions.from_domains.length) parts.push(`Domain: ${r.conditions.from_domains.join(', ')}`);
        if (r.conditions.subject_contains.length) parts.push(`Subject: ${r.conditions.subject_contains.join(', ')}`);
        if (r.conditions.has_attachment) parts.push('Has attachment');
        return <Text type="secondary" style={{ fontSize: 12 }}>{parts.join(' | ') || 'Any'}</Text>;
      },
    },
    {
      title: 'Actions', key: 'actions',
      render: (_: any, r: UnifiedRule) => {
        const tags: React.ReactNode[] = [];
        if (r.actions.mark_important) tags.push(<Tag key="imp" color="gold">Important</Tag>);
        if (r.actions.forward_to.length) tags.push(<Tag key="fwd" color="blue">Forward</Tag>);
        if (r.actions.label) tags.push(<Tag key="lbl" color="purple">Label</Tag>);
        if (r.actions.move_to_folder) tags.push(<Tag key="mv" color="cyan">Move</Tag>);
        if (r.actions.mark_read) tags.push(<Tag key="rd" color="orange">Mark Read</Tag>);
        if (r.actions.skip_inbox) tags.push(<Tag key="skip" color="orange">Skip Inbox</Tag>);
        if (r.actions.delete) tags.push(<Tag key="del" color="red">Delete</Tag>);
        return tags.length ? tags : <Text type="secondary">None</Text>;
      },
    },
    {
      title: 'Active', dataIndex: 'is_active', key: 'active', width: 70,
      render: (v: boolean) => v ? <Tag color="green">Yes</Tag> : <Tag>No</Tag>,
    },
  ];

  // ======== INSIGHT SEVERITY ICON ========
  const severityIcon = (severity: string) => {
    switch (severity) {
      case 'critical': return <WarningOutlined style={{ color: '#f5222d' }} />;
      case 'warning': return <WarningOutlined style={{ color: '#faad14' }} />;
      default: return <InfoCircleOutlined style={{ color: '#1890ff' }} />;
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Title level={3} style={{ margin: 0 }}>
            <FilterOutlined style={{ marginRight: 8 }} />
            Email Rules Intelligence
          </Title>
          <Text type="secondary">View and analyze email rules across account managers</Text>
        </Col>
        <Col>
          <Row gutter={12} align="middle">
            <Col>
              <ClientSelector value={clientId} onChange={setClientId} />
            </Col>
            <Col>
              <Button
                type="primary"
                icon={<ImportOutlined />}
                onClick={handleImportAll}
                disabled={!analytics || analytics.total_mailboxes === 0}
                loading={!!importing}
              >
                Import All Rules
              </Button>
            </Col>
          </Row>
        </Col>
      </Row>

      {!clientId ? (
        <Empty description="Select a client to view email rules" />
      ) : loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
      ) : (
        <>
          {/* Summary Cards */}
          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <MetricCard
                title="Total Rules"
                value={analytics?.total_rules || 0}
                prefix={<FilterOutlined />}
              />
            </Col>
            <Col span={6}>
              <MetricCard
                title="Mailboxes Covered"
                value={(analytics?.total_mailboxes || 0) - (analytics?.mailboxes_with_no_rules || 0)}
                prefix={<CheckCircleOutlined />}
                suffix={`/ ${analytics?.total_mailboxes || 0}`}
              />
            </Col>
            <Col span={6}>
              <MetricCard
                title="Avg Rules / Mailbox"
                value={analytics?.avg_rules_per_mailbox || 0}
                prefix={<SwapOutlined />}
              />
            </Col>
            <Col span={6}>
              <MetricCard
                title="No Rules"
                value={analytics?.mailboxes_with_no_rules || 0}
                prefix={<WarningOutlined />}
                valueStyle={analytics?.mailboxes_with_no_rules ? { color: '#faad14' } : undefined}
              />
            </Col>
          </Row>

          {/* Cross-AM Comparison Table */}
          <Card title="Cross-AM Rules Comparison" style={{ marginBottom: 24 }}>
            <Table
              dataSource={analytics?.mailboxes || []}
              columns={comparisonColumns}
              rowKey="mailbox_id"
              pagination={false}
              size="small"
              rowClassName={(record) => record.total_rules === 0 ? 'ant-table-row-warning' : ''}
            />
          </Card>

          {/* Tabs: All Rules + Insights */}
          <Card>
            <Tabs
              defaultActiveKey="rules"
              items={[
                {
                  key: 'rules',
                  label: `All Rules (${allRules.length})`,
                  children: (
                    <Table
                      dataSource={allRules}
                      columns={rulesColumns}
                      rowKey={(r) => `${r.source_type}-${r.source_rule_id}`}
                      pagination={{ pageSize: 20, showSizeChanger: true }}
                      size="small"
                      scroll={{ x: 1000 }}
                    />
                  ),
                },
                {
                  key: 'insights',
                  label: `Insights (${insights.length})`,
                  children: insights.length === 0 ? (
                    <Empty description="No insights available. Import rules first." />
                  ) : (
                    <div>
                      {insights.map((insight, idx) => (
                        <Alert
                          key={idx}
                          type={insight.severity === 'critical' ? 'error' : insight.severity === 'warning' ? 'warning' : 'info'}
                          icon={severityIcon(insight.severity)}
                          showIcon
                          style={{ marginBottom: 12 }}
                          message={
                            <Text strong>
                              {insight.insight_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                            </Text>
                          }
                          description={
                            <div>
                              <Paragraph style={{ marginBottom: 8 }}>{insight.description}</Paragraph>
                              <Paragraph type="secondary" style={{ marginBottom: 4 }}>
                                <strong>Recommendation:</strong> {insight.recommendation}
                              </Paragraph>
                              {insight.affected_mailboxes.length > 0 && (
                                <div>
                                  {insight.affected_mailboxes.map((mb, i) => (
                                    <Tag key={i} style={{ marginBottom: 4 }}>{mb}</Tag>
                                  ))}
                                </div>
                              )}
                            </div>
                          }
                        />
                      ))}
                    </div>
                  ),
                },
              ]}
            />
          </Card>
        </>
      )}
    </div>
  );
};

export default EmailRulesPage;
