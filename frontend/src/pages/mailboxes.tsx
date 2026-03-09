import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Alert,
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
  Form,
  Select,
  Dropdown,
  Skeleton
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SyncOutlined,
  MailOutlined,
  GoogleOutlined,
  WindowsOutlined,
  LinkOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
  CalendarOutlined,
  TeamOutlined,
  UserOutlined,
  DownOutlined,
  EyeOutlined,
  ExclamationCircleOutlined
} from "@ant-design/icons";
import dayjs from 'dayjs';
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox, hasGmailLiveSync, hasOutlookLiveSync, hasLiveSync, getLiveSyncType } from '../services/mailboxService';
import { MailboxCreateForm } from '../components/MailboxCreateForm';
import { MailboxEditForm } from '../components/MailboxEditForm';
import gmailService from '../services/gmailService';
import outlookService from '../services/outlookService';
import { useAuth } from '../contexts/AuthContext';
import mailboxAssignmentService from '../services/mailboxAssignmentService';
import clientService from '../services/clientService';
import { userService } from '../services/userService';
import ProcessingStatusBadge from '../components/ProcessingStatusBadge';
import { dashboardService } from '../services/dashboardService';
import { formatDate } from '../utils/dateUtils';

const { Text } = Typography;
const { RangePicker } = DatePicker;

export const MailboxList: React.FC = () => {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const isAdmin = useMemo(() => profile?.roles?.includes('admin'), [profile?.roles]);

  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [loading, setLoading] = useState(true);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [outlookConnected, setOutlookConnected] = useState(false);
  const [linkingMailboxId, setLinkingMailboxId] = useState<string | null>(null);
  const [processingJobs, setProcessingJobs] = useState<any[]>([]);

  // Date range fetch modal state
  const [dateRangeModalVisible, setDateRangeModalVisible] = useState(false);
  const [selectedMailboxForFetch, setSelectedMailboxForFetch] = useState<Mailbox | null>(null);
  const [fetchingEmails, setFetchingEmails] = useState(false);
  const [dateRangeForm] = Form.useForm();

  // Assignment modal state
  const [assignmentModalVisible, setAssignmentModalVisible] = useState(false);
  const [assignmentType, setAssignmentType] = useState<'client' | 'user'>('client');
  const [selectedMailboxForAssignment, setSelectedMailboxForAssignment] = useState<Mailbox | null>(null);
  const [clients, setClients] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [assignmentLoading, setAssignmentLoading] = useState(false);
  const [clientsUsersLoading, setClientsUsersLoading] = useState(true); // Track loading state for client/user data

  // Track if component is mounted to prevent state updates after unmount
  const isMountedRef = useRef(true);
  // Use ref to track mailboxes for stale closure prevention
  const mailboxesRef = useRef<Mailbox[]>([]);
  // Use ref to track processingJobs for stale closure prevention
  const processingJobsRef = useRef<any[]>([]);

  // Keep refs in sync with state
  useEffect(() => {
    mailboxesRef.current = mailboxes;
  }, [mailboxes]);

  // Mailboxes where Gmail or Outlook auth has expired and needs user reconnection
  const mailboxesWithExpiredAuth = useMemo(() => {
    return mailboxes.filter(m => {
      const cfg = (m.connection_config || {}) as Record<string, unknown>;
      return cfg.gmail_sync_status === 'auth_expired' || cfg.outlook_sync_status === 'auth_expired';
    });
  }, [mailboxes]);

  useEffect(() => {
    processingJobsRef.current = processingJobs;
  }, [processingJobs]);

  useEffect(() => {
    isMountedRef.current = true;

    // Only load once on mount, not on every isAdmin change
    loadMailboxes();
    checkGmailConnection();
    checkOutlookConnection();
    loadProcessingJobs();
    if (isAdmin) {
      loadClientsAndUsers();
    }

    // Poll for job updates every 5 seconds
    const interval = setInterval(() => {
      if (isMountedRef.current) {
        loadProcessingJobs();
      }
    }, 5000);

    return () => {
      isMountedRef.current = false;
      clearInterval(interval);
    };
  }, []); // Empty dependency array - only run once on mount

  // Separate effect for when isAdmin changes (to load clients/users)
  useEffect(() => {
    if (isAdmin) {
      loadClientsAndUsers();
    }
  }, [isAdmin]);

  const checkGmailConnection = async () => {
    if (!profile?.id) return;
    try {
      const connected = await gmailService.isConnected(profile.id);
      setGmailConnected(connected);
    } catch (error) {
      console.error('Error checking Gmail connection:', error);
    }
  };

  const checkOutlookConnection = async () => {
    if (!profile?.id) return;
    try {
      const connected = await outlookService.isConnected(profile.id);
      setOutlookConnected(connected);
    } catch (error) {
      console.error('Error checking Outlook connection:', error);
    }
  };

  const loadClientsAndUsers = async () => {
    try {
      setClientsUsersLoading(true);
      const [clientsData, usersData] = await Promise.all([
        clientService.list(),
        userService.getAccountManagers()
      ]);
      setClients(clientsData.clients || []);
      setUsers(usersData || []);
    } catch (error) {
      console.error('Error loading clients and users:', error);
    } finally {
      setClientsUsersLoading(false);
    }
  };

  const loadProcessingJobs = async () => {
    try {
      const jobs = await dashboardService._fetchProcessingJobs();
      if (!isMountedRef.current) return;

      // Preserve existing data if API returns empty (transient failure)
      if (jobs && Array.isArray(jobs)) {
        if (jobs.length > 0 || processingJobsRef.current.length === 0) {
          setProcessingJobs(jobs);
        }
      }
    } catch (error) {
      console.error('Error loading processing jobs:', error);
    }
  };

  const loadMailboxes = async () => {
    try {
      if (isMountedRef.current) setLoading(true);
      const data = await mailboxService.getMailboxes();

      if (!isMountedRef.current) return;

      console.log('[Mailboxes] Loaded data:', data?.length || 0, 'mailboxes');

      // Preserve existing data if service returns empty (transient hiccup)
      if (data && data.length > 0) {
        setMailboxes(data);
      } else if (mailboxesRef.current.length === 0) {
        // Only set empty if we have no existing data
        setMailboxes(data || []);
      } else {
        console.warn('[Mailboxes] Received empty data, preserving existing mailboxes');
      }
    } catch (error) {
      console.error('[Mailboxes] Error loading mailboxes:', error);
      // Show error message to user
      message.error('Failed to load mailboxes. Please refresh the page.');
    } finally {
      if (isMountedRef.current) setLoading(false);
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

  const handleOpenAssignment = (mailbox: Mailbox, type: 'client' | 'user') => {
    setSelectedMailboxForAssignment(mailbox);
    setAssignmentType(type);
    setAssignmentModalVisible(true);
  };

  const handleAssignmentSubmit = async (value: string | null) => {
    if (!selectedMailboxForAssignment) return;

    try {
      setAssignmentLoading(true);

      if (assignmentType === 'client') {
        await mailboxAssignmentService.assignToClient(selectedMailboxForAssignment.id, value);
        message.success('Mailbox assigned to client successfully');
      } else {
        await mailboxAssignmentService.assignToUser(selectedMailboxForAssignment.id, value);
        message.success('Mailbox assigned to account manager successfully');
      }

      setAssignmentModalVisible(false);
      loadMailboxes(); // Reload to show updated assignments
    } catch (error: any) {
      message.error(error.message || 'Failed to assign mailbox');
    } finally {
      setAssignmentLoading(false);
    }
  };

  const handleLinkGmail = async (mailboxId: string, mailboxName: string) => {
    if (!gmailConnected) {
      message.warning('Please connect your Gmail account from the Dashboard first');
      navigate('/');
      return;
    }

    if (!profile?.id) {
      message.error('User not authenticated');
      return;
    }

    try {
      setLinkingMailboxId(mailboxId);
      message.loading({ content: `Linking Gmail to ${mailboxName}...`, key: 'link-gmail' });

      const result = await gmailService.extendMailboxWithGmail(mailboxId, profile.id);

      if (result.success) {
        const linkedEmail = (result.mailbox as any)?.connection_config?.gmail_email;
        const currentMailbox = mailboxes.find(m => m.id === mailboxId);

        // Validate: prevent linking a different Gmail account
        if (linkedEmail && currentMailbox?.email_address) {
          if (linkedEmail.toLowerCase() !== currentMailbox.email_address.toLowerCase()) {
            message.error({
              content: `Cannot link ${linkedEmail}. This mailbox is already associated with ${currentMailbox.email_address}. Please use the same account or remove the existing link first.`,
              key: 'link-gmail',
              duration: 6,
            });
            setLinkingMailboxId(null);
            return;
          }
        }

        // Auto-populate email_address if available and not set
        if (linkedEmail && currentMailbox && !currentMailbox.email_address) {
          try {
            await mailboxService.updateMailbox(mailboxId, {
              email_address: linkedEmail
            });
          } catch (updateError) {
            console.error('Failed to auto-populate email_address:', updateError);
          }
        }

        message.success({ content: result.message, key: 'link-gmail' });
        mailboxService.clearCache();
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

  const handleLinkOutlook = async (mailboxId: string, mailboxName: string) => {
    if (!outlookConnected) {
      message.warning('Please connect your Outlook account from the Dashboard first');
      navigate('/');
      return;
    }

    if (!profile?.id) {
      message.error('User not authenticated');
      return;
    }

    try {
      setLinkingMailboxId(mailboxId);
      message.loading({ content: `Linking Outlook to ${mailboxName}...`, key: 'link-outlook' });

      const result = await outlookService.extendMailboxWithOutlook(mailboxId, profile.id);

      if (result.success) {
        const linkedEmail = (result.mailbox as any)?.connection_config?.outlook_email;
        const currentMailbox = mailboxes.find(m => m.id === mailboxId);

        // Validate: prevent linking a different Outlook account
        if (linkedEmail && currentMailbox?.email_address) {
          if (linkedEmail.toLowerCase() !== currentMailbox.email_address.toLowerCase()) {
            message.error({
              content: `Cannot link ${linkedEmail}. This mailbox is already associated with ${currentMailbox.email_address}. Please use the same account or remove the existing link first.`,
              key: 'link-outlook',
              duration: 6,
            });
            setLinkingMailboxId(null);
            return;
          }
        }

        // Auto-populate email_address if available and not set
        if (linkedEmail && currentMailbox && !currentMailbox.email_address) {
          try {
            await mailboxService.updateMailbox(mailboxId, {
              email_address: linkedEmail
            });
          } catch (updateError) {
            console.error('Failed to auto-populate email_address:', updateError);
          }
        }

        message.success({ content: result.message, key: 'link-outlook' });
        mailboxService.clearCache();
        loadMailboxes(); // Reload to show updated status
      } else {
        message.error({ content: result.message, key: 'link-outlook' });
      }
    } catch (error) {
      message.error({ content: 'Failed to link Outlook', key: 'link-outlook' });
    } finally {
      setLinkingMailboxId(null);
    }
  };

  const handleReconnectGmail = async (mailboxId: string, mailboxName: string) => {
    try {
      setLinkingMailboxId(mailboxId);
      message.loading({ content: `Reconnecting Gmail for ${mailboxName}...`, key: 'reconnect-gmail' });
      const result = await gmailService.connectToMailbox(mailboxId);
      if (result.success) {
        const linkedEmail = result.gmail_email;
        const currentMailbox = mailboxes.find(m => m.id === mailboxId);

        // Validate: prevent reconnecting with a different Gmail account
        if (linkedEmail && currentMailbox?.email_address) {
          if (linkedEmail.toLowerCase() !== currentMailbox.email_address.toLowerCase()) {
            message.error({
              content: `Cannot reconnect with ${linkedEmail}. This mailbox is associated with ${currentMailbox.email_address}. Please use the same Gmail account.`,
              key: 'reconnect-gmail',
              duration: 6,
            });
            setLinkingMailboxId(null);
            return;
          }
        }

        // Auto-populate email_address if available and not set
        if (linkedEmail && currentMailbox && !currentMailbox.email_address) {
          try {
            await mailboxService.updateMailbox(mailboxId, {
              email_address: linkedEmail
            });
          } catch (updateError) {
            console.error('Failed to auto-populate email_address:', updateError);
          }
        }

        message.success({ content: result.message || 'Gmail reconnected successfully', key: 'reconnect-gmail' });
        mailboxService.clearCache();
        loadMailboxes();
      } else {
        message.error({ content: result.message || 'Failed to reconnect Gmail', key: 'reconnect-gmail' });
      }
    } catch (error: any) {
      if (error?.message?.includes('cancelled')) {
        message.info({ content: 'Reconnection cancelled', key: 'reconnect-gmail' });
      } else {
        message.error({ content: error?.message || 'Failed to reconnect Gmail', key: 'reconnect-gmail' });
      }
    } finally {
      setLinkingMailboxId(null);
    }
  };

  const handleReconnectOutlook = async (mailboxId: string, mailboxName: string) => {
    try {
      setLinkingMailboxId(mailboxId);
      message.loading({ content: `Reconnecting Outlook for ${mailboxName}...`, key: 'reconnect-outlook' });
      const result = await outlookService.connectToMailbox(mailboxId);
      if (result.success) {
        const linkedEmail = result.outlook_email;
        const currentMailbox = mailboxes.find(m => m.id === mailboxId);

        // Validate: prevent reconnecting with a different Outlook account
        if (linkedEmail && currentMailbox?.email_address) {
          if (linkedEmail.toLowerCase() !== currentMailbox.email_address.toLowerCase()) {
            message.error({
              content: `Cannot reconnect with ${linkedEmail}. This mailbox is associated with ${currentMailbox.email_address}. Please use the same Outlook account.`,
              key: 'reconnect-outlook',
              duration: 6,
            });
            setLinkingMailboxId(null);
            return;
          }
        }

        // Auto-populate email_address if available and not set
        if (linkedEmail && currentMailbox && !currentMailbox.email_address) {
          try {
            await mailboxService.updateMailbox(mailboxId, {
              email_address: linkedEmail
            });
          } catch (updateError) {
            console.error('Failed to auto-populate email_address:', updateError);
          }
        }

        message.success({ content: result.message || 'Outlook reconnected successfully', key: 'reconnect-outlook' });
        mailboxService.clearCache();
        loadMailboxes();
      } else {
        message.error({ content: result.message || 'Failed to reconnect Outlook', key: 'reconnect-outlook' });
      }
    } catch (error: any) {
      if (error?.message?.includes('cancelled')) {
        message.info({ content: 'Reconnection cancelled', key: 'reconnect-outlook' });
      } else {
        message.error({ content: error?.message || 'Failed to reconnect Outlook', key: 'reconnect-outlook' });
      }
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

    if (!profile?.id) {
      message.error('User not authenticated');
      return;
    }

    const { dateRange, maxEmails } = values;
    if (!dateRange || dateRange.length !== 2) {
      message.error('Please select a date range');
      return;
    }

    const startDate = dateRange[0].format('YYYY-MM-DD');
    const endDate = dateRange[1].format('YYYY-MM-DD');

    // Determine which service to use based on sync type
    const syncType = getLiveSyncType(selectedMailboxForFetch);

    try {
      setFetchingEmails(true);
      let result;

      if (syncType === 'outlook') {
        result = await outlookService.fetchEmailsByDateRange(
          selectedMailboxForFetch.id,
          profile.id,
          startDate,
          endDate,
          maxEmails
        );
      } else {
        // Default to Gmail
        result = await gmailService.fetchEmailsByDateRange(
          selectedMailboxForFetch.id,
          profile.id,
          startDate,
          endDate,
          maxEmails
        );
      }

      if (result.success) {
        message.success(`${result.message}. Job ID: ${result.job_id}`);
        setDateRangeModalVisible(false);
        // Navigate to processing page filtered to this mailbox
        navigate(`/processing/${selectedMailboxForFetch.id}`);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('Failed to start email fetch');
    } finally {
      setFetchingEmails(false);
    }
  };

  // Helper: Detect email provider from domain for validation
  const getEmailProvider = (email?: string): 'gmail' | 'outlook' | 'unknown' => {
    if (!email) return 'unknown';
    const domain = email.toLowerCase().split('@')[1];
    if (domain === 'gmail.com') return 'gmail';
    if (['outlook.com', 'hotmail.com', 'live.com', 'msn.com'].includes(domain)) return 'outlook';
    return 'unknown';
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
        const cfg = (record.connection_config || {}) as Record<string, unknown>;
        const isAuthExpired = cfg.gmail_sync_status === 'auth_expired' || cfg.outlook_sync_status === 'auth_expired';

        return (
          <Space size={4}>
            <Tag color={colors[displayType] || 'default'}>
              {labels[displayType] || displayType.toUpperCase()}
            </Tag>
            {isLiveEnabled && !isAuthExpired && (
              <Tag color="cyan" icon={<ThunderboltOutlined />}>
                LIVE
              </Tag>
            )}
            {isAuthExpired && (
              <Tag color="warning" icon={<ExclamationCircleOutlined />}>
                Reconnect
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
      title: 'Sync Status',
      key: 'sync_status',
      render: (_: any, record: Mailbox) => (
        <ProcessingStatusBadge
          mailboxId={record.id}
          jobs={processingJobs}
          showProgress={false}
          onClick={() => navigate(`/processing/${record.id}`)}
        />
      ),
    },
    {
      title: 'Errors',
      key: 'errors',
      width: 100,
      render: (_: any, record: Mailbox) => {

        // Count failed jobs for this mailbox
        const failedJobs = processingJobs.filter(
          j => j.mailbox_id === record.id && (j.status === 'failed' || j.failed_records > 0)
        );
        const totalFailed = failedJobs.reduce((sum, j) => sum + (j.failed_records || 0), 0);

        if (totalFailed === 0 && failedJobs.length === 0) {
          return <Text type="secondary">-</Text>;
        }

        return (
          <Button
            type="link"
            danger
            size="small"
            icon={<ExclamationCircleOutlined />}
            onClick={() => navigate(`/errors/${record.id}`)}
          >
            {totalFailed > 0 ? totalFailed : failedJobs.length}
          </Button>
        );
      },
    },
    ...(isAdmin ? [{
      title: 'Client',
      dataIndex: 'client_id',
      key: 'client_id',
      render: (clientId: string, record: any) => {
        // Show skeleton while clients are loading
        if (clientsUsersLoading) {
          return <Skeleton.Input active size="small" style={{ width: 100 }} />;
        }
        const client = clients.find(c => c.id === clientId);
        return client ? (
          <Space>
            <TeamOutlined />
            <Text>{client.client_name}</Text>
          </Space>
        ) : (
          <Button
            size="small"
            type="link"
            icon={<TeamOutlined />}
            onClick={() => handleOpenAssignment(record, 'client')}
          >
            Assign Client
          </Button>
        );
      },
    },
    {
      title: 'Account Manager',
      dataIndex: 'user_id',
      key: 'user_id',
      render: (userId: string, record: any) => {
        // Show skeleton while users are loading
        if (clientsUsersLoading) {
          return <Skeleton.Input active size="small" style={{ width: 100 }} />;
        }
        const user = users.find(u => u.id === userId);
        return user ? (
          <Space>
            <UserOutlined />
            <Text>{user.name}</Text>
          </Space>
        ) : (
          <Button
            size="small"
            type="link"
            icon={<UserOutlined />}
            onClick={() => handleOpenAssignment(record, 'user')}
          >
            Assign User
          </Button>
        );
      },
    }] : []),
    {
      title: 'Emails',
      dataIndex: 'total_emails',
      key: 'total_emails',
      render: (count: number, record: Mailbox) => (
        <Button
          type="link"
          size="small"
          icon={<MailOutlined />}
          onClick={() => navigate(`/emails/${record.id}`)}
          style={{ padding: 0 }}
        >
          {count.toLocaleString()}
        </Button>
      ),
    },
    {
      title: 'Last Sync',
      dataIndex: 'last_sync_at',
      key: 'last_sync_at',
      render: (date: string) => {
        if (!date) return 'Never';
        return formatDate(date);
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, record: Mailbox) => {
        const isGmailLive = hasGmailLiveSync(record);
        const isOutlookLive = hasOutlookLiveSync(record);
        const isAnyLiveSync = hasLiveSync(record) || ['gmail', 'outlook_live'].includes(record.mailbox_type);
        const isArchiveType = ['mbox', 'pst', 'olm'].includes(record.mailbox_type);
        const actionCfg = (record.connection_config || {}) as Record<string, unknown>;
        const gmailAuthExpired = actionCfg.gmail_sync_status === 'auth_expired';
        const outlookAuthExpired = actionCfg.outlook_sync_status === 'auth_expired';

        // Guardrail 1: Mutual exclusivity - don't allow linking to both providers
        const isAlreadyLinked = isGmailLive || isOutlookLive;

        // Guardrail 2: Email domain validation - only show appropriate Link button
        const emailProvider = getEmailProvider(record.email_address);
        const canLinkGmail = isArchiveType && !isAlreadyLinked && gmailConnected &&
          (emailProvider === 'gmail' || emailProvider === 'unknown');
        const canLinkOutlook = isArchiveType && !isAlreadyLinked && outlookConnected &&
          (emailProvider === 'outlook' || emailProvider === 'unknown');

        // Consolidated sync menu
        const syncMenuItems = [
          {
            key: 'sync-now',
            icon: <SyncOutlined />,
            label: 'Sync Now',
            onClick: () => handleSync(record.id, record.name)
          },
          ...(isAnyLiveSync ? [{
            key: 'fetch-range',
            icon: <CalendarOutlined />,
            label: 'Fetch Date Range',
            onClick: () => handleOpenDateRangeFetch(record)
          }] : []),
          {
            key: 'view-history',
            icon: <EyeOutlined />,
            label: 'View Sync History',
            onClick: () => navigate(`/processing/${record.id}`)
          }
        ];

        return (
          <Space wrap>
            <Dropdown.Button
              type="primary"
              size="small"
              icon={<DownOutlined />}
              menu={{ items: syncMenuItems }}
              onClick={() => handleSync(record.id, record.name)}
              disabled={!record.is_active}
            >
              <SyncOutlined /> Sync
            </Dropdown.Button>
            {/* Reconnect buttons - shown when OAuth token has expired */}
            {gmailAuthExpired && (
              <Button
                size="small"
                danger
                icon={<GoogleOutlined />}
                onClick={() => handleReconnectGmail(record.id, record.name)}
                loading={linkingMailboxId === record.id}
              >
                Reconnect Gmail
              </Button>
            )}
            {outlookAuthExpired && (
              <Button
                size="small"
                danger
                icon={<WindowsOutlined />}
                onClick={() => handleReconnectOutlook(record.id, record.name)}
                loading={linkingMailboxId === record.id}
              >
                Reconnect Outlook
              </Button>
            )}
            {/* Link Gmail - enforces mutual exclusivity and email domain validation */}
            {canLinkGmail && (
              <Button
                size="small"
                icon={<LinkOutlined />}
                onClick={() => handleLinkGmail(record.id, record.name)}
                loading={linkingMailboxId === record.id}
                title="Link Gmail account for LIVE sync"
                style={{
                  color: '#4285f4',
                  borderColor: '#4285f4'
                }}
              >
                <GoogleOutlined /> Link Gmail
              </Button>
            )}
            {/* Link Outlook - enforces mutual exclusivity and email domain validation */}
            {canLinkOutlook && (
              <Button
                size="small"
                icon={<LinkOutlined />}
                onClick={() => handleLinkOutlook(record.id, record.name)}
                loading={linkingMailboxId === record.id}
                title="Link Outlook account for LIVE sync"
                style={{
                  color: '#0078d4',
                  borderColor: '#0078d4'
                }}
              >
                <WindowsOutlined /> Link Outlook
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

      {/* Auth Expired Banner */}
      {mailboxesWithExpiredAuth.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message={`${mailboxesWithExpiredAuth.length} mailbox${mailboxesWithExpiredAuth.length > 1 ? 'es need' : ' needs'} reauthentication`}
          description={`${mailboxesWithExpiredAuth.map(m => m.name).join(', ')} — the Gmail or Outlook connection has expired. Find the mailbox below and click the Reconnect action to restore sync.`}
          style={{ marginBottom: 16, borderRadius: 8 }}
          closable
        />
      )}

      {/* Table */}
      <div className="glass-table-container fade-in-up stagger-1">
        {loading && mailboxes.length === 0 ? (
          <div style={{ padding: 24 }}>
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} style={{ display: 'flex', gap: 16, marginBottom: 20, alignItems: 'center' }}>
                <Skeleton.Input active size="small" style={{ width: 140 }} />
                <Skeleton.Button active size="small" style={{ width: 60 }} />
                <Skeleton.Input active size="small" style={{ width: 100 }} />
                <Skeleton.Input active size="small" style={{ width: 80 }} />
                <Skeleton.Input active size="small" style={{ width: 70 }} />
                <Skeleton.Input active size="small" style={{ width: 90 }} />
                <Space>
                  <Skeleton.Button active size="small" />
                  <Skeleton.Button active size="small" />
                </Space>
              </div>
            ))}
          </div>
        ) : (
          <Table
            dataSource={mailboxes}
            columns={columns}
            rowKey="id"
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total, range) =>
                `${range[0]}-${range[1]} of ${total} mailboxes`,
            }}
          />
        )}
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
        {(() => {
          const syncType = selectedMailboxForFetch ? getLiveSyncType(selectedMailboxForFetch) : null;
          const providerName = syncType === 'outlook' ? 'Outlook' : 'Gmail';
          const providerIcon = syncType === 'outlook' ? <WindowsOutlined style={{ color: '#0078d4' }} /> : <GoogleOutlined style={{ color: '#4285f4' }} />;
          return (
            <div style={{ marginBottom: 16 }}>
              <Text type="secondary">
                Pull historical emails from {providerIcon} <strong>{providerName}</strong> for <strong>{selectedMailboxForFetch?.name}</strong> within a specific date range.
                This uses the LIVE sync connection to fetch older emails on-demand.
              </Text>
            </div>
          );
        })()}

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

      {/* Assignment Modal */}
      {isAdmin && (
        <Modal
          title={
            <Space>
              {assignmentType === 'client' ? <TeamOutlined /> : <UserOutlined />}
              <span>
                Assign {assignmentType === 'client' ? 'Client' : 'Account Manager'} to {selectedMailboxForAssignment?.name}
              </span>
            </Space>
          }
          open={assignmentModalVisible}
          onCancel={() => setAssignmentModalVisible(false)}
          footer={null}
          destroyOnClose
        >
          <div style={{ marginTop: 24 }}>
            <Select
              style={{ width: '100%' }}
              placeholder={`Select ${assignmentType === 'client' ? 'client' : 'account manager'}`}
              onChange={(value) => handleAssignmentSubmit(value)}
              loading={assignmentLoading}
              showSearch
              optionFilterProp="label"
              allowClear
              options={
                assignmentType === 'client'
                  ? clients.map(c => ({ label: c.client_name, value: c.id }))
                  : (() => {
                      // Filter users based on mailbox's client assignment
                      const mailboxClientId = selectedMailboxForAssignment?.client_id;
                      let filteredUsers = users;

                      if (mailboxClientId) {
                        // Show only account_managers assigned to this mailbox's client
                        filteredUsers = users.filter((u: any) => {
                          const hasAccountManagerRole = u.roles?.includes('account_manager');
                          const isAssignedToClient = u.assigned_clients?.some((c: any) => c.id === mailboxClientId);
                          return hasAccountManagerRole && isAssignedToClient;
                        });
                      }

                      return filteredUsers.map(u => ({ label: `${u.name} (${u.email})`, value: u.id }));
                    })()
              }
            />
            <div style={{ marginTop: 16 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {assignmentType === 'client'
                  ? 'Assign this mailbox to a client. Client Managers assigned to this client will be able to access it.'
                  : selectedMailboxForAssignment?.client_id
                    ? 'Assign this mailbox to an account manager who is assigned to this client.'
                    : 'First assign this mailbox to a client, then assign an account manager.'}
              </Text>
            </div>
          </div>
        </Modal>
      )}
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