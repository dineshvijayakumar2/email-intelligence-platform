import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Button, Tag, Descriptions, Skeleton, Table } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { MetricCard } from '../../components/analytics/MetricCard';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import {
  companiesApi,
  threadsApi,
  formatRelativeTime,
  engagementStatusConfig,
  threadStatusConfig,
} from '../../services/analyticsService';
import type { CompanyAnalytics, ThreadStatusSummary } from '../../types/analytics';

const { Title, Text } = Typography;

export const CompanyDetail: React.FC = () => {
  const { companyId } = useParams<{ companyId: string }>();
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const [company, setCompany] = useState<CompanyAnalytics | null>(null);
  const [threads, setThreads] = useState<ThreadStatusSummary[]>([]);
  const [totalEmails, setTotalEmails] = useState(0);
  const [totalSent, setTotalSent] = useState(0);
  const [totalReceived, setTotalReceived] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!companyId) return;
    const load = async () => {
      setLoading(true);
      const [result, emailResult, threadResult] = await Promise.all([
        companiesApi.getDetail(companyId),
        companiesApi.getEmails(companyId, 1, 0),
        threadsApi.byCompany(companyId, 100),
      ]);
      if (isMountedRef.current) {
        setCompany(result);
        setTotalEmails(emailResult.total || 0);
        setTotalSent(emailResult.total_sent ?? 0);
        setTotalReceived(emailResult.total_received ?? 0);
        setThreads(threadResult.threads);
        setLoading(false);
      }
    };
    load();
  }, [companyId]);

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
    { title: 'Contact', key: 'contact', render: (_: any, r: ThreadStatusSummary) => r.contact_name || r.contact_email || '-' },
    { title: 'Messages', dataIndex: 'total_messages', key: 'msgs', width: 90 },
    { title: 'Last Message', dataIndex: 'last_message_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  if (loading) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/analytics/companies')} style={{ marginBottom: 16 }}>Back</Button>
        <Skeleton active paragraph={{ rows: 10 }} />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/analytics/companies')} style={{ marginBottom: 16 }}>Back</Button>
        <Text type="secondary">Company not found</Text>
      </div>
    );
  }

  const statusCfg = engagementStatusConfig[company.engagement_status || 'unknown'];
  const companyParam = encodeURIComponent(company.company_name);

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/analytics/companies')} style={{ marginBottom: 16 }}>Back to Companies</Button>

      <div className="glass-card fade-in-up" style={{ padding: 20, marginBottom: 16 }}>
        <Row align="middle" gutter={16}>
          <Col flex="auto">
            <Title level={4} style={{ margin: 0 }}>{company.company_name}</Title>
            {company.industry && <Tag>{company.industry}</Tag>}
            {company.email_domains?.length && <Text type="secondary"> ({company.email_domains.join(', ')})</Text>}
          </Col>
          <Col>
            <EngagementBadge score={company.engagement_score} showBar />
            <Tag color={statusCfg.color} style={{ marginLeft: 8 }}>{statusCfg.label}</Tag>
          </Col>
        </Row>
      </div>

      <Row gutter={[16, 16]} className="fade-in-up stagger-1">
        <Col xs={12} sm={6}>
          <MetricCard
            title="Total Emails"
            value={totalEmails}
            onClick={() => navigate(`/emails?company_id=${companyId}&name=${companyParam}`)}
          />
        </Col>
        <Col xs={12} sm={6}>
          <MetricCard title="Contacts" value={company.contact_count} onClick={() => navigate(`/analytics/contacts?company=${companyParam}`)} />
        </Col>
        <Col xs={12} sm={6}>
          <MetricCard title="Decision Makers" value={company.decision_maker_count} onClick={() => navigate(`/analytics/contacts?company=${companyParam}&dm=true`)} />
        </Col>
        <Col xs={12} sm={6}>
          <MetricCard
            title="Active Threads"
            value={company.active_threads}
            onClick={() => navigate(`/analytics/threads?company_id=${companyId}&name=${companyParam}`)}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-2">
        <Col xs={24} lg={10}>
          <div className="glass-card" style={{ padding: 20 }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Details</Text>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="First Contact">{formatRelativeTime(company.first_contact_date)}</Descriptions.Item>
              <Descriptions.Item label="Last Contact">{formatRelativeTime(company.last_contact_date)}</Descriptions.Item>
              <Descriptions.Item label="Inbound Emails">{totalReceived}</Descriptions.Item>
              <Descriptions.Item label="Outbound Emails">{totalSent}</Descriptions.Item>
              <Descriptions.Item label="Overdue Threads">{company.overdue_threads || 0}</Descriptions.Item>
              <Descriptions.Item label="Client">{company.client_name || '-'}</Descriptions.Item>
            </Descriptions>
          </div>
        </Col>
        <Col xs={24} lg={14}>
          <div className="glass-table-container" style={{ padding: 16 }}>
            <a
              onClick={() => navigate(`/analytics/threads?company_id=${companyId}&name=${companyParam}`)}
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
    </div>
  );
};
