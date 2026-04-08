/**
 * SyncStatusBar — Shows active sync progress inline. Zero antd.
 */

import React from 'react';
import { RefreshCw, XCircle, Download, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ProcessingJob {
  id: string;
  status: string;
  progress: number;
  mailbox_id: string;
  mailbox_name: string;
  job_type: string;
  started_at?: string;
  completed_at?: string;
  duration?: string;
  estimated_time_remaining?: string;
  processed_records?: number;
  total_records?: number;
  emails_per_second?: number;
}

interface SyncStatusBarProps {
  selectedMailboxIds: string[];
  jobs: ProcessingJob[];
  onViewDetails?: () => void;
}

export const SyncStatusBar: React.FC<SyncStatusBarProps> = ({
  selectedMailboxIds,
  jobs,
  onViewDetails,
}) => {
  const activeJobs = jobs.filter(
    job => selectedMailboxIds.includes(job.mailbox_id) &&
           ['running', 'downloading', 'pending'].includes(job.status)
  );

  const failedJobs = jobs.filter(job => {
    if (!selectedMailboxIds.includes(job.mailbox_id) || job.status !== 'failed') return false;
    const hasMoreRecentSuccess = jobs.some(o =>
      o.mailbox_id === job.mailbox_id && o.status === 'completed' &&
      o.completed_at && job.completed_at &&
      new Date(o.completed_at).getTime() > new Date(job.completed_at).getTime()
    );
    if (hasMoreRecentSuccess) return false;
    if (job.completed_at) {
      return new Date(job.completed_at).getTime() > Date.now() - 3600000;
    }
    return true;
  });

  if (activeJobs.length === 0 && failedJobs.length === 0) return null;

  const displayJob = activeJobs[0] || failedJobs[0];
  const isFailed = displayJob.status === 'failed';
  const mailboxName = displayJob.mailbox_name || 'Unknown Mailbox';

  const infoItems: string[] = [];
  if (displayJob.processed_records != null && displayJob.total_records) {
    infoItems.push(`${displayJob.processed_records.toLocaleString('en-AU')} / ${displayJob.total_records.toLocaleString('en-AU')} emails`);
  }
  if (displayJob.emails_per_second && displayJob.emails_per_second > 0) {
    infoItems.push(`${displayJob.emails_per_second.toFixed(1)} emails/s`);
  }
  if (displayJob.estimated_time_remaining) {
    infoItems.push(`ETA: ${displayJob.estimated_time_remaining}`);
  }

  return (
    <div className="px-4 mb-2">
      <div className={cn(
        'rounded-lg border p-3',
        isFailed ? 'border-destructive/30 bg-destructive/5' : 'border-primary/30 bg-primary/5'
      )}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isFailed ? (
              <XCircle className="h-4 w-4 text-destructive" />
            ) : displayJob.status === 'downloading' ? (
              <Download className="h-4 w-4 text-primary animate-pulse" />
            ) : displayJob.status === 'pending' ? (
              <Zap className="h-4 w-4 text-primary" />
            ) : (
              <RefreshCw className="h-4 w-4 text-primary animate-spin" />
            )}
            <span className="text-sm font-medium text-slate-900">
              {isFailed ? `Sync failed for ${mailboxName}` :
               displayJob.status === 'downloading' ? `Downloading from ${mailboxName}` :
               displayJob.status === 'pending' ? `Queued: ${mailboxName}` :
               `Syncing ${mailboxName}`}
            </span>
            {activeJobs.length > 1 && (
              <span className="text-xs text-slate-500">+{activeJobs.length - 1} more syncing</span>
            )}
          </div>
          {onViewDetails && (
            <button onClick={onViewDetails} className="text-xs text-primary hover:underline">
              View Details
            </button>
          )}
        </div>

        {!isFailed && displayJob.progress != null && (
          <div className="mt-2">
            <div className="h-1.5 rounded-full bg-white/50 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all"
                style={{ width: `${displayJob.progress}%` }}
              />
            </div>
          </div>
        )}

        {infoItems.length > 0 && (
          <p className="text-xs text-slate-500 mt-1.5">{infoItems.join(' \u00b7 ')}</p>
        )}
      </div>
    </div>
  );
};

export default SyncStatusBar;
