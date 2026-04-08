/**
 * ProcessingStatusBadge — Zero antd.
 */

import React from 'react';
import { RefreshCw, CheckCircle, XCircle, Clock, Download, Pause } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ProcessingJob {
  id: string;
  status: string;
  progress: number;
  mailbox_id: string;
  job_type: string;
  started_at?: string;
  completed_at?: string;
  duration?: string;
  estimated_time_remaining?: string;
  processed_records?: number;
  total_records?: number;
  emails_per_second?: number;
}

interface ProcessingStatusBadgeProps {
  mailboxId: string;
  jobs?: ProcessingJob[];
  showProgress?: boolean;
  size?: 'small' | 'default' | 'large';
  onClick?: () => void;
}

export const ProcessingStatusBadge: React.FC<ProcessingStatusBadgeProps> = ({
  mailboxId,
  jobs = [],
  showProgress = false,
  size = 'default',
  onClick,
}) => {
  const activeJob = jobs.find(
    job => job.mailbox_id === mailboxId && ['running', 'downloading', 'pending'].includes(job.status)
  );
  const lastCompletedJob = jobs
    .filter(job => job.mailbox_id === mailboxId && job.status === 'completed')
    .sort((a, b) => new Date(b.completed_at || 0).getTime() - new Date(a.completed_at || 0).getTime())[0];
  const failedJob = jobs.find(
    job => job.mailbox_id === mailboxId && job.status === 'failed'
  );

  const getTimeAgo = (timestamp?: string): string => {
    if (!timestamp) return 'never';
    const diffMs = Date.now() - new Date(timestamp).getTime();
    const mins = Math.floor(diffMs / 60000);
    const hrs = Math.floor(mins / 60);
    const days = Math.floor(hrs / 24);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    if (hrs < 24) return `${hrs}h ago`;
    return `${days}d ago`;
  };

  const getConfig = () => {
    if (activeJob) {
      if (activeJob.status === 'downloading') {
        return {
          icon: <Download className={cn('h-3.5 w-3.5 animate-pulse', size === 'small' && 'h-3 w-3')} />,
          text: `Downloading${activeJob.progress ? ` ${activeJob.progress}%` : ''}`,
          tooltip: `Downloading emails${activeJob.estimated_time_remaining ? ` — ETA: ${activeJob.estimated_time_remaining}` : ''}`,
          color: 'text-purple-600',
        };
      }
      return {
        icon: <RefreshCw className={cn('h-3.5 w-3.5 animate-spin', size === 'small' && 'h-3 w-3')} />,
        text: `Syncing${activeJob.progress ? ` ${activeJob.progress}%` : ''}`,
        tooltip: `Processing emails${activeJob.estimated_time_remaining ? ` — ETA: ${activeJob.estimated_time_remaining}` : ''}`,
        color: 'text-primary',
      };
    }
    if (failedJob) {
      return {
        icon: <XCircle className={cn('h-3.5 w-3.5', size === 'small' && 'h-3 w-3')} />,
        text: 'Failed',
        tooltip: 'Sync failed — click to view details',
        color: 'text-destructive',
      };
    }
    if (lastCompletedJob) {
      const timeAgo = getTimeAgo(lastCompletedJob.completed_at);
      return {
        icon: <CheckCircle className={cn('h-3.5 w-3.5', size === 'small' && 'h-3 w-3')} />,
        text: timeAgo,
        tooltip: `Last synced ${timeAgo}${lastCompletedJob.duration ? ` — took ${lastCompletedJob.duration}` : ''}`,
        color: 'text-success',
      };
    }
    return {
      icon: <Clock className={cn('h-3.5 w-3.5', size === 'small' && 'h-3 w-3')} />,
      text: 'No sync yet',
      tooltip: 'This mailbox has not been synced yet',
      color: 'text-slate-400',
    };
  };

  const config = getConfig();
  const textSize = size === 'small' ? 'text-xs' : 'text-sm';

  return (
    <div
      onClick={onClick}
      className={cn('inline-flex items-center gap-1.5', onClick && 'cursor-pointer')}
      title={config.tooltip}
    >
      <span className={config.color}>{config.icon}</span>
      <span className={cn(textSize, config.color === 'text-destructive' ? 'text-destructive' : 'text-slate-500')}>
        {config.text}
      </span>
      {showProgress && activeJob && activeJob.progress != null && (
        <div className="ml-2 w-32">
          <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${activeJob.progress}%` }}
            />
          </div>
          {activeJob.emails_per_second != null && activeJob.emails_per_second > 0 && (
            <span className="text-[11px] text-slate-400">{activeJob.emails_per_second.toFixed(1)} emails/s</span>
          )}
        </div>
      )}
    </div>
  );
};

export default ProcessingStatusBadge;
