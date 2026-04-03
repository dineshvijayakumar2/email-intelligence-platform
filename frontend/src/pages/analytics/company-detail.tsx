import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Button, Tag, Descriptions, Skeleton, Table, Collapse, Space } from 'antd';
import { ArrowLeftOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { MetricCard } from '../../components/analytics/MetricCard';
import AIInsightsCard from '../../components/AIInsightsCard';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import { LifecycleBadge } from '../../components/analytics/LifecycleBadge';
import { OrderHistoryTable } from '../../components/OrderHistoryTable';
import { ProductProfileCard } from '../../components/ProductProfileCard';
import { RecommendationsPanel } from '../../components/RecommendationsPanel';
import StrikeRateCard from '../../components/StrikeRateCard';
import ContactCapabilitiesCard from '../../components/ContactCapabilitiesCard';
import SeasonalityChart from '../../components/SeasonalityChart';
import CapabilityRhythmCard from '../../components/CapabilityRhythmCard';
import QBLinkWidget from '../../components/QBLinkWidget';
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
  const [orderHistory, setOrderHistory] = useState<any[]>([]);
  const [orderHistoryLoading, setOrderHistoryLoading] = useState(false);
  const [productProfile, setProductProfile] = useState<{ categories: any[]; operations: any[] }>({ categories: [], operations: [] });
  const [productProfileLoading, setProductProfileLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!companyId) return;
    const load = async () => {
      setLoading(true);

      // Fetch company detail with retry — most critical call
      let result = await companiesApi.getDetail(companyId);
      if (!result) {
        // Retry once after 1s (Supabase may be temporarily busy)
        await new Promise(r => setTimeout(r, 1000));
        result = await companiesApi.getDetail(companyId);
      }

      // Fetch thread data — get enough to show recent + compute counts
      const threadResult = await threadsApi.byCompany(companyId, 500);
      const allThreads = threadResult?.threads || [];

      if (isMountedRef.current) {
        setCompany(result);
        setTotalEmails(result?.total_emails || 0);
        setTotalSent(result?.total_outbound || 0);
        setTotalReceived(result?.total_inbound || 0);
        setThreads(allThreads);
        setLoading(false);
      }
      // Load supplementary data in parallel (non-blocking)
      setOrderHistoryLoading(true);
      setProductProfileLoading(true);
      companiesApi.getOrderHistory(companyId).then(d => {
        if (isMountedRef.current) { setOrderHistory(d?.items || []); setOrderHistoryLoading(false); }
      }).catch(() => { if (isMountedRef.current) setOrderHistoryLoading(false); });
      companiesApi.getProductProfile(companyId).then(d => {
        if (isMountedRef.current) { setProductProfile(d || { categories: [], operations: [] }); setProductProfileLoading(false); }
      }).catch(() => { if (isMountedRef.current) setProductProfileLoading(false); });
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
    { title: 'Emails', dataIndex: 'total_messages', key: 'msgs', width: 90 },
    { title: 'Last Email', dataIndex: 'last_message_date', key: 'last', width: 110, render: (v: string) => formatRelativeTime(v) },
  ];

  if (loading) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/customers')} style={{ marginBottom: 16 }}>Back</Button>
        <Skeleton active paragraph={{ rows: 10 }} />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/customers')} style={{ marginBottom: 16 }}>Back</Button>
        <Text type="secondary">Company not found</Text>
      </div>
    );
  }

  const statusCfg = engagementStatusConfig[company.engagement_status || 'unknown'];

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/customers')} style={{ marginBottom: 16 }}>Back to Companies</Button>

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
            onClick={() => navigate(`/emails?company_id=${companyId}`)}
          />
        </Col>
        <Col xs={12} sm={6}>
          <MetricCard title="Contacts" value={company.contact_count} onClick={() => navigate(`/customers/contacts?company_id=${companyId}&client_id=${company.client_id}`)} />
        </Col>
        <Col xs={12} sm={6}>
          <MetricCard
            title="Threads"
            value={threads.length}
            onClick={() => navigate(`/customers/threads?company_id=${companyId}`)}
          />
        </Col>
        <Col xs={12} sm={6}>
          <MetricCard
            title="Overdue"
            value={threads.filter(t => t.status === 'overdue').length}
            onClick={() => navigate(`/customers/threads?company_id=${companyId}`)}
          />
        </Col>
      </Row>

      {/* Business Data + Communication Summary */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }} className="fade-in-up stagger-2">
        <Col xs={24} lg={12}>
          <div className="glass-card" style={{ padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <Text strong style={{ fontSize: 16 }}>Business Data</Text>
              <QBLinkWidget
                mode="company"
                entityId={companyId!}
                clientId={company.client_id}
                qbLinkedId={company.qb_customer_id}
                qbMatchMethod={company.qb_match_method}
                qbDisplayName={company.qb_customer_code ? `QB: ${company.qb_customer_code}` : undefined}
                onLinked={() => window.location.reload()}
              />
            </div>
            <Descriptions column={2} size="small">
              {company.qb_tier && (
                <Descriptions.Item label="Tier"><Tag color="purple">{company.qb_tier}</Tag></Descriptions.Item>
              )}
              {company.qb_account_manager && (
                <Descriptions.Item label="Account Manager">{company.qb_account_manager}</Descriptions.Item>
              )}
              {company.qb_total_revenue != null && (
                <Descriptions.Item label="Revenue">{formatCurrency(company.qb_total_revenue)}</Descriptions.Item>
              )}
              {company.qb_days_since_last_invoice != null && (
                <Descriptions.Item label="Days Since Order">{company.qb_days_since_last_invoice}</Descriptions.Item>
              )}
              {company.qb_invoiced_ty != null && (
                <Descriptions.Item label="This Year">
                  {formatCurrency(company.qb_invoiced_ty)}
                  {company.qb_invoiced_ly != null && company.qb_invoiced_ty > company.qb_invoiced_ly && (
                    <ArrowUpOutlined style={{ color: '#52c41a', marginLeft: 6 }} />
                  )}
                  {company.qb_invoiced_ly != null && company.qb_invoiced_ty < company.qb_invoiced_ly && (
                    <ArrowDownOutlined style={{ color: '#ff4d4f', marginLeft: 6 }} />
                  )}
                </Descriptions.Item>
              )}
              {company.qb_invoiced_ly != null && (
                <Descriptions.Item label="Last Year">{formatCurrency(company.qb_invoiced_ly)}</Descriptions.Item>
              )}
            </Descriptions>
            {(company.qb_capabilities?.length > 0 || company.qb_processes?.length > 0 || company.qb_embellishments?.length > 0) && (
              <div style={{ marginTop: 12 }}>
                {company.qb_capabilities?.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>Capabilities: </Text>
                    <Space size={[4, 4]} wrap>
                      {company.qb_capabilities.map((c: string) => <Tag key={c} color="blue" style={{ fontSize: 11 }}>{c}</Tag>)}
                    </Space>
                  </div>
                )}
                {company.qb_processes?.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>Processes: </Text>
                    <Space size={[4, 4]} wrap>
                      {company.qb_processes.map((p: string) => <Tag key={p} color="cyan" style={{ fontSize: 11 }}>{p}</Tag>)}
                    </Space>
                  </div>
                )}
                {company.qb_embellishments?.length > 0 && (
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>Embellishments: </Text>
                    <Space size={[4, 4]} wrap>
                      {company.qb_embellishments.map((e: string) => <Tag key={e} color="purple" style={{ fontSize: 11 }}>{e}</Tag>)}
                    </Space>
                  </div>
                )}
              </div>
            )}
            {!company.qb_total_revenue && !company.qb_customer_id && (
              <Text type="secondary">No QB data — link a QB customer to enrich this profile.</Text>
            )}
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className="glass-card" style={{ padding: 20 }}>
            <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Communication</Text>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="First Contact">{formatRelativeTime(company.first_contact_date)}</Descriptions.Item>
              <Descriptions.Item label="Last Contact">{formatRelativeTime(company.last_contact_date)}</Descriptions.Item>
              <Descriptions.Item label="Inbound">{totalReceived}</Descriptions.Item>
              <Descriptions.Item label="Outbound">{totalSent}</Descriptions.Item>
              <Descriptions.Item label="Client">{company.client_name || '-'}</Descriptions.Item>
            </Descriptions>
          </div>
        </Col>
      </Row>

      {/* Active Threads */}
      {threads.filter(t => !['dropped', 'complete'].includes(t.status)).length > 0 && (
        <div style={{ marginTop: 16 }} className="fade-in-up stagger-3">
          <div className="glass-table-container" style={{ padding: 16 }}>
            <a
              onClick={() => navigate(`/customers/threads?company_id=${companyId}`)}
              style={{ fontSize: 16, fontWeight: 600, display: 'block', marginBottom: 12, color: '#667eea', cursor: 'pointer' }}
            >
              Active Threads ({threads.filter(t => !['dropped', 'complete'].includes(t.status)).length})
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>{threads.length} total</Text>
            </a>
            <Table
              columns={threadColumns}
              dataSource={threads.filter(t => !['dropped', 'complete'].includes(t.status))}
              rowKey="thread_id"
              size="small"
              pagination={{ pageSize: 10, size: 'small' }}
              onRow={(record) => ({
                onClick: () => handleThreadClick(record),
                style: { cursor: 'pointer' },
              })}
            />
          </div>
        </div>
      )}

      {companyId && !loading && company && <AIInsightsCard entityType="company" entityId={companyId} />}

      {/* Customer Intelligence */}
      {companyId && !loading && company && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={12}><StrikeRateCard companyId={companyId} /></Col>
          <Col xs={24} lg={12}><SeasonalityChart companyId={companyId} /></Col>
          <Col xs={24} lg={12}><CapabilityRhythmCard companyId={companyId} /></Col>
          <Col xs={24} lg={12}><ContactCapabilitiesCard companyId={companyId} /></Col>
          <Col xs={24} lg={12}>
            <div className="glass-card" style={{ padding: 20 }}>
              <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Product Profile</Text>
              <ProductProfileCard categories={productProfile?.categories || []} operations={productProfile?.operations || []} loading={productProfileLoading} />
            </div>
          </Col>
          <Col xs={24} lg={12}>
            <div className="glass-card" style={{ padding: 20 }}>
              <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Sales Opportunities</Text>
              <RecommendationsPanel companyId={companyId} />
            </div>
          </Col>
        </Row>
      )}

      {/* Order History */}
      <div style={{ marginTop: 16 }}>
        <Collapse
          ghost
          items={[{
            key: 'order-history',
            label: <Text strong style={{ fontSize: 15 }}>Order History ({orderHistory.length})</Text>,
            children: (
              <div className="glass-table-container" style={{ padding: 8 }}>
                <OrderHistoryTable items={orderHistory} loading={orderHistoryLoading} />
              </div>
            ),
          }]}
        />
      </div>
    </div>
  );
};
