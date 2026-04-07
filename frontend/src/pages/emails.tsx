import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { emailService, Email, EmailFilters } from '../services/emailService';
import { mailboxService, Mailbox } from '../services/mailboxService';
import SyncStatusBar from '../components/SyncStatusBar';
import { dashboardService } from '../services/dashboardService';
import { contactsApi, companiesApi, threadsApi } from '../services/analyticsService';
import {
  EmailDetailPanel,
  getCategoryColor,
  getCategoryLabel,
  getInitials,
  getAvatarColor,
  filterContentTags,
} from '../components/EmailDetailPanel';
import { formatRelativeDate } from '../utils/dateUtils';
import { useEmails } from '../hooks/queries';
import { cn } from '@/lib/utils';
import { toast } from '@/lib/toast';
import {
  Search, Mail, Send, Trash2, Star, Inbox, Folder, RefreshCw,
  ArrowLeft, Paperclip, Maximize2, Minimize2, LayoutGrid, X,
  ChevronLeft, ChevronRight, User, Calendar, ArrowUpDown,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { Skeleton } from '@/components/ui/skeleton';

// Email List Item Component
const EmailListItem: React.FC<{
  email: Email; isSelected: boolean; onClick: () => void;
}> = React.memo(({ email, isSelected, onClick }) => {
  const contentTags = filterContentTags(email.tags || []);
  const hasAttachments = email.message_size > 50000;
  const initials = getInitials(email.sender_name || '', email.sender_email);
  const avatarColor = getAvatarColor(email.sender_email);

  return (
    <div className={cn('email-list-item', isSelected && 'selected')} onClick={onClick}>
      <div className="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-medium shrink-0"
        style={{ backgroundColor: avatarColor }}>{initials}</div>
      <div className="email-list-item-content">
        <div className="email-list-item-header">
          <span className="font-medium text-slate-900 text-sm truncate email-sender">{email.sender_name || email.sender_email}</span>
          <span className="text-xs text-slate-400 email-date">{formatRelativeDate(email.sent_date)}</span>
        </div>
        <span className="text-sm text-slate-600 truncate email-subject">{email.subject || '(No subject)'}</span>
        <div className="email-list-item-footer">
          <div className="email-tags">
            {email.is_outbound && <span className="inline-flex px-1 py-0 text-[10px] rounded bg-success-subtle text-success">Sent</span>}
            {contentTags.slice(0, 2).map(tag => (
              <span key={tag} className="inline-flex px-1 py-0 text-[10px] rounded bg-slate-100 text-slate-500">
                {getCategoryLabel(tag)}
              </span>
            ))}
          </div>
          <div className="email-indicators">
            {hasAttachments && <Paperclip className="h-3 w-3 text-slate-400" />}
          </div>
        </div>
      </div>
    </div>
  );
});

// Main Email List Component
export const EmailList: React.FC = () => {
  const { mailboxId, emailId } = useParams<{ mailboxId?: string; emailId?: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Analytics mode
  const analyticsContactId = searchParams.get('contact_id');
  const analyticsCompanyId = searchParams.get('company_id');
  const analyticsThreadId = searchParams.get('thread_id');
  const analyticsEmailId = searchParams.get('email_id');
  const analyticsLabel = searchParams.get('name') || 'Contact';
  const isAnalyticsMode = !!(analyticsContactId || analyticsCompanyId || analyticsThreadId || analyticsEmailId);

  // State
  const [analyticsEmails, setAnalyticsEmails] = useState<Email[]>([]);
  const [analyticsTotal, setAnalyticsTotal] = useState(0);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailExpanded, setDetailExpanded] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [accessibleMailboxes, setAccessibleMailboxes] = useState<Mailbox[]>([]);
  const [mailboxesLoading, setMailboxesLoading] = useState(true);
  const [mailboxIdMap, setMailboxIdMap] = useState<Record<string, string>>({});
  const [mailboxIdToNameMap, setMailboxIdToNameMap] = useState<Record<string, string>>({});
  const [folders, setFolders] = useState<string[]>([]);
  const [foldersLoading, setFoldersLoading] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [processingJobs, setProcessingJobs] = useState<any[]>([]);
  const processingJobsRef = useRef<any[]>([]);

  // Filter state
  const [searchText, setSearchText] = useState('');
  const [senderSearch, setSenderSearch] = useState('');
  const [mailboxName, setMailboxName] = useState('');
  const [folderFilter, setFolderFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [directionFilter, setDirectionFilter] = useState('');
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sortBy, setSortBy] = useState('sent_date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Debounced search
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [debouncedSender, setDebouncedSender] = useState('');

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => { setDebouncedSearch(searchText); setDebouncedSender(senderSearch); setPage(1); }, 400);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [searchText, senderSearch]);

  // TanStack Query for emails
  const queryFilters: EmailFilters = useMemo(() => ({
    search: debouncedSearch || undefined, sender: debouncedSender || undefined,
    mailbox: mailboxName || undefined, folder: folderFilter || undefined,
    category: categoryFilter || undefined, isOutbound: directionFilter || undefined,
    dateRange: dateRange || undefined,
  }), [debouncedSearch, debouncedSender, mailboxName, folderFilter, categoryFilter, directionFilter, dateRange]);

  const emailsQuery = useEmails({ filters: queryFilters, page, pageSize, sort_by: sortBy, sort_dir: sortDir });
  const emails = isAnalyticsMode ? analyticsEmails : (emailsQuery.data?.emails || []);
  const totalCount = isAnalyticsMode ? analyticsTotal : (emailsQuery.data?.totalCount || 0);
  const loading = isAnalyticsMode ? analyticsLoading : emailsQuery.isLoading;

  // System folders
  const systemFolders = useMemo(() => [
    { key: '', label: 'All Mail', icon: <LayoutGrid className="h-4 w-4" /> },
    { key: 'Inbox', label: 'Inbox', icon: <Inbox className="h-4 w-4" /> },
    { key: 'Sent', label: 'Sent', icon: <Send className="h-4 w-4" /> },
    { key: 'Starred', label: 'Starred', icon: <Star className="h-4 w-4" /> },
    { key: 'Trash', label: 'Trash', icon: <Trash2 className="h-4 w-4" /> },
  ], []);

  const currentFolderKey = useMemo(() => {
    if (!folderFilter) return '';
    const lower = folderFilter.toLowerCase();
    if (lower.includes('inbox')) return 'Inbox';
    if (lower.includes('sent')) return 'Sent';
    if (lower.includes('starred') || lower.includes('flagged')) return 'Starred';
    if (lower.includes('trash') || lower.includes('deleted')) return 'Trash';
    return folderFilter;
  }, [folderFilter]);

  const additionalFolders = useMemo(() => {
    return folders.filter(f => {
      const lower = f.toLowerCase();
      return !['inbox', 'sent', 'starred', 'flagged', 'trash', 'deleted'].some(sys => lower.includes(sys));
    });
  }, [folders]);

  const hasActiveFilters = !!(categoryFilter || directionFilter || folderFilter || dateRange || debouncedSender);

  // Load mailboxes + categories
  useEffect(() => {
    if (isAnalyticsMode) { setMailboxesLoading(false); return; }
    (async () => {
      try {
        setMailboxesLoading(true);
        const [cats, mbs] = await Promise.all([emailService.getEmailCategories(), mailboxService.getMailboxes()]);
        setCategories(cats); setAccessibleMailboxes(mbs);
        const idMap: Record<string, string> = {}; const nameMap: Record<string, string> = {};
        mbs.forEach((m: Mailbox) => { idMap[m.name] = m.id; nameMap[m.id] = m.name; });
        setMailboxIdMap(idMap); setMailboxIdToNameMap(nameMap);
      } catch { /* silent */ } finally { setMailboxesLoading(false); }
    })();
  }, [isAnalyticsMode]);

  // Navigate to first mailbox
  useEffect(() => {
    if (isAnalyticsMode || mailboxesLoading) return;
    if (accessibleMailboxes.length > 0 && !mailboxId) navigate(`/emails/${accessibleMailboxes[0].id}`, { replace: true });
  }, [accessibleMailboxes, mailboxId, navigate, isAnalyticsMode, mailboxesLoading]);

  // Sync URL → mailbox name
  useEffect(() => {
    if (mailboxesLoading || isAnalyticsMode) return;
    if (mailboxId && mailboxIdToNameMap[mailboxId]) {
      const name = mailboxIdToNameMap[mailboxId];
      if (name !== mailboxName) { setMailboxName(name); setPage(1); if (!emailId) { setSelectedEmail(null); setSelectedEmailId(null); } }
    } else if (mailboxId && Object.keys(mailboxIdToNameMap).length > 0) { navigate('/mailboxes', { replace: true }); }
  }, [mailboxId, mailboxIdToNameMap, emailId, mailboxesLoading, isAnalyticsMode]);

  // Load folders
  useEffect(() => {
    if (!mailboxName || !mailboxIdMap[mailboxName]) return;
    (async () => { setFoldersLoading(true); try { setFolders(await emailService.getFolderNames(mailboxIdMap[mailboxName])); } catch {} finally { setFoldersLoading(false); } })();
  }, [mailboxName, mailboxIdMap]);

  // Email detail
  const loadEmailDetails = useCallback(async (id: string) => {
    setDetailLoading(true); setSelectedEmailId(id);
    try { setSelectedEmail(await emailService.getEmail(id)); } catch { toast.error('Failed to load email'); } finally { setDetailLoading(false); }
  }, []);

  useEffect(() => {
    if (isAnalyticsMode) return;
    if (emailId && emailId !== selectedEmailId) loadEmailDetails(emailId);
    else if (!emailId && selectedEmailId) { setSelectedEmail(null); setSelectedEmailId(null); }
  }, [emailId, selectedEmailId, loadEmailDetails, isAnalyticsMode]);

  // Analytics mode
  useEffect(() => {
    if (!isAnalyticsMode) return;
    (async () => {
      setAnalyticsLoading(true);
      try {
        if (analyticsEmailId) {
          const full = await emailService.getEmail(analyticsEmailId);
          if (full) { setAnalyticsEmails([full as Email]); setAnalyticsTotal(1); setSelectedEmail(full as Email); setSelectedEmailId(analyticsEmailId); }
        } else if (analyticsThreadId) {
          const detail = await threadsApi.getDetail(analyticsThreadId);
          const threadEmails = (detail?.emails || []).map((e: any) => ({ id: e.id, subject: e.subject || '', sender_email: e.sender_email || '', sender_name: e.sender_name || '', recipients: e.recipients || [], sent_date: e.sent_date || '', is_outbound: e.is_outbound ?? false, body_text: e.body_text || '', folder_path: e.folder_path || '' })) as Email[];
          setAnalyticsEmails(threadEmails); setAnalyticsTotal(threadEmails.length);
        } else {
          const result = analyticsContactId ? await contactsApi.getEmails(analyticsContactId, 100, 0) : await companiesApi.getEmails(analyticsCompanyId!, 100, 0);
          setAnalyticsEmails((result.emails || []) as Email[]); setAnalyticsTotal(result.total || 0);
        }
      } catch { toast.error('Failed to load emails'); } finally { setAnalyticsLoading(false); }
    })();
  }, [isAnalyticsMode, analyticsContactId, analyticsCompanyId, analyticsThreadId, analyticsEmailId]);

  // Processing jobs
  useEffect(() => {
    if (isAnalyticsMode) return;
    const load = async () => { try { const jobs = await dashboardService._fetchProcessingJobs(); if (jobs?.length) setProcessingJobs(jobs); } catch {} };
    load(); const interval = setInterval(load, 5000); return () => clearInterval(interval);
  }, [isAnalyticsMode]);
  useEffect(() => { processingJobsRef.current = processingJobs; }, [processingJobs]);

  // Handlers
  const handleFolderSelect = (key: string) => {
    setPage(1); setSelectedEmail(null); setSelectedEmailId(null);
    if (key === '') { setFolderFilter(''); return; }
    const matched = folders.find(f => f === key) || folders.find(f => f.toLowerCase() === key.toLowerCase()) || folders.find(f => f.toLowerCase().includes(key.toLowerCase()));
    setFolderFilter(matched || key);
  };
  const handleEmailSelect = (email: Email) => { if (isAnalyticsMode) loadEmailDetails(email.id); else if (mailboxId) navigate(`/emails/${mailboxId}/${email.id}`); };
  const handleCloseDetail = () => { if (isAnalyticsMode) { setSelectedEmail(null); setSelectedEmailId(null); } else if (mailboxId) navigate(`/emails/${mailboxId}`); };
  const handleRefresh = () => { setSelectedEmail(null); setSelectedEmailId(null); emailsQuery.refetch(); };
  const clearFilters = () => { setCategoryFilter(''); setDirectionFilter(''); setFolderFilter(''); setDateRange(null); setSenderSearch(''); setPage(1); };

  const displayEmails = useMemo(() => {
    if (!isAnalyticsMode || !searchText) return emails;
    const q = searchText.toLowerCase();
    return emails.filter(e => (e.subject || '').toLowerCase().includes(q) || (e.sender_name || '').toLowerCase().includes(q) || (e.sender_email || '').toLowerCase().includes(q));
  }, [isAnalyticsMode, emails, searchText]);

  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="mail-client">
      {/* Sidebar */}
      {!isAnalyticsMode && (
        <div className={`mail-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
          <div className="mail-sidebar-header">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <button onClick={() => navigate('/mailboxes')} className="p-1 rounded hover:bg-white/10" title="Back to Mailboxes">
                <ArrowLeft className="h-4 w-4 text-white/80" />
              </button>
              {!sidebarCollapsed && <span className="text-sm font-semibold text-white truncate">{mailboxName || 'Loading...'}</span>}
            </div>
            <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="p-1 rounded hover:bg-white/10">
              {sidebarCollapsed ? <Maximize2 className="h-4 w-4 text-white/80" /> : <Minimize2 className="h-4 w-4 text-white/80" />}
            </button>
          </div>
          <div className="mail-sidebar-section">
            <div className="mail-sidebar-section-title">
              {foldersLoading ? <Spinner className="h-4 w-4 animate-spin" /> : <Folder className="h-4 w-4" />} {!sidebarCollapsed && 'Folders'}
            </div>
            <div className="mail-sidebar-items">
              {mailboxesLoading ? (!sidebarCollapsed && <div className="p-3 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-4 w-20" />)}</div>)
                : !mailboxName ? (!sidebarCollapsed && <p className="p-3 text-center text-xs text-white/50">Select a mailbox</p>)
                : (<>
                    {systemFolders.map(f => (
                      <div key={f.key} className={`mail-sidebar-item ${currentFolderKey === f.key ? 'active' : ''}`} onClick={() => handleFolderSelect(f.key)}>
                        {f.icon}{!sidebarCollapsed && <span>{f.label}</span>}
                      </div>
                    ))}
                    {additionalFolders.length > 0 && (<><div className="mail-sidebar-divider" />{additionalFolders.map(f => (
                      <div key={f} className={`mail-sidebar-item ${folderFilter === f ? 'active' : ''}`} onClick={() => { setFolderFilter(f); setPage(1); }}>
                        <Folder className="h-4 w-4" />{!sidebarCollapsed && <span>{f}</span>}
                      </div>
                    ))}</>)}
                  </>)}
            </div>
          </div>
        </div>
      )}

      {/* Main */}
      <div className="mail-main">
        {isAnalyticsMode && (
          <div className="flex items-center gap-3 px-4 py-2.5 bg-primary-subtle border-b border-primary/20">
            <button onClick={() => navigate(-1)} className="text-primary hover:underline text-sm inline-flex items-center gap-1"><ArrowLeft className="h-4 w-4" />Back</button>
            <Mail className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium">Emails for {analyticsLabel}</span>
            <span className="text-xs text-primary">{totalCount} email{totalCount !== 1 ? 's' : ''}</span>
          </div>
        )}

        {/* Top bar */}
        <div className="mail-topbar">
          <div className="mail-topbar-left" style={{ flex: 1 }}>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
              <input type="text" placeholder="Search subject, sender..." value={searchText} onChange={e => setSearchText(e.target.value)}
                className="h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-64" />
            </div>
          </div>
          {!isAnalyticsMode && (
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative">
                <User className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400" />
                <input placeholder="From / To / CC..." value={senderSearch} onChange={e => setSenderSearch(e.target.value)}
                  className="h-7 pl-7 pr-2 text-xs rounded border border-slate-200 bg-white focus:outline-none focus:ring-1 focus:ring-primary/20 w-40" />
              </div>
              <select value={directionFilter} onChange={e => { setDirectionFilter(e.target.value); setPage(1); }}
                className="h-7 px-2 text-xs rounded border border-slate-200 bg-white">
                <option value="">Direction</option><option value="inbound">Received</option><option value="outbound">Sent</option>
              </select>
              {categories.length > 0 && (
                <select value={categoryFilter} onChange={e => { setCategoryFilter(e.target.value); setPage(1); }}
                  className="h-7 px-2 text-xs rounded border border-slate-200 bg-white">
                  <option value="">Category</option>{categories.map(c => <option key={c} value={c}>{getCategoryLabel(c)}</option>)}
                </select>
              )}
              <select value={`${sortBy}_${sortDir}`} onChange={e => { const [c, d] = e.target.value.split('_'); setSortBy(c); setSortDir(d as any); setPage(1); }}
                className="h-7 px-2 text-xs rounded border border-slate-200 bg-white">
                <option value="sent_date_desc">Newest</option><option value="sent_date_asc">Oldest</option>
                <option value="sender_name_asc">Sender A→Z</option><option value="subject_asc">Subject A→Z</option>
              </select>
              {hasActiveFilters && <button onClick={clearFilters} className="text-xs text-primary hover:underline inline-flex items-center gap-0.5"><X className="h-3 w-3" />Clear</button>}
              <button onClick={handleRefresh} className="p-1 rounded hover:bg-slate-100"><RefreshCw className={cn('h-3.5 w-3.5 text-slate-400', loading && 'animate-spin')} /></button>
            </div>
          )}
        </div>

        {!isAnalyticsMode && mailboxName && mailboxIdMap[mailboxName] && (
          <SyncStatusBar selectedMailboxIds={[mailboxIdMap[mailboxName]]} jobs={processingJobs} onViewDetails={() => navigate('/processing')} />
        )}

        {/* Content */}
        <div className="mail-content" key={isAnalyticsMode ? 'analytics' : (mailboxName || 'none')}>
          <div className={`mail-list-panel ${selectedEmail ? 'has-detail' : ''}`}>
            {/* Stats + pagination */}
            <div className="mail-list-stats flex items-center justify-between gap-2 flex-wrap">
              <span className="text-xs text-slate-500">
                {loading && displayEmails.length === 0 ? 'Loading...'
                  : isAnalyticsMode ? `${displayEmails.length} email${displayEmails.length !== 1 ? 's' : ''}${searchText ? ` matching "${searchText}"` : ''}`
                  : `${totalCount.toLocaleString()} email${totalCount !== 1 ? 's' : ''}${mailboxName ? ` in ${mailboxName}` : ''}${folderFilter ? ` · ${folderFilter}` : ''}`}
              </span>
              {!isAnalyticsMode && totalCount > pageSize && (
                <div className="flex items-center gap-1">
                  <button onClick={() => { setPage(p => Math.max(1, p - 1)); setSelectedEmail(null); setSelectedEmailId(null); }} disabled={page <= 1} className="p-1 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronLeft className="h-3.5 w-3.5" /></button>
                  <span className="text-xs text-slate-500 tabular-nums px-1">{page} / {totalPages}</span>
                  <button onClick={() => { setPage(p => Math.min(totalPages, p + 1)); setSelectedEmail(null); setSelectedEmailId(null); }} disabled={page >= totalPages} className="p-1 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronRight className="h-3.5 w-3.5" /></button>
                </div>
              )}
            </div>

            {/* Email list */}
            <div className="mail-list-content">
              {(!isAnalyticsMode && mailboxesLoading) || (loading && displayEmails.length === 0) ? (
                <div className="mail-list-loading">{[1,2,3,4,5].map(i => (
                  <div key={i} className="email-skeleton"><Skeleton className="h-10 w-10 rounded-full" /><div className="flex-1 space-y-2"><Skeleton className="h-3 w-3/5" /><Skeleton className="h-3 w-4/5" /></div></div>
                ))}</div>
              ) : !isAnalyticsMode && !mailboxName ? (
                <div className="flex flex-col items-center justify-center py-16 text-slate-400"><Mail className="h-10 w-10 mb-3" /><p className="text-sm">Select a mailbox to view emails</p></div>
              ) : displayEmails.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-slate-400"><Mail className="h-10 w-10 mb-3" /><p className="text-sm">{isAnalyticsMode ? 'No emails linked yet' : 'No emails found'}</p></div>
              ) : (
                displayEmails.map(email => (
                  <EmailListItem key={email.id} email={email} isSelected={selectedEmailId === email.id} onClick={() => handleEmailSelect(email)} />
                ))
              )}
            </div>
          </div>

          <EmailDetailPanel email={selectedEmail} loading={detailLoading} onClose={handleCloseDetail}
            expanded={detailExpanded} onToggleExpand={() => setDetailExpanded(!detailExpanded)} />
        </div>
      </div>
    </div>
  );
};
