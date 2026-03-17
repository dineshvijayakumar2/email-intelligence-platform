/**
 * Opportunities Page — Sprint 3 Session 9
 *
 * 4-tab view: Action Items, Opportunities, Competitors, Entities
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card, Tabs, Table, Tag, Typography, Space, Spin, Empty, Tooltip, Modal,
  DatePicker, Select, Button,
} from 'antd';
import {
  ThunderboltOutlined, DollarOutlined, TrophyOutlined, TeamOutlined,
  ReloadOutlined, FilterOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { bucketApi, entityApi, intelligenceApi } from '../../services/aiService';
import { emailService } from '../../services/emailService';
import { MailboxSelector } from '../../components/MailboxSelector';
import { EmailDetailPanel } from '../../components/EmailDetailPanel';
import { formatDate } from '../../utils/dateUtils';
import type {
  ActionItem, BusinessEntity, OpportunitySignal, IntelligenceResult,
} from '../../types/ai';
import type { Email } from '../../services/emailService';

const { Title, Text } = Typography;

const BUCKET_COLORS: Record<string, string> = {
  response_urgency: 'red', deal_at_risk: 'orange', retention_risk: 'red',
  revenue_opportunity: 'green', new_relationship: 'blue', account_neglect: 'gold',
};

const OpportunitiesPage: React.FC = () => {
  const isMountedRef = useRef(true);
  const [loading, setLoading] = useState(false);
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';
  const [clientId, setClientId] = useState<string>('');
  const [activeTab, setActiveTab] = useState('actions');
  const [dateRange, setDateRange] = useState<number>(30); // days lookback

  // Data
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [opportunities, setOpportunities] = useState<IntelligenceResult[]>([]);
  const [competitors, setCompetitors] = useState<BusinessEntity[]>([]);
  const [entities, setEntities] = useState<BusinessEntity[]>([]);

  // Email preview modal
  const [previewEmail, setPreviewEmail] = useState<Email | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Resolve client_id from mailbox
  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  const loadData = useCallback(async () => {
    if (!mailboxId) return;
    setLoading(true);
    try {
      // Compute date_from based on lookback range
      const dateFrom = new Date();
      dateFrom.setDate(dateFrom.getDate() - dateRange);
      const dateFromStr = dateFrom.toISOString().split('T')[0];

      // Fire mailbox-scoped calls in parallel
      const [actionsData, intelData] = await Promise.all([
        bucketApi.getActionItems(mailboxId, clientId, 0.3, 100),
        intelligenceApi.list(mailboxId, { page_size: 100, date_from: dateFromStr } as any),
      ]);
      if (!isMountedRef.current) return;
      setActionItems(actionsData.items || []);
      setOpportunities(intelData.items || []);

      // Resolve client_id from results if not already set
      const resolvedClientId = clientId ||
        (actionsData.items?.[0] as any)?.client_id ||
        (intelData.items?.[0] as any)?.client_id || '';
      if (resolvedClientId && resolvedClientId !== clientId) {
        setClientId(resolvedClientId);
      }

      // Fire entity calls in parallel (only if client_id available)
      if (resolvedClientId) {
        const [compData, entityData] = await Promise.all([
          entityApi.getCompetitors(resolvedClientId),
          entityApi.list(resolvedClientId, undefined, 100),
        ]);
        if (!isMountedRef.current) return;
        setCompetitors(compData.competitors || []);
        setEntities(entityData.items || []);
      }
    } catch (err) {
      console.error('Failed to load opportunities:', err);
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [mailboxId, clientId, dateRange]);

  useEffect(() => {
    if (mailboxId) loadData();
  }, [mailboxId, loadData]);

  // Handle mailbox change — client_id resolved from loadData results
  const handleMailboxChange = (ids: string[]) => {
    setMailboxIds(ids);
    setClientId('');
  };

  const openEmailPreview = async (emailId: string | undefined) => {
    if (!emailId) return;
    setPreviewLoading(true);
    setPreviewEmail(null);
    const email = await emailService.getEmail(emailId);
    if (isMountedRef.current) {
      setPreviewEmail(email);
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewEmail(null);
    setPreviewLoading(false);
  };

  const rowClickProps = (emailId: string | undefined) => ({
    onClick: () => openEmailPreview(emailId),
    style: { cursor: emailId ? 'pointer' : 'default' },
  });

  // Unique bucket values for filter
  const bucketFilters = [...new Set(actionItems.map(i => i.bucket).filter(Boolean))].map(b => ({ text: b.replace(/_/g, ' '), value: b }));
  const severityFilters = [
    { text: 'Critical', value: 'critical' },
    { text: 'High', value: 'high' },
    { text: 'Medium', value: 'medium' },
  ];

  // Action Items columns
  const actionColumns = [
    {
      title: 'Bucket', dataIndex: 'bucket', key: 'bucket', width: 140,
      filters: bucketFilters,
      onFilter: (value: any, record: ActionItem) => record.bucket === value,
      render: (val: string) => <Tag color={BUCKET_COLORS[val] || 'default'}>{val?.replace(/_/g, ' ')}</Tag>,
    },
    {
      title: 'Severity', dataIndex: 'severity', key: 'severity', width: 90,
      filters: severityFilters,
      onFilter: (value: any, record: ActionItem) => record.severity === value,
      sorter: (a: ActionItem, b: ActionItem) => {
        const order = ['critical', 'high', 'medium'];
        return order.indexOf(a.severity || 'medium') - order.indexOf(b.severity || 'medium');
      },
      render: (val: string) => {
        const colors: Record<string, string> = { critical: 'red', high: 'orange', medium: 'blue' };
        return <Tag color={colors[val] || 'default'}>{val}</Tag>;
      },
    },
    {
      title: 'Date', key: 'date', width: 95,
      sorter: (a: ActionItem, b: ActionItem) => (a.email_date || '').localeCompare(b.email_date || ''),
      defaultSortOrder: 'descend' as const,
      render: (_: unknown, record: ActionItem) => record.email_date ? <Text type="secondary" style={{ fontSize: 12 }}>{formatDate(record.email_date)}</Text> : '—',
    },
    {
      title: 'Email', key: 'email_context', ellipsis: true,
      sorter: (a: ActionItem, b: ActionItem) => (a.email_subject || a.email_summary || '').localeCompare(b.email_subject || b.email_summary || ''),
      render: (_: unknown, record: ActionItem) => (
        <Tooltip title={record.email_subject || record.email_summary}>
          <div>
            <Text style={{ fontSize: 13, display: 'block' }} ellipsis>
              {record.email_subject || record.email_summary || '—'}
            </Text>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {record.email_sender_name || record.email_sender || ''}
            </Text>
          </div>
        </Tooltip>
      ),
    },
    { title: 'Action', dataIndex: 'recommended_action', key: 'action', ellipsis: true },
    {
      title: 'Confidence', dataIndex: 'confidence', key: 'confidence', width: 95,
      sorter: (a: ActionItem, b: ActionItem) => (a.confidence || 0) - (b.confidence || 0),
      render: (val: number) => `${((val || 0) * 100).toFixed(0)}%`,
    },
    {
      title: 'Score', dataIndex: 'business_signal_score', key: 'score', width: 70,
      sorter: (a: ActionItem, b: ActionItem) => (a.business_signal_score || 0) - (b.business_signal_score || 0),
      defaultSortOrder: 'descend' as const,
    },
  ];

  // Signal filters from data
  const signalFilters = [...new Set(opportunities.map(i => i.business_signal).filter(Boolean))].map(s => ({ text: (s as string).replace(/_/g, ' '), value: s as string }));
  const intentFilters = [...new Set(opportunities.map(i => i.intent).filter(Boolean))].map(s => ({ text: (s as string).replace(/_/g, ' '), value: s as string }));
  const urgencyFilters = ['critical', 'high', 'medium', 'low'].map(u => ({ text: u, value: u }));

  // Opportunities columns
  const oppColumns = [
    {
      title: 'Date', dataIndex: 'email_date', key: 'date', width: 100,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) =>
        (a.email_date || '').localeCompare(b.email_date || ''),
      defaultSortOrder: 'descend' as const,
      render: (val: string) => val ? <Text style={{ fontSize: 12 }} type="secondary">{formatDate(val)}</Text> : '—',
    },
    {
      title: 'Subject', key: 'subject', ellipsis: true,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) =>
        (a.email_subject || '').localeCompare(b.email_subject || ''),
      render: (_: any, record: IntelligenceResult) => (
        <Tooltip title={record.email_sender}>
          <Text ellipsis style={{ fontSize: 13 }}>{record.email_subject || '—'}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>{record.email_sender_name || record.email_sender || ''}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Intent', dataIndex: 'intent', key: 'intent', width: 130,
      filters: intentFilters,
      onFilter: (value: any, record: IntelligenceResult) => record.intent === value,
      render: (val: string) => val ? <Tag>{val.replace(/_/g, ' ')}</Tag> : '-',
    },
    {
      title: 'Urgency', dataIndex: 'urgency', key: 'urgency', width: 90,
      filters: urgencyFilters,
      onFilter: (value: any, record: IntelligenceResult) => record.urgency === value,
      sorter: (a: IntelligenceResult, b: IntelligenceResult) => {
        const order = ['critical', 'high', 'medium', 'low', 'none'];
        return order.indexOf(a.urgency || 'none') - order.indexOf(b.urgency || 'none');
      },
      render: (val: string) => {
        const colors: Record<string, string> = { critical: 'red', high: 'volcano', medium: 'orange', low: 'blue' };
        return val ? <Tag color={colors[val] || 'default'}>{val}</Tag> : '-';
      },
    },
    {
      title: 'Signal', dataIndex: 'business_signal', key: 'signal', width: 140,
      filters: signalFilters,
      onFilter: (value: any, record: IntelligenceResult) => record.business_signal === value,
      render: (val: string) => val ? <Tag color="green">{val.replace(/_/g, ' ')}</Tag> : '-',
    },
    { title: 'Summary', dataIndex: 'summary', key: 'summary', ellipsis: true },
    {
      title: 'Score', dataIndex: 'business_signal_score', key: 'score', width: 70,
      sorter: (a: any, b: any) => (a.business_signal_score || 0) - (b.business_signal_score || 0),
      defaultSortOrder: 'descend' as const,
    },
  ];

  // Competitor columns
  const compColumns = [
    { title: 'Competitor', dataIndex: 'entity_name', key: 'name' },
    {
      title: 'Mentions', dataIndex: 'mention_count', key: 'mentions', width: 100,
      sorter: (a: BusinessEntity, b: BusinessEntity) => (b.mention_count || 0) - (a.mention_count || 0),
      defaultSortOrder: 'ascend' as const,
    },
    {
      title: 'First Seen', dataIndex: 'first_seen_at', key: 'first', width: 120,
      render: (val: string) => val ? formatDate(val) : '-',
    },
    {
      title: 'Last Seen', dataIndex: 'last_seen_at', key: 'last', width: 120,
      render: (val: string) => val ? formatDate(val) : '-',
    },
    {
      title: 'Context', dataIndex: 'context_snippets', key: 'context',
      render: (val: string[]) => val?.length ? (
        <Tooltip title={val.join(' | ')}><Text ellipsis>{val[0]}</Text></Tooltip>
      ) : '-',
    },
  ];

  // Entity type filters
  const entityTypeFilters = [...new Set(entities.map(e => e.entity_type).filter(Boolean))].map(t => ({ text: t, value: t }));

  // Entity columns
  const entityColumns = [
    {
      title: 'Type', dataIndex: 'entity_type', key: 'type', width: 100,
      filters: entityTypeFilters,
      onFilter: (value: any, record: BusinessEntity) => record.entity_type === value,
      render: (val: string) => {
        const colors: Record<string, string> = { competitor: 'red', product: 'blue', person: 'green' };
        return <Tag color={colors[val] || 'default'}>{val}</Tag>;
      },
    },
    {
      title: 'Name', dataIndex: 'entity_name', key: 'name',
      sorter: (a: BusinessEntity, b: BusinessEntity) => (a.entity_name || '').localeCompare(b.entity_name || ''),
    },
    {
      title: 'Mentions', dataIndex: 'mention_count', key: 'mentions', width: 100,
      sorter: (a: BusinessEntity, b: BusinessEntity) => (a.mention_count || 0) - (b.mention_count || 0),
      defaultSortOrder: 'descend' as const,
    },
    {
      title: 'First Seen', dataIndex: 'first_seen_at', key: 'first', width: 110,
      sorter: (a: BusinessEntity, b: BusinessEntity) => (a.first_seen_at || '').localeCompare(b.first_seen_at || ''),
      render: (val: string) => val ? formatDate(val) : '-',
    },
    {
      title: 'Last Seen', dataIndex: 'last_seen_at', key: 'last', width: 110,
      sorter: (a: BusinessEntity, b: BusinessEntity) => (a.last_seen_at || '').localeCompare(b.last_seen_at || ''),
      defaultSortOrder: 'descend' as const,
      render: (val: string) => val ? formatDate(val) : '-',
    },
  ];

  const tabItems = [
    {
      key: 'actions',
      label: <Space><ThunderboltOutlined />Action Items ({actionItems.length})</Space>,
      children: (
        <Table
          dataSource={actionItems}
          columns={actionColumns}
          rowKey={(r) => r.email_id || `${Math.random()}`}
          size="small"
          pagination={{ pageSize: 20 }}
          scroll={{ x: 800 }}
          loading={loading}
          onRow={(r) => rowClickProps(r.email_id)}
        />
      ),
    },
    {
      key: 'opportunities',
      label: <Space><DollarOutlined />Active Opportunities ({opportunities.length})</Space>,
      children: (
        <Table
          dataSource={opportunities}
          columns={oppColumns}
          rowKey={(r) => r.email_id || `${Math.random()}`}
          size="small"
          pagination={{ pageSize: 20 }}
          scroll={{ x: 900 }}
          loading={loading}
          onRow={(r) => rowClickProps(r.email_id)}
        />
      ),
    },
    {
      key: 'competitors',
      label: <Space><TrophyOutlined />Competitors ({competitors.length})</Space>,
      children: (
        <Table
          dataSource={competitors}
          columns={compColumns}
          rowKey={(r) => r.id || r.entity_name}
          size="small"
          pagination={{ pageSize: 20 }}
          scroll={{ x: 700 }}
          loading={loading}
        />
      ),
    },
    {
      key: 'entities',
      label: <Space><TeamOutlined />All Entities ({entities.length})</Space>,
      children: (
        <Table
          dataSource={entities}
          columns={entityColumns}
          rowKey={(r) => r.id || `${r.entity_type}-${r.entity_name}`}
          size="small"
          pagination={{ pageSize: 20 }}
          scroll={{ x: 500 }}
          loading={loading}
        />
      ),
    },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <Title level={3} style={{ margin: 0 }}>Opportunities & Signals</Title>
        <Space wrap>
          <MailboxSelector value={mailboxIds} onChange={handleMailboxChange} mode="single" />
          <Select
            value={dateRange}
            onChange={setDateRange}
            style={{ width: 130 }}
            options={[
              { value: 7, label: 'Last 7 days' },
              { value: 14, label: 'Last 14 days' },
              { value: 30, label: 'Last 30 days' },
              { value: 90, label: 'Last 90 days' },
              { value: 180, label: 'Last 6 months' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={loadData} disabled={!mailboxId}>Refresh</Button>
        </Space>
      </div>

      {!mailboxId ? (
        <Card className="glass-card"><Empty description="Select a mailbox to view opportunities" /></Card>
      ) : (
        <Card className="glass-card">
          <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
        </Card>
      )}

      {/* Email preview modal */}
      <Modal
        open={previewLoading || previewEmail !== null}
        onCancel={closePreview}
        footer={null}
        width={860}
        styles={{ body: { padding: 0, maxHeight: '80vh', overflowY: 'auto' } }}
        destroyOnClose
      >
        {previewLoading ? (
          <div style={{ padding: 48, textAlign: 'center' }}>
            <Spin tip="Loading email…" />
          </div>
        ) : (
          <EmailDetailPanel
            email={previewEmail}
            loading={false}
            onClose={closePreview}
            expanded={false}
            onToggleExpand={() => {}}
          />
        )}
      </Modal>
    </div>
  );
};

export default OpportunitiesPage;
