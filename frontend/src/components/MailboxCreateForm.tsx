import React, { useState } from "react";
import {
  CheckCircle2,
  FolderOpen,
  Info,
} from "lucide-react";
import { Spinner } from '@/lib/icons';
import { toast } from '@/lib/toast';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { useNavigate } from "react-router-dom";
import { mailboxService } from '../services/mailboxService';
import GoogleDrivePicker from './GoogleDrivePicker';
import GoogleDriveConnection from './GoogleDriveConnection';
import { clientService } from '../services/clientService';
import { userService } from '../services/userService';
import { useAuth } from '../contexts/AuthContext';

export const MailboxCreateForm: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [selectedType, setSelectedType] = React.useState('gmail');
  const [fileSource, setFileSource] = React.useState<'local' | 'google_drive'>('local');
  const [googleDriveFile, setGoogleDriveFile] = React.useState<any>(null);
  const [googleDriveConnected, setGoogleDriveConnected] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Form field state
  const [formName, setFormName] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formMailboxType, setFormMailboxType] = useState('gmail');
  const [formFilePath, setFormFilePath] = useState('');
  const [formIsActive, setFormIsActive] = useState(true);
  const [formClientId, setFormClientId] = useState<string | null>(null);
  const [formUserId, setFormUserId] = useState<string | null>(null);

  // Validation state
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Client and user assignment state
  const [clients, setClients] = React.useState<any[]>([]);
  const [users, setUsers] = React.useState<any[]>([]);
  const [selectedClientId, setSelectedClientId] = React.useState<string | null>(null);
  const { profile } = useAuth();
  const isAdmin = profile?.roles?.includes('admin');

  // Load clients and users on mount (only for admins)
  React.useEffect(() => {
    loadClientsAndUsers();
  }, [isAdmin]);

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

      // Build connection config based on mailbox type
      const connectionConfig: any = {};

      // All file-based types (MBOX, PST, OLM) use file_path or Google Drive
      if (['mbox', 'pst', 'olm'].includes(formMailboxType)) {
        if (fileSource === 'google_drive' && googleDriveFile) {
          // For non-admins, automatically assign the mailbox to themselves
          const assignedUserId = isAdmin
            ? (formUserId || null)
            : profile?.id || null;

          // Use the new Google Drive mailbox creation method with OAuth2
          const googleDriveData = {
            name: formName,
            email_address: formEmail,
            mailbox_type: formMailboxType,
            is_active: formIsActive,
            google_drive_file_id: googleDriveFile.id,
            google_drive_file_name: googleDriveFile.name,
            user_id: userId, // For OAuth2 token lookup
            assigned_user_id: assignedUserId // For RBAC mailbox assignment
          };

          await mailboxService.createGoogleDriveMailbox(googleDriveData as any);
          toast.success("Google Drive mailbox created successfully");
          navigate('/mailboxes');
          return;
        } else {
          connectionConfig.file_path = formFilePath;
          connectionConfig.file_source = 'local';
        }
      }

      // For non-admins, automatically assign the mailbox to themselves
      // For admins, use the selected user_id from the form (or null)
      const assignedUserId = isAdmin
        ? (formUserId || null)
        : profile?.id || null;

      const mailboxData: any = {
        name: formName,
        mailbox_type: formMailboxType,
        is_active: formIsActive,
        connection_config: connectionConfig,
        client_id: formClientId || null,
        user_id: assignedUserId
      };

      // Only add email_address if provided
      if (formEmail) {
        mailboxData.email_address = formEmail;
      }

      const response = await mailboxService.createMailbox(mailboxData);

      // For LIVE mailboxes (gmail, outlook_live), redirect to edit page to connect
      if (['gmail', 'outlook_live'].includes(formMailboxType)) {
        toast.success("Mailbox created! Now connect your account to start syncing.");
        navigate(`/mailboxes/${response.id}/edit`);
      } else {
        toast.success("Mailbox created successfully");
        navigate('/mailboxes');
      }
    } catch (error) {
      console.error('Error creating mailbox:', error);
      toast.error("Failed to create mailbox");
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async () => {
    try {
      setTesting(true);

      // Build connection config
      const connectionConfig: any = {};

      // All file-based types (MBOX, PST, OLM) use file_path or Google Drive
      if (['mbox', 'pst', 'olm'].includes(formMailboxType)) {
        if (fileSource === 'google_drive' && googleDriveFile) {
          connectionConfig.google_drive_file_id = googleDriveFile.id;
          connectionConfig.google_drive_file_name = googleDriveFile.name;
          connectionConfig.file_source = 'google_drive';
          connectionConfig.user_id = userId; // Include user_id for OAuth2 token lookup
        } else {
          connectionConfig.file_path = formFilePath;
          connectionConfig.file_source = 'local';
        }
      }

      const response = await fetch(`${import.meta.env.API_BASE_URL}/mailboxes/test/test-connection`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mailbox_type: formMailboxType,
          connection_config: connectionConfig
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Connection test failed');
      }

      const result = await response.json();
      toast.success(result.message || 'Connection test successful!');
    } catch (error) {
      toast.error(`Connection test failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
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
      setFormFilePath(filePath);
    }
  };

  const handleTypeChange = (value: string) => {
    setFormMailboxType(value);
    setSelectedType(value);
  };

  return (
    <PageShell>
      <PageHeader title="Create New Mailbox" description="Add a new email source for intelligence gathering" />

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
            <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 mb-1.5">
              Email Address
              <span title="Will be automatically derived when you connect Gmail/Outlook or upload archive file">
                <Info className="h-3.5 w-3.5 text-slate-400" />
              </span>
            </label>
            <input
              type="email"
              value={formEmail}
              disabled
              placeholder="Will be auto-populated from connection or archive"
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

          {/* Gmail LIVE Configuration */}
          {selectedType === 'gmail' && (
            <>
              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-slate-200" /></div>
                <div className="relative flex justify-center text-xs"><span className="bg-white px-2 text-slate-500">Gmail LIVE Sync</span></div>
              </div>
              <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
                <div className="flex items-start gap-3">
                  <svg className="h-5 w-5 text-[#4285f4] mt-0.5 shrink-0" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
                  </svg>
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Gmail LIVE Mailbox</p>
                    <p className="text-sm font-medium text-slate-700 mt-1">
                      After clicking "Create Mailbox", you'll be redirected to connect your Gmail account.
                    </p>
                    <div className="mt-2">
                      <p className="text-xs font-semibold text-slate-600">Features:</p>
                      <ul className="mt-1 ml-5 list-disc space-y-0.5">
                        <li className="text-xs text-slate-500">Automatic email sync at configurable intervals</li>
                        <li className="text-xs text-slate-500">Real-time updates from your Gmail inbox</li>
                        <li className="text-xs text-slate-500">Secure OAuth2 authentication</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Outlook LIVE Configuration */}
          {selectedType === 'outlook_live' && (
            <>
              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-slate-200" /></div>
                <div className="relative flex justify-center text-xs"><span className="bg-white px-2 text-slate-500">Outlook LIVE Sync</span></div>
              </div>
              <div className="rounded-lg border border-[#0078d4]/30 bg-primary/5 p-4">
                <div className="flex items-start gap-3">
                  <svg className="h-5 w-5 text-[#0078d4] mt-0.5 shrink-0" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.4H10.949M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-12.9-1.801"/>
                  </svg>
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Outlook LIVE Mailbox</p>
                    <p className="text-sm font-medium text-slate-700 mt-1">
                      After clicking "Create Mailbox", you'll be redirected to connect your Outlook account.
                    </p>
                    <div className="mt-2">
                      <p className="text-xs font-semibold text-slate-600">Features:</p>
                      <ul className="mt-1 ml-5 list-disc space-y-0.5">
                        <li className="text-xs text-slate-500">Automatic email sync at configurable intervals</li>
                        <li className="text-xs text-slate-500">Works with Office 365 and personal Outlook accounts</li>
                        <li className="text-xs text-slate-500">Secure OAuth2 authentication</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

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
                  disabled={!selectedClientId}
                  className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed"
                >
                  <option value="">{selectedClientId ? 'Select account manager (optional)' : 'Select a client first'}</option>
                  {selectedClientId && users
                    .filter((u: any) => {
                      const hasAccountManagerRole = u.roles?.includes('account_manager');
                      const isAssignedToClient = u.assigned_clients?.some((c: any) => c.id === selectedClientId);
                      return hasAccountManagerRole && isAssignedToClient;
                    })
                    .map((u: any) => (
                      <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
                    ))
                  }
                </select>
                <p className="text-xs text-slate-400 mt-1">
                  {selectedClientId
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

          {/* Divider */}
          <div className="border-t border-slate-200" />

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark transition-colors disabled:opacity-50"
            >
              {loading && <Spinner className="h-4 w-4 animate-spin" />}
              Create Mailbox
            </button>
            {/* Test Connection only available for archive file types */}
            {['mbox', 'pst', 'olm'].includes(selectedType) && (
              <button
                type="button"
                onClick={testConnection}
                disabled={testing || (fileSource === 'local' && !formFilePath) || (fileSource === 'google_drive' && (!googleDriveConnected || !googleDriveFile))}
                className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {testing ? <Spinner className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                Test Connection
              </button>
            )}
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
    </PageShell>
  );
};

export default MailboxCreateForm;
