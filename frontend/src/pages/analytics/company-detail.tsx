import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Button, Tag, Descriptions, Skeleton, Table, Drawer } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { MetricCard } from '../../components/analytics/MetricCard';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import { EmailDetailPanel } from '../../components/EmailDetailPanel';
import { emailService } from '../../services/emailService';
import { summarizeEmail } from '../../services/aiService';
import type { Email } from '../../services/emailService';
import { companiesApi, formatRelativeTime, engagementStatusConfig } from '../../services/analyticsService';
import type { CompanyAnalytics, EngagementStatus } from '../../types/analytics';

const { Title, Text } = Typography;

export const CompanyDetail: React.FC = () => {
  const { companyId } = useParams<{ companyId: string }>();
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const [company, setCompany] = useState<CompanyAnalytics | null>(null);
  const [emails, setEmails] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Email preview drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [emailLoading, setEmailLoading] = useState(false);
  const [drawerExpanded, setDrawerExpanded] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!companyId) return;
    const load = async () => {
      setLoading(true);
      const [result, emailResult] = await Promise.all([
        companiesApi.getDetail(companyId),
        companiesApi.getEmails(companyId),
      ]);
      if (isMountedRef.current) {
        setCompany(result);
        setEmails(emailResult.emails || []);
        setLoading(false);
      }
    };
    load();
  }, [companyId]);

  const handleEmailClick = async (record: any) => {
    setDrawerOpen(true);
    setEmailLoading(true);
    try {
      const full = await emailService.getEmail(record.id);
      if (isMountedRef.current) setSelectedEmail(full);
    } catch {
      if (isMountedRef.current) setSelectedEmail(null);
    } finally {
      if (isMountedRef.current) setEmailLoading(false);
    }
  };

  const handleSummarize = async (emailId: string): Promise<string> => {
    return summarizeEmail(emailId);
  };

  const emailColumns = [
    { title: 'Subject', dataIndex: 'subject', key: 'subject', ellipsis: true },
    { title: 'From', dataIndex: 'sender_name', key: 'from', width: 160, ellipsis: true,
      render: (v: string, r: any) => v || r.sender_email },
    { title: 'Direction', dataIndex: 'is_outbound', key: 'dir', width: 90,
      render: (v: boolean) => <Tag color={v ? 'blue' : 'green'}>{v ? 'Sent' : 'Received'}</Tag> },
    { title: 'Folder', dataIndex: 'folder_path', key: 'folder', width: 100 },
    { title: 'Date', dataIndex: 'sent_date', key: 'date', width: 110, render: (v: string) => formatRelativeTime(v) },
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
        <Col xs={12} sm={6}><MetricCard title="Total Emails" value={company.total_emails} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Contacts" value={company.contact_count} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Decision Makers" value={company.decision_maker_count} /></Col>
        <Col xs={12} sm={6}><MetricCard title="Active Threads" value={company.active_threads} /></Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-2">
        <Col xs={24}>
          <div className="glass-card" style={{ padding: 20 }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Details</Text>
            <Descriptions column={{ xs: 1, sm: 2 }} size="small">
              <Descriptions.Item label="First Contact">{formatRelativeTime(company.first_contact_date)}</Descriptions.Item>
              <Descriptions.Item label="Last Contact">{formatRelativeTime(company.last_contact_date)}</Descriptions.Item>
              <Descriptions.Item label="Inbound Emails">{company.total_inbound || 0}</Descriptions.Item>
              <Descriptions.Item label="Outbound Emails">{company.total_outbound || 0}</Descriptions.Item>
              <Descriptions.Item label="Overdue Threads">{company.overdue_threads || 0}</Descriptions.Item>
              <Descriptions.Item label="Client">{company.client_name || '-'}</Descriptions.Item>
            </Descriptions>
          </div>
        </Col>
      </Row>

      {/* Linked Emails */}
      <Row style={{ marginTop: 16 }} className="fade-in-up stagger-3">
        <Col span={24}>
          <div className="glass-table-container" style={{ padding: 16 }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Linked Emails ({emails.length})</Text>
            <Table
              columns={emailColumns}
              dataSource={emails}
              rowKey="id"
              size="small"
              pagination={emails.length > 10 ? { pageSize: 10 } : false}
              locale={{ emptyText: 'No emails linked yet. Run extraction to link emails to contacts.' }}
              onRow={(record) => ({
                onClick: () => handleEmailClick(record),
                style: { cursor: 'pointer' },
              })}
            />
          </div>
        </Col>
      </Row>

      {/* Email Preview Drawer */}
      <Drawer
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setSelectedEmail(null); }}
        width={drawerExpanded ? '80%' : 640}
        destroyOnClose
        styles={{ body: { padding: 0 } }}
      >
        <EmailDetailPanel
          email={selectedEmail}
          loading={emailLoading}
          onClose={() => { setDrawerOpen(false); setSelectedEmail(null); }}
          expanded={drawerExpanded}
          onToggleExpand={() => setDrawerExpanded(e => !e)}
          onSummarize={handleSummarize}
        />
      </Drawer>
    </div>
  );
};
