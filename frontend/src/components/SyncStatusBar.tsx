import React from 'react';
import { Alert, Space, Typography, Progress, Button } from 'antd';
import {
  SyncOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DownloadOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';

const { Text } = Typography;

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
  onViewDetails
}) => {
  // Find active jobs for selected mailboxes
  const activeJobs = jobs.filter(
    job => selectedMailboxIds.includes(job.mailbox_id) &&
           ['running', 'downloading', 'pending'].includes(job.status)
  );

  // Find recent failed jobs for selected mailboxes
  const failedJobs = jobs.filter(
    job => selectedMailboxIds.includes(job.mailbox_id) && job.status === 'failed'
  );

  if (activeJobs.length === 0 && failedJobs.length === 0) {
    return null; // Don't show anything if no active/failed jobs
  }

  // Show most relevant job (prioritize active over failed)
  const displayJob = activeJobs[0] || failedJobs[0];

  const getAlertType = () => {
    if (displayJob.status === 'failed') return 'error';
    if (displayJob.status === 'downloading') return 'info';
    return 'info';
  };

  const getMessage = () => {
    const mailboxName = displayJob.mailbox_name || 'Unknown Mailbox';

    if (displayJob.status === 'downloading') {
      return (
        <Space size="middle" style={{ width: '100%' }}>
          <Space>
            <DownloadOutlined spin />
            <Text strong>Downloading from {mailboxName}</Text>
          </Space>
          {activeJobs.length > 1 && (
            <Text type="secondary">+{activeJobs.length - 1} more syncing</Text>
          )}
        </Space>
      );
    }

    if (displayJob.status === 'running') {
      return (
        <Space size="middle" style={{ width: '100%' }}>
          <Space>
            <SyncOutlined spin />
            <Text strong>Syncing {mailboxName}</Text>
          </Space>
          {activeJobs.length > 1 && (
            <Text type="secondary">+{activeJobs.length - 1} more syncing</Text>
          )}
        </Space>
      );
    }

    if (displayJob.status === 'pending') {
      return (
        <Space>
          <ThunderboltOutlined />
          <Text strong>Queued: {mailboxName}</Text>
        </Space>
      );
    }

    if (displayJob.status === 'failed') {
      return (
        <Space>
          <CloseCircleOutlined />
          <Text strong>Sync failed for {mailboxName}</Text>
          {failedJobs.length > 1 && (
            <Text type="secondary">+{failedJobs.length - 1} more failed</Text>
          )}
        </Space>
      );
    }

    return <Text strong>Processing {mailboxName}</Text>;
  };

  const getDescription = () => {
    if (displayJob.status === 'failed') {
      return 'Click "View Details" to see error information and retry';
    }

    const parts: React.ReactNode[] = [];

    if (displayJob.progress !== undefined) {
      parts.push(
        <div key="progress" style={{ marginTop: 8, marginBottom: 4 }}>
          <Progress
            percent={displayJob.progress}
            size="small"
            status={displayJob.progress === 100 ? 'success' : 'active'}
            strokeColor={{
              '0%': '#667eea',
              '100%': '#764ba2'
            }}
          />
        </div>
      );
    }

    const infoItems: string[] = [];

    if (displayJob.processed_records !== undefined && displayJob.total_records) {
      infoItems.push(`${displayJob.processed_records.toLocaleString()} / ${displayJob.total_records.toLocaleString()} emails`);
    }

    if (displayJob.emails_per_second && displayJob.emails_per_second > 0) {
      infoItems.push(`${displayJob.emails_per_second.toFixed(1)} emails/s`);
    }

    if (displayJob.estimated_time_remaining) {
      infoItems.push(`ETA: ${displayJob.estimated_time_remaining}`);
    }

    if (infoItems.length > 0) {
      parts.push(
        <Text key="info" type="secondary" style={{ fontSize: 12 }}>
          {infoItems.join(' • ')}
        </Text>
      );
    }

    return parts.length > 0 ? <Space direction="vertical" size={0}>{parts}</Space> : null;
  };

  return (
    <div style={{ padding: '0 16px', marginBottom: 8 }}>
      <Alert
        type={getAlertType()}
        message={getMessage()}
        description={getDescription()}
        showIcon
        closable={false}
        action={
          onViewDetails && (
            <Button size="small" onClick={onViewDetails}>
              View Details
            </Button>
          )
        }
        style={{
          borderRadius: 8,
          border: displayJob.status === 'failed' ? '1px solid #ff4d4f' : '1px solid #667eea'
        }}
      />
    </div>
  );
};

export default SyncStatusBar;