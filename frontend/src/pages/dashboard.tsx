import React, { useState, useEffect } from "react";
import { Row, Col, Statistic, Typography, Table, Tag, Button, Empty, Space } from "antd";
import {
  MailOutlined,
  InboxOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  WindowsOutlined,
  ArrowRightOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import {
  dashboardService,
  DashboardStats,
  ProcessingOverview,
  MailboxSummary,
  RecentJob,
} from '../services/dashboardService';
import GmailConnection from '../components/GmailConnection';

const { Text, Title } = Typography;

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();

  // Get consistent user ID (same pattern as other components)
  const getUserId = () => {
    let visitorId = localStorage.getItem('user_id');
    if (!visitorId) {
      const fingerprint = [
        navigator.userAgent,
        navigator.language,
        screen.width + 'x' + screen.height,
        new Date().getTimezoneOffset()
      ].join('|');
      visitorId = 'user_' + btoa(fingerprint).replace(/[^a-zA-Z0-9]/g, '').substring(0, 16);
      localStorage.setItem('user_id', visitorId);
    }
    return visitorId;
  };
  const userId = getUserId();

  const [stats, setStats] = useState<DashboardStats>({
    totalEmails: 0,
    totalMailboxes: 0,
    todayEmails: 0,
    processingJobs: 0,
  });
  const [processingOverview, setProcessingOverview] = useState<ProcessingOverview>({
    activeJobs: 0,
    completedToday: 0,
    failedToday: 0,
    totalProcessed: 0,
    successRate: 100,
  });
  const [mailboxes, setMailboxes] = useState<MailboxSummary[]>([]);
  const [recentJobs, setRecentJobs] = useState<RecentJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [initialLoadDone, setInitialLoadDone] = useState(false);

  useEffect(() => {
    loadDashboardData(true); // Initial load with loading indicator
    // Refresh every 30 seconds silently (no loading flash)
    const interval = setInterval(() => loadDashboardData(false), 30000);
    return () => clearInterval(interval);
  }, []);

  const loadDashboardData = async (showLoading = false) => {
    try {
      // Only show loading spinner on initial load, not on background refreshes
      if (showLoading && !initialLoadDone) {
        setLoading(true);
      }

      // Use optimized method that fetches all data efficiently (avoids duplicate API calls)
      const data = await dashboardService.getAllDashboardData();

      setStats(data.stats);
      setProcessingOverview(data.processingOverview);
      setMailboxes(data.mailboxes);
      setRecentJobs(data.recentJobs);
    } catch (error) {
      console.error('Error loading dashboard data:', error);
    } finally {
      setLoading(false);
      setInitialLoadDone(true);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
      case 'downloading':
        return <SyncOutlined spin style={{ color: '#667eea' }} />;
      case 'completed':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'failed':
        return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
      case 'pending':
        return <ClockCircleOutlined style={{ color: '#fa8c16' }} />;
      default:
        return <ClockCircleOutlined />;
    }
  };

  const jobColumns = [
    {
      title: 'Mailbox',
      dataIndex: 'mailboxName',
      key: 'mailboxName',
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: 'Type',
      dataIndex: 'jobType',
      key: 'jobType',
      render: (type: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {dashboardService.getJobTypeLabel(type)}
        </Text>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={dashboardService.getStatusColor(status)} icon={getStatusIcon(status)}>
          {status.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Processed',
      key: 'processed',
      render: (_: any, record: RecentJob) => (
        <Text>
          {record.processedCount.toLocaleString()}
          {record.failedCount > 0 && (
            <Text type="danger" style={{ marginLeft: 8 }}>
              ({record.failedCount} failed)
            </Text>
          )}
        </Text>
      ),
    },
    {
      title: 'Time',
      key: 'time',
      render: (_: any, record: RecentJob) => (
        <Text type="secondary">
          {dashboardService.formatRelativeTime(record.completedAt || record.createdAt)}
        </Text>
      ),
    },
  ];

  const mailboxColumns = [
    {
      title: 'Mailbox',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: MailboxSummary) => (
        <Space>
          <InboxOutlined style={{ color: record.isActive ? '#667eea' : '#999' }} />
          <Text strong>{name}</Text>
          <Tag color={record.type === 'mbox' ? 'green' : record.type === 'pst' ? 'blue' : 'purple'}>
            {record.type.toUpperCase()}
          </Tag>
        </Space>
      ),
    },
    {
      title: 'Emails',
      dataIndex: 'emailCount',
      key: 'emailCount',
      align: 'right' as const,
      render: (count: number) => <Text>{count.toLocaleString()}</Text>,
    },
    {
      title: 'Last Processed',
      dataIndex: 'lastSync',
      key: 'lastSync',
      render: (date: string | null) => (
        <Text type="secondary">{dashboardService.formatRelativeTime(date)}</Text>
      ),
    },
    {
      title: '',
      key: 'action',
      width: 100,
      render: (_: any, record: MailboxSummary) => (
        <Button
          type="link"
          size="small"
          onClick={() => navigate(`/mailboxes/process/${record.id}`)}
          disabled={!record.isActive}
        >
          Process
        </Button>
      ),
    },
  ];

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Page Description */}
      <div className="fade-in-up" style={{ marginBottom: 24 }}>
        <Text type="secondary">
          Email processing command center - monitor jobs, manage mailboxes, and track progress
        </Text>
      </div>

      {/* Primary Stats Row */}
      <Row gutter={[16, 16]} className="fade-in-up stagger-1">
        <Col xs={24} sm={12} lg={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic
              title="Total Emails Archived"
              value={stats.totalEmails}
              prefix={<MailOutlined />}
              valueStyle={{ color: "#667eea" }}
              loading={loading}
            />
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic
              title="Active Mailboxes"
              value={stats.totalMailboxes}
              prefix={<InboxOutlined />}
              valueStyle={{ color: "#52c41a" }}
              loading={loading}
            />
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic
              title="Active Jobs"
              value={processingOverview.activeJobs}
              prefix={processingOverview.activeJobs > 0 ? <SyncOutlined spin /> : <PlayCircleOutlined />}
              valueStyle={{ color: processingOverview.activeJobs > 0 ? "#667eea" : "#999" }}
              loading={loading}
            />
            {processingOverview.activeJobs > 0 && (
              <Link to="/processing" style={{ fontSize: 12, color: '#667eea' }}>
                View active jobs <ArrowRightOutlined />
              </Link>
            )}
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic
              title="Emails Processed Today"
              value={stats.todayEmails}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: "#52c41a" }}
              loading={loading}
            />
          </div>
        </Col>
      </Row>

      {/* Processing Activity Row */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }} className="fade-in-up stagger-2">
        {/* Recent Jobs */}
        <Col xs={24} lg={14}>
          <div className="glass-table-container" style={{ height: '100%' }}>
            <div style={{ padding: '16px 24px', borderBottom: '1px solid rgba(102, 126, 234, 0.1)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text strong style={{ fontSize: 16 }}>Recent Processing Jobs</Text>
                <Link to="/processing" style={{ color: '#667eea', fontSize: 13 }}>
                  View All <ArrowRightOutlined />
                </Link>
              </div>
            </div>
            {recentJobs.length > 0 ? (
              <Table
                dataSource={recentJobs}
                columns={jobColumns}
                pagination={false}
                size="small"
                rowKey="id"
                loading={loading}
              />
            ) : (
              <div style={{ padding: 48, textAlign: 'center' }}>
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <Text type="secondary">No processing jobs yet</Text>
                  }
                >
                  <Button type="primary" onClick={() => navigate('/mailboxes')}>
                    Add a Mailbox
                  </Button>
                </Empty>
              </div>
            )}
          </div>
        </Col>

        {/* Today's Summary */}
        <Col xs={24} lg={10}>
          <div className="glass-card-static" style={{ padding: 24, height: '100%' }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 20 }}>
              Today's Processing Summary
            </Text>
            <Row gutter={[16, 24]}>
              <Col span={12}>
                <Statistic
                  title="Jobs Completed"
                  value={processingOverview.completedToday}
                  prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                  valueStyle={{ fontSize: 28 }}
                  loading={loading}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="Jobs Failed"
                  value={processingOverview.failedToday}
                  prefix={<ExclamationCircleOutlined style={{ color: processingOverview.failedToday > 0 ? '#ff4d4f' : '#999' }} />}
                  valueStyle={{ fontSize: 28, color: processingOverview.failedToday > 0 ? '#ff4d4f' : undefined }}
                  loading={loading}
                />
              </Col>
              <Col span={24}>
                <Statistic
                  title="Total Emails Processed (All Time)"
                  value={processingOverview.totalProcessed}
                  prefix={<MailOutlined style={{ color: '#667eea' }} />}
                  valueStyle={{ fontSize: 28 }}
                  loading={loading}
                />
              </Col>
            </Row>
            {processingOverview.failedToday > 0 && (
              <div style={{ marginTop: 16 }}>
                <Link to="/errors" style={{ color: '#ff4d4f' }}>
                  <ExclamationCircleOutlined /> View error details <ArrowRightOutlined />
                </Link>
              </div>
            )}
          </div>
        </Col>
      </Row>

      {/* Mailboxes & Future Integrations Row */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }} className="fade-in-up stagger-3">
        {/* Mailboxes */}
        <Col xs={24} lg={14}>
          <div className="glass-table-container" style={{ height: '100%' }}>
            <div style={{ padding: '16px 24px', borderBottom: '1px solid rgba(102, 126, 234, 0.1)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text strong style={{ fontSize: 16 }}>Connected Mailboxes</Text>
                <Link to="/mailboxes" style={{ color: '#667eea', fontSize: 13 }}>
                  Manage <ArrowRightOutlined />
                </Link>
              </div>
            </div>
            {mailboxes.length > 0 ? (
              <Table
                dataSource={mailboxes}
                columns={mailboxColumns}
                pagination={false}
                size="small"
                rowKey="id"
                loading={loading}
              />
            ) : (
              <div style={{ padding: 48, textAlign: 'center' }}>
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <Text type="secondary">No mailboxes connected</Text>
                  }
                >
                  <Button type="primary" onClick={() => navigate('/mailboxes/create')}>
                    Add Your First Mailbox
                  </Button>
                </Empty>
              </div>
            )}
          </div>
        </Col>

        {/* LIVE Email Integrations */}
        <Col xs={24} lg={10}>
          <div className="glass-card-static" style={{ padding: 24, height: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
              <ThunderboltOutlined style={{ color: '#667eea', fontSize: 18 }} />
              <Text strong style={{ fontSize: 16 }}>LIVE Email Sync</Text>
            </div>

            <Text type="secondary" style={{ display: 'block', marginBottom: 20 }}>
              Connect your email accounts for real-time synchronization
            </Text>

            {/* Gmail LIVE Integration */}
            <div style={{ marginBottom: 16 }}>
              <GmailConnection
                userId={userId}
                compact={true}
                onConnectionChange={(connected) => {
                  if (connected) {
                    loadDashboardData();
                  }
                }}
              />
            </div>

            {/* Outlook Integration - Coming Soon */}
            <div
              style={{
                background: 'linear-gradient(135deg, rgba(0, 120, 212, 0.08) 0%, rgba(106, 57, 172, 0.08) 100%)',
                border: '1px dashed rgba(0, 120, 212, 0.3)',
                borderRadius: 12,
                padding: 20,
                opacity: 0.7,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <WindowsOutlined style={{ fontSize: 24, color: '#0078d4' }} />
                <div>
                  <Title level={5} style={{ margin: 0, color: '#0078d4' }}>Microsoft 365</Title>
                  <Text type="secondary" style={{ fontSize: 12 }}>Coming Soon</Text>
                </div>
              </div>
              <Text type="secondary" style={{ fontSize: 13 }}>
                Outlook & Exchange integration via Microsoft Graph API.
              </Text>
            </div>
          </div>
        </Col>
      </Row>
    </div>
  );
};
