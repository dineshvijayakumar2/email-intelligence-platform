import React, { useState, useEffect } from "react";
import { 
  Card, 
  Table, 
  Space, 
  Button, 
  Typography, 
  Tag, 
  Form, 
  Input, 
  Select, 
  Switch,
  Popconfirm,
  message,
  Divider,
  InputNumber,
  Collapse,
  Alert,
  Progress,
  Badge,
  Radio
} from "antd";
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  SyncOutlined, 
  MailOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  SettingOutlined,
  GoogleOutlined,
  CloudOutlined
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox, CreateMailboxData } from '../services/mailboxService';
import { processingService } from '../services/processingService';
import GoogleDrivePicker from '../components/GoogleDrivePicker';
import GoogleDriveConnection from '../components/GoogleDriveConnection';
import { MailboxCreateForm } from '../components/MailboxCreateForm';
import { MailboxEditForm } from '../components/MailboxEditForm';

const { Title, Text } = Typography;
const { Option } = Select;

export const MailboxList: React.FC = () => {
  const navigate = useNavigate();
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMailboxes();
  }, []);

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
      render: (type: string) => {
        const colors = {
          mbox: 'green',
          pst: 'blue',
          olm: 'purple'
        };
        const labels = {
          mbox: 'MBOX (Universal)',
          pst: 'PST (Outlook Windows)',
          olm: 'OLM (Outlook Mac)'
        };
        return <Tag color={colors[type as keyof typeof colors]}>{labels[type as keyof typeof labels] || type.toUpperCase()}</Tag>;
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
      render: (_: any, record: Mailbox) => (
        <Space>
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
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={2} style={{ margin: 0 }}>
            📮 Mailboxes
          </Title>
          <Text type="secondary">
            Manage your email sources for intelligence gathering
          </Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate('/mailboxes/create')}
        >
          Add Mailbox
        </Button>
      </div>

      <Card>
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
      </Card>
    </Space>
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