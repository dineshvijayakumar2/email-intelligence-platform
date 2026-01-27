import React, { useState, useEffect } from "react";
import {
  Table,
  Space,
  Button,
  Typography,
  Tag,
  Popconfirm,
  message,
  Modal,
  DatePicker,
  InputNumber,
  Form
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SyncOutlined,
  MailOutlined,
  PlayCircleOutlined,
  GoogleOutlined,
  LinkOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
  CalendarOutlined
} from "@ant-design/icons";
import dayjs from 'dayjs';
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox, hasGmailLiveSync } from '../services/mailboxService';
import { MailboxCreateForm } from '../components/MailboxCreateForm';
import { MailboxEditForm } from '../components/MailboxEditForm';
import gmailService from '../services/gmailService';

const { Text } = Typography;
const { RangePicker } = DatePicker;

export const MailboxList: React.FC = () => {
  const navigate = useNavigate();
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [loading, setLoading] = useState(true);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [linkingMailboxId, setLinkingMailboxId] = useState<string | null>(null);

  // Date range fetch modal state
  const [dateRangeModalVisible, setDateRangeModalVisible] = useState(false);
  const [selectedMailboxForFetch, setSelectedMailboxForFetch] = useState<Mailbox | null>(null);
  const [fetchingEmails, setFetchingEmails] = useState(false);
  const [dateRangeForm] = Form.useForm();

  // Get user ID from localStorage (same pattern as other components)
  const getUserId = () => {
    let userId = localStorage.getItem('user_id');
    if (!userId) {
      const fingerprint = [
        navigator.userAgent,
        navigator.language,
        screen.width + 'x' + screen.height,
        new Date().getTimezoneOffset()
      ].join('|');
      userId = 'user_' + btoa(fingerprint).replace(/[^a-zA-Z0-9]/g, '').substring(0, 16);
      localStorage.setItem('user_id', userId);
    }
    return userId;
  };
  const userId = getUserId();

  useEffect(() => {
    loadMailboxes();
    checkGmailConnection();
  }, []);

  const checkGmailConnection = async () => {
    try {
      const connected = await gmailService.isConnected(userId);
      setGmailConnected(connected);
    } catch (error) {
      console.error('Error checking Gmail connection:', error);
    }
  };

  const loadMailboxes = async (retryCount = 0) => {
    let shouldStopLoading = true;

    try {
      setLoading(true);
      const data = await mailboxService.getMailboxes();
      setMailboxes(data);
    } catch (error) {
      console.error('Error loading mailboxes:', error);

      // Retry up to 2 times with exponential backoff for transient errors
      if (retryCount < 2) {
        const delay = Math.pow(2, retryCount) * 500; // 500ms, 1000ms
        shouldStopLoading = false; // Keep loading spinner while retrying
        setTimeout(() => loadMailboxes(retryCount + 1), delay);
        return;
      }

      // Only show error after retries exhausted and if we have no mailboxes to display
      // This prevents error flash when data eventually loads successfully
      if (mailboxes.length === 0) {
        message.error('Failed to load mailboxes. Please check your connection and try again.');
      }
    } finally {
      if (shouldStopLoading) {
        setLoading(false);
      }
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await mailboxService.deleteMailbox(id);
      message.success("Mailbox deleted successfully");
      loadMailboxes(); // Reload the list
    } catch (error) {
      message.error("Failed to delete mailbox");
    }
  };

  const handleSync = async (id: string, name: string) => {
    try {
      message.info(`Starting sync for ${name}...`);
      await mailboxService.syncMailbox(id);
      message.success(`Sync initiated for ${name}`);
      loadMailboxes(); // Reload to show updated sync time
    } catch (error) {
      message.error(`Failed to sync ${name}`);
    }
  };

  const handleLinkGmail = async (mailboxId: string, mailboxName: string) => {
    if (!gmailConnected) {
      message.warning('Please connect your Gmail account from the Dashboard first');
      navigate('/');
      return;
    }

    try {
      setLinkingMailboxId(mailboxId);
      message.loading({ content: `Linking Gmail to ${mailboxName}...`, key: 'link-gmail' });

      const result = await gmailService.extendMailboxWithGmail(mailboxId, userId);

      if (result.success) {
        message.success({ content: result.message, key: 'link-gmail' });
        loadMailboxes(); // Reload to show updated status
      } else {
        message.error({ content: result.message, key: 'link-gmail' });
      }
    } catch (error) {
      message.error({ content: 'Failed to link Gmail', key: 'link-gmail' });
    } finally {
      setLinkingMailboxId(null);
    }
  };

  const handleOpenDateRangeFetch = (mailbox: Mailbox) => {
    setSelectedMailboxForFetch(mailbox);
    setDateRangeModalVisible(true);
    dateRangeForm.resetFields();
  };

  const handleDateRangeFetch = async (values: any) => {
    if (!selectedMailboxForFetch) return;

    const { dateRange, maxEmails } = values;
    if (!dateRange || dateRange.length !== 2) {
      message.error('Please select a date range');
      return;
    }

    const startDate = dateRange[0].format('YYYY-MM-DD');
    const endDate = dateRange[1].format('YYYY-MM-DD');

    try {
      setFetchingEmails(true);
      const result = await gmailService.fetchEmailsByDateRange(
        selectedMailboxForFetch.id,
        userId,
        startDate,
        endDate,
        maxEmails
      );

      if (result.success) {
        message.success(`${result.message}. Job ID: ${result.job_id}`);
        setDateRangeModalVisible(false);
        // Navigate to processing page to see the job
        navigate('/processing');
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('Failed to start email fetch');
    } finally {
      setFetchingEmails(false);
    }
  };

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Mailbox) => (
        <Space>
          <MailOutlined />
          <div>
            <div style={{ fontWeight: 500 }}>{text}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {record.email_address}
            </Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'mailbox_type',
      key: 'mailbox_type',
      render: (type: string, record: Mailbox) => {
        const colors: Record<string, string> = {
          mbox: 'green',
          pst: 'blue',
          olm: 'purple',
          gmail: 'cyan',
          outlook_live: 'geekblue'
        };
        const labels: Record<string, string> = {
          mbox: 'MBOX',
          pst: 'PST',
          olm: 'OLM',
          gmail: 'Gmail LIVE',
          outlook_live: 'Outlook LIVE'
        };
        const isLiveEnabled = hasGmailLiveSync(record);
        const displayType = record.connection_config?.original_type || type;

        return (
          <Space size={4}>
            <Tag color={colors[displayType] || 'default'}>
              {labels[displayType] || displayType.toUpperCase()}
            </Tag>
            {isLiveEnabled && (
              <Tag color="cyan" icon={<ThunderboltOutlined />}>
                LIVE
              </Tag>
            )}
          </Space>
        );
      },
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (isActive: boolean) => (
        <Tag color={isActive ? 'success' : 'default'}>
          {isActive ? 'Active' : 'Inactive'}
        </Tag>
      ),
    },
    {
      title: 'Total Emails',
      dataIndex: 'total_emails',
      key: 'total_emails',
      render: (count: number) => count.toLocaleString(),
    },
    {
      title: 'Last Sync',
      dataIndex: 'last_sync_at',
      key: 'last_sync_at',
      render: (date: string) => {
        if (!date) return 'Never';
        return new Date(date).toLocaleDateString();
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, record: Mailbox) => {
        const isLiveEnabled = hasGmailLiveSync(record);
        const isArchiveType = ['mbox', 'pst', 'olm'].includes(record.mailbox_type);
        const canLinkGmail = isArchiveType && !isLiveEnabled && gmailConnected;

        return (
          <Space wrap>
            <Button
              type="primary"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => navigate(`/mailboxes/process/${record.id}`)}
              disabled={!record.is_active}
            >
              Process
            </Button>
            <Button
              type="primary"
              ghost
              size="small"
              icon={<SyncOutlined />}
              onClick={() => handleSync(record.id, record.name)}
              disabled={!record.is_active}
            >
              Sync
            </Button>
            {/* Link Gmail button - only for archive mailboxes without LIVE sync */}
            {isArchiveType && !isLiveEnabled && (
              <Button
                size="small"
                icon={<LinkOutlined />}
                onClick={() => handleLinkGmail(record.id, record.name)}
                disabled={!canLinkGmail}
                loading={linkingMailboxId === record.id}
                title={!gmailConnected ? 'Connect Gmail from Dashboard first' : 'Link Gmail for LIVE sync'}
                style={{
                  color: gmailConnected ? '#4285f4' : undefined,
                  borderColor: gmailConnected ? '#4285f4' : undefined
                }}
              >
                <GoogleOutlined /> Link Gmail
              </Button>
            )}
            {/* Fetch Historical button - only for mailboxes with LIVE sync enabled */}
            {isLiveEnabled && (
              <Button
                size="small"
                icon={<HistoryOutlined />}
                onClick={() => handleOpenDateRangeFetch(record)}
                title="Fetch historical emails from Gmail for a specific date range"
                style={{
                  color: '#52c41a',
                  borderColor: '#52c41a'
                }}
              >
                Fetch Historical
              </Button>
            )}
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => navigate(`/mailboxes/edit/${record.id}`)}
            >
              Edit
            </Button>
            <Popconfirm
              title="Are you sure you want to delete this mailbox?"
              onConfirm={() => handleDelete(record.id)}
              okText="Yes"
              cancelText="No"
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                Delete
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Header */}
      <div className="fade-in-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Text type="secondary">
            Manage your email sources for intelligence gathering
          </Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate('/mailboxes/create')}
          className="glass-button-primary"
        >
          Add Mailbox
        </Button>
      </div>

      {/* Table */}
      <div className="glass-table-container fade-in-up stagger-1">
        <Table
          dataSource={mailboxes}
          columns={columns}
          loading={loading}
          rowKey="id"
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total, range) =>
              `${range[0]}-${range[1]} of ${total} mailboxes`,
          }}
        />
      </div>

      {/* Date Range Fetch Modal */}
      <Modal
        title={
          <Space>
            <CalendarOutlined style={{ color: '#52c41a' }} />
            <span>Fetch Historical Emails</span>
          </Space>
        }
        open={dateRangeModalVisible}
        onCancel={() => setDateRangeModalVisible(false)}
        footer={null}
        destroyOnClose
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            Pull historical emails from Gmail for <strong>{selectedMailboxForFetch?.name}</strong> within a specific date range.
            This uses the LIVE sync connection to fetch older emails on-demand.
          </Text>
        </div>

        <Form
          form={dateRangeForm}
          layout="vertical"
          onFinish={handleDateRangeFetch}
        >
          <Form.Item
            name="dateRange"
            label="Date Range"
            rules={[{ required: true, message: 'Please select a date range' }]}
          >
            <RangePicker
              style={{ width: '100%' }}
              disabledDate={(current) => current && current > dayjs().endOf('day')}
              presets={[
                { label: 'Last 7 Days', value: [dayjs().subtract(7, 'day'), dayjs()] },
                { label: 'Last 30 Days', value: [dayjs().subtract(30, 'day'), dayjs()] },
                { label: 'Last 3 Months', value: [dayjs().subtract(3, 'month'), dayjs()] },
                { label: 'Last 6 Months', value: [dayjs().subtract(6, 'month'), dayjs()] },
                { label: 'Last Year', value: [dayjs().subtract(1, 'year'), dayjs()] },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="maxEmails"
            label="Maximum Emails (optional)"
            tooltip="Leave empty to fetch all emails in the date range"
          >
            <InputNumber
              style={{ width: '100%' }}
              min={1}
              max={10000}
              placeholder="No limit"
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, marginTop: 24 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setDateRangeModalVisible(false)}>
                Cancel
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                loading={fetchingEmails}
                icon={<HistoryOutlined />}
                style={{ background: '#52c41a', borderColor: '#52c41a' }}
              >
                Start Fetch
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export const MailboxCreate: React.FC = () => {
  return <MailboxCreateForm />;
};

export const MailboxEdit: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  
  if (!id) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <div>Invalid mailbox ID</div>
      </div>
    );
  }
  
  return <MailboxEditForm mailboxId={id} />;
};