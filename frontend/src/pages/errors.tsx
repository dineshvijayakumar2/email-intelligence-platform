/**
 * Errors Page - Stage 2 Error Handling
 *
 * Dedicated page to view all processing errors across all jobs
 * with filtering, search, and retry capabilities.
 *
 * Two views:
 * 1. All Errors - From job_errors table (download, extraction, processing, etc.)
 * 2. Failed Emails - From emails table (email-specific failures with retry)
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Typography,
  Select,
  Row,
  Col,
  Statistic,
  Spin,
  Empty,
  message,
  Modal,
  Tooltip,
  Breadcrumb,
  Tabs,
  Collapse,
} from 'antd';
import {
  ExclamationCircleOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  HomeOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  CloudDownloadOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  TagsOutlined,
  SyncOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import {
  errorService,
  ErrorSummary,
  FailedEmail,
  JobError,
  JobErrorsSummary,
} from '../services/errorService';
// @ts-ignore
import config from '../config.js';

const { Text, Paragraph } = Typography;
const { Option } = Select;
const { TabPane } = Tabs;
const { Panel } = Collapse;

interface ProcessingJob {
  id: string;
  mailbox_id: string;
  status: string;
  total_records: number;
  processed_records: number;
  failed_records: number;
  created_at: string;
  mailbox_name?: string;
}

interface MailboxOption {
  id: string;
  name: string;
}

// Phase icon mapping
const phaseIcons: Record<string, React.ReactNode> = {
  download: <CloudDownloadOutlined />,
  extraction: <FileTextOutlined />,
  normalization: <SyncOutlined />,
  tagging: <TagsOutlined />,
  database: <DatabaseOutlined />,
  categorization: <RobotOutlined />,
};

const ErrorsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const jobIdFromUrl = searchParams.get('jobId');
  const tabFromUrl = searchParams.get('tab') || 'all';

  // State
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [mailboxes, setMailboxes] = useState<MailboxOption[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(jobIdFromUrl);
  const [selectedMailboxId, setSelectedMailboxId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>(tabFromUrl);

  // Job Errors state (from job_errors table)
  const [jobErrors, setJobErrors] = useState<JobError[]>([]);
  const [jobErrorsSummary, setJobErrorsSummary] = useState<JobErrorsSummary | null>(null);
  const [totalJobErrors, setTotalJobErrors] = useState(0);
  const [hasMoreJobErrors, setHasMoreJobErrors] = useState(false);
  const [selectedJobError, setSelectedJobError] = useState<JobError | null>(null);
  const [phaseFilter, setPhaseFilter] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  // Failed Emails state (from emails table - legacy)
  const [errors, setErrors] = useState<FailedEmail[]>([]);
  const [errorSummary, setErrorSummary] = useState<ErrorSummary | null>(null);
  const [totalErrors, setTotalErrors] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [selectedError, setSelectedError] = useState<FailedEmail | null>(null);

  // Load all jobs (any job may have errors logged, even if not marked as failed)
  const loadJobsWithErrors = useCallback(async () => {
    console.log('[ErrorsPage] Loading all jobs...');
    setLoading(true);
    try {
      const url = `${config.apiBaseUrl}/processing-jobs`;
      console.log('[ErrorsPage] Fetching from:', url);
      const response = await fetch(url);
      const allJobs: ProcessingJob[] = await response.json();
      console.log('[ErrorsPage] Got jobs:', allJobs.length);

      // Show all jobs with valid mailbox_id (any job may have errors logged)
      const validJobs = allJobs.filter(j => j.mailbox_id);
      console.log('[ErrorsPage] Valid jobs:', validJobs.length);
      console.log('[ErrorsPage] Valid jobs details:', validJobs.map(j => ({ id: j.id, mailbox_id: j.mailbox_id, mailbox_name: j.mailbox_name, failed: j.failed_records })));
      setJobs(validJobs);

      // Get unique mailboxes from these jobs
      const mailboxIds = [...new Set(validJobs.map(j => j.mailbox_id))];
      const mailboxList: MailboxOption[] = [];
      for (const mbId of mailboxIds) {
        if (!mbId) continue;  // Skip null/undefined mailbox_id
        const job = validJobs.find(j => j.mailbox_id === mbId);
        // Include all mailboxes with names (even 'Unknown Mailbox' for now to debug)
        if (job?.mailbox_name) {
          mailboxList.push({ id: mbId, name: job.mailbox_name });
        }
      }
      console.log('[ErrorsPage] Mailboxes:', mailboxList);
      setMailboxes(mailboxList);
    } catch (error) {
      console.error('[ErrorsPage] Failed to load jobs:', error);
      message.error('Failed to load processing jobs');
    } finally {
      setLoading(false);
    }
  }, []);

  // Load job errors from job_errors table (ALL error types)
  const loadJobErrors = useCallback(async (jobId: string, phase?: string | null, errorType?: string | null) => {
    setLoading(true);
    try {
      const [errorsData, summaryData] = await Promise.all([
        errorService.getJobErrors(jobId, {
          phase: phase || undefined,
          error_type: errorType || undefined,
          limit: 100,
          offset: 0,
        }),
        errorService.getJobErrorsSummary(jobId),
      ]);

      setJobErrors(errorsData.errors || []);
      setTotalJobErrors(errorsData.total_errors || 0);
      setHasMoreJobErrors(errorsData.has_more || false);
      setJobErrorsSummary(summaryData);
    } catch (error: any) {
      console.error('Failed to load job errors:', error);
      // Reset state on error
      setJobErrors([]);
      setTotalJobErrors(0);
      setHasMoreJobErrors(false);
      setJobErrorsSummary(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load failed emails from emails table (legacy)
  const loadErrors = useCallback(async (jobId: string) => {
    setLoading(true);
    try {
      const [errorsData, summaryData] = await Promise.all([
        errorService.getProcessingErrors(jobId, 100, 0),
        errorService.getErrorSummary(jobId),
      ]);

      setErrors(errorsData.emails || []);
      setTotalErrors(errorsData.total_failed || 0);
      setHasMore(errorsData.has_more || false);
      setErrorSummary(summaryData);
    } catch (error: any) {
      console.error('Failed to load errors:', error);
      // Handle specific error cases
      if (error?.message?.includes('no associated mailbox') || error?.message?.includes('400')) {
        message.warning('This job has no associated mailbox - cannot load errors');
        setErrors([]);
        setTotalErrors(0);
        setHasMore(false);
        setErrorSummary(null);
      } else {
        message.error('Failed to load error details');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load - run once on mount
  useEffect(() => {
    console.log('[ErrorsPage] Component mounted, loading jobs...');
    loadJobsWithErrors();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-select job from URL when jobs are loaded
  useEffect(() => {
    if (jobIdFromUrl && jobs.length > 0 && jobs.some(j => j.id === jobIdFromUrl)) {
      console.log('[ErrorsPage] Auto-selecting job from URL:', jobIdFromUrl);
      setSelectedJobId(jobIdFromUrl);
    }
  }, [jobIdFromUrl, jobs]);

  // Load errors when job selected
  useEffect(() => {
    if (selectedJobId) {
      // Load both job errors and failed emails
      loadJobErrors(selectedJobId, phaseFilter, typeFilter);
      loadErrors(selectedJobId);
      // Update URL
      setSearchParams({ jobId: selectedJobId, tab: activeTab });
    } else {
      // Reset both states
      setJobErrors([]);
      setJobErrorsSummary(null);
      setTotalJobErrors(0);
      setErrors([]);
      setErrorSummary(null);
      setTotalErrors(0);
      setSearchParams({});
    }
  }, [selectedJobId, loadJobErrors, loadErrors, setSearchParams, phaseFilter, typeFilter, activeTab]);

  // Handle job selection
  const handleJobSelect = (jobId: string) => {
    setSelectedJobId(jobId);
    setSelectedMailboxId(null);
  };

  // Handle mailbox filter
  const handleMailboxFilter = (mailboxId: string | null) => {
    setSelectedMailboxId(mailboxId);
    if (mailboxId) {
      // Find first job with errors for this mailbox
      const job = jobs.find(j => j.mailbox_id === mailboxId && j.failed_records > 0);
      if (job) {
        setSelectedJobId(job.id);
      }
    }
  };

  // Handle tab change
  const handleTabChange = (key: string) => {
    setActiveTab(key);
    if (selectedJobId) {
      setSearchParams({ jobId: selectedJobId, tab: key });
    }
  };

  // Handle phase filter change
  const handlePhaseFilterChange = (phase: string | null) => {
    setPhaseFilter(phase);
    if (selectedJobId) {
      loadJobErrors(selectedJobId, phase, typeFilter);
    }
  };

  // Handle type filter change
  const handleTypeFilterChange = (errorType: string | null) => {
    setTypeFilter(errorType);
    if (selectedJobId) {
      loadJobErrors(selectedJobId, phaseFilter, errorType);
    }
  };

  // Handle resolve job error
  const handleResolveJobError = async (errorId: string) => {
    if (!selectedJobId) return;
    try {
      await errorService.resolveJobError(selectedJobId, errorId, 'manual_fix');
      message.success('Error marked as resolved');
      loadJobErrors(selectedJobId, phaseFilter, typeFilter);
    } catch (error) {
      console.error('Failed to resolve error:', error);
      message.error('Failed to resolve error');
    }
  };

  // Handle retry
  const handleRetry = async () => {
    if (!selectedJobId) return;

    setRetrying(true);
    try {
      const result = await errorService.retryFailedEmails(selectedJobId, 3);
      message.success(result.message);

      if (result.emails_reset > 0) {
        // Refresh data
        await loadErrors(selectedJobId);
        await loadJobsWithErrors();
      }
    } catch (error) {
      console.error('Failed to retry emails:', error);
      message.error('Failed to retry failed emails');
    } finally {
      setRetrying(false);
    }
  };

  // Load more job errors
  const loadMoreJobErrors = async () => {
    if (!selectedJobId) return;

    setLoading(true);
    try {
      const moreErrors = await errorService.getJobErrors(selectedJobId, {
        phase: phaseFilter || undefined,
        error_type: typeFilter || undefined,
        limit: 100,
        offset: jobErrors.length,
      });
      setJobErrors([...jobErrors, ...moreErrors.errors]);
      setHasMoreJobErrors(moreErrors.has_more);
    } catch (error) {
      console.error('Failed to load more job errors:', error);
    } finally {
      setLoading(false);
    }
  };

  // Load more failed emails
  const loadMore = async () => {
    if (!selectedJobId) return;

    setLoading(true);
    try {
      const moreErrors = await errorService.getProcessingErrors(
        selectedJobId,
        100,
        errors.length
      );
      setErrors([...errors, ...moreErrors.emails]);
      setHasMore(moreErrors.has_more);
    } catch (error) {
      console.error('Failed to load more errors:', error);
    } finally {
      setLoading(false);
    }
  };

  // Job Errors table columns (from job_errors table)
  const jobErrorsColumns = [
    {
      title: 'Phase',
      dataIndex: 'error_phase',
      key: 'error_phase',
      width: '10%',
      render: (phase: string) => (
        <Tag color={errorService.getErrorPhaseColor(phase)} icon={phaseIcons[phase]}>
          {errorService.getErrorPhaseLabel(phase)}
        </Tag>
      ),
    },
    {
      title: 'Severity',
      dataIndex: 'error_severity',
      key: 'error_severity',
      width: '8%',
      render: (severity: string) => (
        <Tag color={errorService.getErrorSeverityColor(severity)}>
          {errorService.getErrorSeverityLabel(severity)}
        </Tag>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'error_type',
      key: 'error_type',
      width: '12%',
      render: (errorType: string) => (
        <Tag color={errorService.getErrorTypeColor(errorType)}>
          {errorService.getErrorTypeLabel(errorType)}
        </Tag>
      ),
    },
    {
      title: 'Message',
      dataIndex: 'error_message',
      key: 'error_message',
      width: '30%',
      render: (msg: string) => (
        <Tooltip title={msg}>
          <Text type="danger" ellipsis style={{ maxWidth: 300 }}>
            {errorService.formatErrorMessage(msg, 60)}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: 'Context',
      dataIndex: 'context_type',
      key: 'context',
      width: '15%',
      render: (_: any, record: JobError) => (
        <Text type="secondary" ellipsis>
          {record.context_type ? `${record.context_type}: ${record.context_id || 'N/A'}` : '-'}
        </Text>
      ),
    },
    {
      title: 'Time',
      dataIndex: 'created_at',
      key: 'created_at',
      width: '12%',
      render: (date: string) =>
        date ? new Date(date).toLocaleString() : 'Unknown',
    },
    {
      title: '',
      key: 'action',
      width: '13%',
      render: (_: any, record: JobError) => (
        <Space size="small">
          <Tooltip title="View Details">
            <Button
              type="text"
              size="small"
              icon={<InfoCircleOutlined />}
              onClick={() => setSelectedJobError(record)}
            />
          </Tooltip>
          {!record.resolved_at && (
            <Tooltip title="Mark as Resolved">
              <Button
                type="text"
                size="small"
                icon={<CheckCircleOutlined />}
                onClick={() => handleResolveJobError(record.id)}
              />
            </Tooltip>
          )}
          {record.resolved_at && (
            <Tag color="green" style={{ marginLeft: 4 }}>Resolved</Tag>
          )}
        </Space>
      ),
    },
  ];

  // Failed Emails table columns (from emails table - legacy)
  const columns = [
    {
      title: 'Subject',
      dataIndex: 'subject',
      key: 'subject',
      ellipsis: true,
      width: '25%',
      render: (subject: string) => (
        <Text ellipsis style={{ maxWidth: 200 }}>
          {subject || '(No Subject)'}
        </Text>
      ),
    },
    {
      title: 'From',
      dataIndex: 'sender_email',
      key: 'sender_email',
      ellipsis: true,
      width: '20%',
      render: (email: string) => (
        <Text ellipsis style={{ maxWidth: 150 }}>
          {email || 'Unknown'}
        </Text>
      ),
    },
    {
      title: 'Date',
      dataIndex: 'sent_date',
      key: 'sent_date',
      width: '12%',
      render: (date: string) =>
        date ? new Date(date).toLocaleDateString() : 'Unknown',
    },
    {
      title: 'Error Type',
      dataIndex: 'processing_error',
      key: 'error_type',
      width: '12%',
      render: (error: string) => {
        const errorType = errorService.classifyError(error);
        return (
          <Tag color={errorService.getErrorTypeColor(errorType)}>
            {errorService.getErrorTypeLabel(errorType)}
          </Tag>
        );
      },
    },
    {
      title: 'Error',
      dataIndex: 'processing_error',
      key: 'processing_error',
      width: '20%',
      render: (error: string) => (
        <Tooltip title={error}>
          <Text type="danger" ellipsis style={{ maxWidth: 200 }}>
            {errorService.formatErrorMessage(error, 40)}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: 'Attempts',
      dataIndex: 'processing_attempts',
      key: 'processing_attempts',
      width: '6%',
      render: (attempts: number) => (
        <Tag color={attempts >= 3 ? 'red' : 'orange'}>{attempts}</Tag>
      ),
    },
    {
      title: '',
      key: 'action',
      width: '5%',
      render: (_: any, record: FailedEmail) => (
        <Tooltip title="View Details">
          <Button
            type="text"
            size="small"
            icon={<InfoCircleOutlined />}
            onClick={() => setSelectedError(record)}
          />
        </Tooltip>
      ),
    },
  ];

  // Calculate stats
  const totalFailedAcrossJobs = jobs.reduce((sum, j) => sum + j.failed_records, 0);
  const jobsWithErrorsCount = jobs.length;

  // Filter jobs by mailbox if selected
  const filteredJobs = selectedMailboxId
    ? jobs.filter(j => j.mailbox_id === selectedMailboxId)
    : jobs;

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Breadcrumb */}
      <Breadcrumb className="fade-in-up" style={{ marginBottom: 16 }}>
        <Breadcrumb.Item>
          <Link to="/"><HomeOutlined /> Home</Link>
        </Breadcrumb.Item>
        <Breadcrumb.Item>
          <Link to="/processing">Processing</Link>
        </Breadcrumb.Item>
        <Breadcrumb.Item>
          <ExclamationCircleOutlined /> Errors
        </Breadcrumb.Item>
      </Breadcrumb>

      {/* Header */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }} className="fade-in-up">
        <Col>
          <Text type="secondary">
            View and manage processing errors across all jobs
          </Text>
        </Col>
        <Col>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              loadJobsWithErrors();
              if (selectedJobId) {
                loadJobErrors(selectedJobId, phaseFilter, typeFilter);
                loadErrors(selectedJobId);
              }
            }}
            loading={loading}
            className="glass-button-primary"
          >
            Refresh
          </Button>
        </Col>
      </Row>

      {/* Summary Stats */}
      <Row gutter={16} style={{ marginBottom: 24 }} className="fade-in-up stagger-1">
        <Col span={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic
              title="Total Jobs"
              value={jobsWithErrorsCount}
              valueStyle={{ color: jobsWithErrorsCount > 0 ? '#667eea' : '#3f8600' }}
              prefix={<WarningOutlined />}
            />
          </div>
        </Col>
        <Col span={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic
              title="Failed Emails"
              value={totalFailedAcrossJobs}
              valueStyle={{ color: totalFailedAcrossJobs > 0 ? '#cf1322' : '#3f8600' }}
            />
          </div>
        </Col>
        {selectedJobId && jobErrorsSummary && (
          <>
            <Col span={6}>
              <div className="glass-card" style={{ padding: 24 }}>
                <Statistic
                  title="All Job Errors"
                  value={jobErrorsSummary.total_errors}
                  suffix={jobErrorsSummary.unresolved_errors > 0 ? <Text type="secondary" style={{ fontSize: 14 }}> ({jobErrorsSummary.unresolved_errors} unresolved)</Text> : null}
                  valueStyle={{ color: jobErrorsSummary.total_errors > 0 ? '#cf1322' : '#3f8600' }}
                />
              </div>
            </Col>
            <Col span={6}>
              <div className="glass-card" style={{ padding: 24 }}>
                <Statistic
                  title="By Phase"
                  value={Object.keys(jobErrorsSummary.by_phase || {}).length}
                  suffix={<Text type="secondary" style={{ fontSize: 14 }}> phases</Text>}
                />
              </div>
            </Col>
          </>
        )}
      </Row>

      {/* Filters */}
      <div className="glass-filters fade-in-up stagger-2" style={{ marginBottom: 24 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Text strong>Filter by Mailbox:</Text>
            <Select
              style={{ width: '100%', marginTop: 8 }}
              placeholder="All Mailboxes"
              allowClear
              value={selectedMailboxId}
              onChange={handleMailboxFilter}
            >
              {mailboxes.map(mb => (
                <Option key={mb.id} value={mb.id}>
                  {mb.name}
                </Option>
              ))}
            </Select>
          </Col>
          <Col span={8}>
            <Text strong>Select Job:</Text>
            <Select
              style={{ width: '100%', marginTop: 8 }}
              placeholder="Select a job to view errors"
              value={selectedJobId}
              onChange={handleJobSelect}
              loading={loading}
            >
              {filteredJobs.map(job => (
                <Option key={job.id} value={job.id}>
                  {job.mailbox_name || 'Unknown'} - {job.failed_records} failed
                  ({new Date(job.created_at).toLocaleDateString()})
                </Option>
              ))}
            </Select>
          </Col>
        </Row>
      </div>

      {/* Error Breakdown by Phase (Job Errors) */}
      {selectedJobId && jobErrorsSummary && Object.keys(jobErrorsSummary.by_phase || {}).length > 0 && (
        <div className="glass-card-static fade-in-up stagger-3" style={{ marginBottom: 24, padding: 24 }}>
          <Text strong style={{ display: 'block', marginBottom: 16 }}>Errors by Phase</Text>
          <Row gutter={[16, 16]}>
            {Object.entries(jobErrorsSummary.by_phase).map(([phase, count]) => (
              <Col key={phase} xs={12} sm={8} md={6} lg={4}>
                <Card size="small" hoverable onClick={() => handlePhaseFilterChange(phaseFilter === phase ? null : phase)}>
                  <Statistic
                    title={
                      <Space>
                        {phaseIcons[phase]}
                        <Tag color={errorService.getErrorPhaseColor(phase)}>
                          {errorService.getErrorPhaseLabel(phase)}
                        </Tag>
                      </Space>
                    }
                    value={count}
                    valueStyle={{ fontSize: 20, color: phaseFilter === phase ? '#1890ff' : undefined }}
                  />
                </Card>
              </Col>
            ))}
          </Row>
        </div>
      )}

      {/* Errors Tabs */}
      <div className="glass-table-container fade-in-up stagger-4">
        <Tabs activeKey={activeTab} onChange={handleTabChange}>
          {/* All Job Errors Tab */}
          <TabPane
            tab={
              <span>
                <ExclamationCircleOutlined />
                All Errors ({totalJobErrors})
              </span>
            }
            key="all"
          >
            {/* Filters for job errors */}
            {selectedJobId && (
              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={6}>
                  <Text type="secondary">Filter by Phase:</Text>
                  <Select
                    style={{ width: '100%', marginTop: 4 }}
                    placeholder="All Phases"
                    allowClear
                    value={phaseFilter}
                    onChange={handlePhaseFilterChange}
                  >
                    <Option value="download">Download</Option>
                    <Option value="extraction">Extraction</Option>
                    <Option value="normalization">Normalization</Option>
                    <Option value="tagging">Tagging</Option>
                    <Option value="database">Database</Option>
                    <Option value="categorization">Categorization</Option>
                  </Select>
                </Col>
                <Col span={6}>
                  <Text type="secondary">Filter by Type:</Text>
                  <Select
                    style={{ width: '100%', marginTop: 4 }}
                    placeholder="All Types"
                    allowClear
                    value={typeFilter}
                    onChange={handleTypeFilterChange}
                  >
                    <Option value="network_error">Network Error</Option>
                    <Option value="timeout_error">Timeout</Option>
                    <Option value="encoding_error">Encoding Error</Option>
                    <Option value="parse_error">Parse Error</Option>
                    <Option value="connection_error">Connection Error</Option>
                    <Option value="auth_error">Auth Error</Option>
                    <Option value="file_error">File Error</Option>
                    <Option value="chunk_error">Chunk Error</Option>
                    <Option value="other_error">Other</Option>
                  </Select>
                </Col>
              </Row>
            )}

            {loading && jobErrors.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 48 }}>
                <Spin size="large" />
              </div>
            ) : !selectedJobId ? (
              <Empty
                description="Select a processing job above to view its errors"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : jobErrors.length === 0 ? (
              <Empty description="No errors found for this job" />
            ) : (
              <>
                <Table
                  dataSource={jobErrors}
                  columns={jobErrorsColumns}
                  rowKey="id"
                  size="small"
                  pagination={false}
                  scroll={{ y: 400 }}
                  loading={loading}
                />

                {hasMoreJobErrors && (
                  <div style={{ textAlign: 'center', marginTop: 16 }}>
                    <Button onClick={loadMoreJobErrors} loading={loading}>
                      Load More ({totalJobErrors - jobErrors.length} remaining)
                    </Button>
                  </div>
                )}
              </>
            )}
          </TabPane>

          {/* Failed Emails Tab */}
          <TabPane
            tab={
              <span>
                <WarningOutlined />
                Failed Emails ({totalErrors})
              </span>
            }
            key="emails"
          >
            {/* Error Type Breakdown */}
            {selectedJobId && errorSummary && errorSummary.error_types && Object.keys(errorSummary.error_types).length > 0 && (
              <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                {Object.entries(errorSummary.error_types).map(([type, data]) => {
                  const count = typeof data === 'number' ? data : data.count;
                  return (
                    <Col key={type} xs={12} sm={8} md={6} lg={4}>
                      <Card size="small">
                        <Statistic
                          title={
                            <Tag color={errorService.getErrorTypeColor(type)}>
                              {errorService.getErrorTypeLabel(type)}
                            </Tag>
                          }
                          value={count}
                          valueStyle={{ fontSize: 16 }}
                        />
                      </Card>
                    </Col>
                  );
                })}
              </Row>
            )}

            {/* Retry button */}
            {selectedJobId && totalErrors > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Tooltip title="Reset failed emails to pending for retry (max 3 attempts per email)">
                  <Button
                    type="primary"
                    danger
                    icon={<ReloadOutlined />}
                    onClick={handleRetry}
                    loading={retrying}
                  >
                    Retry Failed Emails ({totalErrors})
                  </Button>
                </Tooltip>
              </div>
            )}

            {loading && errors.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 48 }}>
                <Spin size="large" />
              </div>
            ) : !selectedJobId ? (
              <Empty
                description="Select a processing job above to view its errors"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : errors.length === 0 ? (
              <Empty description="No failed emails found for this job" />
            ) : (
              <>
                <Table
                  dataSource={errors}
                  columns={columns}
                  rowKey="id"
                  size="small"
                  pagination={false}
                  scroll={{ y: 400 }}
                  loading={loading}
                />

                {hasMore && (
                  <div style={{ textAlign: 'center', marginTop: 16 }}>
                    <Button onClick={loadMore} loading={loading}>
                      Load More ({totalErrors - errors.length} remaining)
                    </Button>
                  </div>
                )}
              </>
            )}
          </TabPane>
        </Tabs>
      </div>

      {/* Error Detail Modal */}
      <Modal
        title="Error Details"
        open={!!selectedError}
        onCancel={() => setSelectedError(null)}
        footer={[
          <Button key="close" onClick={() => setSelectedError(null)}>
            Close
          </Button>,
        ]}
        width={700}
      >
        {selectedError && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Row gutter={16}>
              <Col span={12}>
                <Text strong>Subject:</Text>
                <br />
                <Text>{selectedError.subject || '(No Subject)'}</Text>
              </Col>
              <Col span={12}>
                <Text strong>From:</Text>
                <br />
                <Text>{selectedError.sender_email || 'Unknown'}</Text>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={12}>
                <Text strong>Message ID:</Text>
                <br />
                <Text code style={{ fontSize: 11 }}>
                  {selectedError.message_id || 'Unknown'}
                </Text>
              </Col>
              <Col span={12}>
                <Text strong>Sent Date:</Text>
                <br />
                <Text>
                  {selectedError.sent_date
                    ? new Date(selectedError.sent_date).toLocaleString()
                    : 'Unknown'}
                </Text>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={12}>
                <Text strong>Processing Attempts:</Text>
                <br />
                <Tag color={selectedError.processing_attempts >= 3 ? 'red' : 'orange'}>
                  {selectedError.processing_attempts} attempts
                </Tag>
              </Col>
              <Col span={12}>
                <Text strong>Last Attempt:</Text>
                <br />
                <Text>
                  {selectedError.last_processing_attempt
                    ? new Date(selectedError.last_processing_attempt).toLocaleString()
                    : 'Unknown'}
                </Text>
              </Col>
            </Row>

            <div>
              <Text strong>Error Type:</Text>
              <br />
              <Tag color={errorService.getErrorTypeColor(errorService.classifyError(selectedError.processing_error || ''))}>
                {errorService.getErrorTypeLabel(errorService.classifyError(selectedError.processing_error || ''))}
              </Tag>
            </div>

            <div>
              <Text strong>Error Message:</Text>
              <Paragraph
                style={{
                  background: '#fff2f0',
                  padding: 12,
                  borderRadius: 4,
                  marginTop: 8,
                  border: '1px solid #ffccc7',
                }}
              >
                <Text type="danger" style={{ whiteSpace: 'pre-wrap' }}>
                  {selectedError.processing_error || 'No error message'}
                </Text>
              </Paragraph>
            </div>
          </Space>
        )}
      </Modal>

      {/* Job Error Detail Modal */}
      <Modal
        title="Job Error Details"
        open={!!selectedJobError}
        onCancel={() => setSelectedJobError(null)}
        footer={[
          selectedJobError && !selectedJobError.resolved_at && (
            <Button
              key="resolve"
              type="primary"
              icon={<CheckCircleOutlined />}
              onClick={() => {
                handleResolveJobError(selectedJobError.id);
                setSelectedJobError(null);
              }}
            >
              Mark as Resolved
            </Button>
          ),
          <Button key="close" onClick={() => setSelectedJobError(null)}>
            Close
          </Button>,
        ]}
        width={800}
      >
        {selectedJobError && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Row gutter={16}>
              <Col span={8}>
                <Text strong>Phase:</Text>
                <br />
                <Tag color={errorService.getErrorPhaseColor(selectedJobError.error_phase)} icon={phaseIcons[selectedJobError.error_phase]}>
                  {errorService.getErrorPhaseLabel(selectedJobError.error_phase)}
                </Tag>
              </Col>
              <Col span={8}>
                <Text strong>Type:</Text>
                <br />
                <Tag color={errorService.getErrorTypeColor(selectedJobError.error_type)}>
                  {errorService.getErrorTypeLabel(selectedJobError.error_type)}
                </Tag>
              </Col>
              <Col span={8}>
                <Text strong>Severity:</Text>
                <br />
                <Tag color={errorService.getErrorSeverityColor(selectedJobError.error_severity)}>
                  {errorService.getErrorSeverityLabel(selectedJobError.error_severity)}
                </Tag>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={8}>
                <Text strong>Context Type:</Text>
                <br />
                <Text>{selectedJobError.context_type || 'N/A'}</Text>
              </Col>
              <Col span={8}>
                <Text strong>Context ID:</Text>
                <br />
                <Text code style={{ fontSize: 11 }}>
                  {selectedJobError.context_id || 'N/A'}
                </Text>
              </Col>
              <Col span={8}>
                <Text strong>Created:</Text>
                <br />
                <Text>
                  {selectedJobError.created_at
                    ? new Date(selectedJobError.created_at).toLocaleString()
                    : 'Unknown'}
                </Text>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={8}>
                <Text strong>Retryable:</Text>
                <br />
                <Tag color={selectedJobError.is_retryable ? 'green' : 'red'}>
                  {selectedJobError.is_retryable ? 'Yes' : 'No'}
                </Tag>
              </Col>
              <Col span={8}>
                <Text strong>Retry Count:</Text>
                <br />
                <Text>{selectedJobError.retry_count}</Text>
              </Col>
              <Col span={8}>
                <Text strong>Status:</Text>
                <br />
                {selectedJobError.resolved_at ? (
                  <Tag color="green">Resolved at {new Date(selectedJobError.resolved_at).toLocaleString()}</Tag>
                ) : (
                  <Tag color="red">Unresolved</Tag>
                )}
              </Col>
            </Row>

            {selectedJobError.context_details && Object.keys(selectedJobError.context_details).length > 0 && (
              <div>
                <Text strong>Context Details:</Text>
                <Collapse style={{ marginTop: 8 }}>
                  <Panel header="View Details" key="1">
                    <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4, overflow: 'auto', maxHeight: 200 }}>
                      {JSON.stringify(selectedJobError.context_details, null, 2)}
                    </pre>
                  </Panel>
                </Collapse>
              </div>
            )}

            <div>
              <Text strong>Error Message:</Text>
              <Paragraph
                style={{
                  background: '#fff2f0',
                  padding: 12,
                  borderRadius: 4,
                  marginTop: 8,
                  border: '1px solid #ffccc7',
                }}
              >
                <Text type="danger" style={{ whiteSpace: 'pre-wrap' }}>
                  {selectedJobError.error_message || 'No error message'}
                </Text>
              </Paragraph>
            </div>

            {selectedJobError.error_stack && (
              <div>
                <Text strong>Stack Trace:</Text>
                <Collapse style={{ marginTop: 8 }}>
                  <Panel header="View Stack Trace" key="1">
                    <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4, overflow: 'auto', maxHeight: 300, fontSize: 11 }}>
                      {selectedJobError.error_stack}
                    </pre>
                  </Panel>
                </Collapse>
              </div>
            )}
          </Space>
        )}
      </Modal>
    </div>
  );
};

export default ErrorsPage;
