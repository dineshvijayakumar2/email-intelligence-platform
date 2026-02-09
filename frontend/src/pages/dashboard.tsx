import React, { useState, useEffect, useRef } from "react";
import { Row, Col, Statistic, Typography, Table, Tag, Button, Empty, Space, Alert, Skeleton } from "antd";
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
  GoogleOutlined,
  EditOutlined,
} from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import {
  dashboardService,
  DashboardStats,
  ProcessingOverview,
  MailboxSummary,
  RecentJob,
} from '../services/dashboardService';

const { Text } = Typography;

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();

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

  // Track if component is mounted to prevent state updates after unmount
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    loadDashboardData(true); // Initial load with loading indicator
    // Refresh every 30 seconds silently (no loading flash)
    const interval = setInterval(() => {
      if (isMountedRef.current) {
        loadDashboardData(false);
      }
    }, 30000);
    return () => {
      isMountedRef.current = false;
      clearInterval(interval);
    };
  }, []);

  const loadDashboardData = async (showLoading = false) => {
    try {
      // Only show loading spinner on initial load, not on background refreshes
      if (showLoading && !initialLoadDone && isMountedRef.current) {
        setLoading(true);
      }

      // Use optimized method that fetches all data efficiently (avoids duplicate API calls)
      const data = await dashboardService.getAllDashboardData();

      // Only update state if component is still mounted
      if (!isMountedRef.current) return;

      // On first load, always update. On subsequent loads, preserve existing data if API returns empty
      const isFirstLoad = !initialLoadDone;

      // Update stats - always on first load, or if we have valid data
      if (isFirstLoad || data.stats.totalEmails > 0 || data.stats.totalMailboxes > 0) {
        setStats(data.stats);
      }

      // Update processing overview - always on first load, or if we have valid data
      if (isFirstLoad || data.processingOverview.totalProcessed > 0 || data.processingOverview.activeJobs > 0 || data.processingOverview.completedToday > 0) {
        setProcessingOverview(data.processingOverview);
      }

      // Update mailboxes - always on first load, or if we have data
      if (isFirstLoad || data.mailboxes.length > 0) {
        setMailboxes(data.mailboxes);
      }

      // Update recent jobs - always on first load, or if we have data
      if (isFirstLoad || data.recentJobs.length > 0) {
        setRecentJobs(data.recentJobs);
      }
    } catch (error) {
      console.error('Error loading dashboard data:', error);
      // Don't reset state on error - keep existing data
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
        setInitialLoadDone(true);
      }
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
      render: (name: string, record: MailboxSummary) => {
        const isLive = ['gmail', 'outlook_live'].includes(record.type);
        const typeColor = record.type === 'gmail' ? 'red' :
                         record.type === 'outlook_live' ? 'blue' :
                         record.type === 'mbox' ? 'green' :
                         record.type === 'pst' ? 'geekblue' : 'purple';
        return (
          <Space>
            <InboxOutlined style={{ color: record.isActive ? '#667eea' : '#999' }} />
            <Text strong>{name}</Text>
            <Tag color={typeColor}>
              {record.type === 'outlook_live' ? 'OUTLOOK' : record.type.toUpperCase()}
              {isLive && ' LIVE'}
            </Tag>
          </Space>
        );
      },
    },
    {
      title: 'Emails',
      dataIndex: 'emailCount',
      key: 'emailCount',
      align: 'right' as const,
      render: (count: number) => <Text>{count.toLocaleString()}</Text>,
    },
    {
      title: 'Last Sync',
      dataIndex: 'lastSync',
      key: 'lastSync',
      render: (date: string | null) => (
        <Text type="secondary">{dashboardService.formatRelativeTime(date)}</Text>
      ),
    },
    {
      title: '',
      key: 'action',
      width: 120,
      render: (_: any, record: MailboxSummary) => {
        const isLive = ['gmail', 'outlook_live'].includes(record.type);
        return (
          <Space size={4}>
            {isLive ? (
              <Button
                type="link"
                size="small"
                icon={<SyncOutlined />}
                onClick={() => navigate(`/mailboxes/edit/${record.id}`)}
                disabled={!record.isActive}
              >
                Sync
              </Button>
            ) : (
              <Button
                type="link"
                size="small"
                onClick={() => navigate(`/mailboxes/process/${record.id}`)}
                disabled={!record.isActive}
              >
                Process
              </Button>
            )}
          </Space>
        );
      },
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
            {loading ? (
              <div>
                <Skeleton.Input active size="small" style={{ width: 120, marginBottom: 12 }} />
                <Skeleton.Input active style={{ width: 80, height: 32 }} />
              </div>
            ) : (
              <Statistic
                title="Total Emails Archived"
                value={stats.totalEmails}
                prefix={<MailOutlined />}
                valueStyle={{ color: "#667eea" }}
              />
            )}
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            {loading ? (
              <div>
                <Skeleton.Input active size="small" style={{ width: 100, marginBottom: 12 }} />
                <Skeleton.Input active style={{ width: 60, height: 32 }} />
              </div>
            ) : (
              <Statistic
                title="Active Mailboxes"
                value={stats.totalMailboxes}
                prefix={<InboxOutlined />}
                valueStyle={{ color: "#52c41a" }}
              />
            )}
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            {loading ? (
              <div>
                <Skeleton.Input active size="small" style={{ width: 80, marginBottom: 12 }} />
                <Skeleton.Input active style={{ width: 50, height: 32 }} />
              </div>
            ) : (
              <>
                <Statistic
                  title="Active Jobs"
                  value={processingOverview.activeJobs}
                  prefix={processingOverview.activeJobs > 0 ? <SyncOutlined spin /> : <PlayCircleOutlined />}
                  valueStyle={{ color: processingOverview.activeJobs > 0 ? "#667eea" : "#999" }}
                />
                {processingOverview.activeJobs > 0 && (
                  <Link to="/processing" style={{ fontSize: 12, color: '#667eea' }}>
                    View active jobs <ArrowRightOutlined />
                  </Link>
                )}
              </>
            )}
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            {loading ? (
              <div>
                <Skeleton.Input active size="small" style={{ width: 130, marginBottom: 12 }} />
                <Skeleton.Input active style={{ width: 70, height: 32 }} />
              </div>
            ) : (
              <Statistic
                title="Emails Processed Today"
                value={stats.todayEmails}
                prefix={<CheckCircleOutlined />}
                valueStyle={{ color: "#52c41a" }}
              />
            )}
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
            {loading ? (
              <div style={{ padding: 16 }}>
                {[1, 2, 3, 4].map(i => (
                  <div key={i} style={{ display: 'flex', gap: 16, marginBottom: 16, alignItems: 'center' }}>
                    <Skeleton.Input active size="small" style={{ width: 120 }} />
                    <Skeleton.Input active size="small" style={{ width: 80 }} />
                    <Skeleton.Button active size="small" style={{ width: 70 }} />
                    <Skeleton.Input active size="small" style={{ width: 60 }} />
                    <Skeleton.Input active size="small" style={{ width: 80 }} />
                  </div>
                ))}
              </div>
            ) : recentJobs.length > 0 ? (
              <Table
                dataSource={recentJobs}
                columns={jobColumns}
                pagination={false}
                size="small"
                rowKey="id"
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
            {loading ? (
              <Row gutter={[16, 24]}>
                <Col span={12}>
                  <Skeleton.Input active size="small" style={{ width: 90, marginBottom: 8 }} />
                  <Skeleton.Input active style={{ width: 60, height: 28 }} />
                </Col>
                <Col span={12}>
                  <Skeleton.Input active size="small" style={{ width: 70, marginBottom: 8 }} />
                  <Skeleton.Input active style={{ width: 50, height: 28 }} />
                </Col>
                <Col span={24}>
                  <Skeleton.Input active size="small" style={{ width: 180, marginBottom: 8 }} />
                  <Skeleton.Input active style={{ width: 80, height: 28 }} />
                </Col>
              </Row>
            ) : (
              <>
                <Row gutter={[16, 24]}>
                  <Col span={12}>
                    <Statistic
                      title="Jobs Completed"
                      value={processingOverview.completedToday}
                      prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                      valueStyle={{ fontSize: 28 }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="Jobs Failed"
                      value={processingOverview.failedToday}
                      prefix={<ExclamationCircleOutlined style={{ color: processingOverview.failedToday > 0 ? '#ff4d4f' : '#999' }} />}
                      valueStyle={{ fontSize: 28, color: processingOverview.failedToday > 0 ? '#ff4d4f' : undefined }}
                    />
                  </Col>
                  <Col span={24}>
                    <Statistic
                      title="Total Emails Processed (All Time)"
                      value={processingOverview.totalProcessed}
                      prefix={<MailOutlined style={{ color: '#667eea' }} />}
                      valueStyle={{ fontSize: 28 }}
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
              </>
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
            {loading ? (
              <div style={{ padding: 16 }}>
                {[1, 2, 3].map(i => (
                  <div key={i} style={{ display: 'flex', gap: 16, marginBottom: 16, alignItems: 'center' }}>
                    <Skeleton.Avatar active size="small" />
                    <Skeleton.Input active size="small" style={{ width: 140 }} />
                    <Skeleton.Button active size="small" style={{ width: 50 }} />
                    <Skeleton.Input active size="small" style={{ width: 60 }} />
                    <Skeleton.Input active size="small" style={{ width: 90 }} />
                  </div>
                ))}
              </div>
            ) : mailboxes.length > 0 ? (
              <Table
                dataSource={mailboxes}
                columns={mailboxColumns}
                pagination={false}
                size="small"
                rowKey="id"
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
              Connect email accounts to mailboxes for real-time synchronization
            </Text>

            {/* Gmail LIVE Integration - Per-Mailbox */}
            <div style={{ marginBottom: 16 }}>
              <div
                style={{
                  background: 'linear-gradient(135deg, rgba(66, 133, 244, 0.08) 0%, rgba(52, 168, 83, 0.08) 100%)',
                  border: '1px solid rgba(66, 133, 244, 0.2)',
                  borderRadius: 12,
                  padding: 16,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                  <GoogleOutlined style={{ fontSize: 24, color: '#4285f4' }} />
                  <div style={{ flex: 1 }}>
                    <Text strong style={{ color: '#4285f4' }}>Gmail LIVE Sync</Text>
                    <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
                      Per-mailbox Gmail connections
                    </Text>
                  </div>
                </div>

                {/* Show mailboxes with Gmail sync */}
                {mailboxes.filter(m => m.type && ['mbox', 'pst', 'olm'].includes(m.type)).length > 0 ? (
                  <div style={{ fontSize: 13 }}>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                      Connect Gmail to individual mailboxes from their edit page:
                    </Text>
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      {mailboxes.filter(m => m.type && ['mbox', 'pst', 'olm'].includes(m.type)).slice(0, 3).map(mailbox => (
                        <div key={mailbox.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <Space size={4}>
                            <InboxOutlined style={{ color: '#667eea' }} />
                            <Text>{mailbox.name}</Text>
                          </Space>
                          <Button
                            type="link"
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => navigate(`/mailboxes/edit/${mailbox.id}`)}
                            style={{ padding: 0 }}
                          >
                            Configure
                          </Button>
                        </div>
                      ))}
                      {mailboxes.filter(m => m.type && ['mbox', 'pst', 'olm'].includes(m.type)).length > 3 && (
                        <Link to="/mailboxes" style={{ fontSize: 12, color: '#667eea' }}>
                          + {mailboxes.filter(m => m.type && ['mbox', 'pst', 'olm'].includes(m.type)).length - 3} more mailboxes
                        </Link>
                      )}
                    </Space>
                  </div>
                ) : (
                  <Alert
                    message="No archive mailboxes"
                    description="Create a mailbox (MBOX, PST, or OLM) to enable Gmail LIVE sync."
                    type="info"
                    showIcon={false}
                    style={{ background: 'transparent', border: 'none', padding: 0 }}
                  />
                )}
              </div>
            </div>

            {/* Outlook LIVE Integration - Per-Mailbox */}
            <div
              style={{
                background: 'linear-gradient(135deg, rgba(0, 120, 212, 0.08) 0%, rgba(0, 183, 195, 0.08) 100%)',
                border: '1px solid rgba(0, 120, 212, 0.2)',
                borderRadius: 12,
                padding: 16,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                <WindowsOutlined style={{ fontSize: 24, color: '#0078d4' }} />
                <div style={{ flex: 1 }}>
                  <Text strong style={{ color: '#0078d4' }}>Outlook LIVE Sync</Text>
                  <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
                    O365 & personal Microsoft accounts
                  </Text>
                </div>
              </div>

              {/* Show mailboxes with Outlook sync */}
              {mailboxes.filter(m => m.type && ['mbox', 'pst', 'olm'].includes(m.type)).length > 0 ? (
                <div style={{ fontSize: 13 }}>
                  <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                    Link Outlook to archive mailboxes:
                  </Text>
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    {mailboxes.filter(m => m.type && ['mbox', 'pst', 'olm'].includes(m.type)).slice(0, 3).map(m => (
                      <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text style={{ fontSize: 12 }}>{m.name}</Text>
                        <Link to={`/mailboxes/edit/${m.id}`} style={{ fontSize: 11, color: '#0078d4' }}>
                          Configure
                        </Link>
                      </div>
                    ))}
                    {mailboxes.filter(m => m.type && ['mbox', 'pst', 'olm'].includes(m.type)).length > 3 && (
                      <Link to="/mailboxes" style={{ fontSize: 12, color: '#0078d4' }}>
                        + {mailboxes.filter(m => m.type && ['mbox', 'pst', 'olm'].includes(m.type)).length - 3} more mailboxes
                      </Link>
                    )}
                  </Space>
                </div>
              ) : (
                <Alert
                  message="No archive mailboxes"
                  description="Create a mailbox (MBOX, PST, or OLM) to enable Outlook LIVE sync."
                  type="info"
                  showIcon={false}
                  style={{ background: 'transparent', border: 'none', padding: 0 }}
                />
              )}
            </div>
          </div>
        </Col>
      </Row>
    </div>
  );
};
