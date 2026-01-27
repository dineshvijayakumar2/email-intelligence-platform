import React, { useState, useEffect } from "react";
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
  FolderOpenOutlined,
  GoogleOutlined,
  ThunderboltOutlined,
  LinkOutlined,
  DisconnectOutlined,
  CheckCircleOutlined,
  SyncOutlined
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox, hasGmailLiveSync } from '../services/mailboxService';
import GoogleDrivePicker from './GoogleDrivePicker';
import GoogleDriveConnection from './GoogleDriveConnection';
import gmailService from '../services/gmailService';

const { Title, Text } = Typography;
const { Option } = Select;

interface MailboxEditFormProps {
  mailboxId: string;
}

export const MailboxEditForm: React.FC<MailboxEditFormProps> = ({ mailboxId }) => {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);
  const [mailboxData, setMailboxData] = React.useState<Mailbox | null>(null);
  const [initialLoading, setInitialLoading] = React.useState(true);
  const [selectedType, setSelectedType] = React.useState('mbox');
  const [fileSource, setFileSource] = React.useState<'local' | 'google_drive'>('local');
  const [googleDriveFile, setGoogleDriveFile] = React.useState<any>(null);
  const [googleDriveConnected, setGoogleDriveConnected] = React.useState(false);
  const [gmailConnected, setGmailConnected] = React.useState(false);
  const [gmailLinking, setGmailLinking] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

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

  useEffect(() => {
    if (mailboxId) {
      loadMailboxData();
    }
    checkGmailConnection();
  }, [mailboxId]);

  const checkGmailConnection = async () => {
    try {
      const connected = await gmailService.isConnected(userId);
      setGmailConnected(connected);
    } catch (error) {
      console.error('Error checking Gmail connection:', error);
    }
  };

  const handleLinkGmail = async () => {
    if (!gmailConnected) {
      message.warning('Please connect your Gmail account from the Dashboard first');
      navigate('/');
      return;
    }

    try {
      setGmailLinking(true);
      const result = await gmailService.extendMailboxWithGmail(mailboxId, userId);

      if (result.success) {
        message.success(result.message);
        loadMailboxData(); // Reload to show updated status
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('Failed to link Gmail');
    } finally {
      setGmailLinking(false);
    }
  };

  const loadMailboxData = async () => {
    try {
      const data = await mailboxService.getMailbox(mailboxId);
      if (!data) {
        throw new Error('Mailbox not found');
      }
      
      setMailboxData(data);
      
      // Set form values and derive state from mailbox configuration
      form.setFieldsValue({
        name: data.name,
        email_address: data.email_address,
        mailbox_type: data.mailbox_type,
        is_active: data.is_active,
        file_path: data.connection_config?.file_path || ''
      });
      
      // Determine file source and setup state
      setSelectedType(data.mailbox_type || 'mbox');
      if (data.connection_config?.file_source === 'google_drive') {
        setFileSource('google_drive');
        if (data.connection_config?.google_drive_file_name) {
          setGoogleDriveFile({
            id: data.connection_config.google_drive_file_id,
            name: data.connection_config.google_drive_file_name
          });
        }
        // Check if Google Drive is connected for this user
        setGoogleDriveConnected(!!data.connection_config.user_id);
      } else {
        setFileSource('local');
      }
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
      setLoading(true);

      // Build connection config based on file source
      const connectionConfig: any = {};
      
      if (['mbox', 'pst', 'olm'].includes(values.mailbox_type)) {
        if (fileSource === 'google_drive' && googleDriveFile) {
          // Use Google Drive configuration with OAuth2
          connectionConfig.google_drive_file_id = googleDriveFile.id;
          connectionConfig.google_drive_file_name = googleDriveFile.name;
          connectionConfig.file_source = 'google_drive';
          connectionConfig.user_id = userId; // Include user_id for backend token lookup
        } else {
          connectionConfig.file_path = values.file_path;
          connectionConfig.file_source = 'local';
        }
      }

      const mailboxUpdateData: any = {
        name: values.name,
        mailbox_type: values.mailbox_type,
        is_active: values.is_active,
        connection_config: connectionConfig
      };

      // Only add email_address if provided
      if (values.email_address) {
        mailboxUpdateData.email_address = values.email_address;
      }

      await mailboxService.updateMailbox(mailboxId, mailboxUpdateData);
      message.success("Mailbox updated successfully");
      navigate('/mailboxes');
    } catch (error) {
      console.error('Error updating mailbox:', error);
      message.error("Failed to update mailbox");
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      form.setFieldValue('file_path', file.webkitRelativePath || file.name);
    }
  };

  const handleFileBrowse = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
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

          {/* Gmail LIVE Sync Section - only for archive mailboxes */}
          {['mbox', 'pst', 'olm'].includes(selectedType) && (
            <>
              <Divider>Gmail LIVE Sync</Divider>
              {hasGmailLiveSync(mailboxData) ? (
                // Already linked - show status
                <Alert
                  message={
                    <Space>
                      <CheckCircleOutlined style={{ color: '#52c41a' }} />
                      <span>Gmail LIVE Sync Enabled</span>
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size={4}>
                      <Text type="secondary">
                        <GoogleOutlined style={{ marginRight: 4 }} />
                        {mailboxData.connection_config?.gmail_email || 'Connected'}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        Linked on {new Date(mailboxData.connection_config?.gmail_extended_at || '').toLocaleDateString()}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <SyncOutlined style={{ marginRight: 4 }} />
                        New emails are automatically synced every 15 minutes
                      </Text>
                    </Space>
                  }
                  type="success"
                  style={{ marginBottom: 16 }}
                />
              ) : (
                // Not linked - show option to link
                <div
                  style={{
                    background: 'linear-gradient(135deg, rgba(66, 133, 244, 0.08) 0%, rgba(52, 168, 83, 0.08) 100%)',
                    border: '1px dashed rgba(66, 133, 244, 0.3)',
                    borderRadius: 12,
                    padding: 20,
                    marginBottom: 16
                  }}
                >
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <ThunderboltOutlined style={{ color: '#4285f4', fontSize: 18 }} />
                      <Text strong>Enable Gmail LIVE Sync</Text>
                    </div>
                    <Text type="secondary">
                      Link your Gmail account to keep this mailbox synced with new emails.
                      Only new emails will be synced - your archived emails remain intact.
                    </Text>
                    <Button
                      icon={<LinkOutlined />}
                      onClick={handleLinkGmail}
                      loading={gmailLinking}
                      disabled={!gmailConnected}
                      style={{
                        color: gmailConnected ? '#4285f4' : undefined,
                        borderColor: gmailConnected ? '#4285f4' : undefined
                      }}
                    >
                      <GoogleOutlined /> Link Gmail for LIVE Sync
                    </Button>
                    {!gmailConnected && (
                      <Alert
                        message="Gmail Not Connected"
                        description="Connect your Gmail account from the Dashboard first to enable LIVE sync."
                        type="warning"
                        showIcon
                        style={{ marginTop: 8 }}
                      />
                    )}
                  </Space>
                </div>
              )}
            </>
          )}

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

export default MailboxEditForm;