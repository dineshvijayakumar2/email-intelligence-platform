import React from 'react';
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
import { useCompanyDetail, useOrderHistory, useProductProfile } from '../../hooks/queries';
import { useThreadsByCompany } from '../../hooks/queries';
import {
  formatRelativeTime,
  engagementStatusConfig,
  threadStatusConfig,
} from '../../services/analyticsService';
import type { ThreadStatusSummary, ThreadStatus } from '../../types/analytics';
import { formatCurrency } from '../../utils/numberFormat';

const { Title, Text } = Typography;

export const CompanyDetail: React.FC = () => {
  const { companyId } = useParams<{ companyId: string }>();
  const navigate = useNavigate();

  // All data via TanStack Query — no manual useState/useEffect
  const companyQuery = useCompanyDetail(companyId);
  const threadsQuery = useThreadsByCompany(companyId);
  const orderHistoryQuery = useOrderHistory(companyId);
  const productProfileQuery = useProductProfile(companyId);

  const company = companyQuery.data;
  const threads = threadsQuery.data?.threads || [];
  const orderHistory = orderHistoryQuery.data?.items || [];
  const productProfile = productProfileQuery.data || { categories: [], operations: [], capability_breakdown: [], process_tags: [], embellishment_tags: [] };

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

  if (companyQuery.isLoading) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/customers')} style={{ marginBottom: 12 }}>Back</Button>
        <Skeleton active paragraph={{ rows: 10 }} />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/customers')} style={{ marginBottom: 12 }}>Back</Button>
        <Text type="secondary">Company not found</Text>
      </div>
    );
  }

  const statusCfg = engagementStatusConfig[company.engagement_status || 'unknown'];
  const activeThreads = threads.filter(t => !['dropped', 'complete'].includes(t.status));

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/customers')} style={{ marginBottom: 12 }}>Back to Companies</Button>

      <div className="glass-card fade-in-up" style={{ padding: 16, marginBottom: 12 }}>
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

      {/* Compact summary row: metrics + business data + communication */}
      <Row gutter={[12, 12]} className="fade-in-up stagger-1">
        {/* Left: Key metrics */}
        <Col xs={24} md={6}>
          <div className="glass-card" style={{ padding: 14 }}>
            <Row gutter={[8, 8]}>
              <Col span={12}><MetricCard title="Emails" value={company.total_emails || 0} onClick={() => navigate(`/emails?company_id=${companyId}`)} /></Col>
              <Col span={12}><MetricCard title="Contacts" value={company.contact_count} onClick={() => navigate(`/customers/contacts?company_id=${companyId}&client_id=${company.client_id}`)} /></Col>
              <Col span={12}><MetricCard title="Threads" value={threads.length} onClick={() => navigate(`/customers/threads?company_id=${companyId}`)} /></Col>
              <Col span={12}><MetricCard title="Overdue" value={threads.filter(t => t.status === 'overdue').length} onClick={() => navigate(`/customers/threads?company_id=${companyId}`)} /></Col>
            </Row>
            <Descriptions column={1} size="small" style={{ marginTop: 8 }}>
              <Descriptions.Item label="First Contact">{formatRelativeTime(company.first_contact_date)}</Descriptions.Item>
              <Descriptions.Item label="Last Contact">{formatRelativeTime(company.last_contact_date)}</Descriptions.Item>
              <Descriptions.Item label="In / Out">{company.total_inbound || 0} / {company.total_outbound || 0}</Descriptions.Item>
            </Descriptions>
          </div>
        </Col>

        {/* Right: Business data */}
        <Col xs={24} md={18}>
          <div className="glass-card" style={{ padding: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Text strong>Business Data</Text>
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
            {company.qb_total_revenue != null ? (
              <>
                <Descriptions column={3} size="small">
                  {company.qb_tier && <Descriptions.Item label="Tier"><Tag color="purple">{company.qb_tier}</Tag></Descriptions.Item>}
                  {company.qb_account_manager && <Descriptions.Item label="AM">{company.qb_account_manager}</Descriptions.Item>}
                  <Descriptions.Item label="Revenue">{formatCurrency(company.qb_total_revenue)}</Descriptions.Item>
                  {company.qb_invoiced_ty != null && (
                    <Descriptions.Item label="This Year">
                      {formatCurrency(company.qb_invoiced_ty)}
                      {company.qb_invoiced_ly != null && company.qb_invoiced_ty > company.qb_invoiced_ly && <ArrowUpOutlined style={{ color: '#52c41a', marginLeft: 4 }} />}
                      {company.qb_invoiced_ly != null && company.qb_invoiced_ty < company.qb_invoiced_ly && <ArrowDownOutlined style={{ color: '#ff4d4f', marginLeft: 4 }} />}
                    </Descriptions.Item>
                  )}
                  {company.qb_invoiced_ly != null && <Descriptions.Item label="Last Year">{formatCurrency(company.qb_invoiced_ly)}</Descriptions.Item>}
                  {company.qb_days_since_last_invoice != null && <Descriptions.Item label="Days Since Order">{company.qb_days_since_last_invoice}</Descriptions.Item>}
                  <Descriptions.Item label="Orders">{orderHistory.filter(o => o.status !== 'Cancelled').length}</Descriptions.Item>
                </Descriptions>
                {(company.qb_capabilities?.length > 0 || company.qb_processes?.length > 0 || company.qb_embellishments?.length > 0) && (
                  <div style={{ marginTop: 8 }}>
                    {company.qb_capabilities?.length > 0 && <div style={{ marginBottom: 4 }}><Text type="secondary" style={{ fontSize: 11 }}>Capabilities: </Text><Space size={[3, 3]} wrap>{company.qb_capabilities.map((c: string) => <Tag key={c} color="blue" style={{ fontSize: 10 }}>{c}</Tag>)}</Space></div>}
                    {company.qb_processes?.length > 0 && <div style={{ marginBottom: 4 }}><Text type="secondary" style={{ fontSize: 11 }}>Processes: </Text><Space size={[3, 3]} wrap>{company.qb_processes.map((p: string) => <Tag key={p} color="cyan" style={{ fontSize: 10 }}>{p}</Tag>)}</Space></div>}
                    {company.qb_embellishments?.length > 0 && <div><Text type="secondary" style={{ fontSize: 11 }}>Embellishments: </Text><Space size={[3, 3]} wrap>{company.qb_embellishments.map((e: string) => <Tag key={e} color="purple" style={{ fontSize: 10 }}>{e}</Tag>)}</Space></div>}
                  </div>
                )}
              </>
            ) : (
              <Text type="secondary">No QB data — link a QB customer to enrich this profile.</Text>
            )}
          </div>
        </Col>
      </Row>

      {/* Active Threads */}
      {activeThreads.length > 0 && (
        <div style={{ marginTop: 12 }} className="fade-in-up stagger-3">
          <div className="glass-table-container" style={{ padding: 16 }}>
            <a onClick={() => navigate(`/customers/threads?company_id=${companyId}`)}
              style={{ fontSize: 16, fontWeight: 600, display: 'block', marginBottom: 12, color: '#667eea', cursor: 'pointer' }}>
              Active Threads ({activeThreads.length})
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>{threads.length} total</Text>
            </a>
            <Table
              columns={threadColumns}
              dataSource={activeThreads}
              rowKey="thread_id"
              size="small"
              pagination={{ pageSize: 10, size: 'small' }}
              onRow={(record) => ({ onClick: () => handleThreadClick(record), style: { cursor: 'pointer' } })}
            />
          </div>
        </div>
      )}

      {companyId && company && <AIInsightsCard entityType="company" entityId={companyId} clientId={company.client_id} />}

      {/* Customer Intelligence */}
      {companyId && company && (
        <Row gutter={[16, 16]} style={{ marginTop: 12 }}>
          <Col xs={24} lg={12}><StrikeRateCard companyId={companyId} /></Col>
          <Col xs={24} lg={12}><SeasonalityChart companyId={companyId} /></Col>
          <Col xs={24} lg={12}><CapabilityRhythmCard companyId={companyId} /></Col>
          <Col xs={24} lg={12}><ContactCapabilitiesCard companyId={companyId} /></Col>
          <Col xs={24} lg={12}>
            <div className="glass-card" style={{ padding: 16 }}>
              <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Product Profile</Text>
              <ProductProfileCard
                categories={productProfile.categories}
                operations={productProfile.operations}
                capability_breakdown={productProfile.capability_breakdown}
                process_tags={productProfile.process_tags}
                embellishment_tags={productProfile.embellishment_tags}
                loading={productProfileQuery.isLoading}
              />
            </div>
          </Col>
          <Col xs={24} lg={12}>
            <div className="glass-card" style={{ padding: 16 }}>
              <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Sales Opportunities</Text>
              <RecommendationsPanel companyId={companyId} />
            </div>
          </Col>
        </Row>
      )}

      {/* Order History */}
      <div style={{ marginTop: 12 }}>
        <Collapse
          ghost
          items={[{
            key: 'order-history',
            label: <Text strong style={{ fontSize: 15 }}>Order History ({orderHistory.length})</Text>,
            children: (
              <div className="glass-table-container" style={{ padding: 8 }}>
                <OrderHistoryTable items={orderHistory} loading={orderHistoryQuery.isLoading} />
              </div>
            ),
          }]}
        />
      </div>
    </div>
  );
};
