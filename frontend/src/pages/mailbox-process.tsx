import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Card,
  Space,
  Button,
  Typography,
  Form,
  Select,
  InputNumber,
  Switch,
  Descriptions,
  Alert,
  Progress,
  message,
  Steps,
  List,
  Tag,
  Badge,
  DatePicker,
  Collapse,
  Tooltip,
  Slider,
  Divider
} from "antd";
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  SettingOutlined,
  FolderOutlined,
  CalendarOutlined,
  QuestionCircleOutlined,
  CloudDownloadOutlined,
  DisconnectOutlined,
  SyncOutlined
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox } from '../services/mailboxService';
import { processingService, ProcessingJob, CachedDownload } from '../services/processingService';
import { useConnectionStatus } from '../hooks/useConnectionStatus';

const { Title, Text } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;

export const MailboxProcess: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [form] = Form.useForm();
  const [mailbox, setMailbox] = useState<Mailbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [currentJob, setCurrentJob] = useState<ProcessingJob | null>(null);
  const [jobHistory, setJobHistory] = useState<ProcessingJob[]>([]);
  const [cachedDownload, setCachedDownload] = useState<CachedDownload | null>(null);
  const [checkingCache, setCheckingCache] = useState(false);

  // Track connection status
  const { isConnected, isChecking, checkNow } = useConnectionStatus({
    reconnectInterval: 3000, // Check every 3 seconds when disconnected
    checkOnMount: true,
  });

  // Track if we need to refresh after reconnection
  const wasDisconnectedRef = useRef(false);

  useEffect(() => {
    if (id) {
      loadMailboxData();
      loadJobHistory();
    }
  }, [id]);

  // Handle reconnection - refresh data when connection is restored
  useEffect(() => {
    if (!isConnected) {
      wasDisconnectedRef.current = true;
    } else if (wasDisconnectedRef.current) {
      // Connection restored - refresh data
      console.log('[UI] Connection restored, refreshing data...');
      wasDisconnectedRef.current = false;
      loadJobHistory();
    }
  }, [isConnected]);

  // Polling effect with connection awareness
  useEffect(() => {
    let interval: NodeJS.Timeout;

    // Only poll if connected and there's an active job
    if (isConnected && currentJob) {
      // Determine polling frequency based on job status
      let pollInterval = 5000; // Default: 5 seconds

      if (['pending', 'running', 'downloading'].includes(currentJob.status)) {
        pollInterval = 2000; // Active jobs: poll every 2 seconds for quick updates
      } else if (currentJob.status === 'paused') {
        pollInterval = 10000; // Paused jobs: poll every 10 seconds (less frequent)
      } else {
        // Completed/failed/stopped/interrupted: no polling needed
        return;
      }

      interval = setInterval(() => {
        // Use silent mode for polling - don't throw errors on network issues
        loadJobHistory(true);
      }, pollInterval);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [currentJob, isConnected]);

  const loadMailboxData = async () => {
    try {
      if (!id) return;
      const data = await mailboxService.getMailbox(id);
      setMailbox(data);

      // Check for cached download if it's a Google Drive file
      if (data?.connection_config?.file_source === 'google_drive') {
        checkCachedDownload();
      }
    } catch (error) {
      console.error('Error loading mailbox:', error);
      message.error('Failed to load mailbox data');
      navigate('/mailboxes');
    } finally {
      setLoading(false);
    }
  };

  const checkCachedDownload = async () => {
    if (!id) return;
    try {
      setCheckingCache(true);
      const cache = await processingService.checkCachedDownload(id);
      setCachedDownload(cache);
    } catch (error) {
      console.error('Error checking cached download:', error);
    } finally {
      setCheckingCache(false);
    }
  };

  const handleInvalidateCache = async () => {
    if (!cachedDownload?.cache_id) return;
    try {
      await processingService.invalidateCachedDownload(cachedDownload.cache_id);
      message.success('Cache invalidated. File will be re-downloaded on next processing.');
      setCachedDownload({ cached: false, reason: 'Invalidated by user' });
    } catch (error) {
      console.error('Error invalidating cache:', error);
      message.error('Failed to invalidate cache');
    }
  };

  const loadJobHistory = useCallback(async (silent: boolean = false) => {
    try {
      if (!id) return;
      const jobs = await processingService.getProcessingJobs(silent);

      // If silent mode returned empty due to network error, don't update state
      if (silent && jobs.length === 0 && jobHistory.length > 0) {
        return;
      }

      const mailboxJobs = jobs.filter(job => job.mailbox_id === id);
      setJobHistory(mailboxJobs);

      // Find current active job (include 'downloading' status)
      const activeJob = mailboxJobs.find(job =>
        ['pending', 'running', 'downloading'].includes(job.status)
      );
      setCurrentJob(activeJob || null);
    } catch (error) {
      // Only log error if not in silent mode
      if (!silent) {
        console.error('Error loading job history:', error);
      }
    }
  }, [id, jobHistory.length]);

  const startProcessing = async (values: any) => {
    try {
      if (!id || !mailbox) return;

      setProcessing(true);

      // Build job configuration
      const jobData: any = {
        mailbox_id: id,
        job_type: values.job_type || 'extraction',
        max_emails: values.max_emails || null,  // null means process all emails
        enable_categorization: values.enable_categorization ?? true,
      };

      // Add date filter if specified
      if (values.date_range && values.date_range.length === 2) {
        jobData.start_date = values.date_range[0].format('YYYY-MM-DD');
        jobData.end_date = values.date_range[1].format('YYYY-MM-DD');
      }

      // Add parallel download options for Google Drive files
      if (mailbox?.connection_config?.file_source === 'google_drive') {
        jobData.download_first = values.download_first ?? false;
        jobData.download_threads = values.download_threads ?? 8;
        jobData.use_cached_file = true;  // Always try to use cached file
        jobData.keep_downloaded_file = true;  // Always keep for future reuse
      }

      const job = await processingService.createProcessingJob(jobData);
      setCurrentJob(job);
      message.success('Processing job started successfully');

      // Start polling for updates
      loadJobHistory();
    } catch (error) {
      console.error('Error starting processing:', error);
      message.error('Failed to start processing job');
    } finally {
      setProcessing(false);
    }
  };

  const getJobStatusIcon = (status: string) => {
    switch (status) {
      case 'pending': return <ClockCircleOutlined style={{ color: '#faad14' }} />;
      case 'running': return <ReloadOutlined spin style={{ color: '#1890ff' }} />;
      case 'downloading': return <CloudDownloadOutlined spin style={{ color: '#722ed1' }} />;
      case 'completed': return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'failed': return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
      case 'stopped': return <PauseCircleOutlined style={{ color: '#666' }} />;
      case 'interrupted': return <ExclamationCircleOutlined style={{ color: '#fa8c16' }} />;
      default: return null;
    }
  };

  const getJobStatusColor = (status: string) => {
    switch (status) {
      case 'pending': return 'warning';
      case 'running': return 'processing';
      case 'downloading': return 'purple';
      case 'completed': return 'success';
      case 'failed': return 'error';
      case 'stopped': return 'default';
      case 'interrupted': return 'warning';
      default: return 'default';
    }
  };

  // Check if job uses parallel download (has download_percent field or is downloading)
  const hasDownloadPhase = currentJob?.download_percent !== undefined && currentJob.download_percent > 0 || currentJob?.status === 'downloading';

  const getCurrentStep = () => {
    if (!currentJob) return 0;

    // 4-step flow when download phase exists
    if (hasDownloadPhase) {
      switch (currentJob.status) {
        case 'pending': return 0;
        case 'downloading': return 1;
        case 'running': return 2;
        case 'completed': return 3;
        case 'failed': return 3;
        case 'stopped': return 3;
        case 'interrupted': return 3;
        default: return 0;
      }
    }

    // Original 3-step flow (no download phase)
    switch (currentJob.status) {
      case 'pending': return 0;
      case 'running': return 1;
      case 'completed': return 2;
      case 'failed': return 2;
      case 'stopped': return 2;
      case 'interrupted': return 2;
      default: return 0;
    }
  };

  // Format processing speed - show per minute if less than 1/sec
  const formatProcessingSpeed = (emailsPerSecond: number | undefined): string => {
    if (!emailsPerSecond || emailsPerSecond === 0) return 'Calculating speed...';

    if (emailsPerSecond >= 1) {
      return `${emailsPerSecond.toFixed(1)} emails/sec`;
    } else {
      // Convert to per minute for slow processing
      const emailsPerMinute = emailsPerSecond * 60;
      return `${emailsPerMinute.toFixed(1)} emails/min`;
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <div>Loading mailbox data...</div>
      </div>
    );
  }

  if (!mailbox) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <div>Mailbox not found</div>
      </div>
    );
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      {/* Connection Status Banner */}
      {!isConnected && (
        <Alert
          message={
            <Space>
              <DisconnectOutlined />
              <span>Backend Disconnected</span>
              {isChecking && <SyncOutlined spin />}
            </Space>
          }
          description="Unable to connect to the server. Attempting to reconnect automatically..."
          type="warning"
          showIcon={false}
          action={
            <Button size="small" onClick={checkNow} loading={isChecking}>
              Retry Now
            </Button>
          }
        />
      )}

      <div>
        <Title level={2} style={{ margin: 0 }}>
          ⚡ Process Mailbox: {mailbox.name}
        </Title>
        <Text type="secondary">
          Configure and initiate email processing for this mailbox
        </Text>
      </div>

      {/* Mailbox Information */}
      <Card title={<Space><SettingOutlined />Mailbox Information</Space>}>
        <Descriptions column={2}>
          <Descriptions.Item label="Name">{mailbox.name}</Descriptions.Item>
          <Descriptions.Item label="Email">{mailbox.email_address}</Descriptions.Item>
          <Descriptions.Item label="Type">
            <Tag color="blue">{mailbox.mailbox_type.toUpperCase()}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Status">
            <Badge 
              status={mailbox.is_active ? "success" : "default"}
              text={mailbox.is_active ? "Active" : "Inactive"}
            />
          </Descriptions.Item>
          <Descriptions.Item label="Total Emails">
            {mailbox.total_emails?.toLocaleString() || '0'}
          </Descriptions.Item>
          <Descriptions.Item label="Last Sync">
            {mailbox.last_sync_at ? new Date(mailbox.last_sync_at).toLocaleString() : 'Never'}
          </Descriptions.Item>
        </Descriptions>

        {/* Show connection config for file-based types */}
        {['mbox', 'pst', 'olm'].includes(mailbox.mailbox_type) && mailbox.connection_config?.file_path && (
          <div style={{ marginTop: 16 }}>
            <Text strong>File Path:</Text>
            <div style={{ marginTop: 8 }}>
              <Space>
                <FolderOutlined />
                <Text code>{mailbox.connection_config.file_path}</Text>
              </Space>
            </div>
          </div>
        )}
      </Card>

      {/* Current Job Status */}
      {currentJob && (
        <Card title={<Space><PlayCircleOutlined />Current Processing Job</Space>}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Steps
              current={getCurrentStep()}
              status={currentJob.status === 'failed' ? 'error' : currentJob.status === 'interrupted' ? 'error' : 'process'}
              items={hasDownloadPhase || currentJob.status === 'downloading' ? [
                { title: "Queued", description: "Job created and waiting" },
                { title: "Downloading", description: "Parallel download from Google Drive" },
                { title: "Processing", description: "Extracting and analyzing emails" },
                {
                  title: currentJob.status === 'failed' ? 'Failed' :
                         currentJob.status === 'interrupted' ? 'Interrupted' :
                         currentJob.status === 'stopped' ? 'Stopped' : 'Completed',
                  description: currentJob.status === 'failed' ? 'Processing failed' :
                               currentJob.status === 'interrupted' ? 'Server restarted' :
                               currentJob.status === 'stopped' ? 'Stopped by user' : 'All emails processed'
                }
              ] : [
                { title: "Queued", description: "Job created and waiting" },
                { title: "Processing", description: "Extracting and analyzing emails" },
                {
                  title: currentJob.status === 'failed' ? 'Failed' :
                         currentJob.status === 'interrupted' ? 'Interrupted' :
                         currentJob.status === 'stopped' ? 'Stopped' : 'Completed',
                  description: currentJob.status === 'failed' ? 'Processing failed' :
                               currentJob.status === 'interrupted' ? 'Server restarted' :
                               currentJob.status === 'stopped' ? 'Stopped by user' : 'All emails processed'
                }
              ]}
            />
            
            <div style={{ marginTop: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Space>
                    {getJobStatusIcon(currentJob.status)}
                    <Text strong>Status: {currentJob.status.toUpperCase()}</Text>
                  </Space>
                  <Text type="secondary">Job Type: {currentJob.job_type}</Text>
                </div>
                
                {/* Download progress section - show when downloading from Google Drive */}
                {currentJob.status === 'downloading' && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <Space>
                        <CloudDownloadOutlined style={{ color: '#722ed1' }} />
                        <Text>Downloading from Google Drive...</Text>
                      </Space>
                      <Text strong>{currentJob.download_percent || 0}%</Text>
                    </div>
                    <Progress
                      percent={currentJob.download_percent || 0}
                      status="active"
                      strokeColor="#722ed1"
                    />
                    <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#666' }}>
                      <Text type="secondary">
                        {currentJob.download_speed_mbps ? `${currentJob.download_speed_mbps.toFixed(1)} MB/s` : 'Calculating speed...'}
                      </Text>
                      <Text type="secondary" style={{ fontStyle: 'italic' }}>
                        Using parallel download for faster processing
                      </Text>
                    </div>
                  </div>
                )}

                {/* Progress section - show when not downloading */}
                {currentJob.status !== 'downloading' && (() => {
                  const processed = currentJob.processed_records || 0;
                  const filtered = currentJob.filtered_records || 0;
                  const total = currentJob.total_records || 0;
                  const isCompleted = currentJob.status === 'completed';
                  const isFailed = currentJob.status === 'failed';

                  // Calculate progress:
                  // - Completed: always 100%
                  // - Has known total: (processed + filtered) / total
                  // - Unknown total (streaming): show indeterminate during running, 100% when done
                  let progressPercent = 0;
                  let showIndeterminate = false;

                  if (isCompleted || isFailed) {
                    progressPercent = 100;
                  } else if (total > 0) {
                    progressPercent = Math.min(100, Math.round(((processed + filtered) / total) * 100));
                  } else if (currentJob.status === 'running') {
                    // Streaming mode - no known total
                    showIndeterminate = true;
                  }

                  return (
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                        <Text>Progress</Text>
                        <Text>
                          <strong>{processed.toLocaleString()}</strong> processed
                          {filtered > 0 && (
                            <span style={{ color: '#faad14', marginLeft: 8 }}>
                              <strong>{filtered.toLocaleString()}</strong> filtered by date
                            </span>
                          )}
                          {total > 0 && (
                            <span style={{ color: '#999', marginLeft: 8 }}>
                              / {total.toLocaleString()} total
                            </span>
                          )}
                        </Text>
                      </div>
                      <Progress
                        percent={showIndeterminate ? 0 : progressPercent}
                        status={isFailed ? 'exception' : isCompleted ? 'success' : 'active'}
                        showInfo={!showIndeterminate}
                      />
                      {currentJob.status === 'running' && (
                        <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#666' }}>
                          <Text type="secondary">
                            {formatProcessingSpeed(currentJob.emails_per_second)}
                          </Text>
                          <Text type="secondary">
                            {currentJob.estimated_time_remaining ? `ETA: ${currentJob.estimated_time_remaining}` : ''}
                          </Text>
                        </div>
                      )}
                      {isCompleted && processed > 0 && (
                        <div style={{ marginTop: 8, fontSize: '12px' }}>
                          <Text type="success">
                            {processed.toLocaleString()} emails inserted to database
                          </Text>
                        </div>
                      )}
                    </div>
                  );
                })()}
                
                {currentJob.status === 'failed' && currentJob.error_log && (
                  <Alert
                    message="Processing Failed"
                    description={typeof currentJob.error_log === 'string' ? currentJob.error_log : JSON.stringify(currentJob.error_log)}
                    type="error"
                    showIcon
                  />
                )}

                {currentJob.status === 'interrupted' && (
                  <Alert
                    message="Job Interrupted"
                    description={
                      <Space direction="vertical">
                        <Text>This job was interrupted by a server restart. {currentJob.processed_records || 0} emails were already processed.</Text>
                        <Text type="secondary">You can start a new job - previously processed emails will be skipped automatically (deduplication).</Text>
                      </Space>
                    }
                    type="warning"
                    showIcon
                  />
                )}
                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text type="secondary">
                    Started: {currentJob.started_at ? new Date(currentJob.started_at).toLocaleString() : 'Not started'}
                  </Text>
                  {currentJob.completed_at && (
                    <Text type="secondary">
                      Completed: {new Date(currentJob.completed_at).toLocaleString()}
                    </Text>
                  )}
                </div>
              </Space>
            </div>
          </Space>
        </Card>
      )}

      {/* Processing Configuration */}
      {!currentJob || ['completed', 'failed', 'stopped', 'interrupted'].includes(currentJob.status) ? (
        <Card title={<Space><PlayCircleOutlined />Start New Processing Job</Space>}>
          <Form
            form={form}
            layout="vertical"
            onFinish={startProcessing}
            initialValues={{
              job_type: 'extraction',
              max_emails: undefined,
              enable_categorization: true,
              download_first: true,  // Default to download mode (3-5x faster for large files)
              download_threads: 4  // Capped at 4 for memory efficiency with large files
            }}
          >
            <Form.Item
              name="job_type"
              label="Processing Type"
              rules={[{ required: true, message: 'Please select processing type' }]}
            >
              <Select placeholder="Select processing type">
                <Option value="extraction">Email Extraction (with Auto-Tagging)</Option>
              </Select>
            </Form.Item>

            <Form.Item
              name="max_emails"
              label={
                <Space>
                  Email Limit
                  <Tooltip title="Maximum number of emails to process. Leave empty to process all emails in the mailbox.">
                    <QuestionCircleOutlined style={{ color: '#999' }} />
                  </Tooltip>
                </Space>
              }
            >
              <InputNumber min={1} max={100000} placeholder="All emails" style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item
              name="date_range"
              label={
                <Space>
                  <CalendarOutlined />
                  Date Range Filter
                  <Tooltip title="Only process emails sent within this date range. Leave empty to process all emails regardless of date.">
                    <QuestionCircleOutlined style={{ color: '#999' }} />
                  </Tooltip>
                </Space>
              }
            >
              <RangePicker
                style={{ width: '100%' }}
                placeholder={['Start Date', 'End Date']}
                format="YYYY-MM-DD"
              />
            </Form.Item>

            {/* Google Drive Download Options - shown prominently for Google Drive files */}
            {mailbox?.connection_config?.file_source === 'google_drive' && (
              <>
                <Divider orientation="left">
                  <Space>
                    <CloudDownloadOutlined style={{ color: '#722ed1' }} />
                    <Text strong>Google Drive Processing Mode</Text>
                  </Space>
                </Divider>

                <Form.Item
                  name="download_first"
                  label={
                    <Space>
                      Download Before Processing
                      <Tag color="green">Recommended</Tag>
                      <Tooltip title="Download the entire file first using parallel threads, then process locally. Typically 3-5x faster than streaming for large files.">
                        <QuestionCircleOutlined style={{ color: '#999' }} />
                      </Tooltip>
                    </Space>
                  }
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>

                {/* Show cache info and download options only when download_first is enabled */}
                <Form.Item
                  noStyle
                  shouldUpdate={(prevValues, currentValues) =>
                    prevValues.download_first !== currentValues.download_first
                  }
                >
                  {({ getFieldValue }) =>
                    getFieldValue('download_first') ? (
                      <>
                        {/* Show cached download info if available */}
                        {checkingCache ? (
                          <Alert
                            message="Checking for cached download..."
                            type="info"
                            showIcon
                            icon={<SyncOutlined spin />}
                            style={{ marginBottom: 16 }}
                          />
                        ) : cachedDownload?.cached ? (
                          <Alert
                            message="Using Cached File (No Download Needed)"
                            description={
                              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                                <Text>
                                  <strong>{cachedDownload.file_name}</strong> ({cachedDownload.file_size_formatted})
                                </Text>
                                <Text type="secondary">
                                  Downloaded {cachedDownload.age_formatted} •
                                  Last used: {cachedDownload.last_used_at ? new Date(cachedDownload.last_used_at).toLocaleString() : 'Never'}
                                </Text>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  Path: {cachedDownload.storage_path}
                                </Text>
                                <Space style={{ marginTop: 8 }}>
                                  <Button
                                    size="small"
                                    danger
                                    onClick={handleInvalidateCache}
                                  >
                                    Clear Cache (Force Re-download)
                                  </Button>
                                  <Button
                                    size="small"
                                    onClick={checkCachedDownload}
                                  >
                                    Refresh
                                  </Button>
                                </Space>
                              </Space>
                            }
                            type="success"
                            showIcon
                            icon={<CheckCircleOutlined />}
                            style={{ marginBottom: 16 }}
                          />
                        ) : (
                          /* Show download threads only when NO cache available (actual download will happen) */
                          <Form.Item
                            name="download_threads"
                            label={
                              <Space>
                                Download Threads
                                <Tooltip title="Number of parallel download threads. Limited to 4 for memory efficiency when downloading large files (50GB+). Each thread streams directly to disk.">
                                  <QuestionCircleOutlined style={{ color: '#999' }} />
                                </Tooltip>
                              </Space>
                            }
                          >
                            <Slider
                              min={1}
                              max={4}
                              marks={{
                                1: '1',
                                2: '2',
                                3: '3',
                                4: '4'
                              }}
                              tooltip={{ formatter: (value) => `${value} threads` }}
                            />
                          </Form.Item>
                        )}
                      </>
                    ) : (
                      <Alert
                        message="Streaming Mode"
                        description="Emails will be processed directly from Google Drive without downloading the file first. This is slower but uses less disk space."
                        type="info"
                        showIcon
                        style={{ marginBottom: 16 }}
                      />
                    )
                  }
                </Form.Item>
              </>
            )}

            <Collapse
              ghost
              items={[{
                key: 'advanced',
                label: (
                  <Space>
                    <SettingOutlined />
                    <Text>Advanced Options</Text>
                  </Space>
                ),
                children: (
                  <Form.Item
                    name="enable_categorization"
                    label={
                      <Space>
                        Enable Auto-Tagging
                        <Tooltip title="Automatically categorize emails with tags like Newsletter, Receipt, Meeting, etc.">
                          <QuestionCircleOutlined style={{ color: '#999' }} />
                        </Tooltip>
                      </Space>
                    }
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                )
              }]}
            />

            <Alert
              message="Processing Information"
              description="This will start processing emails from the configured source. You can optionally filter by date range and limit the number of emails processed."
              type="info"
              style={{ marginBottom: 16 }}
            />

            <Form.Item>
              <Space>
                <Button 
                  type="primary" 
                  htmlType="submit" 
                  loading={processing}
                  icon={<PlayCircleOutlined />}
                  disabled={!mailbox.is_active}
                >
                  Start Processing
                </Button>
                <Button onClick={() => navigate('/mailboxes')}>
                  Back to Mailboxes
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Card>
      ) : (
        <Card title={<Space><PauseCircleOutlined />Processing In Progress</Space>}>
          <Alert
            message="Processing job is currently running"
            description="Please wait for the current job to complete before starting a new one."
            type="warning"
            showIcon
          />
          <div style={{ marginTop: 16 }}>
            <Button onClick={() => navigate('/mailboxes')}>
              Back to Mailboxes
            </Button>
          </div>
        </Card>
      )}

      {/* Job History */}
      {jobHistory.length > 0 && (
        <Card title={<Space><ClockCircleOutlined />Recent Processing Jobs</Space>}>
          <List
            dataSource={jobHistory.slice(0, 5)}
            renderItem={(job) => (
              <List.Item>
                <List.Item.Meta
                  avatar={getJobStatusIcon(job.status)}
                  title={
                    <Space>
                      <Text strong>{job.job_type}</Text>
                      <Tag color={getJobStatusColor(job.status)}>{job.status}</Tag>
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size="small">
                      <Text type="secondary">
                        Created: {new Date(job.created_at).toLocaleString()}
                      </Text>
                      {job.total_records && (
                        <Text type="secondary">
                          Processed: {job.processed_records || 0} / {job.total_records} emails
                        </Text>
                      )}
                      {job.failed_records && job.failed_records > 0 && (
                        <Text type="danger">
                          Failed: {job.failed_records} emails
                        </Text>
                      )}
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        </Card>
      )}
    </Space>
  );
};