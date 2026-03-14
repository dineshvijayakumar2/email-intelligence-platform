/**
 * Opportunities Page — Sprint 3 Session 9
 *
 * 4-tab view: Action Items, Opportunities, Competitors, Entities
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card, Tabs, Table, Tag, Typography, Space, Spin, Empty, Tooltip, Modal,
} from 'antd';
import {
  ThunderboltOutlined, DollarOutlined, TrophyOutlined, TeamOutlined,
} from '@ant-design/icons';
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
      // Fire mailbox-scoped calls in parallel
      const [actionsData, intelData] = await Promise.all([
        bucketApi.getActionItems(mailboxId, clientId, 0.3, 100),
        intelligenceApi.list(mailboxId, { page_size: 50, primary_bucket: 'revenue_opportunity' }),
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
  }, [mailboxId, clientId]);

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

  // Action Items columns
  const actionColumns = [
    {
      title: 'Bucket', dataIndex: 'bucket', key: 'bucket', width: 130,
      render: (val: string) => <Tag color={BUCKET_COLORS[val] || 'default'}>{val?.replace(/_/g, ' ')}</Tag>,
    },
    {
      title: 'Severity', dataIndex: 'severity', key: 'severity', width: 85,
      render: (val: string) => {
        const colors: Record<string, string> = { critical: 'red', high: 'orange', medium: 'blue' };
        return <Tag color={colors[val] || 'default'}>{val}</Tag>;
      },
    },
    {
      title: 'Email', key: 'email_context', width: 260, ellipsis: true,
      render: (_: unknown, record: ActionItem) => (
        <Tooltip title={record.email_subject || record.email_summary}>
          <div>
            <Text style={{ fontSize: 13, display: 'block' }} ellipsis>
              {record.email_subject || record.email_summary || '—'}
            </Text>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {record.email_sender_name || record.email_sender || ''}
              {record.email_date ? ` · ${formatDate(record.email_date)}` : ''}
            </Text>
          </div>
        </Tooltip>
      ),
    },
    { title: 'Action', dataIndex: 'recommended_action', key: 'action', ellipsis: true },
    { title: 'Summary', dataIndex: 'email_summary', key: 'summary', ellipsis: true },
    {
      title: 'Confidence', dataIndex: 'confidence', key: 'confidence', width: 95,
      render: (val: number) => `${((val || 0) * 100).toFixed(0)}%`,
    },
    {
      title: 'Score', dataIndex: 'business_signal_score', key: 'score', width: 70,
      sorter: (a: ActionItem, b: ActionItem) => (b.business_signal_score || 0) - (a.business_signal_score || 0),
    },
  ];

  // Opportunities columns
  const oppColumns = [
    {
      title: 'Date', dataIndex: 'email_date', key: 'date', width: 110,
      render: (val: string) => val ? (
        <Text style={{ fontSize: 12 }} type="secondary">{formatDate(val)}</Text>
      ) : '—',
      sorter: (a: IntelligenceResult, b: IntelligenceResult) =>
        new Date(b.email_date || 0).getTime() - new Date(a.email_date || 0).getTime(),
      defaultSortOrder: 'ascend' as const,
    },
    {
      title: 'Subject', dataIndex: 'email_subject', key: 'subject', ellipsis: true,
      render: (val: string, record: IntelligenceResult) => (
        <Tooltip title={record.email_sender}>
          <Text ellipsis style={{ fontSize: 13 }}>{val || '—'}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>{record.email_sender_name || record.email_sender || ''}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Signal', dataIndex: 'business_signal', key: 'signal', width: 150,
      render: (val: string) => val ? <Tag color="green">{val.replace(/_/g, ' ')}</Tag> : '-',
    },
    { title: 'Summary', dataIndex: 'summary', key: 'summary', ellipsis: true },
    {
      title: 'Score', dataIndex: 'business_signal_score', key: 'score', width: 70,
      sorter: (a: any, b: any) => (b.business_signal_score || 0) - (a.business_signal_score || 0),
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

  // Entity columns
  const entityColumns = [
    {
      title: 'Type', dataIndex: 'entity_type', key: 'type', width: 100,
      render: (val: string) => {
        const colors: Record<string, string> = { competitor: 'red', product: 'blue', person: 'green' };
        return <Tag color={colors[val] || 'default'}>{val}</Tag>;
      },
    },
    { title: 'Name', dataIndex: 'entity_name', key: 'name' },
    {
      title: 'Mentions', dataIndex: 'mention_count', key: 'mentions', width: 100,
      sorter: (a: BusinessEntity, b: BusinessEntity) => (b.mention_count || 0) - (a.mention_count || 0),
      defaultSortOrder: 'ascend' as const,
    },
    {
      title: 'Last Seen', dataIndex: 'last_seen_at', key: 'last', width: 120,
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>Opportunities & Signals</Title>
        <MailboxSelector value={mailboxIds} onChange={handleMailboxChange} mode="single" />
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
