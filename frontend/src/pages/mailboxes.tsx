/**
 * Mailboxes Page — Manage email sources for intelligence gathering. Zero antd.
 */
import React, { useState, useEffect, useMemo, useRef } from "react";
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
import { formatDateTime } from '../utils/dateUtils';
import { useMailboxes, useProcessingJobs, useInvalidateMailboxes } from '../hooks/queries';

import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Plus, Pencil, Trash2, RefreshCw, Mail, Link as LinkIcon,
  Zap, Calendar, Users, User, ChevronDown, Eye,
  AlertCircle, History, Spinner,
} from '@/lib/icons';

export const MailboxList: React.FC = () => {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const isAdmin = useMemo(() => profile?.roles?.includes('admin'), [profile?.roles]);

  // TanStack Query — replaces manual fetch + polling
  const mailboxQuery = useMailboxes();
  const jobsQuery = useProcessingJobs();
  const invalidateMailboxes = useInvalidateMailboxes();
  const mailboxes = mailboxQuery.data || [];
  const loading = mailboxQuery.isLoading;
  const processingJobs = jobsQuery.data || [];

  const [gmailConnected, setGmailConnected] = useState(false);
  const [outlookConnected, setOutlookConnected] = useState(false);
  const [linkingMailboxId, setLinkingMailboxId] = useState<string | null>(null);

  // Date range fetch modal state
  const [dateRangeModalVisible, setDateRangeModalVisible] = useState(false);
  const [selectedMailboxForFetch, setSelectedMailboxForFetch] = useState<Mailbox | null>(null);
  const [fetchingEmails, setFetchingEmails] = useState(false);
  // Date range form state (replaces antd Form)
  const [fetchStartDate, setFetchStartDate] = useState('');
  const [fetchEndDate, setFetchEndDate] = useState('');
  const [fetchMaxEmails, setFetchMaxEmails] = useState<number | ''>('');

  // Assignment modal state
  const [assignmentModalVisible, setAssignmentModalVisible] = useState(false);
  const [assignmentType, setAssignmentType] = useState<'client' | 'user'>('client');
  const [selectedMailboxForAssignment, setSelectedMailboxForAssignment] = useState<Mailbox | null>(null);
  const [clients, setClients] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [assignmentLoading, setAssignmentLoading] = useState(false);
  const [clientsUsersLoading, setClientsUsersLoading] = useState(true);

  // Sync dropdown state
  const [openSyncDropdown, setOpenSyncDropdown] = useState<string | null>(null);

  const isMountedRef = useRef(true);

  // Mailboxes where Gmail or Outlook auth has expired and needs user reconnection
  const mailboxesWithExpiredAuth = useMemo(() => {
    return mailboxes.filter(m => {
      const cfg = (m.connection_config || {}) as Record<string, unknown>;
      return cfg.gmail_sync_status === 'auth_expired' || cfg.outlook_sync_status === 'auth_expired';
    });
  }, [mailboxes]);

  useEffect(() => {
    isMountedRef.current = true;
    checkGmailConnection();
    checkOutlookConnection();
    if (isAdmin) loadClientsAndUsers();
    return () => { isMountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (isAdmin) loadClientsAndUsers();
  }, [isAdmin]);

  // Close sync dropdown on outside click
  useEffect(() => {
    if (!openSyncDropdown) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-sync-dropdown]')) {
        setOpenSyncDropdown(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [openSyncDropdown]);

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

  // loadMailboxes replaced by invalidateMailboxes() from TanStack Query

  const handleDelete = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this mailbox?')) return;
    try {
      await mailboxService.deleteMailbox(id);
      toast.success("Mailbox deleted successfully");
      invalidateMailboxes(); // Reload the list
    } catch (error) {
      toast.error("Failed to delete mailbox");
    }
  };

  const handleSync = async (id: string, name: string) => {
    try {
      toast.info(`Starting sync for ${name}...`);
      await mailboxService.syncMailbox(id);
      toast.success(`Sync initiated for ${name}`);
      invalidateMailboxes(); // Reload to show updated sync time
    } catch (error) {
      toast.error(`Failed to sync ${name}`);
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
        toast.success('Mailbox assigned to client successfully');
      } else {
        await mailboxAssignmentService.assignToUser(selectedMailboxForAssignment.id, value);
        toast.success('Mailbox assigned to account manager successfully');
      }

      setAssignmentModalVisible(false);
      invalidateMailboxes(); // Reload to show updated assignments
    } catch (error: any) {
      toast.error(error.message || 'Failed to assign mailbox');
    } finally {
      setAssignmentLoading(false);
    }
  };

  const handleLinkGmail = async (mailboxId: string, mailboxName: string) => {
    if (!gmailConnected) {
      toast.warning('Please connect your Gmail account from the Dashboard first');
      navigate('/');
      return;
    }

    if (!profile?.id) {
      toast.error('User not authenticated');
      return;
    }

    try {
      setLinkingMailboxId(mailboxId);
      toast.info(`Linking Gmail to ${mailboxName}...`);

      const result = await gmailService.extendMailboxWithGmail(mailboxId, profile.id);

      if (result.success) {
        const linkedEmail = (result.mailbox as any)?.connection_config?.gmail_email;
        const currentMailbox = mailboxes.find(m => m.id === mailboxId);

        // Validate: prevent linking a different Gmail account
        if (linkedEmail && currentMailbox?.email_address) {
          if (linkedEmail.toLowerCase() !== currentMailbox.email_address.toLowerCase()) {
            toast.error(`Cannot link ${linkedEmail}. This mailbox is already associated with ${currentMailbox.email_address}. Please use the same account or remove the existing link first.`);
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

        toast.success(result.message);
        mailboxService.clearCache();
        invalidateMailboxes(); // Reload to show updated status
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to link Gmail');
    } finally {
      setLinkingMailboxId(null);
    }
  };

  const handleLinkOutlook = async (mailboxId: string, mailboxName: string) => {
    if (!outlookConnected) {
      toast.warning('Please connect your Outlook account from the Dashboard first');
      navigate('/');
      return;
    }

    if (!profile?.id) {
      toast.error('User not authenticated');
      return;
    }

    try {
      setLinkingMailboxId(mailboxId);
      toast.info(`Linking Outlook to ${mailboxName}...`);

      const result = await outlookService.extendMailboxWithOutlook(mailboxId, profile.id);

      if (result.success) {
        const linkedEmail = (result.mailbox as any)?.connection_config?.outlook_email;
        const currentMailbox = mailboxes.find(m => m.id === mailboxId);

        // Validate: prevent linking a different Outlook account
        if (linkedEmail && currentMailbox?.email_address) {
          if (linkedEmail.toLowerCase() !== currentMailbox.email_address.toLowerCase()) {
            toast.error(`Cannot link ${linkedEmail}. This mailbox is already associated with ${currentMailbox.email_address}. Please use the same account or remove the existing link first.`);
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

        toast.success(result.message);
        mailboxService.clearCache();
        invalidateMailboxes(); // Reload to show updated status
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to link Outlook');
    } finally {
      setLinkingMailboxId(null);
    }
  };

  const handleReconnectGmail = async (mailboxId: string, mailboxName: string) => {
    try {
      setLinkingMailboxId(mailboxId);
      toast.info(`Reconnecting Gmail for ${mailboxName}...`);
      const result = await gmailService.connectToMailbox(mailboxId);
      if (result.success) {
        const linkedEmail = result.gmail_email;
        const currentMailbox = mailboxes.find(m => m.id === mailboxId);

        // Validate: prevent reconnecting with a different Gmail account
        if (linkedEmail && currentMailbox?.email_address) {
          if (linkedEmail.toLowerCase() !== currentMailbox.email_address.toLowerCase()) {
            toast.error(`Cannot reconnect with ${linkedEmail}. This mailbox is associated with ${currentMailbox.email_address}. Please use the same Gmail account.`);
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

        toast.success(result.message || 'Gmail reconnected successfully');
        mailboxService.clearCache();
        invalidateMailboxes();
      } else {
        toast.error(result.message || 'Failed to reconnect Gmail');
      }
    } catch (error: any) {
      if (error?.message?.includes('cancelled')) {
        toast.info('Reconnection cancelled');
      } else {
        toast.error(error?.message || 'Failed to reconnect Gmail');
      }
    } finally {
      setLinkingMailboxId(null);
    }
  };

  const handleReconnectOutlook = async (mailboxId: string, mailboxName: string) => {
    try {
      setLinkingMailboxId(mailboxId);
      toast.info(`Reconnecting Outlook for ${mailboxName}...`);
      const result = await outlookService.connectToMailbox(mailboxId);
      if (result.success) {
        const linkedEmail = result.outlook_email;
        const currentMailbox = mailboxes.find(m => m.id === mailboxId);

        // Validate: prevent reconnecting with a different Outlook account
        if (linkedEmail && currentMailbox?.email_address) {
          if (linkedEmail.toLowerCase() !== currentMailbox.email_address.toLowerCase()) {
            toast.error(`Cannot reconnect with ${linkedEmail}. This mailbox is associated with ${currentMailbox.email_address}. Please use the same Outlook account.`);
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

        toast.success(result.message || 'Outlook reconnected successfully');
        mailboxService.clearCache();
        invalidateMailboxes();
      } else {
        toast.error(result.message || 'Failed to reconnect Outlook');
      }
    } catch (error: any) {
      if (error?.message?.includes('cancelled')) {
        toast.info('Reconnection cancelled');
      } else {
        toast.error(error?.message || 'Failed to reconnect Outlook');
      }
    } finally {
      setLinkingMailboxId(null);
    }
  };

  const handleOpenDateRangeFetch = (mailbox: Mailbox) => {
    setSelectedMailboxForFetch(mailbox);
    setFetchStartDate('');
    setFetchEndDate('');
    setFetchMaxEmails('');
    setDateRangeModalVisible(true);
  };

  const handleDateRangeFetch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMailboxForFetch) return;

    if (!profile?.id) {
      toast.error('User not authenticated');
      return;
    }

    if (!fetchStartDate || !fetchEndDate) {
      toast.error('Please select a date range');
      return;
    }

    const startDate = fetchStartDate;
    const endDate = fetchEndDate;

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
          fetchMaxEmails || undefined
        );
      } else {
        // Default to Gmail
        result = await gmailService.fetchEmailsByDateRange(
          selectedMailboxForFetch.id,
          profile.id,
          startDate,
          endDate,
          fetchMaxEmails || undefined
        );
      }

      if (result.success) {
        toast.success(`${result.message}. Job ID: ${result.job_id}`);
        setDateRangeModalVisible(false);
        // Navigate to processing page filtered to this mailbox
        navigate(`/processing/${selectedMailboxForFetch.id}`);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('Failed to start email fetch');
    } finally {
      setFetchingEmails(false);
    }
  };

  // Quick date presets
  const applyDatePreset = (days: number) => {
    const end = dayjs().format('YYYY-MM-DD');
    const start = dayjs().subtract(days, 'day').format('YYYY-MM-DD');
    setFetchStartDate(start);
    setFetchEndDate(end);
  };

  // Helper: Detect email provider from domain for validation
  const getEmailProvider = (email?: string): 'gmail' | 'outlook' | 'unknown' => {
    if (!email) return 'unknown';
    const domain = email.toLowerCase().split('@')[1];
    if (domain === 'gmail.com') return 'gmail';
    if (['outlook.com', 'hotmail.com', 'live.com', 'msn.com'].includes(domain)) return 'outlook';
    return 'unknown';
  };

  // Helper: Type badge colors
  const typeConfig: Record<string, { label: string; variant: 'success' | 'info' | 'purple' | 'neutral' }> = {
    mbox: { label: 'MBOX', variant: 'success' },
    pst: { label: 'PST', variant: 'info' },
    olm: { label: 'OLM', variant: 'purple' },
    gmail: { label: 'Gmail LIVE', variant: 'info' },
    outlook_live: { label: 'Outlook LIVE', variant: 'info' },
  };

  return (
    <PageShell>
      <PageHeader
        title="Mailboxes"
        description="Manage your email sources for intelligence gathering"
        actions={
          <button
            onClick={() => navigate('/mailboxes/create')}
            className="h-8 px-3 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark inline-flex items-center gap-1.5"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Mailbox
          </button>
        }
      />

      {/* Auth Expired Banner */}
      {mailboxesWithExpiredAuth.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">
                {mailboxesWithExpiredAuth.length} mailbox{mailboxesWithExpiredAuth.length > 1 ? 'es need' : ' needs'} reauthentication
              </p>
              <p className="text-xs text-amber-700 mt-1">
                {mailboxesWithExpiredAuth.map(m => m.name).join(', ')} — the Gmail or Outlook connection has expired. Find the mailbox below and click the Reconnect action to restore sync.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        {loading && mailboxes.length === 0 ? (
          <ContentSkeleton rows={5} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-slate-50/50">
                    <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Name</th>
                    <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Type</th>
                    <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Status</th>
                    <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Sync Status</th>
                    <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Errors</th>
                    {isAdmin && (
                      <>
                        <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Client</th>
                        <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Account Manager</th>
                      </>
                    )}
                    <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Emails</th>
                    <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Last Sync</th>
                    <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {mailboxes.map((record) => {
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

                    const displayType = (record.connection_config as any)?.original_type || record.mailbox_type;
                    const cfg = (record.connection_config || {}) as Record<string, unknown>;
                    const isAuthExpired = cfg.gmail_sync_status === 'auth_expired' || cfg.outlook_sync_status === 'auth_expired';
                    const isLiveEnabled = hasGmailLiveSync(record);

                    const tc = typeConfig[displayType] || { label: displayType.toUpperCase(), variant: 'neutral' as const };

                    // Count failed jobs for this mailbox
                    const failedJobs = processingJobs.filter(
                      j => j.mailbox_id === record.id && (j.status === 'failed' || j.failed_records > 0)
                    );
                    const totalFailed = failedJobs.reduce((sum: number, j: any) => sum + (j.failed_records || 0), 0);

                    return (
                      <tr key={record.id} className="hover:bg-slate-50/50">
                        {/* Name */}
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2">
                            <Mail className="h-4 w-4 text-slate-400 shrink-0" />
                            <div>
                              <div className="font-medium text-slate-900">{record.name}</div>
                              <div className="text-xs text-slate-500">{record.email_address}</div>
                            </div>
                          </div>
                        </td>

                        {/* Type */}
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1">
                            <StatusBadge variant={tc.variant} size="sm">{tc.label}</StatusBadge>
                            {isLiveEnabled && !isAuthExpired && (
                              <StatusBadge variant="info" size="sm">
                                <Zap className="h-3 w-3 mr-0.5" />LIVE
                              </StatusBadge>
                            )}
                            {isAuthExpired && (
                              <StatusBadge variant="warning" size="sm">
                                <AlertCircle className="h-3 w-3 mr-0.5" />Reconnect
                              </StatusBadge>
                            )}
                          </div>
                        </td>

                        {/* Status */}
                        <td className="px-4 py-2.5">
                          <StatusBadge variant={record.is_active ? 'success' : 'neutral'} size="sm">
                            {record.is_active ? 'Active' : 'Inactive'}
                          </StatusBadge>
                        </td>

                        {/* Sync Status */}
                        <td className="px-4 py-2.5">
                          <ProcessingStatusBadge
                            mailboxId={record.id}
                            jobs={processingJobs}
                            showProgress={false}
                            onClick={() => navigate(`/processing/${record.id}`)}
                          />
                        </td>

                        {/* Errors */}
                        <td className="px-4 py-2.5">
                          {totalFailed === 0 && failedJobs.length === 0 ? (
                            <span className="text-slate-400">-</span>
                          ) : (
                            <button
                              className="text-xs text-red-600 hover:text-red-700 inline-flex items-center gap-1"
                              onClick={() => navigate(`/manage/errors/${record.id}`)}
                            >
                              <AlertCircle className="h-3.5 w-3.5" />
                              {totalFailed > 0 ? totalFailed : failedJobs.length}
                            </button>
                          )}
                        </td>

                        {/* Client (admin only) */}
                        {isAdmin && (
                          <td className="px-4 py-2.5">
                            {clientsUsersLoading ? (
                              <Skeleton className="h-4 w-24" />
                            ) : (() => {
                              const client = clients.find(c => c.id === record.client_id);
                              return client ? (
                                <div className="flex items-center gap-1.5 text-sm text-slate-700">
                                  <Users className="h-3.5 w-3.5 text-slate-400" />
                                  {client.client_name}
                                </div>
                              ) : (
                                <button
                                  onClick={() => handleOpenAssignment(record, 'client')}
                                  className="text-xs text-primary hover:underline inline-flex items-center gap-1"
                                >
                                  <Users className="h-3.5 w-3.5" />
                                  Assign Client
                                </button>
                              );
                            })()}
                          </td>
                        )}

                        {/* Account Manager (admin only) */}
                        {isAdmin && (
                          <td className="px-4 py-2.5">
                            {clientsUsersLoading ? (
                              <Skeleton className="h-4 w-24" />
                            ) : (() => {
                              const user = users.find(u => u.id === record.user_id);
                              return user ? (
                                <div className="flex items-center gap-1.5 text-sm text-slate-700">
                                  <User className="h-3.5 w-3.5 text-slate-400" />
                                  {user.name}
                                </div>
                              ) : (
                                <button
                                  onClick={() => handleOpenAssignment(record, 'user')}
                                  className="text-xs text-primary hover:underline inline-flex items-center gap-1"
                                >
                                  <User className="h-3.5 w-3.5" />
                                  Assign User
                                </button>
                              );
                            })()}
                          </td>
                        )}

                        {/* Emails */}
                        <td className="px-4 py-2.5 text-right">
                          <button
                            onClick={() => navigate(`/emails/${record.id}`)}
                            className="text-sm text-primary hover:underline inline-flex items-center gap-1 tabular-nums"
                          >
                            <Mail className="h-3.5 w-3.5" />
                            {record.total_emails.toLocaleString('en-AU')}
                          </button>
                        </td>

                        {/* Last Sync */}
                        <td className="px-4 py-2.5 text-sm text-slate-600">
                          {record.last_sync_at ? formatDateTime(record.last_sync_at) : 'Never'}
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1 flex-wrap">
                            {/* Sync dropdown button */}
                            <div className="relative" data-sync-dropdown>
                              <div className="inline-flex rounded-md shadow-sm">
                                <button
                                  onClick={() => handleSync(record.id, record.name)}
                                  disabled={!record.is_active}
                                  className={cn(
                                    'h-7 px-2.5 text-xs font-medium rounded-l-md border inline-flex items-center gap-1',
                                    record.is_active
                                      ? 'bg-primary text-white border-primary hover:bg-primary-dark'
                                      : 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed'
                                  )}
                                >
                                  <RefreshCw className="h-3 w-3" /> Sync
                                </button>
                                <button
                                  onClick={() => setOpenSyncDropdown(openSyncDropdown === record.id ? null : record.id)}
                                  disabled={!record.is_active}
                                  className={cn(
                                    'h-7 px-1.5 text-xs rounded-r-md border-t border-r border-b inline-flex items-center',
                                    record.is_active
                                      ? 'bg-primary text-white border-primary hover:bg-primary-dark'
                                      : 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed'
                                  )}
                                >
                                  <ChevronDown className="h-3 w-3" />
                                </button>
                              </div>
                              {openSyncDropdown === record.id && (
                                <div className="absolute right-0 mt-1 w-48 rounded-md border bg-white shadow-lg z-20">
                                  <div className="py-1">
                                    <button
                                      onClick={() => { handleSync(record.id, record.name); setOpenSyncDropdown(null); }}
                                      className="w-full px-3 py-1.5 text-left text-xs hover:bg-slate-50 flex items-center gap-2"
                                    >
                                      <RefreshCw className="h-3.5 w-3.5 text-slate-400" /> Sync Now
                                    </button>
                                    {isAnyLiveSync && (
                                      <button
                                        onClick={() => { handleOpenDateRangeFetch(record); setOpenSyncDropdown(null); }}
                                        className="w-full px-3 py-1.5 text-left text-xs hover:bg-slate-50 flex items-center gap-2"
                                      >
                                        <Calendar className="h-3.5 w-3.5 text-slate-400" /> Fetch Date Range
                                      </button>
                                    )}
                                    <button
                                      onClick={() => { navigate(`/processing/${record.id}`); setOpenSyncDropdown(null); }}
                                      className="w-full px-3 py-1.5 text-left text-xs hover:bg-slate-50 flex items-center gap-2"
                                    >
                                      <Eye className="h-3.5 w-3.5 text-slate-400" /> View Sync History
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>

                            {/* Reconnect buttons - shown when OAuth token has expired */}
                            {gmailAuthExpired && (
                              <button
                                onClick={() => handleReconnectGmail(record.id, record.name)}
                                disabled={linkingMailboxId === record.id}
                                className="h-7 px-2.5 text-xs font-medium rounded-md border border-red-300 text-red-600 hover:bg-red-50 inline-flex items-center gap-1 disabled:opacity-50"
                              >
                                {linkingMailboxId === record.id ? <Spinner className="h-3 w-3 animate-spin" /> : null}
                                Reconnect Gmail
                              </button>
                            )}
                            {outlookAuthExpired && (
                              <button
                                onClick={() => handleReconnectOutlook(record.id, record.name)}
                                disabled={linkingMailboxId === record.id}
                                className="h-7 px-2.5 text-xs font-medium rounded-md border border-red-300 text-red-600 hover:bg-red-50 inline-flex items-center gap-1 disabled:opacity-50"
                              >
                                {linkingMailboxId === record.id ? <Spinner className="h-3 w-3 animate-spin" /> : null}
                                Reconnect Outlook
                              </button>
                            )}

                            {/* Link Gmail - enforces mutual exclusivity and email domain validation */}
                            {canLinkGmail && (
                              <button
                                onClick={() => handleLinkGmail(record.id, record.name)}
                                disabled={linkingMailboxId === record.id}
                                title="Link Gmail account for LIVE sync"
                                className="h-7 px-2.5 text-xs font-medium rounded-md border border-blue-300 text-blue-600 hover:bg-blue-50 inline-flex items-center gap-1 disabled:opacity-50"
                              >
                                {linkingMailboxId === record.id ? <Spinner className="h-3 w-3 animate-spin" /> : <LinkIcon className="h-3 w-3" />}
                                Link Gmail
                              </button>
                            )}

                            {/* Link Outlook - enforces mutual exclusivity and email domain validation */}
                            {canLinkOutlook && (
                              <button
                                onClick={() => handleLinkOutlook(record.id, record.name)}
                                disabled={linkingMailboxId === record.id}
                                title="Link Outlook account for LIVE sync"
                                className="h-7 px-2.5 text-xs font-medium rounded-md border border-sky-300 text-sky-700 hover:bg-sky-50 inline-flex items-center gap-1 disabled:opacity-50"
                              >
                                {linkingMailboxId === record.id ? <Spinner className="h-3 w-3 animate-spin" /> : <LinkIcon className="h-3 w-3" />}
                                Link Outlook
                              </button>
                            )}

                            <button
                              onClick={() => navigate(`/mailboxes/edit/${record.id}`)}
                              className="p-1.5 rounded hover:bg-slate-100"
                              title="Edit"
                            >
                              <Pencil className="h-3.5 w-3.5 text-slate-400" />
                            </button>
                            <button
                              onClick={() => handleDelete(record.id)}
                              className="p-1.5 rounded hover:bg-red-50"
                              title="Delete"
                            >
                              <Trash2 className="h-3.5 w-3.5 text-red-400" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {mailboxes.length === 0 && !loading && (
              <div className="py-12 text-center text-sm text-slate-400">
                No mailboxes found. Click "Add Mailbox" to create one.
              </div>
            )}
          </>
        )}
      </div>

      {/* Date Range Fetch Modal */}
      <Dialog open={dateRangeModalVisible} onOpenChange={setDateRangeModalVisible}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-green-500" />
              Fetch Historical Emails
            </DialogTitle>
          </DialogHeader>

          {(() => {
            const syncType = selectedMailboxForFetch ? getLiveSyncType(selectedMailboxForFetch) : null;
            const providerName = syncType === 'outlook' ? 'Outlook' : 'Gmail';
            return (
              <p className="text-sm text-slate-500 -mt-2">
                Pull historical emails from <strong>{providerName}</strong> for <strong>{selectedMailboxForFetch?.name}</strong> within a specific date range.
                This uses the LIVE sync connection to fetch older emails on-demand.
              </p>
            );
          })()}

          <form onSubmit={handleDateRangeFetch} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Date Range</label>
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={fetchStartDate}
                  onChange={e => setFetchStartDate(e.target.value)}
                  max={dayjs().format('YYYY-MM-DD')}
                  required
                  className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 flex-1"
                />
                <span className="text-sm text-slate-400">to</span>
                <input
                  type="date"
                  value={fetchEndDate}
                  onChange={e => setFetchEndDate(e.target.value)}
                  max={dayjs().format('YYYY-MM-DD')}
                  required
                  className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 flex-1"
                />
              </div>
              <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                <span className="text-xs text-slate-400">Quick:</span>
                {[
                  { label: '7d', days: 7 },
                  { label: '30d', days: 30 },
                  { label: '3mo', days: 90 },
                  { label: '6mo', days: 180 },
                  { label: '1yr', days: 365 },
                ].map(preset => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => applyDatePreset(preset.days)}
                    className="px-2 py-0.5 text-xs rounded border border-slate-200 hover:bg-slate-50 text-slate-600"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Maximum Emails (optional)
              </label>
              <input
                type="number"
                value={fetchMaxEmails}
                onChange={e => setFetchMaxEmails(e.target.value ? parseInt(e.target.value) : '')}
                min={1}
                max={10000}
                placeholder="No limit"
                className="h-9 w-full px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
              <p className="text-xs text-slate-400 mt-1">Leave empty to fetch all emails in the date range</p>
            </div>

            <DialogFooter>
              <button
                type="button"
                onClick={() => setDateRangeModalVisible(false)}
                className="h-8 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={fetchingEmails}
                className="h-8 px-3 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 inline-flex items-center gap-1.5 disabled:opacity-50"
              >
                {fetchingEmails ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <History className="h-3.5 w-3.5" />}
                Start Fetch
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Assignment Modal */}
      {isAdmin && (
        <Dialog open={assignmentModalVisible} onOpenChange={setAssignmentModalVisible}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {assignmentType === 'client' ? <Users className="h-5 w-5" /> : <User className="h-5 w-5" />}
                Assign {assignmentType === 'client' ? 'Client' : 'Account Manager'} to {selectedMailboxForAssignment?.name}
              </DialogTitle>
            </DialogHeader>

            <div className="space-y-4">
              <select
                className="h-9 w-full px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
                onChange={(e) => handleAssignmentSubmit(e.target.value || null)}
                disabled={assignmentLoading}
                defaultValue=""
              >
                <option value="">
                  Select {assignmentType === 'client' ? 'client' : 'account manager'}
                </option>
                {assignmentType === 'client'
                  ? clients.map(c => (
                    <option key={c.id} value={c.id}>{c.client_name}</option>
                  ))
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

                    return filteredUsers.map(u => (
                      <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
                    ));
                  })()
                }
              </select>

              <p className="text-xs text-slate-500">
                {assignmentType === 'client'
                  ? 'Assign this mailbox to a client. Client Managers assigned to this client will be able to access it.'
                  : selectedMailboxForAssignment?.client_id
                    ? 'Assign this mailbox to an account manager who is assigned to this client.'
                    : 'First assign this mailbox to a client, then assign an account manager.'}
              </p>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </PageShell>
  );
};

export const MailboxCreate: React.FC = () => {
  return <MailboxCreateForm />;
};

export const MailboxEdit: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  if (!id) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-slate-500">Invalid mailbox ID</p>
      </div>
    );
  }

  return <MailboxEditForm mailboxId={id} />;
};
