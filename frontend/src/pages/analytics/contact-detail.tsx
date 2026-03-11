import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Button, Tag, Descriptions, Skeleton, Table } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { MetricCard } from '../../components/analytics/MetricCard';
import AIInsightsCard from '../../components/AIInsightsCard';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import {
  contactsApi,
  threadsApi,
  patternsApi,
  formatRelativeTime,
  formatResponseTime,
  formatRatio,
  threadStatusConfig,
} from '../../services/analyticsService';
import type { ContactAnalytics, ThreadStatusSummary, CommunicationPattern } from '../../types/analytics';

const { Title, Text } = Typography;

export const ContactDetail: React.FC = () => {
  const { contactId } = useParams<{ contactId: string }>();
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const [contact, setContact] = useState<ContactAnalytics | null>(null);
  const [threads, setThreads] = useState<ThreadStatusSummary[]>([]);
  const [pattern, setPattern] = useState<CommunicationPattern | null>(null);
  const [totalEmails, setTotalEmails] = useState(0);
  const [totalSent, setTotalSent] = useState(0);
  const [totalReceived, setTotalReceived] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!contactId) return;
    loadAll();
  }, [contactId]);

  const loadAll = async () => {
    setLoading(true);
    const [c, t, p, e] = await Promise.all([
      contactsApi.getDetail(contactId!),
      threadsApi.byContact(contactId!),
      patternsApi.byContact(contactId!),
      contactsApi.getEmails(contactId!, 1, 0),  // fetch just total count
    ]);
    if (isMountedRef.current) {
      setContact(c);
      setThreads(t.threads);
      setPattern(p);
      setTotalEmails(e.total || 0);
      setTotalSent(e.total_sent ?? 0);
      setTotalReceived(e.total_received ?? 0);
      setLoading(false);
    }
  };

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
    { title: 'Messages', dataIndex: 'total_messages', key: 'msgs', width: 90 },
    { title: 'Last Message', dataIndex: 'last_message_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  if (loading) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/analytics/contacts')} style={{ marginBottom: 16 }}>Back</Button>
        <Skeleton active paragraph={{ rows: 12 }} />
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/analytics/contacts')} style={{ marginBottom: 16 }}>Back</Button>
        <Text type="secondary">Contact not found</Text>
      </div>
    );
  }

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/analytics/contacts')} style={{ marginBottom: 16 }}>Back to Contacts</Button>

      {/* Header */}
      <div className="glass-card fade-in-up" style={{ padding: 20, marginBottom: 16 }}>
        <Row align="middle" gutter={16}>
          <Col flex="auto">
            <Title level={4} style={{ margin: 0 }}>{contact.full_name || contact.email_address}</Title>
            <Text type="secondary">{contact.email_address}</Text>
            {contact.job_title && <div><Text>{contact.job_title}</Text></div>}
            {contact.company_name && <div><Text type="secondary">{contact.company_name}</Text></div>}
          </Col>
          <Col>
            <EngagementBadge score={contact.engagement_score} showBar />
            {contact.is_decision_maker && <Tag color="gold" style={{ marginLeft: 8 }}>Decision Maker</Tag>}
            {contact.seniority_level && contact.seniority_level !== 'unknown' && <Tag>{contact.seniority_level}</Tag>}
          </Col>
        </Row>
        {(contact.qb_customer_type || contact.qb_tier || contact.qb_quotes_count != null) && (
          <div style={{ marginTop: 12, borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 10 }}>
            {contact.qb_customer_type && <Tag color="blue">{contact.qb_customer_type}</Tag>}
            {contact.qb_tier && <Tag color="purple">{contact.qb_tier}</Tag>}
            {contact.qb_quotes_count != null && <Tag>{contact.qb_quotes_count} quote{contact.qb_quotes_count !== 1 ? 's' : ''}</Tag>}
          </div>
        )}
      </div>

      {/* Stats */}
      <Row gutter={[16, 16]} className="fade-in-up stagger-1">
        <Col xs={12} sm={6}>
          <MetricCard
            title="Total Emails"
            value={totalEmails}
            onClick={() => navigate(`/emails?contact_id=${contactId}&name=${encodeURIComponent(contact.full_name || contact.email_address)}`)}
          />
        </Col>
        <Col xs={12} sm={6}><MetricCard title="Initiation Ratio" value={formatRatio(pattern?.thread_initiation_ratio)} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Our Reply Rate" value={formatRatio(pattern?.reply_rate)} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Our Avg Response" value={formatResponseTime(pattern?.avg_response_time_hours)} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Their Avg Response" value={formatResponseTime(pattern?.their_avg_response_time_hours)} /></Col>
      </Row>

      {/* Details */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-2">
        <Col xs={24} lg={10}>
          <div className="glass-card" style={{ padding: 20 }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Details</Text>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="First Contact">{formatRelativeTime(contact.first_contacted_at)}</Descriptions.Item>
              <Descriptions.Item label="Last Contact">{formatRelativeTime(contact.last_contacted_at)}</Descriptions.Item>
              <Descriptions.Item label="Emails Sent">{totalSent}</Descriptions.Item>
              <Descriptions.Item label="Emails Received">{totalReceived}</Descriptions.Item>
              <Descriptions.Item label="Threads">{pattern?.total_threads ?? 'N/A'}</Descriptions.Item>
              <Descriptions.Item label="Avg Thread Depth">{contact.avg_thread_depth?.toFixed(1) ?? 'N/A'}</Descriptions.Item>
              <Descriptions.Item label="Emails/Week">{pattern?.emails_per_week?.toFixed(1) ?? 'N/A'}</Descriptions.Item>
            </Descriptions>
          </div>
        </Col>
        <Col xs={24} lg={14}>
          <div className="glass-table-container" style={{ padding: 16 }}>
            <a
              onClick={() => navigate(`/analytics/threads?contact_id=${contactId}&name=${encodeURIComponent(contact.full_name || contact.email_address)}`)}
              style={{ fontSize: 16, fontWeight: 600, display: 'block', marginBottom: 12, color: '#667eea', cursor: 'pointer' }}
            >
              Threads ({threads.length})
            </a>
            <Table
              columns={threadColumns}
              dataSource={threads}
              rowKey="thread_id"
              size="small"
              pagination={threads.length > 10 ? { pageSize: 10 } : false}
              onRow={(record) => ({
                onClick: () => handleThreadClick(record),
                style: { cursor: 'pointer' },
              })}
            />
          </div>
        </Col>
      </Row>

      {contactId && <AIInsightsCard entityType="contact" entityId={contactId} />}
    </div>
  );
};
