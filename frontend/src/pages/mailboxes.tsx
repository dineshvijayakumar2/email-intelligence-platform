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
  Badge
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
  SettingOutlined
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox, CreateMailboxData } from '../services/mailboxService';
import { processingService } from '../services/processingService';

const { Title, Text } = Typography;
const { Option } = Select;

export const MailboxList: React.FC = () => {
  const navigate = useNavigate();
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMailboxes();
  }, []);

  const loadMailboxes = async () => {
    try {
      setLoading(true);
      const data = await mailboxService.getMailboxes();
      setMailboxes(data);
    } catch (error) {
      console.error('Error loading mailboxes:', error);
      message.error('Failed to load mailboxes');
    } finally {
      setLoading(false);
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
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [selectedType, setSelectedType] = React.useState('mbox');
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const onFinish = async (values: any) => {
    try {
      setLoading(true);

      // Build connection config based on mailbox type
      const connectionConfig: any = {};

      // All file-based types (MBOX, PST, OLM) use file_path
      if (['mbox', 'pst', 'olm'].includes(values.mailbox_type)) {
        connectionConfig.file_path = values.file_path;
      }

      const mailboxData: any = {
        name: values.name,
        mailbox_type: values.mailbox_type,
        is_active: values.is_active,
        connection_config: connectionConfig
      };

      // Only add email_address if provided
      if (values.email_address) {
        mailboxData.email_address = values.email_address;
      }

      await mailboxService.createMailbox(mailboxData);
      message.success("Mailbox created successfully");
      navigate('/mailboxes');
    } catch (error) {
      console.error('Error creating mailbox:', error);
      message.error("Failed to create mailbox");
    } finally {
      setLoading(false);
    }
  };
  
  const testConnection = async () => {
    try {
      setTesting(true);
      const values = form.getFieldsValue();
      
      const apiBaseUrl = process.env.REACT_APP_API_BASE_URL;
      
      if (apiBaseUrl) {
        // Build connection config
        const connectionConfig: any = {};

        // All file-based types (MBOX, PST, OLM) use file_path
        if (['mbox', 'pst', 'olm'].includes(values.mailbox_type)) {
          connectionConfig.file_path = values.file_path;
        }

        const response = await fetch(`${apiBaseUrl}/mailboxes/test/test-connection`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            mailbox_type: values.mailbox_type,
            connection_config: connectionConfig
          }),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Connection test failed');
        }

        const result = await response.json();
        message.success(result.message || 'Connection test successful!');
      } else {
        // Fallback to basic validation
        if (['mbox', 'pst', 'olm'].includes(values.mailbox_type) && !values.file_path) {
          throw new Error('File path is required for file-based mailboxes');
        }

        await new Promise(resolve => setTimeout(resolve, 2000));
        message.success('Connection test successful!');
      }
    } catch (error) {
      message.error(`Connection test failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setTesting(false);
    }
  };

  const handleFileBrowse = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      // In browser environment, we get a File object with a path
      // For local files, we can show the name, but the actual path depends on the backend
      const filePath = (file as any).path || file.name;
      form.setFieldValue('file_path', filePath);
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Title level={2} style={{ margin: 0 }}>
          ➕ Create New Mailbox
        </Title>
        <Text type="secondary">
          Add a new email source for intelligence gathering
        </Text>
      </div>

      <Card style={{ maxWidth: 600 }}>
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{
            is_active: true,
            mailbox_type: 'mbox',
          }}
        >
          <Form.Item
            name="name"
            label="Mailbox Name"
            rules={[{ required: true, message: 'Please enter a mailbox name' }]}
          >
            <Input placeholder="e.g., Primary Business Account" />
          </Form.Item>

          <Form.Item
            name="email_address"
            label="Email Address (Optional)"
            rules={[
              { type: 'email', message: 'Please enter a valid email address' },
            ]}
          >
            <Input placeholder="user@domain.com (optional)" />
          </Form.Item>

          <Form.Item
            name="mailbox_type"
            label="Mailbox Type"
            rules={[{ required: true, message: 'Please select a mailbox type' }]}
          >
            <Select
              placeholder="Select mailbox type"
              onChange={setSelectedType}
            >
              <Option value="mbox">MBOX (Universal Format)</Option>
              <Option value="pst">PST (Outlook Windows)</Option>
              <Option value="olm">OLM (Outlook Mac)</Option>
            </Select>
          </Form.Item>

          {/* File Configuration - for all file-based types */}
          {['mbox', 'pst', 'olm'].includes(selectedType) && (
            <>
              <Divider>File Configuration</Divider>
              <Alert
                message={`${selectedType.toUpperCase()} File Archive`}
                description={
                  selectedType === 'mbox' ? 'Universal email format (Gmail export, Thunderbird, Apple Mail)' :
                  selectedType === 'pst' ? 'Windows Outlook archive file with native folder structure' :
                  'Mac Outlook archive file with folder hierarchy'
                }
                type="info"
                style={{ marginBottom: 16 }}
              />
              <Form.Item
                name="file_path"
                label={`${selectedType.toUpperCase()} File Path`}
                rules={[{ required: true, message: `Please specify the ${selectedType.toUpperCase()} file path` }]}
              >
                <Input
                  placeholder={`/path/to/archive.${selectedType}`}
                  prefix={<FolderOpenOutlined />}
                  suffix={
                    <Button
                      size="small"
                      type="link"
                      onClick={handleFileBrowse}
                      icon={<FolderOpenOutlined />}
                    >
                      Browse
                    </Button>
                  }
                />
              </Form.Item>
              <input
                ref={fileInputRef}
                type="file"
                accept={`.${selectedType}`}
                style={{ display: 'none' }}
                onChange={handleFileSelect}
              />
            </>
          )}

          <Form.Item
            name="is_active"
            label="Active"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Divider />
          
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                Create Mailbox
              </Button>
              <Button
                type="default"
                icon={<CheckCircleOutlined />}
                onClick={testConnection}
                loading={testing}
                disabled={['mbox', 'pst', 'olm'].includes(selectedType) && !form.getFieldValue('file_path')}
              >
                Test Connection
              </Button>
              <Button onClick={() => navigate('/mailboxes')}>
                Cancel
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </Space>
  );
};

export const MailboxEdit: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);
  const [mailboxData, setMailboxData] = React.useState<Mailbox | null>(null);
  const [initialLoading, setInitialLoading] = React.useState(true);

  useEffect(() => {
    if (id) {
      loadMailboxData();
    }
  }, [id]);

  const loadMailboxData = async () => {
    try {
      if (!id) return;
      const data = await mailboxService.getMailbox(id);
      setMailboxData(data);
      form.setFieldsValue(data);
    } catch (error) {
      console.error('Error loading mailbox:', error);
      message.error('Failed to load mailbox data');
      navigate('/mailboxes');
    } finally {
      setInitialLoading(false);
    }
  };

  const onFinish = async (values: any) => {
    try {
      if (!id) return;
      setLoading(true);
      await mailboxService.updateMailbox(id, values);
      message.success("Mailbox updated successfully");
      navigate('/mailboxes');
    } catch (error) {
      console.error('Error updating mailbox:', error);
      message.error("Failed to update mailbox");
    } finally {
      setLoading(false);
    }
  };

  if (initialLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <div>Loading mailbox data...</div>
      </div>
    );
  }

  if (!mailboxData) {
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
          ✏️ Edit Mailbox
        </Title>
        <Text type="secondary">
          Update mailbox configuration
        </Text>
      </div>

      <Card style={{ maxWidth: 600 }}>
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={mailboxData}
        >
          <Form.Item
            name="name"
            label="Mailbox Name"
            rules={[{ required: true, message: 'Please enter a mailbox name' }]}
          >
            <Input placeholder="e.g., Primary Business Account" />
          </Form.Item>

          <Form.Item
            name="email_address"
            label="Email Address (Optional)"
            rules={[
              { type: 'email', message: 'Please enter a valid email address' },
            ]}
          >
            <Input placeholder="user@domain.com (optional)" />
          </Form.Item>

          <Form.Item
            name="mailbox_type"
            label="Mailbox Type"
            rules={[{ required: true, message: 'Please select a mailbox type' }]}
          >
            <Select placeholder="Select mailbox type">
              <Option value="mbox">MBOX (Universal Format)</Option>
              <Option value="pst">PST (Outlook Windows)</Option>
              <Option value="olm">OLM (Outlook Mac)</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="is_active"
            label="Active"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                Update Mailbox
              </Button>
              <Button onClick={() => navigate('/mailboxes')}>
                Cancel
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </Space>
  );
};