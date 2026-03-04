/**
 * Opportunities Page — Sprint 3 Session 9
 *
 * 4-tab view: Action Items, Opportunities, Competitors, Entities
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card, Tabs, Table, Tag, Typography, Space, Spin, Empty, Tooltip,
} from 'antd';
import {
  ThunderboltOutlined, DollarOutlined, TrophyOutlined, TeamOutlined,
} from '@ant-design/icons';
import { bucketApi, entityApi, intelligenceApi } from '../../services/aiService';
import { MailboxSelector } from '../../components/MailboxSelector';
import type {
  ActionItem, BusinessEntity, OpportunitySignal, IntelligenceResult,
} from '../../types/ai';

const { Title, Text } = Typography;

const BUCKET_COLORS: Record<string, string> = {
  buying_signal: 'green', expansion_signal: 'blue', churn_risk: 'red',
  competitor_threat: 'red', missed_opportunity: 'orange', stakeholder_entry: 'purple',
  silent_champion: 'gold', unresolved_block: 'yellow',
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

  // Resolve client_id from mailbox
  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  const loadData = useCallback(async () => {
    if (!mailboxId) return;
    setLoading(true);
    try {
      // Fetch action items (these don't need client_id)
      const actionsData = await bucketApi.getActionItems(mailboxId, clientId, 0.3, 100);
      if (!isMountedRef.current) return;
      setActionItems(actionsData.items || []);

      // Fetch high-signal intelligence
      const intelData = await intelligenceApi.list(mailboxId, {
        page_size: 50,
        has_buying_signal: true,
      });
      if (!isMountedRef.current) return;
      setOpportunities(intelData.items || []);

      // Fetch entities if we have client_id
      if (clientId) {
        const [compData, entityData] = await Promise.all([
          entityApi.getCompetitors(clientId),
          entityApi.list(clientId, undefined, 100),
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

  // Handle mailbox change — also resolve client_id
  const handleMailboxChange = async (ids: string[]) => {
    setMailboxIds(ids);
    const id = ids[0] || '';
    // Try to get client_id from first intelligence result
    if (id) {
      try {
        const statsData = await intelligenceApi.list(id, { page_size: 1 });
        const firstItem: any = statsData.items?.[0];
        if (firstItem?.client_id) {
          setClientId(firstItem.client_id);
        }
      } catch { /* ok */ }
    }
  };

  // Action Items columns
  const actionColumns = [
    {
      title: 'Bucket', dataIndex: 'bucket', key: 'bucket', width: 140,
      render: (val: string) => <Tag color={BUCKET_COLORS[val] || 'default'}>{val?.replace(/_/g, ' ')}</Tag>,
    },
    {
      title: 'Severity', dataIndex: 'severity', key: 'severity', width: 90,
      render: (val: string) => {
        const colors: Record<string, string> = { critical: 'red', high: 'orange', medium: 'blue' };
        return <Tag color={colors[val] || 'default'}>{val}</Tag>;
      },
    },
    { title: 'Action', dataIndex: 'recommended_action', key: 'action' },
    { title: 'Summary', dataIndex: 'email_summary', key: 'summary', ellipsis: true },
    {
      title: 'Confidence', dataIndex: 'confidence', key: 'confidence', width: 100,
      render: (val: number) => `${((val || 0) * 100).toFixed(0)}%`,
    },
    {
      title: 'Score', dataIndex: 'business_signal_score', key: 'score', width: 80,
      sorter: (a: ActionItem, b: ActionItem) => (b.business_signal_score || 0) - (a.business_signal_score || 0),
    },
  ];

  // Opportunities columns
  const oppColumns = [
    { title: 'Subject', dataIndex: 'email_subject', key: 'subject', ellipsis: true },
    { title: 'Sender', dataIndex: 'email_sender', key: 'sender', width: 180, ellipsis: true },
    {
      title: 'Signal', dataIndex: 'business_signal', key: 'signal', width: 140,
      render: (val: string) => val ? <Tag color="green">{val.replace(/_/g, ' ')}</Tag> : '-',
    },
    { title: 'Summary', dataIndex: 'summary', key: 'summary', ellipsis: true },
    {
      title: 'Score', dataIndex: 'business_signal_score', key: 'score', width: 80,
      sorter: (a: any, b: any) => (b.business_signal_score || 0) - (a.business_signal_score || 0),
      defaultSortOrder: 'ascend' as const,
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
      render: (val: string) => val ? new Date(val).toLocaleDateString() : '-',
    },
    {
      title: 'Last Seen', dataIndex: 'last_seen_at', key: 'last', width: 120,
      render: (val: string) => val ? new Date(val).toLocaleDateString() : '-',
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
      render: (val: string) => val ? new Date(val).toLocaleDateString() : '-',
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
          scroll={{ x: 800 }}
          loading={loading}
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
    </div>
  );
};

export default OpportunitiesPage;
