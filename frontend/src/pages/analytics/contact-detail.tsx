import React from 'react';
import QBLinkWidget from '../../components/QBLinkWidget';
import { useParams, useNavigate } from 'react-router-dom';
import AIInsightsCard from '../../components/AIInsightsCard';
import { EngagementBadge } from '../../components/analytics/EngagementBadge';
import { LifecycleBadge } from '../../components/analytics/LifecycleBadge';
import { useContactDetail } from '../../hooks/queries';
import { useThreadsByContact } from '../../hooks/queries';
import { useQuery } from '@tanstack/react-query';
import {
  patternsApi,
  formatRelativeTime,
  formatResponseTime,
  formatRatio,
  threadStatusConfig,
} from '../../services/analyticsService';
import type { ThreadStatusSummary, CommunicationPattern } from '../../types/analytics';
import { PageShell } from '@/components/ui/page-shell';
import { KPICard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { ArrowLeft } from 'lucide-react';

export const ContactDetail: React.FC = () => {
  const { contactId } = useParams<{ contactId: string }>();
  const navigate = useNavigate();

  const contactQuery = useContactDetail(contactId);
  const threadsQuery = useThreadsByContact(contactId);
  const patternQuery = useQuery<CommunicationPattern | null>({
    queryKey: ['contact-pattern', contactId],
    queryFn: () => patternsApi.byContact(contactId!),
    enabled: !!contactId,
    staleTime: 60_000,
  });

  const contact = contactQuery.data;
  const threads = threadsQuery.data?.threads || [];
  const pattern = patternQuery.data;

  if (contactQuery.isLoading) {
    return <PageShell><ContentSkeleton rows={6} /></PageShell>;
  }

  if (!contact) {
    return (
      <PageShell>
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 mb-4">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <p className="text-slate-500">Contact not found</p>
      </PageShell>
    );
  }

  const totalEmails = (contact.total_emails_sent || 0) + (contact.total_emails_received || 0);

  return (
    <PageShell>
      {/* Header */}
      <div className="rounded-lg border bg-white shadow-sm p-4 mb-4">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="p-1 rounded hover:bg-slate-100">
            <ArrowLeft className="h-4 w-4 text-slate-500" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold text-slate-900">{contact.full_name || contact.email_address}</h1>
            {contact.full_name && <p className="text-sm text-slate-400">{contact.email_address}</p>}
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {(contact.customer_company_name || contact.company_name) && (
                <button
                  onClick={() => contact.customer_company_id && navigate(`/customers/${contact.customer_company_id}`)}
                  className="text-sm text-primary hover:underline"
                >
                  {contact.customer_company_name || contact.company_name}
                </button>
              )}
              {contact.job_title && <StatusBadge variant="neutral" size="sm">{contact.job_title}</StatusBadge>}
              {contact.qb_customer_type && <LifecycleBadge tier={contact.qb_customer_type} />}
              {contact.qb_tier && <StatusBadge variant="purple" size="sm">{contact.qb_tier}</StatusBadge>}
              {contact.qb_quotes_count != null && contact.qb_quotes_count > 0 && (
                <StatusBadge variant="info" size="sm">{contact.qb_quotes_count} quotes</StatusBadge>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <EngagementBadge score={contact.engagement_score} showBar />
            <QBLinkWidget
              mode="contact" entityId={contactId!} clientId={contact.client_id}
              qbLinkedId={contact.qb_contact_id}
              qbDisplayName={contact.qb_contact_id ? `QB Contact` : undefined}
              onLinked={() => window.location.reload()}
            />
          </div>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <KPICard title="Total Emails" value={totalEmails} onClick={() => navigate(`/emails?contact_id=${contactId}`)}
          subtitle={`${contact.total_emails_sent || 0} sent / ${contact.total_emails_received || 0} received`} />
        <KPICard title="Initiation Ratio" value={contact.initiation_ratio != null ? formatRatio(contact.initiation_ratio) : 'N/A'} />
        <KPICard title="Our Reply Rate" value={contact.reply_rate != null ? formatRatio(contact.reply_rate) : 'N/A'} />
        <KPICard title="Avg Response" value={formatResponseTime(contact.avg_response_time_seconds)} />
      </div>

      {/* Details + Threads */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mb-4">
        {/* Details */}
        <div className="lg:col-span-2 rounded-lg border bg-white shadow-sm p-4">
          <h2 className="text-sm font-semibold text-slate-900 mb-3">Details</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-slate-500">First Contact</span><span>{formatRelativeTime(contact.first_contacted_at)}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Last Contact</span><span>{formatRelativeTime(contact.last_contacted_at)}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Emails Sent</span><span className="tabular-nums">{contact.total_emails_sent || 0}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Emails Received</span><span className="tabular-nums">{contact.total_emails_received || 0}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Threads</span><span className="tabular-nums">{pattern?.total_threads ?? 'N/A'}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Avg Thread Depth</span><span className="tabular-nums">{pattern?.avg_thread_depth != null ? Number(pattern.avg_thread_depth).toFixed(1) : 'N/A'}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Emails/Week</span><span className="tabular-nums">{pattern?.emails_per_week != null ? Number(pattern.emails_per_week).toFixed(1) : 'N/A'}</span></div>
            {pattern?.their_avg_response_time_hours != null && (
              <div className="flex justify-between"><span className="text-slate-500">Their Avg Response</span><span className="tabular-nums">{Number(pattern.their_avg_response_time_hours).toFixed(1)}h</span></div>
            )}
          </div>
        </div>

        {/* Threads */}
        <div className="lg:col-span-3">
          {threads.length > 0 && (
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b">
                <button onClick={() => navigate(`/customers/threads?contact_id=${contactId}`)}
                  className="text-sm font-semibold text-primary hover:underline">
                  Threads ({threads.length})
                </button>
              </div>
              <div className="divide-y max-h-[400px] overflow-y-auto">
                {threads.slice(0, 50).map(t => {
                  const cfg = threadStatusConfig[t.status] || { label: t.status };
                  const variant = t.status === 'overdue' ? 'danger' : t.status === 'awaiting_our_response' ? 'warning' : t.status === 'ongoing' ? 'info' : 'neutral';
                  return (
                    <div key={t.thread_id}
                      className="flex items-center gap-3 px-4 py-2 hover:bg-slate-50 cursor-pointer transition-colors"
                      onClick={() => {
                        const name = encodeURIComponent(t.subject || t.thread_id?.slice(0, 20) || 'Thread');
                        navigate(`/emails?thread_id=${encodeURIComponent(t.thread_id)}&name=${name}`);
                      }}>
                      <div className="flex-1 min-w-0">
                        <span className="text-sm text-slate-800 truncate block">{t.subject || t.thread_id?.slice(0, 16)}</span>
                      </div>
                      <StatusBadge variant={variant as any} size="sm">{cfg.label}</StatusBadge>
                      <span className="text-xs text-slate-500 tabular-nums w-6 text-right">{t.total_messages}</span>
                      <span className="text-xs text-slate-400 w-14 text-right">{formatRelativeTime(t.last_message_date)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* AI Insights */}
      {contactId && contact && <AIInsightsCard entityType="contact" entityId={contactId} clientId={contact.client_id} />}
    </PageShell>
  );
};
