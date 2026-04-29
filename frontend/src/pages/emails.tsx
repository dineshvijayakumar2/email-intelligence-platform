import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useNavigate } from 'react-router-dom';
import { emailService, Email } from '../services/emailService';
import { mailboxService, Mailbox } from '../services/mailboxService';
import SyncStatusBar from '../components/SyncStatusBar';
import {
  EmailDetailPanel, getCategoryLabel, getInitials, getAvatarColor, filterContentTags,
} from '../components/EmailDetailPanel';
import { formatRelativeDate } from '../utils/dateUtils';
import { useEmails, useEmailDetail, useContactEmails, useCompanyEmails, useThreadEmails, useMailboxes, useProcessingJobs } from '../hooks/queries';
import { useEmailFilters } from '../hooks/useEmailFilters';
import { cn } from '@/lib/utils';
import { useClient } from '@/contexts/ClientContext';
import { JourneySidebar } from '@/components/JourneySidebar';
import {
  Search, Mail, Send, Trash2, Star, Inbox, Folder, RefreshCw,
  ArrowLeft, Paperclip, Maximize2, Minimize2, LayoutGrid, X,
  ChevronLeft, ChevronRight, User, Link2,
} from 'lucide-react';

// ── Email List Item ──────────────────────────────────────────────
const EmailListItem: React.FC<{ email: Email; isSelected: boolean; onClick: () => void }> = React.memo(({ email, isSelected, onClick }) => {
  const contentTags = filterContentTags(email.tags || []);
  const hasAttachments = email.message_size > 50000;
  return (
    <div className={cn('flex gap-3 px-4 py-3 cursor-pointer border-b border-slate-100 transition-colors',
      isSelected ? 'bg-primary/5 border-l-2 border-l-primary' : 'hover:bg-slate-50')}
      onClick={onClick}>
      <div className="w-9 h-9 rounded-full flex items-center justify-center text-white text-xs font-medium shrink-0"
        style={{ backgroundColor: getAvatarColor(email.sender_email) }}>
        {getInitials(email.sender_name || '', email.sender_email)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium text-sm text-slate-900 truncate">{email.sender_name || email.sender_email}</span>
          <span className="text-[11px] text-slate-400 shrink-0">{formatRelativeDate(email.sent_date)}</span>
        </div>
        <p className="text-sm text-slate-600 truncate mt-0.5">{email.subject || '(No subject)'}</p>
        <div className="flex items-center gap-1.5 mt-1">
          {email.is_outbound && <span className="px-1 py-0 text-[10px] rounded bg-success-subtle text-success">Sent</span>}
          {contentTags.slice(0, 2).map(tag => <span key={tag} className="px-1 py-0 text-[10px] rounded bg-slate-100 text-slate-500">{getCategoryLabel(tag)}</span>)}
          {hasAttachments && <Paperclip className="h-3 w-3 text-slate-300" />}
        </div>
      </div>
    </div>
  );
});

// ── System folder config ─────────────────────────────────────────
const SYSTEM_FOLDERS = [
  { key: '', label: 'All Mail', icon: <LayoutGrid className="h-4 w-4" /> },
  { key: 'Inbox', label: 'Inbox', icon: <Inbox className="h-4 w-4" /> },
  { key: 'Sent', label: 'Sent', icon: <Send className="h-4 w-4" /> },
  { key: 'Starred', label: 'Starred', icon: <Star className="h-4 w-4" /> },
  { key: 'Trash', label: 'Trash', icon: <Trash2 className="h-4 w-4" /> },
];

// ── Main Component ──────────────────────────────────────────────
export const EmailList: React.FC = () => {
  const { mailboxId, emailId } = useParams<{ mailboxId?: string; emailId?: string }>();
  const navigate = useNavigate();
  const { clientId } = useClient();

  // 1. Consolidated filters + analytics mode
  const {
    filters, setFilter, clearFilters, hasActiveFilters,
    debouncedSearch, debouncedSender,
    page, setPage, pageSize,
    queryFilters, analyticsMode,
  } = useEmailFilters();

  // 2. Mailbox data
  const mailboxesQuery = useMailboxes();
  const accessibleMailboxes = mailboxesQuery.data || [];
  const mailboxesLoading = mailboxesQuery.isLoading;

  const { mailboxIdMap, mailboxIdToNameMap } = useMemo(() => {
    const idMap: Record<string, string> = {};
    const nameMap: Record<string, string> = {};
    accessibleMailboxes.forEach((m: Mailbox) => { idMap[m.name] = m.id; nameMap[m.id] = m.name; });
    return { mailboxIdMap: idMap, mailboxIdToNameMap: nameMap };
  }, [accessibleMailboxes]);

  const mailboxName = mailboxId ? (mailboxIdToNameMap[mailboxId] || '') : '';

  // 3. Categories + folders
  const [categories, setCategories] = useState<string[]>([]);
  const [folders, setFolders] = useState<string[]>([]);

  useEffect(() => {
    if (analyticsMode.isActive) return;
    emailService.getEmailCategories().then(setCategories).catch(() => {});
  }, [analyticsMode.isActive]);

  useEffect(() => {
    if (!mailboxName || !mailboxIdMap[mailboxName]) return;
    emailService.getFolderNames(mailboxIdMap[mailboxName]).then(setFolders).catch(() => {});
  }, [mailboxName, mailboxIdMap]);

  // 4. Email data — unified across modes
  const emailQueryFilters = useMemo(() => ({
    ...queryFilters, mailbox: mailboxName || undefined,
  }), [queryFilters, mailboxName]);

  const emailsQuery = useEmails({
    filters: emailQueryFilters, page, pageSize,
    sort_by: filters.sortBy, sort_dir: filters.sortDir,
  });
  const contactEmailsQuery = useContactEmails(analyticsMode.contactId);
  const companyEmailsQuery = useCompanyEmails(analyticsMode.companyId);
  const threadEmailsQuery = useThreadEmails(analyticsMode.threadId);
  const singleEmailQuery = useEmailDetail(analyticsMode.emailId);

  const { emails, totalCount, loading } = useMemo(() => {
    if (analyticsMode.emailId) {
      const d = singleEmailQuery.data;
      return { emails: d ? [d as Email] : [], totalCount: d ? 1 : 0, loading: singleEmailQuery.isLoading };
    }
    if (analyticsMode.threadId) {
      const d = threadEmailsQuery.data;
      return { emails: d?.emails || [], totalCount: d?.total || 0, loading: threadEmailsQuery.isLoading };
    }
    if (analyticsMode.contactId) {
      const d = contactEmailsQuery.data;
      return { emails: d?.emails || [], totalCount: d?.total || 0, loading: contactEmailsQuery.isLoading };
    }
    if (analyticsMode.companyId) {
      const d = companyEmailsQuery.data;
      return { emails: d?.emails || [], totalCount: d?.total || 0, loading: companyEmailsQuery.isLoading };
    }
    return {
      emails: emailsQuery.data?.emails || [],
      totalCount: emailsQuery.data?.totalCount || 0,
      loading: emailsQuery.isLoading,
    };
  }, [analyticsMode, emailsQuery, contactEmailsQuery, companyEmailsQuery, threadEmailsQuery, singleEmailQuery]);

  // 5. Selected email detail
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(emailId || null);
  const selectedEmailQuery = useEmailDetail(
    analyticsMode.emailId ? null : selectedEmailId,
  );
  const selectedEmail = analyticsMode.emailId
    ? (singleEmailQuery.data as Email | null)
    : (selectedEmailQuery.data as Email | null);
  const detailLoading = analyticsMode.emailId ? singleEmailQuery.isLoading : selectedEmailQuery.isLoading;

  // 6. UI state
  const [detailExpanded, setDetailExpanded] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [journeyOpen, setJourneyOpen] = useState(true);

  // 7. Processing jobs
  const processingJobsQuery = useProcessingJobs(!analyticsMode.isActive);
  const processingJobs = processingJobsQuery.data || [];

  // ── Navigation effects ─────────────────────────────────────────
  useEffect(() => {
    if (analyticsMode.isActive || mailboxesLoading) return;
    if (accessibleMailboxes.length > 0 && !mailboxId) {
      navigate(`/emails/${accessibleMailboxes[0].id}`, { replace: true });
    }
  }, [accessibleMailboxes, mailboxId, navigate, analyticsMode.isActive, mailboxesLoading]);

  useEffect(() => {
    if (mailboxesLoading || analyticsMode.isActive) return;
    if (mailboxId && !mailboxIdToNameMap[mailboxId] && Object.keys(mailboxIdToNameMap).length > 0) {
      navigate('/mailboxes', { replace: true });
    }
  }, [mailboxId, mailboxIdToNameMap, mailboxesLoading, analyticsMode.isActive]);

  useEffect(() => {
    if (analyticsMode.isActive) return;
    if (emailId && emailId !== selectedEmailId) setSelectedEmailId(emailId);
    else if (!emailId && selectedEmailId) setSelectedEmailId(null);
  }, [emailId, analyticsMode.isActive]);

  // Auto-select first email in single-email analytics mode
  useEffect(() => {
    if (analyticsMode.emailId && singleEmailQuery.data) {
      setSelectedEmailId(analyticsMode.emailId);
    }
  }, [analyticsMode.emailId, singleEmailQuery.data]);

  // ── Handlers ───────────────────────────────────────────────────
  const handleEmailSelect = useCallback((email: Email) => {
    setSelectedEmailId(email.id);
    if (!analyticsMode.isActive && mailboxId) navigate(`/emails/${mailboxId}/${email.id}`);
  }, [analyticsMode.isActive, mailboxId, navigate]);

  const handleCloseDetail = useCallback(() => {
    setSelectedEmailId(null);
    if (!analyticsMode.isActive && mailboxId) navigate(`/emails/${mailboxId}`);
  }, [analyticsMode.isActive, mailboxId, navigate]);

  const handleFolderSelect = useCallback((key: string) => {
    setPage(1);
    setSelectedEmailId(null);
    if (key === '') { setFilter('folder', ''); return; }
    const match = folders.find(f => f === key)
      || folders.find(f => f.toLowerCase() === key.toLowerCase())
      || folders.find(f => f.toLowerCase().includes(key.toLowerCase()));
    setFilter('folder', match || key);
  }, [folders, setFilter, setPage]);

  // ── Derived ────────────────────────────────────────────────────
  const displayEmails = useMemo(() => {
    if (!analyticsMode.isActive || !filters.search) return emails;
    const q = filters.search.toLowerCase();
    return emails.filter(e =>
      (e.subject || '').toLowerCase().includes(q) ||
      (e.sender_name || '').toLowerCase().includes(q) ||
      (e.sender_email || '').toLowerCase().includes(q),
    );
  }, [analyticsMode.isActive, emails, filters.search]);

  const currentFolderKey = useMemo(() => {
    if (!filters.folder) return '';
    const l = filters.folder.toLowerCase();
    if (l.includes('inbox')) return 'Inbox';
    if (l.includes('sent')) return 'Sent';
    if (l.includes('starred') || l.includes('flagged')) return 'Starred';
    if (l.includes('trash') || l.includes('deleted')) return 'Trash';
    return filters.folder;
  }, [filters.folder]);

  const additionalFolders = useMemo(() =>
    folders.filter(f => !['inbox', 'sent', 'starred', 'flagged', 'trash', 'deleted'].some(s => f.toLowerCase().includes(s))),
  [folders]);

  const totalPages = Math.ceil(totalCount / pageSize);

  // ── Render ─────────────────────────────────────────────────────
  return (
    <div className="flex h-[calc(100vh-56px)]">
      {/* ── Folder sidebar ── */}
      {!analyticsMode.isActive && (
        <div className={cn('border-r bg-white flex flex-col shrink-0 transition-all duration-200', sidebarCollapsed ? 'w-14' : 'w-56')}>
          <div className="flex items-center gap-2 px-3 py-3 border-b">
            <button onClick={() => navigate('/mailboxes')} className="p-1 rounded hover:bg-slate-100" title="Back"><ArrowLeft className="h-4 w-4 text-slate-500" /></button>
            {!sidebarCollapsed && <span className="text-sm font-semibold text-slate-800 truncate flex-1">{mailboxName || 'Loading...'}</span>}
            <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="p-1 rounded hover:bg-slate-100">
              {sidebarCollapsed ? <Maximize2 className="h-3.5 w-3.5 text-slate-400" /> : <Minimize2 className="h-3.5 w-3.5 text-slate-400" />}
            </button>
          </div>
          <div className="flex-1 overflow-y-auto py-2">
            {!sidebarCollapsed && <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Folders</p>}
            {SYSTEM_FOLDERS.map(f => (
              <button key={f.key} onClick={() => handleFolderSelect(f.key)}
                className={cn('w-full flex items-center gap-2.5 px-3 py-1.5 text-sm transition-colors',
                  currentFolderKey === f.key ? 'text-primary bg-primary/5 font-medium' : 'text-slate-600 hover:bg-slate-50')}>
                {f.icon}{!sidebarCollapsed && <span>{f.label}</span>}
              </button>
            ))}
            {additionalFolders.length > 0 && (
              <>
                <div className="h-px bg-slate-100 mx-3 my-2" />
                {additionalFolders.map(f => (
                  <button key={f} onClick={() => { setFilter('folder', f); setPage(1); }}
                    className={cn('w-full flex items-center gap-2.5 px-3 py-1.5 text-sm transition-colors',
                      filters.folder === f ? 'text-primary bg-primary/5 font-medium' : 'text-slate-600 hover:bg-slate-50')}>
                    <Folder className="h-4 w-4" />{!sidebarCollapsed && <span className="truncate">{f}</span>}
                  </button>
                ))}
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Main content + journey sidebar ── */}
      <div className="flex-1 flex min-w-0">
        {/* Main area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Analytics banner */}
          {analyticsMode.isActive && (
            <div className="flex items-center gap-3 px-5 py-2.5 bg-primary-subtle border-b">
              <button onClick={() => navigate(-1)} className="text-sm text-primary hover:underline inline-flex items-center gap-1"><ArrowLeft className="h-4 w-4" />Back</button>
              <Mail className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium text-slate-800">Emails for {analyticsMode.label}</span>
              <span className="text-xs text-primary">{totalCount} email{totalCount !== 1 ? 's' : ''}</span>
              {analyticsMode.threadId && clientId && (
                <button
                  onClick={() => setJourneyOpen(o => !o)}
                  className={cn('ml-auto inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border transition-colors',
                    journeyOpen ? 'bg-primary/10 text-primary border-primary/20' : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50')}
                >
                  <Link2 className="h-3 w-3" />Journey
                </button>
              )}
            </div>
          )}

          {/* Filter bar */}
          <div className="flex items-center gap-2 px-5 py-2.5 border-b bg-white flex-wrap">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
              <input type="text" placeholder="Search subject, sender..." value={filters.search}
                onChange={e => setFilter('search', e.target.value)}
                className="w-full h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20" />
            </div>
            {!analyticsMode.isActive && (
              <>
                <div className="relative group">
                  <User className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400" />
                  <input placeholder="Person name or email..." value={filters.sender}
                    onChange={e => setFilter('sender', e.target.value)}
                    className="h-8 pl-7 pr-2 text-sm rounded-md border border-slate-200 bg-white w-48 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:w-64 transition-all"
                    title="Search across From, To, CC and BCC fields" />
                </div>

                <select value={`${filters.sortBy}|${filters.sortDir}`}
                  onChange={e => { const [sb, sd] = e.target.value.split('|'); setFilter('sortBy', sb); setFilter('sortDir', sd); }}
                  className="h-8 px-2 text-xs rounded-md border border-slate-200 bg-white">
                  <option value="sent_date|desc">Newest first</option>
                  <option value="sent_date|asc">Oldest first</option>
                  <option value="sender_name|asc">Sender A→Z</option>
                  <option value="subject|asc">Subject A→Z</option>
                </select>

                <div className="flex rounded-md border border-slate-200 overflow-hidden">
                  <button onClick={() => setFilter('direction', filters.direction === 'inbound' ? '' : 'inbound')}
                    className={cn('px-2.5 py-1 text-xs transition-colors', filters.direction === 'inbound' ? 'bg-primary text-white' : 'bg-white text-slate-500 hover:bg-slate-50')}>
                    Received
                  </button>
                  <button onClick={() => setFilter('direction', filters.direction === 'outbound' ? '' : 'outbound')}
                    className={cn('px-2.5 py-1 text-xs border-l transition-colors', filters.direction === 'outbound' ? 'bg-primary text-white' : 'bg-white text-slate-500 hover:bg-slate-50')}>
                    Sent
                  </button>
                </div>

                {hasActiveFilters && <button onClick={clearFilters} className="text-xs text-primary hover:underline inline-flex items-center gap-0.5"><X className="h-3 w-3" />Clear</button>}
                <button onClick={() => { setSelectedEmailId(null); emailsQuery.refetch(); }} className="p-1.5 rounded hover:bg-slate-100">
                  <RefreshCw className={cn('h-3.5 w-3.5 text-slate-400', loading && 'animate-spin')} />
                </button>
              </>
            )}
          </div>

          {/* Sync status */}
          {!analyticsMode.isActive && mailboxName && mailboxIdMap[mailboxName] && (
            <SyncStatusBar selectedMailboxIds={[mailboxIdMap[mailboxName]]} jobs={processingJobs} onViewDetails={() => navigate('/processing')} />
          )}

          {/* Email list + detail split */}
          <div className="flex-1 flex overflow-hidden">
            {/* List */}
            <div className={cn('flex flex-col border-r bg-white transition-all duration-200', selectedEmail ? 'w-[380px] shrink-0' : 'flex-1')}>
              <div className="flex items-center justify-between px-4 py-2 border-b bg-slate-50/50">
                <span className="text-xs text-slate-500">
                  {loading && displayEmails.length === 0 ? 'Loading...'
                    : `${totalCount.toLocaleString('en-AU')} email${totalCount !== 1 ? 's' : ''}${filters.folder ? ` · ${filters.folder}` : ''}`}
                </span>
                {!analyticsMode.isActive && totalCount > pageSize && (
                  <div className="flex items-center gap-1">
                    <button onClick={() => { setPage(p => Math.max(1, p - 1)); setSelectedEmailId(null); }} disabled={page <= 1}
                      className="p-1 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronLeft className="h-3.5 w-3.5" /></button>
                    <span className="text-xs text-slate-500 tabular-nums">{page}/{totalPages}</span>
                    <button onClick={() => { setPage(p => Math.min(totalPages, p + 1)); setSelectedEmailId(null); }} disabled={page >= totalPages}
                      className="p-1 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronRight className="h-3.5 w-3.5" /></button>
                  </div>
                )}
              </div>
              <div className="flex-1 overflow-y-auto">
                {(!analyticsMode.isActive && mailboxesLoading) || (loading && displayEmails.length === 0) ? (
                  <div className="p-4 space-y-4">{[1, 2, 3, 4, 5].map(i => <div key={i} className="flex gap-3"><div className="w-9 h-9 rounded-full bg-slate-100 animate-pulse" /><div className="flex-1 space-y-2"><div className="h-3 w-3/5 bg-slate-100 rounded animate-pulse" /><div className="h-3 w-4/5 bg-slate-100 rounded animate-pulse" /></div></div>)}</div>
                ) : !analyticsMode.isActive && !mailboxName ? (
                  <div className="flex flex-col items-center justify-center h-full text-slate-400"><Mail className="h-10 w-10 mb-3" /><p className="text-sm">Select a mailbox</p></div>
                ) : displayEmails.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-slate-400"><Mail className="h-10 w-10 mb-3" /><p className="text-sm">{analyticsMode.isActive ? 'No emails linked' : 'No emails found'}</p></div>
                ) : (
                  displayEmails.map(email => <EmailListItem key={email.id} email={email} isSelected={selectedEmailId === email.id} onClick={() => handleEmailSelect(email)} />)
                )}
              </div>
            </div>

            {/* Detail panel */}
            {selectedEmail && (
              <div className="flex-1 overflow-y-auto bg-white">
                <EmailDetailPanel email={selectedEmail} loading={detailLoading} onClose={handleCloseDetail}
                  expanded={detailExpanded} onToggleExpand={() => setDetailExpanded(!detailExpanded)} />
              </div>
            )}
          </div>
        </div>

        {/* ── Journey sidebar (right, toggleable) ── */}
        {analyticsMode.threadId && clientId && (
          <JourneySidebar
            threadId={analyticsMode.threadId}
            clientId={clientId}
            isOpen={journeyOpen}
            onToggle={() => setJourneyOpen(o => !o)}
          />
        )}
      </div>
    </div>
  );
};
