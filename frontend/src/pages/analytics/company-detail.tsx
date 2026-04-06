import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AIInsightsCard from '../../components/AIInsightsCard';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import { LifecycleBadge } from '../../components/analytics/LifecycleBadge';
import { OrderHistoryTable } from '../../components/OrderHistoryTable';
import { ProductProfileCards } from '../../components/ProductProfileCard';
import { RecommendationsPanel } from '../../components/RecommendationsPanel';
import StrikeRateCard from '../../components/StrikeRateCard';
import ContactCapabilitiesCard from '../../components/ContactCapabilitiesCard';
import SeasonalityChart from '../../components/SeasonalityChart';
import CapabilityRhythmCard from '../../components/CapabilityRhythmCard';
import QBLinkWidget from '../../components/QBLinkWidget';
import { useCompanyDetail, useOrderHistory, useProductProfile } from '../../hooks/queries';
import { useThreadsByCompany } from '../../hooks/queries';
import { formatRelativeTime, threadStatusConfig } from '../../services/analyticsService';
import type { ThreadStatusSummary } from '../../types/analytics';
import { formatCurrency } from '../../utils/numberFormat';
import { PageShell } from '@/components/ui/page-shell';
import { KPICard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { cn } from '@/lib/utils';
import { ArrowLeft, ArrowUp, ArrowDown, ChevronDown, ChevronRight } from 'lucide-react';

export const CompanyDetail: React.FC = () => {
  const { companyId } = useParams<{ companyId: string }>();
  const navigate = useNavigate();
  const [showOrderHistory, setShowOrderHistory] = useState(false);

  const companyQuery = useCompanyDetail(companyId);
  const threadsQuery = useThreadsByCompany(companyId);
  const orderHistoryQuery = useOrderHistory(companyId);
  const productProfileQuery = useProductProfile(companyId);

  const company = companyQuery.data;
  const threads = threadsQuery.data?.threads || [];
  const orderHistory = orderHistoryQuery.data?.items || [];
  const productProfile = productProfileQuery.data || { categories: [], operations: [], capability_breakdown: [], process_tags: [], embellishment_tags: [] };

  if (companyQuery.isLoading) {
    return <PageShell><ContentSkeleton rows={8} /></PageShell>;
  }

  if (!company) {
    return (
      <PageShell>
        <button onClick={() => navigate('/customers')} className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 mb-4">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <p className="text-slate-500">Company not found</p>
      </PageShell>
    );
  }

  const activeThreads = threads.filter(t => !['dropped', 'complete'].includes(t.status));
  const isAtRisk = company.engagement_status === 'at_risk' || (company.engagement_status as string) === 'churning';

  return (
    <PageShell>
      {/* Header card */}
      <div className={cn(
        'rounded-lg border bg-white shadow-sm p-4 mb-4',
        isAtRisk && 'border-l-4 border-l-destructive bg-red-50/30',
      )}>
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/customers')} className="p-1 rounded hover:bg-slate-100">
            <ArrowLeft className="h-4 w-4 text-slate-500" />
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-lg font-semibold text-slate-900">{company.company_name}</h1>
              {company.industry && <StatusBadge variant="neutral" size="sm">{company.industry}</StatusBadge>}
              <LifecycleBadge tier={company.qb_customer_type} />
            </div>
            {company.email_domains?.length > 0 && (
              <p className="text-xs text-slate-400 mt-0.5">{company.email_domains.join(', ')}</p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <EngagementBadge score={company.engagement_score} showBar />
            {isAtRisk && <StatusBadge variant="danger">At Risk</StatusBadge>}
          </div>
        </div>
      </div>

      {/* KPI strip + Business Data */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-4">
        <KPICard title="Emails" value={company.total_emails || 0} onClick={() => navigate(`/emails?company_id=${companyId}`)}
          subtitle={`${company.total_inbound || 0} in / ${company.total_outbound || 0} out`} />
        <KPICard title="Contacts" value={company.contact_count} onClick={() => navigate(`/customers/contacts?company_id=${companyId}&client_id=${company.client_id}`)}
          subtitle={company.decision_maker_count > 0 ? `${company.decision_maker_count} decision makers` : undefined} />
        <KPICard title="Threads" value={threads.length} onClick={() => navigate(`/customers/threads?company_id=${companyId}`)}
          subtitle={activeThreads.length > 0 ? `${activeThreads.length} active` : 'None active'} />
        <KPICard title="Overdue" value={threads.filter(t => t.status === 'overdue').length}
          danger={threads.filter(t => t.status === 'overdue').length > 0} />
      </div>

      {/* Business Data */}
      <div className="rounded-lg border bg-white shadow-sm p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-900">Business Data</h2>
          <QBLinkWidget
            mode="company" entityId={companyId!} clientId={company.client_id}
            qbLinkedId={company.qb_customer_id} qbMatchMethod={company.qb_match_method}
            qbDisplayName={company.qb_customer_code ? `QB: ${company.qb_customer_code}` : undefined}
            onLinked={() => window.location.reload()}
          />
        </div>
        {company.qb_total_revenue != null ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-2 text-sm">
            {company.qb_customer_type && <div><span className="text-slate-500">Type</span><div className="font-medium">{company.qb_customer_type}</div></div>}
            {company.qb_tier && <div><span className="text-slate-500">Tier</span><div><StatusBadge variant="purple" size="sm">{company.qb_tier}</StatusBadge></div></div>}
            {company.qb_account_manager && <div><span className="text-slate-500">AM</span><div className="font-medium">{company.qb_account_manager}</div></div>}
            {company.industry && <div><span className="text-slate-500">Industry</span><div className="font-medium">{company.industry}</div></div>}
            <div><span className="text-slate-500">Revenue</span><div className="font-semibold tabular-nums">{formatCurrency(company.qb_total_revenue)}</div></div>
            {company.qb_invoiced_ty != null && (
              <div>
                <span className="text-slate-500">This Year</span>
                <div className="font-medium tabular-nums inline-flex items-center gap-1">
                  {formatCurrency(company.qb_invoiced_ty)}
                  {company.qb_invoiced_ly != null && company.qb_invoiced_ty > company.qb_invoiced_ly && <ArrowUp className="h-3 w-3 text-success" />}
                  {company.qb_invoiced_ly != null && company.qb_invoiced_ty < company.qb_invoiced_ly && <ArrowDown className="h-3 w-3 text-destructive" />}
                </div>
              </div>
            )}
            {company.qb_invoiced_ly != null && <div><span className="text-slate-500">Last Year</span><div className="font-medium tabular-nums">{formatCurrency(company.qb_invoiced_ly)}</div></div>}
            {company.qb_growth_90d != null && (
              <div><span className="text-slate-500">Growth 90d</span>
                <div className={cn('font-medium tabular-nums', company.qb_growth_90d > 0 ? 'text-success' : company.qb_growth_90d < 0 ? 'text-destructive' : '')}>
                  {company.qb_growth_90d > 0 ? '+' : ''}{Number(company.qb_growth_90d).toFixed(1)}%
                </div>
              </div>
            )}
            {company.qb_days_since_last_invoice != null && <div><span className="text-slate-500">Days Since Order</span><div className="font-medium tabular-nums">{company.qb_days_since_last_invoice}</div></div>}
            <div><span className="text-slate-500">Orders</span><div className="font-medium tabular-nums">{orderHistory.filter(o => o.status !== 'Cancelled').length}</div></div>
            <div><span className="text-slate-500">First Contact</span><div className="text-xs text-slate-600">{formatRelativeTime(company.first_contact_date)}</div></div>
            <div><span className="text-slate-500">Last Contact</span><div className="text-xs text-slate-600">{formatRelativeTime(company.last_contact_date)}</div></div>
          </div>
        ) : (
          <p className="text-sm text-slate-400">No QB data — link a QB customer to enrich this profile.</p>
        )}
      </div>

      {/* Active Threads */}
      {activeThreads.length > 0 && (
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden mb-4">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <button onClick={() => navigate(`/customers/threads?company_id=${companyId}`)}
              className="text-sm font-semibold text-primary hover:underline">
              Active Threads ({activeThreads.length})
              <span className="text-xs text-slate-400 font-normal ml-2">{threads.length} total</span>
            </button>
          </div>
          <div className="divide-y">
            {activeThreads.slice(0, 10).map(t => {
              const cfg = threadStatusConfig[t.status] || { label: t.status, color: 'default' };
              const statusVariant = t.status === 'overdue' ? 'danger' : t.status === 'awaiting_our_response' ? 'warning' : t.status === 'ongoing' ? 'info' : 'neutral';
              return (
                <div key={t.thread_id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50 cursor-pointer transition-colors"
                  onClick={() => {
                    const name = encodeURIComponent(t.subject || t.thread_id?.slice(0, 20) || 'Thread');
                    navigate(`/emails?thread_id=${encodeURIComponent(t.thread_id)}&name=${name}`);
                  }}>
                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-slate-800 truncate block">{t.subject || t.thread_id?.slice(0, 16)}</span>
                    <span className="text-xs text-slate-400">{t.contact_name || t.contact_email || '—'}</span>
                  </div>
                  <StatusBadge variant={statusVariant as any} size="sm">{cfg.label}</StatusBadge>
                  <span className="text-xs text-slate-500 tabular-nums w-8 text-right">{t.total_messages}</span>
                  <span className="text-xs text-slate-400 w-16 text-right">{formatRelativeTime(t.last_message_date)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* AI Insights — still uses antd internally (migrated in Phase 4) */}
      {companyId && company && <AIInsightsCard entityType="company" entityId={companyId} clientId={company.client_id} />}

      {/* Intelligence cards grid — these still use antd internally */}
      {companyId && company && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
          <StrikeRateCard companyId={companyId} />
          <SeasonalityChart companyId={companyId} />
          <CapabilityRhythmCard companyId={companyId} />
          <ContactCapabilitiesCard companyId={companyId} />
          <ProductProfileCards
            categories={productProfile.categories}
            operations={productProfile.operations}
            capability_breakdown={productProfile.capability_breakdown}
            process_tags={productProfile.process_tags}
            embellishment_tags={productProfile.embellishment_tags}
            loading={productProfileQuery.isLoading}
          />
          <div className="rounded-lg border bg-white shadow-sm p-4">
            <h3 className="text-sm font-semibold text-slate-900 mb-3">Sales Opportunities</h3>
            <RecommendationsPanel companyId={companyId} />
          </div>
        </div>
      )}

      {/* Order History — collapsible */}
      <div className="mt-4">
        <button
          onClick={() => setShowOrderHistory(!showOrderHistory)}
          className="flex items-center gap-2 text-sm font-semibold text-slate-700 hover:text-slate-900 mb-2"
        >
          {showOrderHistory ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Order History ({orderHistory.length})
        </button>
        {showOrderHistory && (
          <div className="rounded-lg border bg-white shadow-sm p-3">
            <OrderHistoryTable items={orderHistory} loading={orderHistoryQuery.isLoading} />
          </div>
        )}
      </div>
    </PageShell>
  );
};
