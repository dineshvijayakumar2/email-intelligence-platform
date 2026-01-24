import React, { useState, useEffect, useRef } from "react";
import {
  Card,
  Table,
  Space,
  Typography,
  Tag,
  Progress,
  Button,
  Tooltip,
  Modal,
  Descriptions,
  List,
  Alert,
  Popconfirm,
  Popover,
  message
} from "antd";
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  EyeOutlined,
  ReloadOutlined,
  DeleteOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
  CalendarOutlined,
  CloudDownloadOutlined
} from "@ant-design/icons";
import { processingService, ProcessingJob } from '../services/processingService';
import { ErrorDisplay } from '../components/ErrorDisplay';

const { Text } = Typography;

const getStatusIcon = (status: string) => {
  const icons = {
    pending: <ClockCircleOutlined />,
    downloading: <CloudDownloadOutlined spin />,
    running: <PlayCircleOutlined />,
    completed: <CheckCircleOutlined />,
    failed: <ExclamationCircleOutlined />,
    paused: <PauseCircleOutlined />,
    stopped: <StopOutlined />
  };
  return icons[status as keyof typeof icons] || <ClockCircleOutlined />;
};

// Format processing speed - show per minute if less than 1/sec
const formatProcessingSpeed = (emailsPerSecond: number | undefined): string => {
  if (!emailsPerSecond || emailsPerSecond === 0) return '';

  if (emailsPerSecond >= 1) {
    return `${emailsPerSecond.toFixed(1)}/s`;
  } else {
    // Convert to per minute for slow processing
    const emailsPerMinute = emailsPerSecond * 60;
    return `${emailsPerMinute.toFixed(1)}/min`;
  }
};

export const ProcessingJobs: React.FC = () => {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedJob, setSelectedJob] = useState<ProcessingJob | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [reprocessingJobs, setReprocessingJobs] = useState<Set<string>>(new Set());

  // Track if component is mounted to avoid state updates after unmount
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    loadJobs(true); // Show loading on initial load

    // Auto-refresh every 5 seconds (without loading spinner)
    const interval = setInterval(() => {
      if (isMountedRef.current) {
        loadJobs(false);
      }
    }, 5000);

    return () => {
      isMountedRef.current = false;
      clearInterval(interval);
    };
  }, []);

  const loadJobs = async (showLoading = false) => {
    try {
      if (showLoading && isMountedRef.current) {
        setLoading(true);
      }
      const jobsData = await processingService.getProcessingJobs();
      // Only update state if component is still mounted
      if (isMountedRef.current) {
        setJobs(jobsData);
      }
    } catch (error) {
      // Only show error if component is still mounted and it's not a cancelled request
      if (isMountedRef.current) {
        console.error('Error loading jobs:', error);
        message.error('Failed to load processing jobs');
      }
    } finally {
      if (showLoading && isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  const showJobDetails = (job: ProcessingJob) => {
    setSelectedJob(job);
    setModalVisible(true);
  };

  const handleJobAction = async (action: 'pause' | 'resume' | 'stop', jobId: string) => {
    try {
      await processingService.controlJob(jobId, action);
      message.success(`${action.charAt(0).toUpperCase() + action.slice(1)} job ${jobId}`);
      loadJobs(); // Reload jobs to show updated status
    } catch (error) {
      message.error(`Failed to ${action} job`);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      await processingService.deleteJob(jobId);
      message.success(`Deleted job ${jobId}`);
      loadJobs(); // Reload jobs
    } catch (error) {
      message.error('Failed to delete job');
    }
  };

  const handleReprocessJob = async (jobId: string) => {
    try {
      console.log(`Starting reprocessing for job ${jobId}`);

      // Mark this job as being reprocessed
      setReprocessingJobs(prev => new Set(prev).add(jobId));

      const result = await processingService.reprocessJob(jobId);
      console.log('Reprocessing job created:', result);

      message.success(`Reprocessing started! Watch for the new "Reprocessing" job in the list.`);

      // Reload jobs to show the new reprocessing job
      await loadJobs();

      // Remove from reprocessing set
      setReprocessingJobs(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
    } catch (error) {
      console.error('Failed to start reprocessing:', error);
      message.error(`Failed to start reprocessing: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setReprocessingJobs(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
    }
  };

  const refreshJobs = () => {
    loadJobs(true); // Show loading when manually refreshing
    message.info('Refreshing job status...');
  };

  const columns = [
    {
      title: 'Job ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
      render: (id: string) => (
        <Text code style={{ fontSize: 11 }}>{id.substring(0, 8)}</Text>
      ),
    },
    {
      title: 'Job Type',
      dataIndex: 'job_type',
      key: 'job_type',
      render: (type: string) => (
        <Space>
          <Tag color="blue">{processingService.getJobTypeLabel(type)}</Tag>
        </Space>
      ),
    },
    {
      title: 'Mailbox',
      dataIndex: 'mailbox_name',
      key: 'mailbox_name',
      render: (name: string) => <Text>{name}</Text>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string, record: ProcessingJob) => {
        const tag = (
          <Tag color={processingService.getStatusColor(status)} icon={getStatusIcon(status)}>
            {status.toUpperCase()}
          </Tag>
        );

        // Show error details in popover for failed jobs
        if (status === 'failed' && record.error_log && Array.isArray(record.error_log) && record.error_log.length > 0) {
          const errors = record.error_log as string[];
          const errorContent = (
            <div style={{ maxWidth: 400 }}>
              <Text strong>Error Details:</Text>
              <div style={{ marginTop: 8, maxHeight: 300, overflowY: 'auto' }}>
                {errors.map((error: string, index: number) => (
                  <Alert
                    key={index}
                    description={error}
                    type="error"
                    showIcon
                    style={{ marginBottom: index < errors.length - 1 ? 8 : 0 }}
                  />
                ))}
              </div>
            </div>
          );

          return (
            <Popover content={errorContent} title="Job Failed" trigger="hover">
              <span style={{ cursor: 'pointer' }}>{tag}</span>
            </Popover>
          );
        }

        return tag;
      },
    },
    {
      title: 'Progress',
      key: 'progress',
      render: (_: any, record: ProcessingJob) => {
        const { status, processed_records, total_records, failed_records, filtered_records, filter_start_date, filter_end_date } = record;
        const progress = total_records > 0 ? Math.round((processed_records / total_records) * 100) : 0;
        const hasDateFilter = filter_start_date || filter_end_date;

        // Show download progress for downloading status
        if (status === 'downloading') {
          return (
            <Space direction="vertical" size="small" style={{ width: 250 }}>
              <Progress
                percent={record.download_percent || 0}
                size="small"
                status="active"
                strokeColor="#722ed1"
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                <Text type="secondary">
                  <CloudDownloadOutlined style={{ marginRight: 4, color: '#722ed1' }} />
                  Downloading...
                </Text>
                <Text strong style={{ color: '#722ed1' }}>
                  {record.download_percent || 0}%
                </Text>
              </div>
              {record.download_speed_mbps && (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  Speed: {record.download_speed_mbps.toFixed(1)} MB/s
                </Text>
              )}
            </Space>
          );
        }

        // Calculate effective progress
        const effectiveTotal = total_records > 0 ? total_records : (processed_records + (filtered_records || 0));
        const effectiveProgress = status === 'completed' ? 100 :
          (effectiveTotal > 0 ? Math.min(100, Math.round(((processed_records + (filtered_records || 0)) / effectiveTotal) * 100)) : 0);
        const isStreaming = total_records === 0 && status === 'running';

        return (
          <Space direction="vertical" size="small" style={{ width: 250 }}>
            <Progress
              percent={effectiveProgress}
              size="small"
              status={status === 'failed' ? 'exception' : status === 'completed' ? 'success' : 'active'}
              showInfo={!isStreaming}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {processed_records.toLocaleString()} processed
              {total_records > 0 && (
                <span> / {total_records.toLocaleString()}</span>
              )}
              {failed_records > 0 && (
                <span style={{ color: '#ff4d4f' }}> ({failed_records} failed)</span>
              )}
              {(filtered_records ?? 0) > 0 && (
                <span style={{ color: '#faad14' }}> ({filtered_records!.toLocaleString()} filtered)</span>
              )}
            </Text>
            {hasDateFilter && (
              <Tooltip title={`Date filter: ${filter_start_date || 'any'} to ${filter_end_date || 'any'}`}>
                <Tag icon={<CalendarOutlined />} color="blue" style={{ fontSize: 10 }}>
                  Date Filter
                </Tag>
              </Tooltip>
            )}
            {status === 'running' && (record.emails_per_second || record.estimated_time_remaining) && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#999' }}>
                <span>{formatProcessingSpeed(record.emails_per_second)}</span>
                <span>{record.estimated_time_remaining ? `ETA: ${record.estimated_time_remaining}` : ''}</span>
              </div>
            )}
          </Space>
        );
      },
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => {
        if (!date) return '-';
        return (
          <Space direction="vertical" size="small">
            <Text>{new Date(date).toLocaleDateString()}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {new Date(date).toLocaleTimeString()}
            </Text>
          </Space>
        );
      },
    },
    {
      title: 'Started',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (date: string) => {
        if (!date) return 'Not started';
        return (
          <Space direction="vertical" size="small">
            <Text>{new Date(date).toLocaleDateString()}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {new Date(date).toLocaleTimeString()}
            </Text>
          </Space>
        );
      },
    },
    {
      title: 'Duration',
      key: 'duration',
      render: (_: any, record: ProcessingJob) => {
        const { started_at, completed_at, status } = record;
        if (!started_at) return '-';

        // For terminal states (completed/failed/stopped), require completed_at
        // Otherwise old jobs would show ever-increasing duration
        const terminalStates = ['completed', 'failed', 'stopped'];
        if (terminalStates.includes(status) && !completed_at) {
          return <Text type="secondary">-</Text>;
        }

        const start = new Date(started_at);
        // Only use current time for running jobs; otherwise use completed_at
        const end = completed_at ? new Date(completed_at) : (status === 'running' ? new Date() : null);

        if (!end) return <Text type="secondary">-</Text>;

        const duration = Math.round((end.getTime() - start.getTime()) / 1000);

        const minutes = Math.floor(duration / 60);
        const seconds = duration % 60;

        return (
          <Text type="secondary">
            {minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`}
            {status === 'running' && ' (ongoing)'}
            {status === 'stopped' && ' (stopped)'}
          </Text>
        );
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, record: ProcessingJob) => (
        <Space size="small">
          <Tooltip title="View Details">
            <Button
              type="text"
              icon={<EyeOutlined />}
              onClick={() => showJobDetails(record)}
            />
          </Tooltip>
          
          {record.status === 'running' && (
            <Tooltip title="Pause Job">
              <Button
                type="text"
                icon={<PauseCircleOutlined />}
                onClick={() => handleJobAction('pause', record.id)}
              />
            </Tooltip>
          )}
          
          {record.status === 'paused' && (
            <Tooltip title="Resume Job">
              <Button
                type="text"
                icon={<PlayCircleOutlined />}
                onClick={() => handleJobAction('resume', record.id)}
              />
            </Tooltip>
          )}
          
          {(record.status === 'running' || record.status === 'paused') && (
            <Tooltip title="Stop Job">
              <Button
                type="text"
                danger
                icon={<StopOutlined />}
                onClick={() => handleJobAction('stop', record.id)}
              />
            </Tooltip>
          )}
          
          {record.status === 'completed' && record.job_type.toLowerCase().includes('extraction') && (
            <Tooltip title={reprocessingJobs.has(record.id) ? "Starting reprocessing..." : "Reprocess with Categorization"}>
              <Button
                type="text"
                icon={<SyncOutlined spin={reprocessingJobs.has(record.id)} />}
                onClick={() => handleReprocessJob(record.id)}
                disabled={reprocessingJobs.has(record.id)}
                loading={reprocessingJobs.has(record.id)}
              />
            </Tooltip>
          )}

          {(record.status === 'completed' || record.status === 'failed') && (
            <Popconfirm
              title="Are you sure you want to delete this job?"
              onConfirm={() => handleDeleteJob(record.id)}
              okText="Yes"
              cancelText="No"
            >
              <Tooltip title="Delete Job">
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const runningJobs = jobs.filter(job => job.status === 'running');

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Header */}
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Text type="secondary">
            Monitor extraction and processing job status
          </Text>
        </div>
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          onClick={refreshJobs}
          loading={loading}
          className="glass-button-primary"
        >
          Refresh
        </Button>
      </div>

      {/* Active Jobs Alert */}
      {runningJobs.length > 0 && (
        <div className="fade-in-up stagger-1" style={{ marginBottom: 24 }}>
          <Alert
            message="Active Jobs Running"
            description={
              `${runningJobs.length} job(s) currently processing.
              Avoid starting new extractions for the same mailboxes.`
            }
            type="info"
            showIcon
            style={{ borderRadius: 12 }}
          />
        </div>
      )}

      {/* Table */}
      <div className="glass-table-container fade-in-up stagger-2">
        <Table
          dataSource={jobs}
          columns={columns}
          loading={loading}
          rowKey="id"
          size="small"
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total, range) =>
              `${range[0]}-${range[1]} of ${total} jobs`,
          }}
          rowClassName={(record) => {
            if (record.status === 'failed') return 'error-row';
            if (record.status === 'running') return 'running-row';
            return '';
          }}
        />
      </div>

      {/* Job Details Modal */}
      <Modal
        title={
          <Space>
            ⚙️ Job Details
            {selectedJob && (
              <Tag color={processingService.getStatusColor(selectedJob.status)} icon={getStatusIcon(selectedJob.status)}>
                {selectedJob.status.toUpperCase()}
              </Tag>
            )}
          </Space>
        }
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setModalVisible(false)}>
            Close
          </Button>
        ]}
        width={700}
      >
        {selectedJob && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Descriptions title="Job Information" bordered size="small">
              <Descriptions.Item label="Job ID" span={2}>
                <Text code>{selectedJob.id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Status">
                <Tag color={processingService.getStatusColor(selectedJob.status)} icon={getStatusIcon(selectedJob.status)}>
                  {selectedJob.status.toUpperCase()}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Job Type" span={2}>
                {processingService.getJobTypeLabel(selectedJob.job_type)}
              </Descriptions.Item>
              <Descriptions.Item label="Mailbox">
                {selectedJob.mailbox_name}
              </Descriptions.Item>
              <Descriptions.Item label="Total Records" span={2}>
                {selectedJob.total_records.toLocaleString()}
              </Descriptions.Item>
              <Descriptions.Item label="Processed">
                {selectedJob.processed_records.toLocaleString()}
              </Descriptions.Item>
              <Descriptions.Item label="Failed Records" span={2}>
                <Text type={selectedJob.failed_records > 0 ? 'danger' : 'secondary'}>
                  {selectedJob.failed_records.toLocaleString()}
                </Text>
              </Descriptions.Item>
              {(selectedJob.filtered_records !== undefined && selectedJob.filtered_records > 0) && (
                <Descriptions.Item label="Filtered Records" span={3}>
                  <Text type="warning">
                    {selectedJob.filtered_records.toLocaleString()} (excluded by date filter)
                  </Text>
                </Descriptions.Item>
              )}
              {(selectedJob.filter_start_date || selectedJob.filter_end_date) && (
                <Descriptions.Item label="Date Filter" span={3}>
                  <Tag icon={<CalendarOutlined />} color="blue">
                    {selectedJob.filter_start_date || 'Any'} → {selectedJob.filter_end_date || 'Any'}
                  </Tag>
                </Descriptions.Item>
              )}
              <Descriptions.Item label="Progress">
                <Progress 
                  percent={Math.round((selectedJob.processed_records / selectedJob.total_records) * 100)} 
                  status={selectedJob.status === 'failed' ? 'exception' : selectedJob.status === 'completed' ? 'success' : 'active'}
                />
              </Descriptions.Item>
              <Descriptions.Item label="Started At" span={2}>
                {selectedJob.started_at ? new Date(selectedJob.started_at).toLocaleString() : 'Not started'}
              </Descriptions.Item>
              <Descriptions.Item label="Completed At">
                {selectedJob.completed_at ? new Date(selectedJob.completed_at).toLocaleString() : 'Not completed'}
              </Descriptions.Item>
            </Descriptions>

            {selectedJob.error_log && Array.isArray(selectedJob.error_log) && selectedJob.error_log.length > 0 && (
              <Card title="Error Log" size="small">
                <List
                  size="small"
                  dataSource={selectedJob.error_log as string[]}
                  renderItem={(error: string, index: number) => (
                    <List.Item>
                      <Text type="danger">
                        {index + 1}. {error}
                      </Text>
                    </List.Item>
                  )}
                />
              </Card>
            )}

            {/* Stage 2: Enhanced Error Display with detailed breakdown and retry */}
            {selectedJob.failed_records > 0 && (
              <ErrorDisplay
                jobId={selectedJob.id}
                failedCount={selectedJob.failed_records}
                onRetryComplete={() => loadJobs(false)}
              />
            )}
          </Space>
        )}
      </Modal>

      <style>{`
        .error-row {
          background-color: #fff1f0;
        }
        .running-row {
          background-color: #f0f9ff;
        }
      `}</style>
    </div>
  );
};