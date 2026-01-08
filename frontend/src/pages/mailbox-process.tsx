import React, { useState, useEffect } from "react";
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
  Divider,
  List,
  Tag,
  Badge
} from "antd";
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  SettingOutlined,
  FolderOutlined
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox } from '../services/mailboxService';
import { processingService, ProcessingJob } from '../services/processingService';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

export const MailboxProcess: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [form] = Form.useForm();
  const [mailbox, setMailbox] = useState<Mailbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [currentJob, setCurrentJob] = useState<ProcessingJob | null>(null);
  const [jobHistory, setJobHistory] = useState<ProcessingJob[]>([]);

  useEffect(() => {
    if (id) {
      loadMailboxData();
      loadJobHistory();
    }
  }, [id]);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (currentJob) {
      // Determine polling frequency based on job status
      let pollInterval = 5000; // Default: 5 seconds

      if (['pending', 'running'].includes(currentJob.status)) {
        pollInterval = 2000; // Active jobs: poll every 2 seconds for quick updates
      } else if (currentJob.status === 'paused') {
        pollInterval = 10000; // Paused jobs: poll every 10 seconds (less frequent)
      } else {
        // Completed/failed/stopped: no polling needed
        return;
      }

      interval = setInterval(() => {
        loadJobHistory();
      }, pollInterval);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [currentJob]);

  const loadMailboxData = async () => {
    try {
      if (!id) return;
      const data = await mailboxService.getMailbox(id);
      setMailbox(data);
    } catch (error) {
      console.error('Error loading mailbox:', error);
      message.error('Failed to load mailbox data');
      navigate('/mailboxes');
    } finally {
      setLoading(false);
    }
  };

  const loadJobHistory = async () => {
    try {
      if (!id) return;
      const jobs = await processingService.getProcessingJobs();
      const mailboxJobs = jobs.filter(job => job.mailbox_id === id);
      setJobHistory(mailboxJobs);
      
      // Find current active job
      const activeJob = mailboxJobs.find(job => ['pending', 'running'].includes(job.status));
      setCurrentJob(activeJob || null);
    } catch (error) {
      console.error('Error loading job history:', error);
    }
  };

  const startProcessing = async (values: any) => {
    try {
      if (!id || !mailbox) return;
      
      setProcessing(true);
      
      const jobData = {
        mailbox_id: id,
        job_type: values.job_type || 'extraction',
        total_records: values.email_limit || null  // null means process all emails
      };

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
      case 'completed': return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'failed': return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
      default: return null;
    }
  };

  const getJobStatusColor = (status: string) => {
    switch (status) {
      case 'pending': return 'warning';
      case 'running': return 'processing';
      case 'completed': return 'success';
      case 'failed': return 'error';
      default: return 'default';
    }
  };

  const getCurrentStep = () => {
    if (!currentJob) return 0;
    switch (currentJob.status) {
      case 'pending': return 0;
      case 'running': return 1;
      case 'completed': return 2;
      case 'failed': return 2;
      default: return 0;
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
              status={currentJob.status === 'failed' ? 'error' : 'process'}
              items={[
                { title: "Queued", description: "Job created and waiting" },
                { title: "Processing", description: "Extracting and analyzing emails" },
                { title: currentJob.status === 'failed' ? 'Failed' : 'Completed', description: currentJob.status === 'failed' ? 'Processing failed' : 'All emails processed' }
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
                
                {currentJob.total_records && currentJob.total_records > 0 && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <Text>Progress</Text>
                      <Text>{currentJob.processed_records || 0} / {currentJob.total_records}</Text>
                    </div>
                    <Progress
                      percent={Math.round(((currentJob.processed_records || 0) / currentJob.total_records) * 100)}
                      status={currentJob.status === 'failed' ? 'exception' : 'active'}
                    />
                    {currentJob.status === 'running' && (
                      <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#666' }}>
                        <Text type="secondary">
                          {currentJob.emails_per_second ? `${currentJob.emails_per_second.toFixed(1)} emails/sec` : ''}
                        </Text>
                        <Text type="secondary">
                          {currentJob.estimated_time_remaining ? `ETA: ${currentJob.estimated_time_remaining}` : ''}
                        </Text>
                      </div>
                    )}
                  </div>
                )}
                
                {currentJob.status === 'failed' && currentJob.error_log && (
                  <Alert
                    message="Processing Failed"
                    description={typeof currentJob.error_log === 'string' ? currentJob.error_log : JSON.stringify(currentJob.error_log)}
                    type="error"
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
      {!currentJob || ['completed', 'failed'].includes(currentJob.status) ? (
        <Card title={<Space><PlayCircleOutlined />Start New Processing Job</Space>}>
          <Form
            form={form}
            layout="vertical"
            onFinish={startProcessing}
            initialValues={{
              job_type: 'extraction',
              email_limit: 10,
              batch_size: 1000,
              enable_categorization: true,
              enable_enrichment: false
            }}
          >
            <Form.Item
              name="job_type"
              label="Processing Type"
              rules={[{ required: true, message: 'Please select processing type' }]}
            >
              <Select placeholder="Select processing type">
                <Option value="extraction">Email Extraction</Option>
                <Option value="categorization">Categorization Only</Option>
                <Option value="enrichment">AI Enrichment</Option>
                <Option value="full">Full Processing (Extract + Categorize + Enrich)</Option>
              </Select>
            </Form.Item>

            <Form.Item
              name="email_limit"
              label="Email Limit"
              tooltip="Maximum number of emails to process (leave empty for all emails)"
            >
              <InputNumber min={1} max={100000} placeholder="Enter email limit or leave empty for all" style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item
              name="batch_size"
              label="Batch Size"
              tooltip="Number of emails to process in each batch (advanced setting)"
            >
              <InputNumber min={100} max={10000} style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item
              name="enable_categorization"
              label="Enable Categorization"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>

            <Form.Item
              name="enable_enrichment"
              label="Enable AI Enrichment"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>

            <Alert
              message="Processing Information"
              description="This will start processing emails from the configured source. Depending on the number of emails, this may take some time."
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