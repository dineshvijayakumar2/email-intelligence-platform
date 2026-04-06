import React, { useState, useEffect, useRef } from "react";
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
import { useClient } from '../contexts/ClientContext';
import { cn } from '@/lib/utils';
import { PageShell } from '@/components/ui/page-shell';
import { KPICard, KPIStrip } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { EmptyState, ContentSkeleton } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Mail, Inbox, AlertTriangle, CheckCircle2, Zap, ChevronRight,
  Lightbulb, Users, Flame, Clock, ArrowRight, Plus, Activity,
  RefreshCw, XCircle,
} from 'lucide-react';

// Signal config
const SIGNALS: Record<string, { label: string; variant: 'danger' | 'warning' | 'success' | 'info'; icon: React.ReactNode }> = {
  response_urgency:    { label: 'Response Urgency',  variant: 'danger',  icon: <AlertTriangle className="h-4 w-4" /> },
  deal_at_risk:        { label: 'Deal at Risk',      variant: 'warning', icon: <AlertTriangle className="h-4 w-4" /> },
  retention_risk:      { label: 'Retention Risk',     variant: 'danger',  icon: <XCircle className="h-4 w-4" /> },
  revenue_opportunity: { label: 'Revenue Opp.',       variant: 'success', icon: <Flame className="h-4 w-4" /> },
  new_relationship:    { label: 'New Relationship',   variant: 'info',    icon: <Users className="h-4 w-4" /> },
  account_neglect:     { label: 'Account Neglect',    variant: 'warning', icon: <Clock className="h-4 w-4" /> },
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

  const urgentCount = (bucketSummary?.response_urgency || 0) + (bucketSummary?.retention_risk || 0) + (bucketSummary?.deal_at_risk || 0) + (bucketSummary?.account_neglect || 0);
  const opportunityCount = (bucketSummary?.revenue_opportunity || 0) + (bucketSummary?.new_relationship || 0);

  return (
    <PageShell>
      {/* Greeting */}
      <p className="text-sm text-slate-500 mb-5">
        {profile?.name ? `Welcome back, ${profile.name.split(' ')[0]}` : 'Email intelligence overview'}
      </p>

      {/* KPI Strip */}
      <KPIStrip className="mb-6">
        <KPICard
          title="Total Emails"
          value={stats.totalEmails}
          loading={statsLoading}
          onClick={() => navigate('/emails')}
          subtitle={stats.todayEmails > 0 ? `+${stats.todayEmails} today` : undefined}
          trend={stats.todayEmails > 0 ? 'up' : undefined}
          delta={stats.todayEmails > 0 ? `${stats.todayEmails}` : undefined}
        />
        <KPICard
          title="Mailboxes"
          value={stats.totalMailboxes}
          loading={statsLoading}
          onClick={() => navigate('/mailboxes')}
          subtitle={`${processingOverview.activeJobs} active jobs`}
        />
        <KPICard
          title="Needs Attention"
          value={urgentCount}
          loading={aiLoading}
          danger={urgentCount > 0}
          onClick={() => urgentCount > 0 ? navigate('/insights/inbox') : undefined}
          subtitle={urgentCount === 0 ? 'All clear' : undefined}
        />
        <KPICard
          title="Opportunities"
          value={opportunityCount}
          loading={aiLoading}
          onClick={() => opportunityCount > 0 ? navigate('/insights/opportunities') : undefined}
          trend={opportunityCount > 0 ? 'up' : undefined}
          delta={opportunityCount > 0 ? `${opportunityCount}` : undefined}
        />
      </KPIStrip>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        {/* Mailboxes — 3/5 width */}
        <div className="lg:col-span-3">
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <h2 className="text-sm font-semibold text-slate-900">Your Mailboxes</h2>
              <Link to="/mailboxes" className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1">
                Manage <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {statsLoading ? (
              <ContentSkeleton rows={3} />
            ) : mailboxes.length > 0 ? (
              <div className="divide-y">
                {mailboxes.map(mb => {
                  const isLive = mb.hasLiveSync || ['gmail', 'outlook_live'].includes(mb.type);
                  const typeLabel = mb.type === 'outlook_live' ? 'OUTLOOK' : mb.type.toUpperCase();
                  return (
                    <div
                      key={mb.id}
                      className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50 cursor-pointer transition-colors"
                      onClick={() => navigate(`/emails/${mb.id}`)}
                    >
                      <Inbox className={cn('h-5 w-5 shrink-0', mb.isActive ? 'text-primary' : 'text-slate-300')} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-slate-900 truncate">{mb.name}</span>
                          <StatusBadge variant={mb.type === 'gmail' ? 'danger' : 'info'} size="sm">
                            {typeLabel}{isLive ? ' LIVE' : ''}
                          </StatusBadge>
                        </div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-xs text-slate-500">{mb.emailCount.toLocaleString()} emails</span>
                          <span className="text-xs text-slate-400">
                            {mb.lastSync ? `Synced ${dashboardService.formatRelativeTime(mb.lastSync)}` : 'Never synced'}
                          </span>
                        </div>
                      </div>
                      <ChevronRight className="h-4 w-4 text-slate-300 shrink-0" />
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                icon={<Mail className="h-10 w-10" />}
                title="No mailboxes connected"
                description="Connect your first mailbox to start analyzing emails"
                action={
                  <button onClick={() => navigate('/mailboxes/create')}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark transition-colors">
                    <Plus className="h-4 w-4" /> Add Mailbox
                  </button>
                }
              />
            )}
          </div>
        </div>

        {/* AI Signals — 2/5 width */}
        <div className="lg:col-span-2">
          <div className="rounded-lg border bg-white shadow-sm h-full">
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <div className="flex items-center gap-2">
                <Lightbulb className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-semibold text-slate-900">AI Signals</h2>
              </div>
              <Link to="/insights/inbox" className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1">
                View All <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {aiLoading ? (
              <ContentSkeleton rows={4} />
            ) : bucketSummary && bucketSummary.total > 0 ? (
              <div className="p-3 space-y-1.5">
                {Object.entries(SIGNALS).map(([key, cfg]) => {
                  const count = (bucketSummary as any)[key] || 0;
                  if (count === 0) return null;
                  return (
                    <div
                      key={key}
                      className="flex items-center justify-between px-3 py-2 rounded-md hover:bg-slate-50 cursor-pointer transition-colors"
                      onClick={() => navigate('/insights/inbox')}
                    >
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          cfg.variant === 'danger' ? 'text-destructive' :
                          cfg.variant === 'warning' ? 'text-warning' :
                          cfg.variant === 'success' ? 'text-success' : 'text-primary'
                        )}>{cfg.icon}</span>
                        <span className="text-sm text-slate-700">{cfg.label}</span>
                      </div>
                      <StatusBadge variant={cfg.variant}>{count}</StatusBadge>
                    </div>
                  );
                })}
                <div className="pt-2 px-3">
                  <Link to="/insights/digest" className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1">
                    <Lightbulb className="h-3 w-3" /> View today's digest <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-10">
                <CheckCircle2 className="h-8 w-8 text-success mb-2" />
                <p className="text-sm text-slate-500">No action items detected</p>
                <Link to="/insights/digest" className="text-xs text-primary hover:underline mt-2 inline-flex items-center gap-1">
                  View digest <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Row 2: Priority Actions + Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 mt-5">
        {/* Priority Actions */}
        <div className="lg:col-span-3">
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <h2 className="text-sm font-semibold text-slate-900">Priority Actions</h2>
              <Link to="/insights/opportunities" className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1">
                All Opportunities <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {aiLoading ? (
              <ContentSkeleton rows={3} />
            ) : actionItems.length > 0 ? (
              <div className="divide-y">
                {actionItems.slice(0, 5).map((item, i) => {
                  const cfg = SIGNALS[item.bucket] || { label: item.bucket, variant: 'info' as const, icon: <Lightbulb className="h-4 w-4" /> };
                  return (
                    <div key={i} className="flex items-start gap-3 px-5 py-3">
                      <span className={cn(
                        'mt-0.5',
                        cfg.variant === 'danger' ? 'text-destructive' :
                        cfg.variant === 'warning' ? 'text-warning' :
                        cfg.variant === 'success' ? 'text-success' : 'text-primary'
                      )}>{cfg.icon}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-slate-800 truncate">{item.email_summary || item.recommended_action || 'Action item'}</span>
                          <StatusBadge variant={cfg.variant} size="sm">{cfg.label}</StatusBadge>
                        </div>
                        {item.justification && (
                          <p className="text-xs text-slate-500 mt-0.5 truncate">{item.justification}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-10">
                <CheckCircle2 className="h-8 w-8 text-success mb-2" />
                <p className="text-sm text-slate-500">No priority actions right now</p>
              </div>
            )}
          </div>
        </div>

        {/* Recent Activity */}
        <div className="lg:col-span-2">
          <div className="rounded-lg border bg-white shadow-sm h-full">
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <h2 className="text-sm font-semibold text-slate-900">Recent Activity</h2>
              <Link to="/processing" className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1">
                View All <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {processingLoading ? (
              <ContentSkeleton rows={3} />
            ) : (
              <div className="p-4">
                {/* Processing stats */}
                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="text-center">
                    <p className="text-lg font-semibold tabular-nums text-slate-900">{processingOverview.completedToday}</p>
                    <p className="text-xs text-slate-500">Completed</p>
                  </div>
                  <div className="text-center">
                    <p className={cn('text-lg font-semibold tabular-nums', processingOverview.failedToday > 0 ? 'text-destructive' : 'text-slate-900')}>
                      {processingOverview.failedToday}
                    </p>
                    <p className="text-xs text-slate-500">Failed</p>
                  </div>
                  <div className="text-center">
                    <p className="text-lg font-semibold tabular-nums text-slate-900">{processingOverview.activeJobs}</p>
                    <p className="text-xs text-slate-500">Active</p>
                  </div>
                </div>

                {/* Recent jobs */}
                {recentJobs.length > 0 ? (
                  <div className="space-y-2">
                    {recentJobs.map(job => {
                      const statusColor = job.status === 'completed' ? 'bg-success' : job.status === 'failed' ? 'bg-destructive' : job.status === 'running' ? 'bg-primary' : 'bg-warning';
                      return (
                        <div key={job.id} className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className={cn('w-1.5 h-1.5 rounded-full', statusColor)} />
                            <span className="text-xs text-slate-700">{job.mailboxName}</span>
                          </div>
                          <span className="text-xs text-slate-400">
                            {dashboardService.formatRelativeTime(job.completedAt || job.createdAt)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 text-center">No recent jobs</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </PageShell>
  );
};
