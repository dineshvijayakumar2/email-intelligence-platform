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
  Radio,
  InputNumber
} from "antd";
import {
  FolderOpenOutlined,
  GoogleOutlined,
  WindowsOutlined,
  DisconnectOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  SettingOutlined,
  SaveOutlined
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox } from '../services/mailboxService';
import GoogleDrivePicker from './GoogleDrivePicker';
import GoogleDriveConnection from './GoogleDriveConnection';
import gmailService, { MailboxGmailStatus } from '../services/gmailService';
import outlookService, { MailboxOutlookStatus } from '../services/outlookService';
import { clientService, Client } from '../services/clientService';
import { userService, UserProfile } from '../services/userService';
import { useAuth } from '../contexts/AuthContext';

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
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Per-mailbox Gmail connection state
  const [mailboxGmailStatus, setMailboxGmailStatus] = React.useState<MailboxGmailStatus | null>(null);
  const [connectingGmail, setConnectingGmail] = React.useState(false);
  const [disconnectingGmail, setDisconnectingGmail] = React.useState(false);
  const [syncingGmail, setSyncingGmail] = React.useState(false);

  // Per-mailbox Outlook connection state
  const [mailboxOutlookStatus, setMailboxOutlookStatus] = React.useState<MailboxOutlookStatus | null>(null);
  const [connectingOutlook, setConnectingOutlook] = React.useState(false);
  const [disconnectingOutlook, setDisconnectingOutlook] = React.useState(false);
  const [syncingOutlook, setSyncingOutlook] = React.useState(false);

  // Sync interval configuration
  const [syncInterval, setSyncInterval] = React.useState<number>(15);
  const [showSyncSettings, setShowSyncSettings] = React.useState(false);
  const [savingConfig, setSavingConfig] = React.useState(false);

  // Manual sync state
  const [syncing, setSyncing] = React.useState(false);

  // Client and user assignment state
  const [clients, setClients] = React.useState<any[]>([]);
  const [users, setUsers] = React.useState<any[]>([]);
  const [selectedClientId, setSelectedClientId] = React.useState<string | null>(null);
  const { profile } = useAuth();
  const isAdmin = profile?.roles?.includes('admin');

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
    const init = async () => {
      // Load clients and users FIRST, then mailbox data
      await loadClientsAndUsers();

      if (mailboxId) {
        await loadMailboxData();
        loadMailboxGmailStatus();
        loadMailboxOutlookStatus();
      }
      loadSyncConfig();
    };

    init();
  }, [mailboxId]);

  const loadClientsAndUsers = async () => {
    try {
      // Only admins need clients and users for assignment
      if (!isAdmin) return;

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

  const loadSyncConfig = async () => {
    try {
      const config = await gmailService.getConfig();
      setSyncInterval(config.sync_interval_minutes);
    } catch (error) {
      console.error('Error loading sync config:', error);
    }
  };

  const handleSaveConfig = async () => {
    try {
      setSavingConfig(true);
      const result = await gmailService.updateConfig({
        sync_interval_minutes: syncInterval
      });

      if (result.success) {
        message.success(`Sync interval updated to ${syncInterval} minutes`);
        setShowSyncSettings(false);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('Failed to save sync configuration');
    } finally {
      setSavingConfig(false);
    }
  };

  // Load Gmail status for this specific mailbox
  const loadMailboxGmailStatus = async () => {
    try {
      const status = await gmailService.getMailboxGmailStatus(mailboxId);
      setMailboxGmailStatus(status);
    } catch (error) {
      console.error('Error loading mailbox Gmail status:', error);
    }
  };

  // Connect Gmail directly to this mailbox via OAuth
  const handleConnectGmail = async () => {
    try {
      setConnectingGmail(true);
      const result = await gmailService.connectToMailbox(mailboxId);

      if (result.success) {
        message.success(`Gmail ${result.gmail_email} connected to mailbox`);
        loadMailboxGmailStatus(); // Reload status
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to connect Gmail');
    } finally {
      setConnectingGmail(false);
    }
  };

  // Disconnect Gmail from this mailbox
  const handleDisconnectGmail = async () => {
    try {
      setDisconnectingGmail(true);
      const result = await gmailService.disconnectFromMailbox(mailboxId);

      if (result.success) {
        message.success('Gmail disconnected from mailbox');
        setMailboxGmailStatus({ connected: false, sync_status: 'disconnected', email_count: 0 });
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('Failed to disconnect Gmail');
    } finally {
      setDisconnectingGmail(false);
    }
  };

  // Trigger manual sync for this mailbox
  const handleSyncNow = async () => {
    try {
      setSyncingGmail(true);
      const result = await gmailService.triggerMailboxSync(mailboxId);

      if (result.success) {
        message.success('Sync started');
        // Poll for status update
        setTimeout(loadMailboxGmailStatus, 2000);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('Failed to trigger sync');
    } finally {
      setSyncingGmail(false);
    }
  };

  // Load Outlook status for this specific mailbox
  const loadMailboxOutlookStatus = async () => {
    try {
      const status = await outlookService.getMailboxOutlookStatus(mailboxId);
      setMailboxOutlookStatus(status);
    } catch (error) {
      console.error('Error loading mailbox Outlook status:', error);
    }
  };

  // Connect Outlook directly to this mailbox via OAuth
  const handleConnectOutlook = async () => {
    try {
      setConnectingOutlook(true);
      const result = await outlookService.connectToMailbox(mailboxId);

      if (result.success) {
        message.success(`Outlook ${result.outlook_email} connected to mailbox`);
        loadMailboxOutlookStatus(); // Reload status
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to connect Outlook');
    } finally {
      setConnectingOutlook(false);
    }
  };

  // Disconnect Outlook from this mailbox
  const handleDisconnectOutlook = async () => {
    try {
      setDisconnectingOutlook(true);
      const result = await outlookService.disconnectFromMailbox(mailboxId);

      if (result.success) {
        message.success('Outlook disconnected from mailbox');
        setMailboxOutlookStatus({ connected: false, sync_status: 'disconnected', email_count: 0 });
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('Failed to disconnect Outlook');
    } finally {
      setDisconnectingOutlook(false);
    }
  };

  // Trigger manual Outlook sync for this mailbox
  const handleOutlookSyncNow = async () => {
    try {
      setSyncingOutlook(true);
      const result = await outlookService.triggerMailboxSync(mailboxId);

      if (result.success) {
        message.success('Outlook sync started');
        // Poll for status update
        setTimeout(loadMailboxOutlookStatus, 2000);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('Failed to trigger Outlook sync');
    } finally {
      setSyncingOutlook(false);
    }
  };

  const loadMailboxData = async () => {
    try {
      const data = await mailboxService.getMailbox(mailboxId);
      if (!data) {
        throw new Error('Mailbox not found');
      }
      
      setMailboxData(data);

      // Set selected client for filtering users FIRST (before setting form values)
      if (data.client_id) {
        setSelectedClientId(data.client_id);
      }

      // Set form values and derive state from mailbox configuration
      form.setFieldsValue({
        name: data.name,
        email_address: data.email_address,
        mailbox_type: data.mailbox_type,
        is_active: data.is_active,
        file_path: data.connection_config?.file_path || '',
        client_id: data.client_id || null,
        user_id: data.user_id || null
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

      // Start with existing connection config to preserve Gmail/Outlook connections
      const connectionConfig: any = { ...(mailboxData?.connection_config || {}) };

      // Only update file-related fields for file-based mailbox types
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
          // Clear Google Drive fields if switching to local
          delete connectionConfig.google_drive_file_id;
          delete connectionConfig.google_drive_file_name;
        }
      }

      // Note: Gmail/Outlook connection fields (gmail_sync_enabled, gmail_access_token, etc.)
      // are preserved from the existing connection_config and not modified here

      const mailboxUpdateData: any = {
        name: values.name,
        mailbox_type: values.mailbox_type,
        is_active: values.is_active,
        connection_config: connectionConfig,
        client_id: values.client_id || null,
        user_id: values.user_id || null
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

  const handleMailboxSync = async () => {
    try {
      setSyncing(true);
      await mailboxService.syncMailbox(mailboxId);
      message.success('Sync triggered successfully');
    } catch (error) {
      console.error('Error syncing mailbox:', error);
      message.error('Failed to trigger sync');
    } finally {
      setSyncing(false);
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
              <Select.OptGroup label="LIVE Mailboxes">
                <Option value="gmail">
                  <Space><GoogleOutlined />Gmail</Space>
                </Option>
                <Option value="outlook_live">
                  <Space><WindowsOutlined />Outlook / Office 365</Space>
                </Option>
              </Select.OptGroup>
              <Select.OptGroup label="Archive Files">
                <Option value="mbox">MBOX (Universal Format)</Option>
                <Option value="pst">PST (Outlook Windows)</Option>
                <Option value="olm">OLM (Outlook Mac)</Option>
              </Select.OptGroup>
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

          {/* Gmail Connection Section - for gmail type OR archive mailboxes */}
          {(selectedType === 'gmail' || ['mbox', 'pst', 'olm'].includes(selectedType)) && (
            <>
              <Divider>
                {selectedType === 'gmail' ? 'Gmail Connection' : 'Gmail LIVE Sync'}
              </Divider>
              {mailboxGmailStatus?.connected ? (
                // Connected - show status with sync controls
                <div style={{ marginBottom: 16 }}>
                  <Alert
                    message={
                      <Space>
                        <CheckCircleOutlined style={{ color: '#52c41a' }} />
                        <span>Gmail LIVE Sync Enabled</span>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        <Text type="secondary">
                          <GoogleOutlined style={{ marginRight: 4 }} />
                          {mailboxGmailStatus.gmail_email || 'Connected'}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          <SyncOutlined style={{ marginRight: 4 }} />
                          {mailboxGmailStatus.sync_status === 'syncing'
                            ? 'Syncing now...'
                            : `Last sync: ${gmailService.formatRelativeTime(mailboxGmailStatus.last_sync_at || null)}`
                          }
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {mailboxGmailStatus.email_count} emails synced
                        </Text>
                        {mailboxGmailStatus.error && (
                          <Text type="danger" style={{ fontSize: 12 }}>
                            Error: {mailboxGmailStatus.error}
                          </Text>
                        )}
                      </Space>
                    }
                    type="success"
                    style={{ marginBottom: 12 }}
                    action={
                      <Space direction="vertical" size={4}>
                        <Button
                          size="small"
                          icon={<SyncOutlined spin={syncingGmail} />}
                          onClick={handleSyncNow}
                          loading={syncingGmail}
                        >
                          Sync Now
                        </Button>
                        <Button
                          size="small"
                          danger
                          icon={<DisconnectOutlined />}
                          onClick={handleDisconnectGmail}
                          loading={disconnectingGmail}
                        >
                          Disconnect
                        </Button>
                      </Space>
                    }
                  />

                  {/* Sync Settings */}
                  <div
                    style={{
                      background: 'rgba(82, 196, 26, 0.05)',
                      border: '1px solid rgba(82, 196, 26, 0.2)',
                      borderRadius: 8,
                      padding: 12
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: showSyncSettings ? 12 : 0 }}>
                      <Space>
                        <SettingOutlined />
                        <Text strong style={{ fontSize: 13 }}>Sync Settings</Text>
                      </Space>
                      <Button
                        type="text"
                        size="small"
                        onClick={() => setShowSyncSettings(!showSyncSettings)}
                      >
                        {showSyncSettings ? 'Hide' : 'Configure'}
                      </Button>
                    </div>

                    {showSyncSettings && (
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        <div>
                          <Text type="secondary" style={{ display: 'block', marginBottom: 4, fontSize: 12 }}>
                            Sync Interval (minutes)
                          </Text>
                          <Space>
                            <InputNumber
                              min={1}
                              max={1440}
                              value={syncInterval}
                              onChange={(value) => setSyncInterval(value || 15)}
                              style={{ width: 80 }}
                              size="small"
                            />
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              (1 min - 24 hours)
                            </Text>
                          </Space>
                        </div>
                        <Button
                          type="primary"
                          icon={<SaveOutlined />}
                          onClick={handleSaveConfig}
                          loading={savingConfig}
                          size="small"
                          style={{ background: '#52c41a', borderColor: '#52c41a' }}
                        >
                          Save Settings
                        </Button>
                      </Space>
                    )}
                  </div>
                </div>
              ) : (
                // Not connected - show connect button
                <div
                  style={{
                    background: 'linear-gradient(135deg, rgba(66, 133, 244, 0.08) 0%, rgba(52, 168, 83, 0.08) 100%)',
                    border: '1px dashed rgba(66, 133, 244, 0.3)',
                    borderRadius: 12,
                    padding: 20,
                    marginBottom: 16,
                    textAlign: 'center'
                  }}
                >
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <GoogleOutlined style={{ fontSize: 48, color: '#4285f4' }} />
                    <div>
                      <Text strong style={{ fontSize: 16 }}>Connect Gmail for LIVE Sync</Text>
                    </div>
                    <Text type="secondary">
                      {selectedType === 'gmail'
                        ? 'Connect your Gmail account to start syncing emails from this mailbox.'
                        : 'Link a Gmail account to automatically sync new emails to this mailbox. Each mailbox can have its own Gmail connection.'
                      }
                    </Text>
                    <Button
                      type="primary"
                      icon={<GoogleOutlined />}
                      onClick={handleConnectGmail}
                      loading={connectingGmail}
                      style={{
                        marginTop: 8,
                        background: '#4285f4',
                        borderColor: '#4285f4'
                      }}
                    >
                      {selectedType === 'gmail' ? 'Connect Gmail' : 'Connect Gmail Account'}
                    </Button>
                  </Space>
                </div>
              )}
            </>
          )}

          {/* Outlook Connection Section - for outlook_live type OR archive mailboxes */}
          {(selectedType === 'outlook_live' || ['mbox', 'pst', 'olm'].includes(selectedType)) && (
            <>
              <Divider>
                {selectedType === 'outlook_live' ? 'Outlook Connection' : 'Outlook LIVE Sync'}
              </Divider>
              {mailboxOutlookStatus?.connected ? (
                // Connected - show status with sync controls
                <div style={{ marginBottom: 16 }}>
                  <Alert
                    message={
                      <Space>
                        <CheckCircleOutlined style={{ color: '#0078d4' }} />
                        <span>Outlook LIVE Sync Enabled</span>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        <Text type="secondary">
                          <WindowsOutlined style={{ marginRight: 4, color: '#0078d4' }} />
                          {mailboxOutlookStatus.outlook_email || 'Connected'}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          <SyncOutlined style={{ marginRight: 4 }} />
                          {mailboxOutlookStatus.sync_status === 'syncing'
                            ? 'Syncing now...'
                            : `Last sync: ${outlookService.formatRelativeTime(mailboxOutlookStatus.last_sync_at || null)}`
                          }
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {mailboxOutlookStatus.email_count} emails synced
                        </Text>
                        {mailboxOutlookStatus.error && (
                          <Text type="danger" style={{ fontSize: 12 }}>
                            Error: {mailboxOutlookStatus.error}
                          </Text>
                        )}
                      </Space>
                    }
                    type="info"
                    style={{ marginBottom: 12, borderColor: '#0078d4' }}
                    action={
                      <Space direction="vertical" size={4}>
                        <Button
                          size="small"
                          icon={<SyncOutlined spin={syncingOutlook} />}
                          onClick={handleOutlookSyncNow}
                          loading={syncingOutlook}
                        >
                          Sync Now
                        </Button>
                        <Button
                          size="small"
                          danger
                          icon={<DisconnectOutlined />}
                          onClick={handleDisconnectOutlook}
                          loading={disconnectingOutlook}
                        >
                          Disconnect
                        </Button>
                      </Space>
                    }
                  />
                </div>
              ) : (
                // Not connected - show connect button
                <div
                  style={{
                    background: 'linear-gradient(135deg, rgba(0, 120, 212, 0.08) 0%, rgba(0, 99, 177, 0.08) 100%)',
                    border: '1px dashed rgba(0, 120, 212, 0.3)',
                    borderRadius: 12,
                    padding: 20,
                    marginBottom: 16,
                    textAlign: 'center'
                  }}
                >
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <WindowsOutlined style={{ fontSize: 48, color: '#0078d4' }} />
                    <div>
                      <Text strong style={{ fontSize: 16 }}>Connect Outlook for LIVE Sync</Text>
                    </div>
                    <Text type="secondary">
                      {selectedType === 'outlook_live'
                        ? 'Connect your Outlook account (O365 or personal) to start syncing emails from this mailbox.'
                        : 'Link an Outlook account (O365 or personal) to automatically sync new emails to this mailbox. Each mailbox can have its own Outlook connection.'
                      }
                    </Text>
                    <Button
                      type="primary"
                      icon={<WindowsOutlined />}
                      onClick={handleConnectOutlook}
                      loading={connectingOutlook}
                      style={{
                        marginTop: 8,
                        background: '#0078d4',
                        borderColor: '#0078d4'
                      }}
                    >
                      {selectedType === 'outlook_live' ? 'Connect Outlook' : 'Connect Outlook Account'}
                    </Button>
                  </Space>
                </div>
              )}
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
                  selectedClientId || form.getFieldValue('client_id')
                    ? 'Assign this mailbox to an account manager assigned to the selected client.'
                    : 'First assign this mailbox to a client to see available account managers.'
                }
              >
                <Select
                  placeholder={(selectedClientId || form.getFieldValue('client_id')) ? 'Select account manager (optional)' : 'Select a client first'}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  disabled={!selectedClientId && !form.getFieldValue('client_id')}
                  options={(() => {
                    const clientId = selectedClientId || form.getFieldValue('client_id');
                    if (!clientId) return [];

                    return users
                      .filter((u: any) => {
                        const hasAccountManagerRole = u.roles?.includes('account_manager');
                        const isAssignedToClient = u.assigned_clients?.some((c: any) => c.id === clientId);
                        return hasAccountManagerRole && isAssignedToClient;
                      })
                      .map((u: any) => ({
                        label: `${u.name} (${u.email})`,
                        value: u.id
                      }));
                  })()}
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

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                Update Mailbox
              </Button>
              <Button
                icon={<SyncOutlined spin={syncing} />}
                onClick={handleMailboxSync}
                loading={syncing}
              >
                Sync Now
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