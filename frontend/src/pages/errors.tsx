/**
 * Errors Page - Stage 2 Error Handling
 *
 * Dedicated page to view all processing errors across all jobs
 * with filtering, search, and retry capabilities.
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
} from 'antd';
import {
  ExclamationCircleOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  HomeOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import {
  errorService,
  ErrorSummary,
  FailedEmail,
} from '../services/errorService';
// @ts-ignore
import config from '../config.js';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

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

const ErrorsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const jobIdFromUrl = searchParams.get('jobId');

  // State
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [mailboxes, setMailboxes] = useState<MailboxOption[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(jobIdFromUrl);
  const [selectedMailboxId, setSelectedMailboxId] = useState<string | null>(null);
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

  // Load errors for selected job
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
      loadErrors(selectedJobId);
      // Update URL
      setSearchParams({ jobId: selectedJobId });
    } else {
      setErrors([]);
      setErrorSummary(null);
      setTotalErrors(0);
      setSearchParams({});
    }
  }, [selectedJobId, loadErrors, setSearchParams]);

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

  // Load more errors
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

  // Table columns
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
    <div style={{ padding: 24 }}>
      {/* Breadcrumb */}
      <Breadcrumb style={{ marginBottom: 16 }}>
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
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Title level={2} style={{ margin: 0 }}>
            <ExclamationCircleOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
            Processing Errors
          </Title>
        </Col>
        <Col>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              loadJobsWithErrors();
              if (selectedJobId) loadErrors(selectedJobId);
            }}
            loading={loading}
          >
            Refresh
          </Button>
        </Col>
      </Row>

      {/* Summary Stats */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="Jobs with Errors"
              value={jobsWithErrorsCount}
              valueStyle={{ color: jobsWithErrorsCount > 0 ? '#cf1322' : '#3f8600' }}
              prefix={<WarningOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Total Failed Emails"
              value={totalFailedAcrossJobs}
              valueStyle={{ color: totalFailedAcrossJobs > 0 ? '#cf1322' : '#3f8600' }}
            />
          </Card>
        </Col>
        {selectedJobId && errorSummary && (
          <>
            <Col span={6}>
              <Card>
                <Statistic
                  title="Selected Job Errors"
                  value={errorSummary.total_errors}
                  valueStyle={{ color: '#cf1322' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="Error Types"
                  value={Object.keys(errorSummary.error_types || {}).length}
                />
              </Card>
            </Col>
          </>
        )}
      </Row>

      {/* Filters */}
      <Card style={{ marginBottom: 24 }}>
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
          <Col span={8}>
            {selectedJobId && (
              <div style={{ marginTop: 28 }}>
                <Space>
                  <Tooltip title="Reset failed emails to pending for retry (max 3 attempts per email)">
                    <Button
                      type="primary"
                      danger
                      icon={<ReloadOutlined />}
                      onClick={handleRetry}
                      loading={retrying}
                      disabled={!selectedJobId || totalErrors === 0}
                    >
                      Retry Failed ({totalErrors})
                    </Button>
                  </Tooltip>
                </Space>
              </div>
            )}
          </Col>
        </Row>
      </Card>

      {/* Error Type Breakdown */}
      {selectedJobId && errorSummary && errorSummary.error_types && (
        <Card title="Error Type Breakdown" style={{ marginBottom: 24 }}>
          <Row gutter={[16, 16]}>
            {Object.entries(errorSummary.error_types).map(([type, data]) => {
              const count = typeof data === 'number' ? data : data.count;
              const description =
                typeof data === 'object' && data.description
                  ? data.description
                  : errorService.getErrorTypeLabel(type);

              return (
                <Col key={type} xs={12} sm={8} md={6} lg={4}>
                  <Card size="small">
                    <Statistic
                      title={
                        <Tooltip title={description}>
                          <Tag color={errorService.getErrorTypeColor(type)}>
                            {errorService.getErrorTypeLabel(type)}
                          </Tag>
                        </Tooltip>
                      }
                      value={count}
                      valueStyle={{ fontSize: 20 }}
                    />
                  </Card>
                </Col>
              );
            })}
          </Row>
        </Card>
      )}

      {/* Errors Table */}
      <Card title={selectedJobId ? `Failed Emails (${totalErrors})` : 'Select a job to view errors'}>
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
          <Empty description="No errors found for this job" />
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
      </Card>

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
    </div>
  );
};

export default ErrorsPage;
