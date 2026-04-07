import React, { useState, useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  dashboardService, DashboardStats, ProcessingOverview, MailboxSummary, RecentJob,
} from '../services/dashboardService';
import { useAuth } from '../contexts/AuthContext';
import { useClient } from '../contexts/ClientContext';
import { cn } from '@/lib/utils';
import { PageShell } from '@/components/ui/page-shell';
import { KPICard, KPIStrip } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { EmptyState, ContentSkeleton } from '@/components/ui/empty-state';
import {
  Mail, Inbox, ChevronRight, ArrowRight, Plus, Activity,
  RefreshCw, Building2, Users, FolderOpen, Database, Clock,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const { clientId, clientName } = useClient();

  const [stats, setStats] = useState<DashboardStats>({ totalEmails: 0, totalMailboxes: 0, todayEmails: 0, processingJobs: 0 });
  const [processingOverview, setProcessingOverview] = useState<ProcessingOverview>({ activeJobs: 0, completedToday: 0, failedToday: 0, totalProcessed: 0, successRate: 100 });
  const [mailboxes, setMailboxes] = useState<MailboxSummary[]>([]);
  const [recentJobs, setRecentJobs] = useState<RecentJob[]>([]);
  const [statsLoading, setStatsLoading] = useState(true);
  const [processingLoading, setProcessingLoading] = useState(true);
  const isMountedRef = useRef(true);

  const isAdmin = profile?.roles?.includes('admin') || profile?.roles?.includes('client_manager');

  const loadFastData = async () => {
    try {
      const [newStats, newMailboxes] = await Promise.all([dashboardService.getDashboardStats(), dashboardService.getMailboxSummaries()]);
      if (!isMountedRef.current) return;
      setStats(newStats);
      if (newMailboxes.length > 0 || mailboxes.length === 0) setMailboxes(newMailboxes);
    } catch {} finally { if (isMountedRef.current) setStatsLoading(false); }
  };

  const loadProcessingData = async () => {
    try {
      const [overview, jobs] = await Promise.all([dashboardService.getProcessingOverview(), dashboardService.getRecentJobs(5)]);
      if (!isMountedRef.current) return;
      setProcessingOverview(overview);
      if (jobs.length > 0 || recentJobs.length === 0) setRecentJobs(jobs);
    } catch {} finally { if (isMountedRef.current) setProcessingLoading(false); }
  };

  useEffect(() => {
    isMountedRef.current = true;
    loadFastData(); loadProcessingData();
    const interval = setInterval(() => { if (isMountedRef.current) { loadFastData(); loadProcessingData(); } }, 30000);
    return () => { isMountedRef.current = false; clearInterval(interval); };
  }, []);

  const getTypeLabel = (type: string, hasLive: boolean) => {
    const label = type === 'outlook_live' ? 'Outlook' : type === 'gmail' ? 'Gmail' : type.toUpperCase();
    return `${label}${hasLive ? ' LIVE' : ''}`;
  };

  return (
    <PageShell>
      {/* Greeting */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-lg font-bold text-slate-900">
            {profile?.name ? `Welcome back, ${profile.name.split(' ')[0]}` : 'Dashboard'}
          </h1>
          {clientName && <p className="text-sm text-slate-500 mt-0.5">{clientName}</p>}
        </div>
        <button onClick={() => { loadFastData(); loadProcessingData(); }}
          className="h-8 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5">
          <RefreshCw className={cn('h-3.5 w-3.5', statsLoading && 'animate-spin')} />Refresh
        </button>
      </div>

      {/* KPI Strip — role-aware */}
      <KPIStrip className="mb-5">
        <KPICard title="Total Emails" value={stats.totalEmails} loading={statsLoading}
          onClick={() => navigate('/emails')}
          delta={stats.todayEmails > 0 ? `+${stats.todayEmails}` : undefined}
          trend={stats.todayEmails > 0 ? 'up' : undefined}
          subtitle={stats.todayEmails > 0 ? 'today' : undefined} />
        <KPICard title="Mailboxes" value={stats.totalMailboxes} loading={statsLoading}
          onClick={() => navigate('/mailboxes')}
          subtitle={`${processingOverview.activeJobs} active jobs`} />
        {isAdmin ? (
          <>
            <KPICard title="Companies" value={mailboxes.reduce((s, m) => s + (m.emailCount > 0 ? 1 : 0), 0)} loading={statsLoading}
              onClick={() => navigate('/customers')} subtitle="with emails" />
            <KPICard title="Processing" value={processingOverview.completedToday} loading={processingLoading}
              subtitle={processingOverview.failedToday > 0 ? `${processingOverview.failedToday} failed` : 'completed today'}
              danger={processingOverview.failedToday > 0} />
          </>
        ) : (
          <>
            <KPICard title="My Emails" value={stats.totalEmails} loading={statsLoading}
              onClick={() => navigate('/emails')} subtitle="across all mailboxes" />
            <KPICard title="Today" value={stats.todayEmails} loading={statsLoading}
              subtitle="new emails" trend={stats.todayEmails > 0 ? 'up' : undefined} />
          </>
        )}
      </KPIStrip>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        {/* Left: Mailboxes — 3/5 */}
        <div className="lg:col-span-3">
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <h2 className="text-sm font-bold text-slate-900">Your Mailboxes</h2>
              <Link to="/mailboxes" className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1">
                Manage <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {statsLoading ? <ContentSkeleton rows={3} /> : mailboxes.length > 0 ? (
              <div className="divide-y divide-slate-50">
                {mailboxes.map(mb => {
                  const isLive = mb.hasLiveSync || ['gmail', 'outlook_live'].includes(mb.type);
                  return (
                    <div key={mb.id} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50 cursor-pointer transition-colors"
                      onClick={() => navigate(`/emails/${mb.id}`)}>
                      <Inbox className={cn('h-5 w-5 shrink-0', mb.isActive ? 'text-primary' : 'text-slate-300')} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-slate-900 truncate">{mb.name}</span>
                          <StatusBadge variant={mb.type === 'gmail' ? 'danger' : 'info'} size="sm">
                            {getTypeLabel(mb.type, isLive)}
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
              <EmptyState icon={<Mail className="h-10 w-10" />} title="No mailboxes connected"
                description="Connect your first mailbox to start analyzing emails"
                action={<button onClick={() => navigate('/mailboxes/create')} className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark"><Plus className="h-4 w-4" />Add Mailbox</button>} />
            )}
          </div>
        </div>

        {/* Right: Quick links + Activity — 2/5 */}
        <div className="lg:col-span-2 space-y-5">
          {/* Quick Links */}
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="px-5 py-3 border-b">
              <h2 className="text-sm font-bold text-slate-900">Quick Access</h2>
            </div>
            <div className="divide-y divide-slate-50">
              {[
                { label: 'Companies', href: '/customers', icon: <Building2 className="h-4 w-4 text-primary" />, desc: 'View customer profiles' },
                { label: 'Contacts', href: '/customers/contacts', icon: <Users className="h-4 w-4 text-primary" />, desc: 'Browse contacts' },
                { label: 'Threads', href: '/customers/threads', icon: <FolderOpen className="h-4 w-4 text-primary" />, desc: 'Active conversations' },
                { label: 'Semantic Search', href: '/insights/search', icon: <Mail className="h-4 w-4 text-primary" />, desc: 'Search with AI' },
                ...(isAdmin ? [
                  { label: 'QB Synced Data', href: '/manage/quickbase-data', icon: <Database className="h-4 w-4 text-primary" />, desc: 'QuickBase data' },
                ] : []),
              ].map(item => (
                <Link key={item.href} to={item.href}
                  className="flex items-center gap-3 px-5 py-2.5 hover:bg-slate-50 transition-colors">
                  {item.icon}
                  <div className="flex-1">
                    <span className="text-sm font-medium text-slate-800">{item.label}</span>
                    <p className="text-xs text-slate-400">{item.desc}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-slate-300" />
                </Link>
              ))}
            </div>
          </div>

          {/* Recent Activity */}
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <h2 className="text-sm font-bold text-slate-900">Recent Activity</h2>
              <Link to="/manage/processing" className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1">
                View All <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            {processingLoading ? <ContentSkeleton rows={3} /> : (
              <div className="p-4">
                {/* Processing stats */}
                <div className="grid grid-cols-3 gap-3 mb-3">
                  <div className="text-center">
                    <p className="text-lg font-bold tabular-nums text-slate-900">{processingOverview.completedToday}</p>
                    <p className="text-[11px] text-slate-500">Completed</p>
                  </div>
                  <div className="text-center">
                    <p className={cn('text-lg font-bold tabular-nums', processingOverview.failedToday > 0 ? 'text-destructive' : 'text-slate-900')}>{processingOverview.failedToday}</p>
                    <p className="text-[11px] text-slate-500">Failed</p>
                  </div>
                  <div className="text-center">
                    <p className="text-lg font-bold tabular-nums text-slate-900">{processingOverview.activeJobs}</p>
                    <p className="text-[11px] text-slate-500">Active</p>
                  </div>
                </div>

                {recentJobs.length > 0 ? (
                  <div className="space-y-1.5">
                    {recentJobs.map(job => {
                      const color = job.status === 'completed' ? 'bg-success' : job.status === 'failed' ? 'bg-destructive' : job.status === 'running' ? 'bg-primary' : 'bg-warning';
                      return (
                        <div key={job.id} className="flex items-center justify-between text-sm">
                          <div className="flex items-center gap-2">
                            <span className={cn('w-1.5 h-1.5 rounded-full', color)} />
                            <span className="text-xs text-slate-700">{job.mailboxName}</span>
                            <StatusBadge variant={job.status === 'completed' ? 'success' : job.status === 'failed' ? 'danger' : 'info'} size="sm">{job.status}</StatusBadge>
                          </div>
                          <span className="text-xs text-slate-400">{dashboardService.formatRelativeTime(job.completedAt || job.createdAt)}</span>
                        </div>
                      );
                    })}
                  </div>
                ) : <p className="text-xs text-slate-400 text-center">No recent jobs</p>}
              </div>
            )}
          </div>
        </div>
      </div>
    </PageShell>
  );
};
