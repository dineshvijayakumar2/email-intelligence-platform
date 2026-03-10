import React, { useState, useEffect, useRef } from "react";
import { Row, Col, Statistic, Typography, Tag, Button, Empty, Space, Skeleton, List } from "antd";
import {
  MailOutlined,
  InboxOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ArrowRightOutlined,
  SyncOutlined,
  BulbOutlined,
  WarningOutlined,
  AlertOutlined,
  RightOutlined,
  FireOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import {
  dashboardService,
  DashboardStats,
  ProcessingOverview,
  MailboxSummary,
  RecentJob,
} from '../services/dashboardService';
import { bucketApi } from '../services/aiService';
import type { BucketSummary, ActionItem } from '../types/ai';
import { useAuth } from '../contexts/AuthContext';

const { Text } = Typography;

// Bucket display config
const BUCKET_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  churn_risk: { label: 'Churn Risk', color: '#f5222d', icon: <AlertOutlined /> },
  unresolved_block: { label: 'Unresolved', color: '#fa541c', icon: <ExclamationCircleOutlined /> },
  buying_signal: { label: 'Buying Signal', color: '#52c41a', icon: <FireOutlined /> },
  expansion_signal: { label: 'Expansion', color: '#1890ff', icon: <ArrowRightOutlined /> },
  competitor_threat: { label: 'Competitor', color: '#722ed1', icon: <WarningOutlined /> },
  missed_opportunity: { label: 'Missed Opp.', color: '#fa8c16', icon: <BulbOutlined /> },
  stakeholder_entry: { label: 'New Stakeholder', color: '#13c2c2', icon: <TeamOutlined /> },
  silent_champion: { label: 'Silent Champion', color: '#eb2f96', icon: <BulbOutlined /> },
};

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const { profile } = useAuth();

  const [stats, setStats] = useState<DashboardStats>({ totalEmails: 0, totalMailboxes: 0, todayEmails: 0, processingJobs: 0 });
  const [processingOverview, setProcessingOverview] = useState<ProcessingOverview>({ activeJobs: 0, completedToday: 0, failedToday: 0, totalProcessed: 0, successRate: 100 });
  const [mailboxes, setMailboxes] = useState<MailboxSummary[]>([]);
  const [recentJobs, setRecentJobs] = useState<RecentJob[]>([]);
  const [bucketSummary, setBucketSummary] = useState<BucketSummary | null>(null);
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);

  const [statsLoading, setStatsLoading] = useState(true);
  const [processingLoading, setProcessingLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(true);

  const isMountedRef = useRef(true);

  // Get first accessible mailbox for AI data
  const firstMailboxId = profile?.accessibleMailboxIds?.[0];

  const loadFastData = async () => {
    try {
      const [newStats, newMailboxes] = await Promise.all([
        dashboardService.getDashboardStats(),
        dashboardService.getMailboxSummaries(),
      ]);
      if (!isMountedRef.current) return;
      setStats(newStats);
      if (newMailboxes.length > 0 || mailboxes.length === 0) setMailboxes(newMailboxes);
    } catch { /* silent */ } finally {
      if (isMountedRef.current) setStatsLoading(false);
    }
  };

  const loadProcessingData = async () => {
    try {
      const [overview, jobs] = await Promise.all([
        dashboardService.getProcessingOverview(),
        dashboardService.getRecentJobs(3),
      ]);
      if (!isMountedRef.current) return;
      setProcessingOverview(overview);
      if (jobs.length > 0 || recentJobs.length === 0) setRecentJobs(jobs);
    } catch { /* silent */ } finally {
      if (isMountedRef.current) setProcessingLoading(false);
    }
  };

  const loadAiData = async () => {
    if (!firstMailboxId) { setAiLoading(false); return; }
    try {
      const [summary, items] = await Promise.all([
        bucketApi.getSummary(firstMailboxId),
        bucketApi.getActionItems(firstMailboxId, undefined, 0.5, 5),
      ]);
      if (!isMountedRef.current) return;
      setBucketSummary(summary);
      setActionItems(items.items || []);
    } catch { /* silent */ } finally {
      if (isMountedRef.current) setAiLoading(false);
    }
  };

  useEffect(() => {
    isMountedRef.current = true;
    loadFastData();
    loadProcessingData();
    loadAiData();
    const interval = setInterval(() => {
      if (isMountedRef.current) { loadFastData(); loadProcessingData(); }
    }, 30000);
    return () => { isMountedRef.current = false; clearInterval(interval); };
  }, [firstMailboxId]);

  // Count urgent action items (churn + unresolved)
  const urgentCount = (bucketSummary?.churn_risk || 0) + (bucketSummary?.unresolved_block || 0);
  const opportunityCount = (bucketSummary?.buying_signal || 0) + (bucketSummary?.expansion_signal || 0);

  const getTypeTag = (type: string, hasLive: boolean) => {
    const color = type === 'gmail' ? 'red' : type === 'outlook_live' ? 'blue' : type === 'mbox' ? 'green' : type === 'pst' ? 'geekblue' : 'purple';
    return (
      <Tag color={color} style={{ fontSize: 11 }}>
        {type === 'outlook_live' ? 'OUTLOOK' : type.toUpperCase()}{hasLive && ' LIVE'}
      </Tag>
    );
  };

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Greeting */}
      <div className="fade-in-up" style={{ marginBottom: 24 }}>
        <Text type="secondary">
          {profile?.name ? `Welcome back, ${profile.name.split(' ')[0]}` : 'Email intelligence overview'}
        </Text>
      </div>

      {/* Row 1: Key metrics */}
      <Row gutter={[16, 16]} className="fade-in-up stagger-1">
        <Col xs={12} sm={6}>
          <div className="glass-card" style={{ padding: 20, cursor: 'pointer' }} onClick={() => navigate('/emails')}>
            {statsLoading ? <Skeleton.Input active style={{ width: 80, height: 28 }} /> : (
              <Statistic title="Total Emails" value={stats.totalEmails} prefix={<MailOutlined />} valueStyle={{ color: "#667eea" }} />
            )}
          </div>
        </Col>
        <Col xs={12} sm={6}>
          <div className="glass-card" style={{ padding: 20, cursor: 'pointer' }} onClick={() => navigate('/mailboxes')}>
            {statsLoading ? <Skeleton.Input active style={{ width: 60, height: 28 }} /> : (
              <Statistic title="Mailboxes" value={stats.totalMailboxes} prefix={<InboxOutlined />} valueStyle={{ color: "#52c41a" }} />
            )}
          </div>
        </Col>
        <Col xs={12} sm={6}>
          <div className="glass-card" style={{ padding: 20, cursor: urgentCount > 0 ? 'pointer' : 'default' }} onClick={() => urgentCount > 0 && navigate('/intelligence/inbox')}>
            {aiLoading ? <Skeleton.Input active style={{ width: 60, height: 28 }} /> : (
              <Statistic
                title="Needs Attention"
                value={urgentCount}
                prefix={urgentCount > 0 ? <WarningOutlined /> : <CheckCircleOutlined />}
                valueStyle={{ color: urgentCount > 0 ? '#f5222d' : '#52c41a' }}
              />
            )}
          </div>
        </Col>
        <Col xs={12} sm={6}>
          <div className="glass-card" style={{ padding: 20, cursor: opportunityCount > 0 ? 'pointer' : 'default' }} onClick={() => opportunityCount > 0 && navigate('/intelligence/opportunities')}>
            {aiLoading ? <Skeleton.Input active style={{ width: 60, height: 28 }} /> : (
              <Statistic
                title="Opportunities"
                value={opportunityCount}
                prefix={<FireOutlined />}
                valueStyle={{ color: opportunityCount > 0 ? '#52c41a' : '#999' }}
              />
            )}
          </div>
        </Col>
      </Row>

      {/* Row 2: Mailboxes + AI Signals */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }} className="fade-in-up stagger-2">
        {/* Mailboxes — click to open emails */}
        <Col xs={24} lg={14}>
          <div className="glass-table-container" style={{ height: '100%' }}>
            <div style={{ padding: '16px 24px', borderBottom: '1px solid rgba(102, 126, 234, 0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text strong style={{ fontSize: 16 }}>Your Mailboxes</Text>
              <Link to="/mailboxes" style={{ color: '#667eea', fontSize: 13 }}>Manage <ArrowRightOutlined /></Link>
            </div>
            {statsLoading ? (
              <div style={{ padding: 16 }}>
                {[1, 2, 3].map(i => (
                  <div key={i} style={{ display: 'flex', gap: 16, marginBottom: 16, alignItems: 'center' }}>
                    <Skeleton.Avatar active size="small" />
                    <Skeleton.Input active size="small" style={{ width: 140 }} />
                    <Skeleton.Input active size="small" style={{ width: 60 }} />
                  </div>
                ))}
              </div>
            ) : mailboxes.length > 0 ? (
              <List
                dataSource={mailboxes}
                size="small"
                renderItem={(mb) => {
                  const isLive = mb.hasLiveSync || ['gmail', 'outlook_live'].includes(mb.type);
                  return (
                    <List.Item
                      style={{ padding: '12px 24px', cursor: 'pointer', transition: 'background 0.2s' }}
                      className="hover-highlight"
                      onClick={() => navigate(`/emails/${mb.id}`)}
                      actions={[
                        <RightOutlined key="go" style={{ color: '#667eea', fontSize: 12 }} />,
                      ]}
                    >
                      <List.Item.Meta
                        avatar={<InboxOutlined style={{ fontSize: 20, color: mb.isActive ? '#667eea' : '#999', marginTop: 4 }} />}
                        title={
                          <Space>
                            <Text strong>{mb.name}</Text>
                            {getTypeTag(mb.type, isLive)}
                          </Space>
                        }
                        description={
                          <Space size={16}>
                            <Text type="secondary" style={{ fontSize: 12 }}>{mb.emailCount.toLocaleString()} emails</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {mb.lastSync ? `Synced ${dashboardService.formatRelativeTime(mb.lastSync)}` : 'Never synced'}
                            </Text>
                          </Space>
                        }
                      />
                    </List.Item>
                  );
                }}
              />
            ) : (
              <div style={{ padding: 48, textAlign: 'center' }}>
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<Text type="secondary">No mailboxes connected</Text>}>
                  <Button type="primary" onClick={() => navigate('/mailboxes/create')}>Add Your First Mailbox</Button>
                </Empty>
              </div>
            )}
          </div>
        </Col>

        {/* AI Signal Summary */}
        <Col xs={24} lg={10}>
          <div className="glass-card-static" style={{ padding: 24, height: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <Space>
                <BulbOutlined style={{ color: '#667eea', fontSize: 18 }} />
                <Text strong style={{ fontSize: 16 }}>AI Signals</Text>
              </Space>
              <Link to="/intelligence/inbox" style={{ color: '#667eea', fontSize: 13 }}>View All <ArrowRightOutlined /></Link>
            </div>

            {aiLoading ? (
              <div>
                {[1, 2, 3, 4].map(i => <Skeleton.Input key={i} active size="small" style={{ width: '100%', marginBottom: 8 }} />)}
              </div>
            ) : bucketSummary && bucketSummary.total > 0 ? (
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                {Object.entries(BUCKET_CONFIG).map(([key, cfg]) => {
                  const count = (bucketSummary as any)[key] || 0;
                  if (count === 0) return null;
                  return (
                    <div
                      key={key}
                      style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.02)', cursor: 'pointer' }}
                      onClick={() => navigate('/intelligence/inbox')}
                    >
                      <Space size={8}>
                        <span style={{ color: cfg.color }}>{cfg.icon}</span>
                        <Text style={{ fontSize: 13 }}>{cfg.label}</Text>
                      </Space>
                      <Tag color={cfg.color} style={{ margin: 0, minWidth: 28, textAlign: 'center' }}>{count}</Tag>
                    </div>
                  );
                })}
                <div style={{ marginTop: 8 }}>
                  <Link to="/intelligence/digest" style={{ fontSize: 13, color: '#667eea' }}>
                    <BulbOutlined /> View today's digest <ArrowRightOutlined />
                  </Link>
                </div>
              </Space>
            ) : (
              <div style={{ textAlign: 'center', padding: '24px 0' }}>
                <CheckCircleOutlined style={{ fontSize: 32, color: '#52c41a', marginBottom: 12 }} />
                <Text type="secondary" style={{ display: 'block' }}>No action items detected</Text>
                <Link to="/intelligence/digest" style={{ fontSize: 13, color: '#667eea', marginTop: 8, display: 'inline-block' }}>
                  View digest <ArrowRightOutlined />
                </Link>
              </div>
            )}
          </div>
        </Col>
      </Row>

      {/* Row 3: Priority Action Items + Recent Activity */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }} className="fade-in-up stagger-3">
        {/* Priority Action Items */}
        <Col xs={24} lg={14}>
          <div className="glass-table-container" style={{ height: '100%' }}>
            <div style={{ padding: '16px 24px', borderBottom: '1px solid rgba(102, 126, 234, 0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text strong style={{ fontSize: 16 }}>Priority Actions</Text>
              <Link to="/intelligence/opportunities" style={{ color: '#667eea', fontSize: 13 }}>All Opportunities <ArrowRightOutlined /></Link>
            </div>
            {aiLoading ? (
              <div style={{ padding: 16 }}>
                {[1, 2, 3].map(i => <Skeleton.Input key={i} active style={{ width: '100%', marginBottom: 12 }} />)}
              </div>
            ) : actionItems.length > 0 ? (
              <List
                dataSource={actionItems.slice(0, 5)}
                size="small"
                renderItem={(item) => {
                  const cfg = BUCKET_CONFIG[item.bucket] || { label: item.bucket, color: '#999', icon: <BulbOutlined /> };
                  return (
                    <List.Item style={{ padding: '10px 24px' }}>
                      <List.Item.Meta
                        avatar={<span style={{ color: cfg.color, fontSize: 16 }}>{cfg.icon}</span>}
                        title={
                          <Space size={8}>
                            <Text style={{ fontSize: 13 }}>{item.email_summary || item.recommended_action || 'Email action item'}</Text>
                            <Tag color={cfg.color} style={{ fontSize: 11 }}>{cfg.label}</Tag>
                          </Space>
                        }
                        description={
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {item.justification || ''}
                            {item.severity && <Tag style={{ marginLeft: 8, fontSize: 10 }}>{item.severity}</Tag>}
                          </Text>
                        }
                      />
                    </List.Item>
                  );
                }}
              />
            ) : (
              <div style={{ padding: 32, textAlign: 'center' }}>
                <CheckCircleOutlined style={{ fontSize: 28, color: '#52c41a', marginBottom: 8 }} />
                <Text type="secondary" style={{ display: 'block' }}>No priority actions right now</Text>
              </div>
            )}
          </div>
        </Col>

        {/* Recent Activity (compact) */}
        <Col xs={24} lg={10}>
          <div className="glass-card-static" style={{ padding: 24, height: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <Text strong style={{ fontSize: 16 }}>Recent Activity</Text>
              <Link to="/processing" style={{ color: '#667eea', fontSize: 13 }}>View All <ArrowRightOutlined /></Link>
            </div>
            {processingLoading ? (
              <div>{[1, 2, 3].map(i => <Skeleton.Input key={i} active style={{ width: '100%', marginBottom: 8 }} />)}</div>
            ) : (
              <>
                {/* Compact stats */}
                <Row gutter={[8, 8]} style={{ marginBottom: 16 }}>
                  <Col span={8}>
                    <Statistic title="Completed" value={processingOverview.completedToday} valueStyle={{ fontSize: 20 }}
                      prefix={<CheckCircleOutlined style={{ color: '#52c41a', fontSize: 14 }} />} />
                  </Col>
                  <Col span={8}>
                    <Statistic title="Failed" value={processingOverview.failedToday} valueStyle={{ fontSize: 20, color: processingOverview.failedToday > 0 ? '#f5222d' : undefined }}
                      prefix={<ExclamationCircleOutlined style={{ color: processingOverview.failedToday > 0 ? '#f5222d' : '#999', fontSize: 14 }} />} />
                  </Col>
                  <Col span={8}>
                    <Statistic title="Active" value={processingOverview.activeJobs} valueStyle={{ fontSize: 20 }}
                      prefix={processingOverview.activeJobs > 0 ? <SyncOutlined spin style={{ color: '#667eea', fontSize: 14 }} /> : <SyncOutlined style={{ color: '#999', fontSize: 14 }} />} />
                  </Col>
                </Row>

                {/* Recent jobs list */}
                {recentJobs.length > 0 ? (
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    {recentJobs.map(job => {
                      const statusColor = job.status === 'completed' ? '#52c41a' : job.status === 'failed' ? '#f5222d' : job.status === 'running' ? '#667eea' : '#fa8c16';
                      return (
                        <div key={job.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, padding: '4px 0' }}>
                          <Space size={6}>
                            <span style={{ width: 6, height: 6, borderRadius: '50%', background: statusColor, display: 'inline-block' }} />
                            <Text style={{ fontSize: 12 }}>{job.mailboxName}</Text>
                          </Space>
                          <Text type="secondary" style={{ fontSize: 11 }}>{dashboardService.formatRelativeTime(job.completedAt || job.createdAt)}</Text>
                        </div>
                      );
                    })}
                  </Space>
                ) : (
                  <Text type="secondary" style={{ fontSize: 12 }}>No recent jobs</Text>
                )}
              </>
            )}
          </div>
        </Col>
      </Row>
    </div>
  );
};
