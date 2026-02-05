import React, { useState, useEffect } from 'react';
import { Badge, Tooltip, Progress, Space, Typography } from 'antd';
import {
  SyncOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  DownloadOutlined,
  PauseCircleOutlined
} from '@ant-design/icons';

const { Text } = Typography;

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
  onClick
}) => {
  // Find active job for this mailbox
  const activeJob = jobs.find(
    job => job.mailbox_id === mailboxId && ['running', 'downloading', 'pending'].includes(job.status)
  );

  // Find most recent completed job
  const lastCompletedJob = jobs
    .filter(job => job.mailbox_id === mailboxId && job.status === 'completed')
    .sort((a, b) => new Date(b.completed_at || 0).getTime() - new Date(a.completed_at || 0).getTime())[0];

  // Find any failed jobs
  const failedJob = jobs.find(
    job => job.mailbox_id === mailboxId && job.status === 'failed'
  );

  const getStatusConfig = () => {
    if (activeJob) {
      if (activeJob.status === 'downloading') {
        return {
          status: 'processing' as const,
          icon: <DownloadOutlined spin />,
          color: 'purple',
          text: `Downloading${activeJob.progress ? ` ${activeJob.progress}%` : ''}`,
          tooltip: `Downloading emails${activeJob.estimated_time_remaining ? ` - ETA: ${activeJob.estimated_time_remaining}` : ''}`
        };
      }
      return {
        status: 'processing' as const,
        icon: <SyncOutlined spin />,
        color: 'blue',
        text: `Syncing${activeJob.progress ? ` ${activeJob.progress}%` : ''}`,
        tooltip: `Processing emails${activeJob.estimated_time_remaining ? ` - ETA: ${activeJob.estimated_time_remaining}` : ''}`
      };
    }

    if (failedJob) {
      return {
        status: 'error' as const,
        icon: <CloseCircleOutlined />,
        color: 'red',
        text: 'Failed',
        tooltip: 'Sync failed - click to view details'
      };
    }

    if (lastCompletedJob) {
      const timeAgo = getTimeAgo(lastCompletedJob.completed_at);
      return {
        status: 'success' as const,
        icon: <CheckCircleOutlined />,
        color: 'green',
        text: timeAgo,
        tooltip: `Last synced ${timeAgo}${lastCompletedJob.duration ? ` - took ${lastCompletedJob.duration}` : ''}`
      };
    }

    return {
      status: 'default' as const,
      icon: <ClockCircleOutlined />,
      color: 'default',
      text: 'No sync yet',
      tooltip: 'This mailbox has not been synced yet'
    };
  };

  const getTimeAgo = (timestamp?: string): string => {
    if (!timestamp) return 'never';

    const now = new Date();
    const then = new Date(timestamp);
    const diffMs = now.getTime() - then.getTime();
    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffSeconds / 60);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSeconds < 60) return 'just now';
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  const config = getStatusConfig();

  const badgeContent = (
    <div
      onClick={onClick}
      style={{
        cursor: onClick ? 'pointer' : 'default',
        display: 'inline-block'
      }}
    >
      <Badge
        status={config.status}
        text={
          <Space size={4} style={{ fontSize: size === 'small' ? 12 : 14 }}>
            {config.icon}
            <Text
              type={config.status === 'error' ? 'danger' : 'secondary'}
              style={{ fontSize: size === 'small' ? 12 : 14 }}
            >
              {config.text}
            </Text>
          </Space>
        }
      />
      {showProgress && activeJob && activeJob.progress !== undefined && (
        <div style={{ marginTop: 4, width: 200 }}>
          <Progress
            percent={activeJob.progress}
            size="small"
            status={activeJob.progress === 100 ? 'success' : 'active'}
            format={percent => `${percent}%${activeJob.estimated_time_remaining ? ` · ${activeJob.estimated_time_remaining}` : ''}`}
          />
          {activeJob.emails_per_second && activeJob.emails_per_second > 0 && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              {activeJob.emails_per_second.toFixed(1)} emails/s
            </Text>
          )}
        </div>
      )}
    </div>
  );

  return <Tooltip title={config.tooltip}>{badgeContent}</Tooltip>;
};

export default ProcessingStatusBadge;