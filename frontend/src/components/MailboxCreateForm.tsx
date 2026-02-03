import React, { useState } from "react";
import { 
  Card, 
  Space, 
  Button, 
  Typography, 
  Form, 
  Input, 
  Select, 
  Switch,
  message,
  Divider,
  Alert,
  Radio
} from "antd";
import { 
  CheckCircleOutlined,
  FolderOpenOutlined,
  GoogleOutlined
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { mailboxService } from '../services/mailboxService';
import GoogleDrivePicker from './GoogleDrivePicker';
import GoogleDriveConnection from './GoogleDriveConnection';
import { clientService } from '../services/clientService';
import { userService } from '../services/userService';
import { useAuth } from '../contexts/AuthContext';

const { Title, Text } = Typography;
const { Option } = Select;

export const MailboxCreateForm: React.FC = () => {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [selectedType, setSelectedType] = React.useState('gmail');
  const [fileSource, setFileSource] = React.useState<'local' | 'google_drive'>('local');
  const [googleDriveFile, setGoogleDriveFile] = React.useState<any>(null);
  const [googleDriveConnected, setGoogleDriveConnected] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Client and user assignment state
  const [clients, setClients] = React.useState<any[]>([]);
  const [users, setUsers] = React.useState<any[]>([]);
  const [selectedClientId, setSelectedClientId] = React.useState<string | null>(null);
  const { profile } = useAuth();
  const isAdmin = profile?.roles?.includes('admin');

  // Load clients and users on mount
  React.useEffect(() => {
    loadClientsAndUsers();
  }, []);

  const loadClientsAndUsers = async () => {
    try {
      // Load clients
      const clientsData = await clientService.list();
      setClients(clientsData.clients || []);

      // Load all users (will be filtered based on client selection)
      const usersData = await userService.getUsers();
      setUsers(usersData || []);
    } catch (error) {
      console.error('Error loading clients and users:', error);
    }
  };
  
  // Generate a consistent user ID based on browser fingerprint or use a stored value
  // In a real app, this would come from authentication context (JWT, session, etc.)
  const getUserId = () => {
    let userId = localStorage.getItem('user_id');
    if (!userId) {
      // Generate a unique ID based on browser characteristics + timestamp
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

  const onFinish = async (values: any) => {
    try {
      setLoading(true);

      // Build connection config based on mailbox type
      const connectionConfig: any = {};

      // All file-based types (MBOX, PST, OLM) use file_path or Google Drive
      if (['mbox', 'pst', 'olm'].includes(values.mailbox_type)) {
        if (fileSource === 'google_drive' && googleDriveFile) {
          // Use the new Google Drive mailbox creation method with OAuth2
          const googleDriveData = {
            name: values.name,
            email_address: values.email_address,
            mailbox_type: values.mailbox_type,
            is_active: values.is_active,
            google_drive_file_id: googleDriveFile.id,
            google_drive_file_name: googleDriveFile.name,
            user_id: userId
          };

          await mailboxService.createGoogleDriveMailbox(googleDriveData);
          message.success("Google Drive mailbox created successfully");
          navigate('/mailboxes');
          return;
        } else {
          connectionConfig.file_path = values.file_path;
          connectionConfig.file_source = 'local';
        }
      }

      const mailboxData: any = {
        name: values.name,
        mailbox_type: values.mailbox_type,
        is_active: values.is_active,
        connection_config: connectionConfig,
        client_id: values.client_id || null,
        user_id: values.user_id || null
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
      
      // Build connection config
      const connectionConfig: any = {};

      // All file-based types (MBOX, PST, OLM) use file_path or Google Drive
      if (['mbox', 'pst', 'olm'].includes(values.mailbox_type)) {
        if (fileSource === 'google_drive' && googleDriveFile) {
          connectionConfig.google_drive_file_id = googleDriveFile.id;
          connectionConfig.google_drive_file_name = googleDriveFile.name;
          connectionConfig.file_source = 'google_drive';
          connectionConfig.user_id = userId; // Include user_id for OAuth2 token lookup
        } else {
          connectionConfig.file_path = values.file_path;
          connectionConfig.file_source = 'local';
        }
      }

      const response = await fetch(`${import.meta.env.API_BASE_URL}/mailboxes/test/test-connection`, {
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
            mailbox_type: 'gmail',
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
                label="File Source"
                required
              >
                <Radio.Group 
                  value={fileSource} 
                  onChange={(e) => setFileSource(e.target.value)}
                  style={{ marginBottom: 16 }}
                >
                  <Radio.Button value="local">
                    <FolderOpenOutlined /> Local File
                  </Radio.Button>
                  <Radio.Button value="google_drive">
                    <GoogleOutlined /> Google Drive
                  </Radio.Button>
                </Radio.Group>
              </Form.Item>

              {fileSource === 'local' ? (
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
              ) : (
                <>
                  <Form.Item label="Google Drive Connection">
                    <GoogleDriveConnection 
                      userId={userId}
                      onConnectionChange={setGoogleDriveConnected}
                    />
                  </Form.Item>
                  
                  {googleDriveConnected && (
                    <Form.Item
                      label="Google Drive File"
                      required
                      help={googleDriveFile ? `Selected: ${googleDriveFile.name}` : 'No file selected'}
                    >
                      <GoogleDrivePicker
                        onFileSelect={(file) => {
                          setGoogleDriveFile(file);
                          message.success(`Selected file: ${file.name}`);
                        }}
                        acceptedFormats={[`.${selectedType}`]}
                      />
                    </Form.Item>
                  )}
                  
                  {!googleDriveConnected && (
                    <Alert
                      message="Google Drive Not Connected"
                      description="Please connect your Google Drive account above to select files."
                      type="warning"
                      style={{ marginBottom: 16 }}
                    />
                  )}
                </>
              )}
              
              <input
                ref={fileInputRef}
                type="file"
                accept={`.${selectedType}`}
                style={{ display: 'none' }}
                onChange={handleFileSelect}
              />
            </>
          )}

          {/* Client and Account Manager Assignment - only visible to admins */}
          {isAdmin && (
            <>
              <Divider>Assignment</Divider>

              <Form.Item
                name="client_id"
                label="Assign to Client"
                help="Assign this mailbox to a client. Client managers assigned to this client will be able to access it."
              >
                <Select
                  placeholder="Select a client (optional)"
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  onChange={(value) => {
                    setSelectedClientId(value || null);
                    // Clear user selection when client changes
                    form.setFieldValue('user_id', null);
                  }}
                  options={clients.map(c => ({
                    label: c.client_name,
                    value: c.id
                  }))}
                />
              </Form.Item>

              <Form.Item
                name="user_id"
                label="Assign to Account Manager"
                help={
                  selectedClientId
                    ? 'Assign this mailbox to an account manager assigned to the selected client.'
                    : 'First assign this mailbox to a client to see available account managers.'
                }
              >
                <Select
                  placeholder={selectedClientId ? 'Select account manager (optional)' : 'Select a client first'}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  disabled={!selectedClientId}
                  options={
                    selectedClientId
                      ? users
                          .filter((u: any) => {
                            const hasAccountManagerRole = u.roles?.includes('account_manager');
                            const isAssignedToClient = u.assigned_clients?.some((c: any) => c.id === selectedClientId);
                            return hasAccountManagerRole && isAssignedToClient;
                          })
                          .map((u: any) => ({
                            label: `${u.name} (${u.email})`,
                            value: u.id
                          }))
                      : []
                  }
                />
              </Form.Item>
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
                disabled={['mbox', 'pst', 'olm'].includes(selectedType) && ((fileSource === 'local' && !form.getFieldValue('file_path')) || (fileSource === 'google_drive' && (!googleDriveConnected || !googleDriveFile)))}
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

export default MailboxCreateForm;