import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Button, Tag, Descriptions, Skeleton, Table } from 'antd';
import { ArrowLeftOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { MetricCard } from '../../components/analytics/MetricCard';
import AIInsightsCard from '../../components/AIInsightsCard';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import { LifecycleBadge } from '../../components/analytics/LifecycleBadge';
import {
  companiesApi,
  threadsApi,
  formatRelativeTime,
  engagementStatusConfig,
  threadStatusConfig,
} from '../../services/analyticsService';
import type { CompanyAnalytics, ThreadStatusSummary } from '../../types/analytics';
import { formatCurrency } from '../../utils/numberFormat';

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
            <LifecycleBadge tier={company.qb_customer_type} />
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
        {company.qb_total_revenue != null && (
          <Col xs={24} lg={10}>
            <div className="glass-card" style={{ padding: 20 }}>
              <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Business Data</Text>
              <Descriptions column={1} size="small">
                {company.qb_customer_type && (
                  <Descriptions.Item label="Customer Type"><Tag color="blue">{company.qb_customer_type}</Tag></Descriptions.Item>
                )}
                {company.qb_tier && (
                  <Descriptions.Item label="Tier"><Tag color="purple">{company.qb_tier}</Tag></Descriptions.Item>
                )}
                <Descriptions.Item label="Revenue">
                  {formatCurrency(company.qb_total_revenue ?? 0)}
                </Descriptions.Item>
                {company.qb_invoiced_ty != null && (
                  <Descriptions.Item label="This Year">
                    {formatCurrency(company.qb_invoiced_ty)}
                  </Descriptions.Item>
                )}
                {company.qb_invoiced_ly != null && (
                  <Descriptions.Item label="Last Year">
                    {formatCurrency(company.qb_invoiced_ly)}
                    {company.qb_invoiced_ty != null && company.qb_invoiced_ty > company.qb_invoiced_ly && (
                      <ArrowUpOutlined style={{ color: '#52c41a', marginLeft: 6 }} />
                    )}
                    {company.qb_invoiced_ty != null && company.qb_invoiced_ty < company.qb_invoiced_ly && (
                      <ArrowDownOutlined style={{ color: '#ff4d4f', marginLeft: 6 }} />
                    )}
                  </Descriptions.Item>
                )}
                {company.qb_growth_90d != null && (
                  <Descriptions.Item label="Growth 90d">
                    <span style={{ color: company.qb_growth_90d >= 0 ? '#52c41a' : '#ff4d4f' }}>
                      {company.qb_growth_90d >= 0 ? '+' : ''}{(company.qb_growth_90d * 100).toFixed(1)}%
                    </span>
                  </Descriptions.Item>
                )}
                {company.qb_days_since_last_invoice != null && (
                  <Descriptions.Item label="Days Since Order">{company.qb_days_since_last_invoice}</Descriptions.Item>
                )}
                {company.qb_account_manager && (
                  <Descriptions.Item label="Account Manager">{company.qb_account_manager}</Descriptions.Item>
                )}
              </Descriptions>
            </div>
          </Col>
        )}
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

      {companyId && <AIInsightsCard entityType="company" entityId={companyId} />}
    </div>
  );
};
