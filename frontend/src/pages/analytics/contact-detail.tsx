import React from 'react';
import { Row, Col, Typography, Button, Tag, Descriptions, Skeleton, Table } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import QBLinkWidget from '../../components/QBLinkWidget';
import { useParams, useNavigate } from 'react-router-dom';
import { MetricCard } from '../../components/analytics/MetricCard';
import AIInsightsCard from '../../components/AIInsightsCard';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import { LifecycleBadge } from '../../components/analytics/LifecycleBadge';
import { useContactDetail } from '../../hooks/queries';
import { useThreadsByContact } from '../../hooks/queries';
import { useQuery } from '@tanstack/react-query';
import {
  patternsApi,
  formatRelativeTime,
  formatResponseTime,
  formatRatio,
  threadStatusConfig,
} from '../../services/analyticsService';
import type { ThreadStatusSummary, CommunicationPattern } from '../../types/analytics';

const { Title, Text } = Typography;

export const ContactDetail: React.FC = () => {
  const { contactId } = useParams<{ contactId: string }>();
  const navigate = useNavigate();

  // All data via TanStack Query
  const contactQuery = useContactDetail(contactId);
  const threadsQuery = useThreadsByContact(contactId);
  const patternQuery = useQuery<CommunicationPattern | null>({
    queryKey: ['contact-pattern', contactId],
    queryFn: () => patternsApi.byContact(contactId!),
    enabled: !!contactId,
    staleTime: 60_000,
  });

  const contact = contactQuery.data;
  const threads = threadsQuery.data?.threads || [];
  const pattern = patternQuery.data;

  const handleThreadClick = (record: ThreadStatusSummary) => {
    const name = encodeURIComponent(record.subject || record.thread_id?.slice(0, 20) || 'Thread');
    navigate(`/emails?thread_id=${encodeURIComponent(record.thread_id)}&name=${name}`);
  };

  const threadColumns = [
    {
      title: 'Subject', dataIndex: 'subject', key: 'subject', ellipsis: true,
      render: (v: string, r: ThreadStatusSummary) => (
        <a onClick={(e) => { e.stopPropagation(); handleThreadClick(r); }} style={{ color: '#667eea' }}>
          {v || r.thread_id?.slice(0, 16) + '...'}
        </a>
      ),
    },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 140,
      render: (v: string) => {
        const cfg = threadStatusConfig[v] || { label: v, color: 'default' };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    { title: 'Emails', dataIndex: 'total_messages', key: 'msgs', width: 90 },
    { title: 'Last Email', dataIndex: 'last_message_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  if (contactQuery.isLoading) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>Back to Contacts</Button>
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>Back to Contacts</Button>
        <Text type="secondary">Contact not found</Text>
      </div>
    );
  }

  const totalEmails = (contact.total_emails_sent || 0) + (contact.total_emails_received || 0);

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>Back to Contacts</Button>

      <div className="glass-card fade-in-up" style={{ padding: 20, marginBottom: 16 }}>
        <Row align="middle" gutter={16}>
          <Col flex="auto">
            <Title level={4} style={{ margin: 0 }}>{contact.full_name || contact.email_address}</Title>
            {contact.full_name && <Text type="secondary">{contact.email_address}</Text>}
            {contact.qb_quotes_count != null && <Tag style={{ marginLeft: 8 }}>{contact.qb_quotes_count} quotes</Tag>}
          </Col>
          <Col>
            <EngagementBadge score={contact.engagement_score} showBar />
            <QBLinkWidget
              mode="contact"
              entityId={contactId!}
              clientId={contact.client_id}
              qbLinkedId={contact.qb_contact_id}
              qbDisplayName={contact.qb_contact_id ? `QB Contact` : undefined}
              onLinked={() => window.location.reload()}
            />
          </Col>
        </Row>
      </div>

      <Row gutter={[16, 16]} className="fade-in-up stagger-1">
        <Col xs={12} sm={6}><MetricCard title="Total Emails" value={totalEmails} onClick={() => navigate(`/emails?contact_id=${contactId}`)} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Initiation Ratio" value={contact.initiation_ratio != null ? formatRatio(contact.initiation_ratio) : 'N/A'} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Our Reply Rate" value={contact.reply_rate != null ? formatRatio(contact.reply_rate) : 'N/A'} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Our Avg Response" value={formatResponseTime(contact.avg_response_time_seconds)} /></Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-2">
        <Col xs={24} sm={10}>
          <div className="glass-card" style={{ padding: 20 }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Details</Text>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="First Contact">{formatRelativeTime(contact.first_contacted_at)}</Descriptions.Item>
              <Descriptions.Item label="Last Contact">{formatRelativeTime(contact.last_contacted_at)}</Descriptions.Item>
              <Descriptions.Item label="Emails Sent">{contact.total_emails_sent || 0}</Descriptions.Item>
              <Descriptions.Item label="Emails Received">{contact.total_emails_received || 0}</Descriptions.Item>
              <Descriptions.Item label="Threads">{pattern?.total_threads ?? 'N/A'}</Descriptions.Item>
              <Descriptions.Item label="Avg Thread Depth">{pattern?.avg_thread_depth != null ? Number(pattern.avg_thread_depth).toFixed(1) : 'N/A'}</Descriptions.Item>
              <Descriptions.Item label="Emails/Week">{pattern?.emails_per_week != null ? Number(pattern.emails_per_week).toFixed(1) : 'N/A'}</Descriptions.Item>
            </Descriptions>
          </div>
        </Col>
        <Col xs={24} sm={14}>
          {threads.length > 0 && (
            <div className="glass-table-container" style={{ padding: 16 }}>
              <a onClick={() => navigate(`/customers/threads?contact_id=${contactId}`)}
                style={{ fontSize: 16, fontWeight: 600, display: 'block', marginBottom: 12, color: '#667eea', cursor: 'pointer' }}>
                Threads ({threads.length})
              </a>
              <Table
                columns={threadColumns}
                dataSource={threads.slice(0, 50)}
                rowKey="thread_id"
                size="small"
                pagination={threads.length > 10 ? { pageSize: 10, size: 'small' } : false}
                onRow={(record) => ({ onClick: () => handleThreadClick(record), style: { cursor: 'pointer' } })}
              />
            </div>
          )}
        </Col>
      </Row>

      {contact.qb_customer_type && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} sm={8}>
            <div className="glass-card" style={{ padding: 16 }}>
              <Text type="secondary">Their Avg Response</Text>
              <div style={{ fontSize: 20, fontWeight: 600 }}>{pattern?.their_avg_response_time_hours != null ? `${Number(pattern.their_avg_response_time_hours).toFixed(1)}h` : 'N/A'}</div>
            </div>
          </Col>
          <Col xs={24} sm={8}>
            <div className="glass-card" style={{ padding: 16 }}>
              <LifecycleBadge tier={contact.qb_customer_type} />
              {contact.qb_tier && <Tag color="purple" style={{ marginLeft: 8 }}>{contact.qb_tier}</Tag>}
            </div>
          </Col>
        </Row>
      )}

      {contactId && contact && <AIInsightsCard entityType="contact" entityId={contactId} />}
    </div>
  );
};
