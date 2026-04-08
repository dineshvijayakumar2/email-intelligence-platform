import React, { useState, useEffect } from "react";
import {
  FolderOpen,
  CheckCircle2,
  RefreshCw,
  Settings,
  Save,
  Calendar,
  History,
  Unplug,
} from "lucide-react";
import { Spinner } from '@/lib/icons';
import { toast } from '@/lib/toast';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import dayjs from 'dayjs';
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox } from '../services/mailboxService';
import GoogleDrivePicker from './GoogleDrivePicker';
import GoogleDriveConnection from './GoogleDriveConnection';
import gmailService, { MailboxGmailStatus } from '../services/gmailService';
import outlookService, { MailboxOutlookStatus } from '../services/outlookService';
import { clientService, Client } from '../services/clientService';
import { userService, UserProfile } from '../services/userService';
import { useAuth } from '../contexts/AuthContext';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';

interface MailboxEditFormProps {
  mailboxId: string;
}

export const MailboxEditForm: React.FC<MailboxEditFormProps> = ({ mailboxId }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = React.useState(false);
  const [mailboxData, setMailboxData] = React.useState<Mailbox | null>(null);
  const [initialLoading, setInitialLoading] = React.useState(true);
  const [selectedType, setSelectedType] = React.useState('mbox');
  const [fileSource, setFileSource] = React.useState<'local' | 'google_drive'>('local');
  const [googleDriveFile, setGoogleDriveFile] = React.useState<any>(null);
  const [googleDriveConnected, setGoogleDriveConnected] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Form field state
  const [formName, setFormName] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formMailboxType, setFormMailboxType] = useState('mbox');
  const [formFilePath, setFormFilePath] = useState('');
  const [formIsActive, setFormIsActive] = useState(true);
  const [formClientId, setFormClientId] = useState<string | null>(null);
  const [formUserId, setFormUserId] = useState<string | null>(null);

  // Validation state
  const [errors, setErrors] = useState<Record<string, string>>({});

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

  // Date range fetch state
  const [dateRangeModalVisible, setDateRangeModalVisible] = React.useState(false);
  const [fetchingEmails, setFetchingEmails] = React.useState(false);
  const [dateRangeStart, setDateRangeStart] = useState('');
  const [dateRangeEnd, setDateRangeEnd] = useState('');
  const [dateRangeMax, setDateRangeMax] = useState(500);

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
        toast.success(`Sync interval updated to ${syncInterval} minutes`);
        setShowSyncSettings(false);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to save sync configuration');
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
        toast.success(`Gmail ${result.gmail_email} connected to mailbox`);
        loadMailboxGmailStatus(); // Reload status
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to connect Gmail');
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
        toast.success('Gmail disconnected from mailbox');
        setMailboxGmailStatus({ connected: false, sync_status: 'disconnected', email_count: 0 });
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to disconnect Gmail');
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
        toast.success('Sync started');
        // Poll for status update
        setTimeout(loadMailboxGmailStatus, 2000);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to trigger sync');
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
        toast.success(`Outlook ${result.outlook_email} connected to mailbox`);
        loadMailboxOutlookStatus(); // Reload status
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to connect Outlook');
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
        toast.success('Outlook disconnected from mailbox');
        setMailboxOutlookStatus({ connected: false, sync_status: 'disconnected', email_count: 0 });
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to disconnect Outlook');
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
        toast.success('Outlook sync started');
        // Poll for status update
        setTimeout(loadMailboxOutlookStatus, 2000);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to trigger Outlook sync');
    } finally {
      setSyncingOutlook(false);
    }
  };

  // Fetch emails by date range
  const handleDateRangeFetch = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!profile?.id) {
      toast.error('User not authenticated');
      return;
    }

    if (!dateRangeStart || !dateRangeEnd) {
      toast.error('Please select a date range');
      return;
    }

    const startDate = dateRangeStart;
    const endDate = dateRangeEnd;

    // Determine which service to use
    const isOutlookType = selectedType === 'outlook_live' || mailboxOutlookStatus?.connected;
    const isGmailType = selectedType === 'gmail' || mailboxGmailStatus?.connected;

    try {
      setFetchingEmails(true);
      let result;

      if (isOutlookType && mailboxOutlookStatus?.connected) {
        result = await outlookService.fetchEmailsByDateRange(
          mailboxId,
          profile.id,
          startDate,
          endDate,
          dateRangeMax
        );
      } else if (isGmailType && mailboxGmailStatus?.connected) {
        result = await gmailService.fetchEmailsByDateRange(
          mailboxId,
          profile.id,
          startDate,
          endDate,
          dateRangeMax
        );
      } else {
        toast.error('No LIVE sync connection available');
        return;
      }

      if (result.success) {
        toast.success(`${result.message}. Job ID: ${result.job_id}`);
        setDateRangeModalVisible(false);
        setDateRangeStart('');
        setDateRangeEnd('');
        setDateRangeMax(500);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to start email fetch');
    } finally {
      setFetchingEmails(false);
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

      // Set form state from mailbox data
      setFormName(data.name || '');
      setFormEmail(data.email_address || '');
      setFormMailboxType(data.mailbox_type || 'mbox');
      setFormFilePath(data.connection_config?.file_path || '');
      setFormIsActive(data.is_active ?? true);
      setFormClientId(data.client_id || null);
      setFormUserId(data.user_id || null);

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
      toast.error('Failed to load mailbox data');
      navigate('/mailboxes');
    } finally {
      setInitialLoading(false);
    }
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (!formName.trim()) newErrors.name = 'Please enter a mailbox name';
    if (!formMailboxType) newErrors.mailbox_type = 'Please select a mailbox type';
    if (formEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formEmail)) {
      newErrors.email = 'Please enter a valid email address';
    }
    if (['mbox', 'pst', 'olm'].includes(formMailboxType) && fileSource === 'local' && !formFilePath.trim()) {
      newErrors.file_path = `Please specify the ${formMailboxType.toUpperCase()} file path`;
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    try {
      setLoading(true);

      // Start with existing connection config to preserve Gmail/Outlook connections
      const connectionConfig: any = { ...(mailboxData?.connection_config || {}) };

      // Only update file-related fields for file-based mailbox types
      if (['mbox', 'pst', 'olm'].includes(formMailboxType)) {
        if (fileSource === 'google_drive' && googleDriveFile) {
          // Use Google Drive configuration with OAuth2
          connectionConfig.google_drive_file_id = googleDriveFile.id;
          connectionConfig.google_drive_file_name = googleDriveFile.name;
          connectionConfig.file_source = 'google_drive';
          connectionConfig.user_id = userId; // Include user_id for backend token lookup
        } else {
          connectionConfig.file_path = formFilePath;
          connectionConfig.file_source = 'local';
          // Clear Google Drive fields if switching to local
          delete connectionConfig.google_drive_file_id;
          delete connectionConfig.google_drive_file_name;
        }
      }

      // Note: Gmail/Outlook connection fields (gmail_sync_enabled, gmail_access_token, etc.)
      // are preserved from the existing connection_config and not modified here

      const mailboxUpdateData: any = {
        name: formName,
        mailbox_type: formMailboxType,
        is_active: formIsActive,
        connection_config: connectionConfig,
        client_id: formClientId || null,
        user_id: formUserId || null
      };

      // Only add email_address if provided
      if (formEmail) {
        mailboxUpdateData.email_address = formEmail;
      }

      await mailboxService.updateMailbox(mailboxId, mailboxUpdateData);
      toast.success("Mailbox updated successfully");
      navigate('/mailboxes');
    } catch (error) {
      console.error('Error updating mailbox:', error);
      toast.error("Failed to update mailbox");
    } finally {
      setLoading(false);
    }
  };

  const handleMailboxSync = async () => {
    try {
      setSyncing(true);
      await mailboxService.syncMailbox(mailboxId);
      toast.success('Sync triggered successfully');
    } catch (error) {
      console.error('Error syncing mailbox:', error);
      toast.error('Failed to trigger sync');
    } finally {
      setSyncing(false);
    }
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setFormFilePath(file.webkitRelativePath || file.name);
    }
  };

  const handleFileBrowse = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleTypeChange = (value: string) => {
    setFormMailboxType(value);
    setSelectedType(value);
  };

  const todayStr = dayjs().format('YYYY-MM-DD');

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner className="h-6 w-6 animate-spin text-primary" />
        <span className="ml-2 text-sm text-slate-500">Loading mailbox data...</span>
      </div>
    );
  }

  if (!mailboxData) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-slate-500">Mailbox not found</p>
      </div>
    );
  }

  return (
    <PageShell>
      <PageHeader title="Edit Mailbox" description="Update mailbox configuration" />

      <div className="rounded-lg border bg-white shadow-sm">
        <form onSubmit={handleSubmit} className="p-5 flex flex-col gap-4">
          {/* Mailbox Name */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Mailbox Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="e.g., Primary Business Account"
              className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
            {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name}</p>}
          </div>

          {/* Email Address */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Email Address
            </label>
            <input
              type="email"
              value={formEmail}
              disabled
              placeholder={
                mailboxData?.connection_config?.gmail_email
                  ? `${mailboxData.connection_config.gmail_email} (from Gmail)`
                  : mailboxData?.connection_config?.outlook_email
                  ? `${mailboxData.connection_config.outlook_email} (from Outlook)`
                  : 'Will be derived from connection or archive'
              }
              className="w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500 placeholder:text-slate-400 cursor-not-allowed"
            />
            {errors.email && <p className="text-xs text-red-500 mt-1">{errors.email}</p>}
          </div>

          {/* Mailbox Type */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Mailbox Type <span className="text-red-500">*</span>
            </label>
            <select
              value={formMailboxType}
              onChange={(e) => handleTypeChange(e.target.value)}
              className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            >
              <optgroup label="LIVE Mailboxes">
                <option value="gmail">Gmail</option>
                <option value="outlook_live">Outlook / Office 365</option>
              </optgroup>
              <optgroup label="Archive Files">
                <option value="mbox">MBOX (Universal Format)</option>
                <option value="pst">PST (Outlook Windows)</option>
                <option value="olm">OLM (Outlook Mac)</option>
              </optgroup>
            </select>
            {errors.mailbox_type && <p className="text-xs text-red-500 mt-1">{errors.mailbox_type}</p>}
          </div>

          {/* File Configuration - for all file-based types */}
          {['mbox', 'pst', 'olm'].includes(selectedType) && (
            <>
              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-slate-200" /></div>
                <div className="relative flex justify-center text-xs"><span className="bg-white px-2 text-slate-500">File Configuration</span></div>
              </div>

              <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                <p className="text-sm font-medium text-slate-900">{selectedType.toUpperCase()} File Archive</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {selectedType === 'mbox' ? 'Universal email format (Gmail export, Thunderbird, Apple Mail)' :
                   selectedType === 'pst' ? 'Windows Outlook archive file with native folder structure' :
                   'Mac Outlook archive file with folder hierarchy'}
                </p>
              </div>

              {/* File Source */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  File Source <span className="text-red-500">*</span>
                </label>
                <div className="inline-flex rounded-md border border-slate-200 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setFileSource('local')}
                    className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
                      fileSource === 'local'
                        ? 'bg-primary text-white'
                        : 'bg-white text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <FolderOpen className="h-4 w-4" /> Local File
                  </button>
                  <button
                    type="button"
                    onClick={() => setFileSource('google_drive')}
                    className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-l border-slate-200 transition-colors ${
                      fileSource === 'google_drive'
                        ? 'bg-primary text-white'
                        : 'bg-white text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
                    </svg>
                    Google Drive
                  </button>
                </div>
              </div>

              {fileSource === 'local' ? (
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">
                    {selectedType.toUpperCase()} File Path <span className="text-red-500">*</span>
                  </label>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <FolderOpen className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <input
                        type="text"
                        value={formFilePath}
                        onChange={(e) => setFormFilePath(e.target.value)}
                        placeholder={`/path/to/archive.${selectedType}`}
                        className="w-full rounded-md border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={handleFileBrowse}
                      className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
                    >
                      <FolderOpen className="h-4 w-4" />
                      Browse
                    </button>
                  </div>
                  {errors.file_path && <p className="text-xs text-red-500 mt-1">{errors.file_path}</p>}
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      Google Drive Connection
                    </label>
                    <GoogleDriveConnection
                      userId={userId}
                      onConnectionChange={setGoogleDriveConnected}
                    />
                  </div>

                  {googleDriveConnected && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1.5">
                        Google Drive File <span className="text-red-500">*</span>
                      </label>
                      <GoogleDrivePicker
                        onFileSelect={(file) => {
                          setGoogleDriveFile(file);
                          toast.success(`Selected file: ${file.name}`);
                        }}
                        acceptedFormats={[`.${selectedType}`]}
                      />
                      {googleDriveFile && (
                        <p className="text-xs text-slate-500 mt-1">Selected: {googleDriveFile.name}</p>
                      )}
                      {!googleDriveFile && (
                        <p className="text-xs text-slate-400 mt-1">No file selected</p>
                      )}
                    </div>
                  )}

                  {!googleDriveConnected && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <p className="text-sm font-medium text-amber-800">Google Drive Not Connected</p>
                      <p className="text-xs text-amber-600 mt-0.5">Please connect your Google Drive account above to select files.</p>
                    </div>
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
              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-slate-200" /></div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-white px-2 text-slate-500">
                    {selectedType === 'gmail' ? 'Gmail Connection' : 'Gmail LIVE Sync'}
                  </span>
                </div>
              </div>

              {mailboxGmailStatus?.connected ? (
                // Connected - show status with sync controls
                <div className="mb-4">
                  <div className="rounded-lg border border-green-200 bg-green-50 p-4 mb-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <CheckCircle2 className="h-4 w-4 text-green-600" />
                          <span className="text-sm font-medium text-slate-900">Gmail LIVE Sync Enabled</span>
                        </div>
                        <div className="flex flex-col gap-1">
                          <p className="text-xs text-slate-500 flex items-center gap-1">
                            <svg className="h-3.5 w-3.5 text-[#4285f4]" viewBox="0 0 24 24" fill="currentColor">
                              <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
                            </svg>
                            {mailboxGmailStatus.gmail_email || 'Connected'}
                          </p>
                          <p className="text-xs text-slate-500 flex items-center gap-1">
                            <RefreshCw className={`h-3.5 w-3.5 ${mailboxGmailStatus.sync_status === 'syncing' ? 'animate-spin' : ''}`} />
                            {mailboxGmailStatus.sync_status === 'syncing'
                              ? 'Syncing now...'
                              : `Last sync: ${gmailService.formatRelativeTime(mailboxGmailStatus.last_sync_at || null)}`
                            }
                          </p>
                          <p className="text-xs text-slate-500">
                            {mailboxGmailStatus.email_count} emails synced
                          </p>
                          {mailboxGmailStatus.error && (
                            <p className="text-xs text-red-500">
                              Error: {mailboxGmailStatus.error}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <button
                          type="button"
                          onClick={handleSyncNow}
                          disabled={syncingGmail}
                          className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
                        >
                          {syncingGmail ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                          Sync Now
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setDateRangeStart('');
                            setDateRangeEnd('');
                            setDateRangeMax(500);
                            setDateRangeModalVisible(true);
                          }}
                          className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                        >
                          <Calendar className="h-3.5 w-3.5" />
                          Fetch Range
                        </button>
                        <button
                          type="button"
                          onClick={handleDisconnectGmail}
                          disabled={disconnectingGmail}
                          className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                        >
                          {disconnectingGmail ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <Unplug className="h-3.5 w-3.5" />}
                          Disconnect
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Sync Settings */}
                  <div className="rounded-lg border border-green-200/50 bg-green-50/30 p-3">
                    <div className={`flex items-center justify-between ${showSyncSettings ? 'mb-3' : ''}`}>
                      <div className="flex items-center gap-2">
                        <Settings className="h-4 w-4 text-slate-500" />
                        <span className="text-[13px] font-medium text-slate-700">Sync Settings</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowSyncSettings(!showSyncSettings)}
                        className="text-xs text-slate-500 hover:text-primary transition-colors"
                      >
                        {showSyncSettings ? 'Hide' : 'Configure'}
                      </button>
                    </div>

                    {showSyncSettings && (
                      <div className="flex flex-col gap-3">
                        <div>
                          <label className="block text-xs text-slate-500 mb-1">
                            Sync Interval (minutes)
                          </label>
                          <div className="flex items-center gap-2">
                            <input
                              type="number"
                              min={1}
                              max={1440}
                              value={syncInterval}
                              onChange={(e) => setSyncInterval(parseInt(e.target.value) || 15)}
                              className="w-20 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                            />
                            <span className="text-[11px] text-slate-400">(1 min - 24 hours)</span>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={handleSaveConfig}
                          disabled={savingConfig}
                          className="inline-flex items-center gap-1.5 self-start rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 transition-colors disabled:opacity-50"
                        >
                          {savingConfig ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                          Save Settings
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                // Not connected - show connect button
                <div className="rounded-xl border border-dashed border-blue-300/50 bg-gradient-to-br from-blue-50/50 to-green-50/50 p-5 mb-4 text-center">
                  <div className="flex flex-col items-center gap-3">
                    <svg className="h-12 w-12 text-[#4285f4]" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
                    </svg>
                    <p className="text-base font-semibold text-slate-900">Connect Gmail for LIVE Sync</p>
                    <p className="text-sm text-slate-500 max-w-sm">
                      {selectedType === 'gmail'
                        ? 'Connect your Gmail account to start syncing emails from this mailbox.'
                        : 'Link a Gmail account to automatically sync new emails to this mailbox. Each mailbox can have its own Gmail connection.'
                      }
                    </p>
                    <button
                      type="button"
                      onClick={handleConnectGmail}
                      disabled={connectingGmail}
                      className="mt-2 inline-flex items-center gap-2 rounded-md bg-[#4285f4] px-4 py-2 text-sm font-medium text-white hover:bg-[#3367d6] transition-colors disabled:opacity-50"
                    >
                      {connectingGmail && <Spinner className="h-4 w-4 animate-spin" />}
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
                      </svg>
                      {selectedType === 'gmail' ? 'Connect Gmail' : 'Connect Gmail Account'}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Outlook Connection Section - for outlook_live type OR archive mailboxes */}
          {(selectedType === 'outlook_live' || ['mbox', 'pst', 'olm'].includes(selectedType)) && (
            <>
              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-slate-200" /></div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-white px-2 text-slate-500">
                    {selectedType === 'outlook_live' ? 'Outlook Connection' : 'Outlook LIVE Sync'}
                  </span>
                </div>
              </div>

              {mailboxOutlookStatus?.connected ? (
                // Connected - show status with sync controls
                <div className="mb-4">
                  <div className="rounded-lg border border-[#0078d4]/30 bg-primary/5 p-4 mb-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <CheckCircle2 className="h-4 w-4 text-[#0078d4]" />
                          <span className="text-sm font-medium text-slate-900">Outlook LIVE Sync Enabled</span>
                        </div>
                        <div className="flex flex-col gap-1">
                          <p className="text-xs text-slate-500 flex items-center gap-1">
                            <svg className="h-3.5 w-3.5 text-[#0078d4]" viewBox="0 0 24 24" fill="currentColor">
                              <path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.4H10.949M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-12.9-1.801"/>
                            </svg>
                            {mailboxOutlookStatus.outlook_email || 'Connected'}
                          </p>
                          <p className="text-xs text-slate-500 flex items-center gap-1">
                            <RefreshCw className={`h-3.5 w-3.5 ${mailboxOutlookStatus.sync_status === 'syncing' ? 'animate-spin' : ''}`} />
                            {mailboxOutlookStatus.sync_status === 'syncing'
                              ? 'Syncing now...'
                              : `Last sync: ${outlookService.formatRelativeTime(mailboxOutlookStatus.last_sync_at || null)}`
                            }
                          </p>
                          <p className="text-xs text-slate-500">
                            {mailboxOutlookStatus.email_count} emails synced
                          </p>
                          {mailboxOutlookStatus.error && (
                            <p className="text-xs text-red-500">
                              Error: {mailboxOutlookStatus.error}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <button
                          type="button"
                          onClick={handleOutlookSyncNow}
                          disabled={syncingOutlook}
                          className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
                        >
                          {syncingOutlook ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                          Sync Now
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setDateRangeStart('');
                            setDateRangeEnd('');
                            setDateRangeMax(500);
                            setDateRangeModalVisible(true);
                          }}
                          className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                        >
                          <Calendar className="h-3.5 w-3.5" />
                          Fetch Range
                        </button>
                        <button
                          type="button"
                          onClick={handleDisconnectOutlook}
                          disabled={disconnectingOutlook}
                          className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                        >
                          {disconnectingOutlook ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <Unplug className="h-3.5 w-3.5" />}
                          Disconnect
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                // Not connected - show connect button
                <div className="rounded-xl border border-dashed border-[#0078d4]/30 bg-gradient-to-br from-blue-50/50 to-blue-100/30 p-5 mb-4 text-center">
                  <div className="flex flex-col items-center gap-3">
                    <svg className="h-12 w-12 text-[#0078d4]" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.4H10.949M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-12.9-1.801"/>
                    </svg>
                    <p className="text-base font-semibold text-slate-900">Connect Outlook for LIVE Sync</p>
                    <p className="text-sm text-slate-500 max-w-sm">
                      {selectedType === 'outlook_live'
                        ? 'Connect your Outlook account (O365 or personal) to start syncing emails from this mailbox.'
                        : 'Link an Outlook account (O365 or personal) to automatically sync new emails to this mailbox. Each mailbox can have its own Outlook connection.'
                      }
                    </p>
                    <button
                      type="button"
                      onClick={handleConnectOutlook}
                      disabled={connectingOutlook}
                      className="mt-2 inline-flex items-center gap-2 rounded-md bg-[#0078d4] px-4 py-2 text-sm font-medium text-white hover:bg-[#005a9e] transition-colors disabled:opacity-50"
                    >
                      {connectingOutlook && <Spinner className="h-4 w-4 animate-spin" />}
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.4H10.949M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-12.9-1.801"/>
                      </svg>
                      {selectedType === 'outlook_live' ? 'Connect Outlook' : 'Connect Outlook Account'}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Client and Account Manager Assignment - only visible to admins */}
          {isAdmin && (
            <>
              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-slate-200" /></div>
                <div className="relative flex justify-center text-xs"><span className="bg-white px-2 text-slate-500">Assignment</span></div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Assign to Client
                </label>
                <select
                  value={formClientId || ''}
                  onChange={(e) => {
                    const val = e.target.value || null;
                    setFormClientId(val);
                    setSelectedClientId(val);
                    setFormUserId(null);
                  }}
                  className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                >
                  <option value="">Select a client (optional)</option>
                  {clients.map(c => (
                    <option key={c.id} value={c.id}>{c.client_name}</option>
                  ))}
                </select>
                <p className="text-xs text-slate-400 mt-1">
                  Assign this mailbox to a client. Client managers assigned to this client will be able to access it.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Assign to Account Manager
                </label>
                <select
                  value={formUserId || ''}
                  onChange={(e) => setFormUserId(e.target.value || null)}
                  disabled={!selectedClientId && !formClientId}
                  className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed"
                >
                  <option value="">{(selectedClientId || formClientId) ? 'Select account manager (optional)' : 'Select a client first'}</option>
                  {(() => {
                    const clientId = selectedClientId || formClientId;
                    if (!clientId) return null;
                    return users
                      .filter((u: any) => {
                        const hasAccountManagerRole = u.roles?.includes('account_manager');
                        const isAssignedToClient = u.assigned_clients?.some((c: any) => c.id === clientId);
                        return hasAccountManagerRole && isAssignedToClient;
                      })
                      .map((u: any) => (
                        <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
                      ));
                  })()}
                </select>
                <p className="text-xs text-slate-400 mt-1">
                  {selectedClientId || formClientId
                    ? 'Assign this mailbox to an account manager assigned to the selected client.'
                    : 'First assign this mailbox to a client to see available account managers.'}
                </p>
              </div>
            </>
          )}

          {/* Active Toggle */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-slate-700">Active</label>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={formIsActive}
                onChange={(e) => setFormIsActive(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary/30 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary" />
            </label>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark transition-colors disabled:opacity-50"
            >
              {loading && <Spinner className="h-4 w-4 animate-spin" />}
              Update Mailbox
            </button>
            <button
              type="button"
              onClick={handleMailboxSync}
              disabled={syncing}
              className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
            >
              {syncing ? <Spinner className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Sync Now
            </button>
            <button
              type="button"
              onClick={() => navigate('/mailboxes')}
              className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>

      {/* Date Range Fetch Modal */}
      <Dialog open={dateRangeModalVisible} onOpenChange={setDateRangeModalVisible}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History className="h-5 w-5" />
              Fetch Emails by Date Range
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={handleDateRangeFetch} className="flex flex-col gap-4">
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
              <p className="text-sm font-medium text-slate-900">Historical Email Fetch</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {mailboxOutlookStatus?.connected
                  ? "Fetch historical emails from your connected Outlook account for a specific date range."
                  : "Fetch historical emails from your connected Gmail account for a specific date range."
                }
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Date Range <span className="text-red-500">*</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={dateRangeStart}
                  onChange={(e) => setDateRangeStart(e.target.value)}
                  max={todayStr}
                  className="flex-1 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                />
                <span className="text-sm text-slate-400">to</span>
                <input
                  type="date"
                  value={dateRangeEnd}
                  onChange={(e) => setDateRangeEnd(e.target.value)}
                  max={todayStr}
                  className="flex-1 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                />
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {[
                  { label: 'Last 7 Days', days: 7 },
                  { label: 'Last 30 Days', days: 30 },
                  { label: 'Last 90 Days', days: 90 },
                  { label: 'Last Year', days: 365 },
                ].map((preset) => (
                  <button
                    key={preset.days}
                    type="button"
                    onClick={() => {
                      setDateRangeEnd(dayjs().format('YYYY-MM-DD'));
                      setDateRangeStart(dayjs().subtract(preset.days, 'day').format('YYYY-MM-DD'));
                    }}
                    className="rounded border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50 transition-colors"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Maximum Emails
              </label>
              <input
                type="number"
                min={1}
                max={5000}
                value={dateRangeMax}
                onChange={(e) => setDateRangeMax(parseInt(e.target.value) || 500)}
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
              <p className="text-xs text-slate-400 mt-1">Limit the number of emails to fetch (max 5000)</p>
            </div>

            <DialogFooter className="mt-2">
              <button
                type="button"
                onClick={() => {
                  setDateRangeModalVisible(false);
                  setDateRangeStart('');
                  setDateRangeEnd('');
                  setDateRangeMax(500);
                }}
                className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={fetchingEmails}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark transition-colors disabled:opacity-50"
              >
                {fetchingEmails ? <Spinner className="h-4 w-4 animate-spin" /> : <Calendar className="h-4 w-4" />}
                Fetch Emails
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
};

export default MailboxEditForm;
