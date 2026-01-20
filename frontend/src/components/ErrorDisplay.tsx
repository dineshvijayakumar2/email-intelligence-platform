/**
 * ErrorDisplay Component - Stage 2 Error Handling
 *
 * Displays detailed error information for processing jobs
 * Includes error summary, failed emails list, and retry functionality
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Typography,
  Statistic,
  Row,
  Col,
  Collapse,
  Tooltip,
  Modal,
  message,
  Spin,
  Empty,
  Alert,
} from 'antd';
import {
  ExclamationCircleOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  errorService,
  ErrorSummary,
  FailedEmail,
  FailedEmailsResponse,
} from '../services/errorService';

const { Text, Paragraph } = Typography;
const { Panel } = Collapse;

interface ErrorDisplayProps {
  jobId: string;
  failedCount: number;
  onRetryComplete?: () => void;
}

export const ErrorDisplay: React.FC<ErrorDisplayProps> = ({
  jobId,
  failedCount,
  onRetryComplete,
}) => {
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<ErrorSummary | null>(null);
  const [errors, setErrors] = useState<FailedEmail[]>([]);
  const [totalFailed, setTotalFailed] = useState(failedCount);
  const [hasMore, setHasMore] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [selectedError, setSelectedError] = useState<FailedEmail | null>(null);

  useEffect(() => {
    if (expanded && failedCount > 0) {
      loadErrors();
    }
  }, [expanded, jobId, failedCount]);

  const loadErrors = async () => {
    setLoading(true);
    try {
      const [summaryData, errorsData] = await Promise.all([
        errorService.getErrorSummary(jobId),
        errorService.getProcessingErrors(jobId, 50, 0),
      ]);

      setSummary(summaryData);
      setErrors(errorsData.emails);
      setTotalFailed(errorsData.total_failed);
      setHasMore(errorsData.has_more);
    } catch (error) {
      console.error('Failed to load errors:', error);
      message.error('Failed to load error details');
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const result = await errorService.retryFailedEmails(jobId, 3);
      message.success(result.message);

      if (result.emails_reset > 0) {
        // Refresh error list
        await loadErrors();
        onRetryComplete?.();
      }
    } catch (error) {
      console.error('Failed to retry emails:', error);
      message.error('Failed to retry failed emails');
    } finally {
      setRetrying(false);
    }
  };

  const loadMore = async () => {
    setLoading(true);
    try {
      const moreErrors = await errorService.getProcessingErrors(
        jobId,
        50,
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

  // Error type statistics
  const renderErrorTypeStats = () => {
    if (!summary || !summary.error_types) return null;

    const errorTypes = Object.entries(summary.error_types);
    if (errorTypes.length === 0) return null;

    return (
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {errorTypes.map(([type, data]) => {
          const count = typeof data === 'number' ? data : data.count;
          const description =
            typeof data === 'object' && data.description
              ? data.description
              : errorService.getErrorTypeLabel(type);

          return (
            <Col key={type} xs={12} sm={8} md={6}>
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
    );
  };

  // Failed emails table columns
  const columns = [
    {
      title: 'Subject',
      dataIndex: 'subject',
      key: 'subject',
      ellipsis: true,
      width: '30%',
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
      title: 'Error',
      dataIndex: 'processing_error',
      key: 'processing_error',
      width: '35%',
      render: (error: string) => (
        <Tooltip title={error}>
          <Text type="danger" ellipsis style={{ maxWidth: 250 }}>
            {errorService.formatErrorMessage(error, 50)}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: 'Attempts',
      dataIndex: 'processing_attempts',
      key: 'processing_attempts',
      width: '10%',
      render: (attempts: number) => (
        <Tag color={attempts >= 3 ? 'red' : 'orange'}>{attempts}</Tag>
      ),
    },
    {
      title: 'Action',
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

  if (failedCount === 0) {
    return null;
  }

  return (
    <>
      <Collapse
        activeKey={expanded ? ['errors'] : []}
        onChange={() => setExpanded(!expanded)}
        style={{ marginTop: 16 }}
      >
        <Panel
          key="errors"
          header={
            <Space>
              <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
              <Text strong>
                {totalFailed.toLocaleString()} Failed Emails
              </Text>
              {loading && <Spin size="small" />}
            </Space>
          }
          extra={
            expanded && (
              <Space onClick={(e) => e.stopPropagation()}>
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={loadErrors}
                  loading={loading}
                >
                  Refresh
                </Button>
                <Tooltip title="Reset failed emails to pending for retry (max 3 attempts per email)">
                  <Button
                    size="small"
                    type="primary"
                    danger
                    icon={<ReloadOutlined />}
                    onClick={handleRetry}
                    loading={retrying}
                  >
                    Retry Failed
                  </Button>
                </Tooltip>
              </Space>
            )
          }
        >
          {loading && errors.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 24 }}>
              <Spin size="large" />
            </div>
          ) : errors.length === 0 ? (
            <Empty description="No error details available" />
          ) : (
            <>
              {/* Error Type Summary */}
              {renderErrorTypeStats()}

              {/* Sample Errors Alert */}
              {summary?.sample_errors && summary.sample_errors.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  icon={<WarningOutlined />}
                  message="Recent Error Samples"
                  description={
                    <ul style={{ margin: 0, paddingLeft: 20 }}>
                      {summary.sample_errors.slice(0, 3).map((err, idx) => (
                        <li key={idx}>
                          <Text type="secondary">
                            [{errorService.getErrorTypeLabel(err.error_type)}]
                          </Text>{' '}
                          {errorService.formatErrorMessage(err.error_message, 80)}
                        </li>
                      ))}
                    </ul>
                  }
                  style={{ marginBottom: 16 }}
                />
              )}

              {/* Failed Emails Table */}
              <Table
                dataSource={errors}
                columns={columns}
                rowKey="id"
                size="small"
                pagination={false}
                scroll={{ y: 300 }}
              />

              {/* Load More Button */}
              {hasMore && (
                <div style={{ textAlign: 'center', marginTop: 16 }}>
                  <Button onClick={loadMore} loading={loading}>
                    Load More ({totalFailed - errors.length} remaining)
                  </Button>
                </div>
              )}
            </>
          )}
        </Panel>
      </Collapse>

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
        width={600}
      >
        {selectedError && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <Text strong>Subject: </Text>
              <Text>{selectedError.subject || '(No Subject)'}</Text>
            </div>
            <div>
              <Text strong>From: </Text>
              <Text>{selectedError.sender_email || 'Unknown'}</Text>
            </div>
            <div>
              <Text strong>Message ID: </Text>
              <Text code>{selectedError.message_id || 'Unknown'}</Text>
            </div>
            <div>
              <Text strong>Attempts: </Text>
              <Tag color={selectedError.processing_attempts >= 3 ? 'red' : 'orange'}>
                {selectedError.processing_attempts}
              </Tag>
            </div>
            <div>
              <Text strong>Last Attempt: </Text>
              <Text>
                {selectedError.last_processing_attempt
                  ? new Date(selectedError.last_processing_attempt).toLocaleString()
                  : 'Unknown'}
              </Text>
            </div>
            <div>
              <Text strong>Error Message:</Text>
              <Paragraph
                style={{
                  background: '#f5f5f5',
                  padding: 12,
                  borderRadius: 4,
                  marginTop: 8,
                }}
              >
                <Text type="danger">{selectedError.processing_error || 'No error message'}</Text>
              </Paragraph>
            </div>
          </Space>
        )}
      </Modal>
    </>
  );
};

export default ErrorDisplay;
