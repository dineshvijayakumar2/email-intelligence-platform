import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { emailService, Email, EmailFilters } from '../services/emailService';
import { mailboxService, Mailbox } from '../services/mailboxService';
import SyncStatusBar from '../components/SyncStatusBar';
import { dashboardService } from '../services/dashboardService';
import { contactsApi, companiesApi, threadsApi } from '../services/analyticsService';
import {
  EmailDetailPanel, getCategoryLabel, getInitials, getAvatarColor, filterContentTags,
} from '../components/EmailDetailPanel';
import { formatRelativeDate } from '../utils/dateUtils';
import { useEmails } from '../hooks/queries';
import { cn } from '@/lib/utils';
import { toast } from '@/lib/toast';
import {
  Search, Mail, Send, Trash2, Star, Inbox, Folder, RefreshCw,
  ArrowLeft, Paperclip, Maximize2, Minimize2, LayoutGrid, X,
  ChevronLeft, ChevronRight, User,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';

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

// ── Main Component ──────────────────────────────────────────────
export const EmailList: React.FC = () => {
  const { mailboxId, emailId } = useParams<{ mailboxId?: string; emailId?: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const analyticsContactId = searchParams.get('contact_id');
  const analyticsCompanyId = searchParams.get('company_id');
  const analyticsThreadId = searchParams.get('thread_id');
  const analyticsEmailId = searchParams.get('email_id');
  const analyticsLabel = searchParams.get('name') || 'Contact';
  const isAnalyticsMode = !!(analyticsContactId || analyticsCompanyId || analyticsThreadId || analyticsEmailId);

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

  const [searchText, setSearchText] = useState('');
  const [senderSearch, setSenderSearch] = useState('');
  const [mailboxName, setMailboxName] = useState('');
  const [folderFilter, setFolderFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [directionFilter, setDirectionFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sortBy, setSortBy] = useState('sent_date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [debouncedSender, setDebouncedSender] = useState('');

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => { setDebouncedSearch(searchText); setDebouncedSender(senderSearch); setPage(1); }, 400);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [searchText, senderSearch]);

  const queryFilters: EmailFilters = useMemo(() => ({
    search: debouncedSearch || undefined, sender: debouncedSender || undefined,
    mailbox: mailboxName || undefined, folder: folderFilter || undefined,
    category: categoryFilter || undefined, isOutbound: directionFilter || undefined,
  }), [debouncedSearch, debouncedSender, mailboxName, folderFilter, categoryFilter, directionFilter]);

  const emailsQuery = useEmails({ filters: queryFilters, page, pageSize, sort_by: sortBy, sort_dir: sortDir });
  const emails = isAnalyticsMode ? analyticsEmails : (emailsQuery.data?.emails || []);
  const totalCount = isAnalyticsMode ? analyticsTotal : (emailsQuery.data?.totalCount || 0);
  const loading = isAnalyticsMode ? analyticsLoading : emailsQuery.isLoading;

  const systemFolders = useMemo(() => [
    { key: '', label: 'All Mail', icon: <LayoutGrid className="h-4 w-4" /> },
    { key: 'Inbox', label: 'Inbox', icon: <Inbox className="h-4 w-4" /> },
    { key: 'Sent', label: 'Sent', icon: <Send className="h-4 w-4" /> },
    { key: 'Starred', label: 'Starred', icon: <Star className="h-4 w-4" /> },
    { key: 'Trash', label: 'Trash', icon: <Trash2 className="h-4 w-4" /> },
  ], []);

  const currentFolderKey = useMemo(() => {
    if (!folderFilter) return '';
    const l = folderFilter.toLowerCase();
    if (l.includes('inbox')) return 'Inbox'; if (l.includes('sent')) return 'Sent';
    if (l.includes('starred') || l.includes('flagged')) return 'Starred';
    if (l.includes('trash') || l.includes('deleted')) return 'Trash';
    return folderFilter;
  }, [folderFilter]);

  const additionalFolders = useMemo(() => folders.filter(f => !['inbox','sent','starred','flagged','trash','deleted'].some(s => f.toLowerCase().includes(s))), [folders]);
  const hasActiveFilters = !!(directionFilter || folderFilter || debouncedSender);

  useEffect(() => {
    if (isAnalyticsMode) { setMailboxesLoading(false); return; }
    (async () => {
      setMailboxesLoading(true);
      try {
        const [cats, mbs] = await Promise.all([emailService.getEmailCategories(), mailboxService.getMailboxes()]);
        setCategories(cats); setAccessibleMailboxes(mbs);
        const idMap: Record<string, string> = {}; const nameMap: Record<string, string> = {};
        mbs.forEach((m: Mailbox) => { idMap[m.name] = m.id; nameMap[m.id] = m.name; });
        setMailboxIdMap(idMap); setMailboxIdToNameMap(nameMap);
      } catch {} finally { setMailboxesLoading(false); }
    })();
  }, [isAnalyticsMode]);

  useEffect(() => { if (isAnalyticsMode || mailboxesLoading) return; if (accessibleMailboxes.length > 0 && !mailboxId) navigate(`/emails/${accessibleMailboxes[0].id}`, { replace: true }); }, [accessibleMailboxes, mailboxId, navigate, isAnalyticsMode, mailboxesLoading]);

  useEffect(() => {
    if (mailboxesLoading || isAnalyticsMode) return;
    if (mailboxId && mailboxIdToNameMap[mailboxId]) { const name = mailboxIdToNameMap[mailboxId]; if (name !== mailboxName) { setMailboxName(name); setPage(1); if (!emailId) { setSelectedEmail(null); setSelectedEmailId(null); } } }
    else if (mailboxId && Object.keys(mailboxIdToNameMap).length > 0) navigate('/mailboxes', { replace: true });
  }, [mailboxId, mailboxIdToNameMap, emailId, mailboxesLoading, isAnalyticsMode]);

  useEffect(() => { if (!mailboxName || !mailboxIdMap[mailboxName]) return; (async () => { setFoldersLoading(true); try { setFolders(await emailService.getFolderNames(mailboxIdMap[mailboxName])); } catch {} finally { setFoldersLoading(false); } })(); }, [mailboxName, mailboxIdMap]);

  const loadEmailDetails = useCallback(async (id: string) => { setDetailLoading(true); setSelectedEmailId(id); try { setSelectedEmail(await emailService.getEmail(id)); } catch { toast.error('Failed to load email'); } finally { setDetailLoading(false); } }, []);

  useEffect(() => { if (isAnalyticsMode) return; if (emailId && emailId !== selectedEmailId) loadEmailDetails(emailId); else if (!emailId && selectedEmailId) { setSelectedEmail(null); setSelectedEmailId(null); } }, [emailId, selectedEmailId, loadEmailDetails, isAnalyticsMode]);

  useEffect(() => {
    if (!isAnalyticsMode) return;
    (async () => {
      setAnalyticsLoading(true);
      try {
        if (analyticsEmailId) { const full = await emailService.getEmail(analyticsEmailId); if (full) { setAnalyticsEmails([full as Email]); setAnalyticsTotal(1); setSelectedEmail(full as Email); setSelectedEmailId(analyticsEmailId); } }
        else if (analyticsThreadId) { const detail = await threadsApi.getDetail(analyticsThreadId); const te = (detail?.emails || []).map((e: any) => ({ id: e.id, subject: e.subject||'', sender_email: e.sender_email||'', sender_name: e.sender_name||'', recipients: e.recipients||[], sent_date: e.sent_date||'', is_outbound: e.is_outbound??false, body_text: e.body_text||'', folder_path: e.folder_path||'' })) as Email[]; setAnalyticsEmails(te); setAnalyticsTotal(te.length); }
        else { const r = analyticsContactId ? await contactsApi.getEmails(analyticsContactId, 100, 0) : await companiesApi.getEmails(analyticsCompanyId!, 100, 0); setAnalyticsEmails((r.emails||[]) as Email[]); setAnalyticsTotal(r.total||0); }
      } catch { toast.error('Failed to load emails'); } finally { setAnalyticsLoading(false); }
    })();
  }, [isAnalyticsMode, analyticsContactId, analyticsCompanyId, analyticsThreadId, analyticsEmailId]);

  useEffect(() => { if (isAnalyticsMode) return; const load = async () => { try { const j = await dashboardService._fetchProcessingJobs(); if (j?.length) setProcessingJobs(j); } catch {} }; load(); const i = setInterval(load, 5000); return () => clearInterval(i); }, [isAnalyticsMode]);
  useEffect(() => { processingJobsRef.current = processingJobs; }, [processingJobs]);

  const handleFolderSelect = (key: string) => { setPage(1); setSelectedEmail(null); setSelectedEmailId(null); if (key === '') { setFolderFilter(''); return; } const m = folders.find(f => f === key) || folders.find(f => f.toLowerCase() === key.toLowerCase()) || folders.find(f => f.toLowerCase().includes(key.toLowerCase())); setFolderFilter(m || key); };
  const handleEmailSelect = (email: Email) => { if (isAnalyticsMode) loadEmailDetails(email.id); else if (mailboxId) navigate(`/emails/${mailboxId}/${email.id}`); };
  const handleCloseDetail = () => { if (isAnalyticsMode) { setSelectedEmail(null); setSelectedEmailId(null); } else if (mailboxId) navigate(`/emails/${mailboxId}`); };
  const clearFilters = () => { setDirectionFilter(''); setFolderFilter(''); setSenderSearch(''); setPage(1); };

  const displayEmails = useMemo(() => {
    if (!isAnalyticsMode || !searchText) return emails;
    const q = searchText.toLowerCase();
    return emails.filter(e => (e.subject||'').toLowerCase().includes(q) || (e.sender_name||'').toLowerCase().includes(q) || (e.sender_email||'').toLowerCase().includes(q));
  }, [isAnalyticsMode, emails, searchText]);

  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="flex h-[calc(100vh-56px)]">
      {/* ── Sidebar ── */}
      {!isAnalyticsMode && (
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
            {systemFolders.map(f => (
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
                  <button key={f} onClick={() => { setFolderFilter(f); setPage(1); }}
                    className={cn('w-full flex items-center gap-2.5 px-3 py-1.5 text-sm transition-colors',
                      folderFilter === f ? 'text-primary bg-primary/5 font-medium' : 'text-slate-600 hover:bg-slate-50')}>
                    <Folder className="h-4 w-4" />{!sidebarCollapsed && <span className="truncate">{f}</span>}
                  </button>
                ))}
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Main area ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Analytics banner */}
        {isAnalyticsMode && (
          <div className="flex items-center gap-3 px-5 py-2.5 bg-primary-subtle border-b">
            <button onClick={() => navigate(-1)} className="text-sm text-primary hover:underline inline-flex items-center gap-1"><ArrowLeft className="h-4 w-4" />Back</button>
            <Mail className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium text-slate-800">Emails for {analyticsLabel}</span>
            <span className="text-xs text-primary">{totalCount} email{totalCount !== 1 ? 's' : ''}</span>
          </div>
        )}

        {/* Filter bar */}
        <div className="flex items-center gap-2 px-5 py-2.5 border-b bg-white flex-wrap">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
            <input type="text" placeholder="Search subject, sender..." value={searchText} onChange={e => setSearchText(e.target.value)}
              className="w-full h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20" />
          </div>
          {!isAnalyticsMode && (
            <>
              {/* People search with helper text */}
              <div className="relative group">
                <User className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400" />
                <input placeholder="Person name or email..." value={senderSearch} onChange={e => setSenderSearch(e.target.value)}
                  className="h-8 pl-7 pr-2 text-sm rounded-md border border-slate-200 bg-white w-48 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:w-64 transition-all"
                  title="Search across From, To, CC and BCC fields" />
              </div>

              {/* Sort */}
              <select value={`${sortBy}|${sortDir}`} onChange={e => { const parts = e.target.value.split('|'); setSortBy(parts[0]); setSortDir(parts[1] as any); setPage(1); }}
                className="h-8 px-2 text-xs rounded-md border border-slate-200 bg-white">
                <option value="sent_date|desc">Newest first</option>
                <option value="sent_date|asc">Oldest first</option>
                <option value="sender_name|asc">Sender A→Z</option>
                <option value="subject|asc">Subject A→Z</option>
              </select>

              {/* Sent/Received toggle — compact pills instead of dropdown */}
              <div className="flex rounded-md border border-slate-200 overflow-hidden">
                <button onClick={() => { setDirectionFilter(directionFilter === 'inbound' ? '' : 'inbound'); setPage(1); }}
                  className={cn('px-2.5 py-1 text-xs transition-colors', directionFilter === 'inbound' ? 'bg-primary text-white' : 'bg-white text-slate-500 hover:bg-slate-50')}>
                  Received
                </button>
                <button onClick={() => { setDirectionFilter(directionFilter === 'outbound' ? '' : 'outbound'); setPage(1); }}
                  className={cn('px-2.5 py-1 text-xs border-l transition-colors', directionFilter === 'outbound' ? 'bg-primary text-white' : 'bg-white text-slate-500 hover:bg-slate-50')}>
                  Sent
                </button>
              </div>

              {hasActiveFilters && <button onClick={clearFilters} className="text-xs text-primary hover:underline inline-flex items-center gap-0.5"><X className="h-3 w-3" />Clear</button>}
              <button onClick={() => { setSelectedEmail(null); setSelectedEmailId(null); emailsQuery.refetch(); }} className="p-1.5 rounded hover:bg-slate-100">
                <RefreshCw className={cn('h-3.5 w-3.5 text-slate-400', loading && 'animate-spin')} />
              </button>
            </>
          )}
        </div>

        {/* Sync status */}
        {!isAnalyticsMode && mailboxName && mailboxIdMap[mailboxName] && (
          <SyncStatusBar selectedMailboxIds={[mailboxIdMap[mailboxName]]} jobs={processingJobs} onViewDetails={() => navigate('/processing')} />
        )}

        {/* Email list + detail split */}
        <div className="flex-1 flex overflow-hidden">
          {/* List */}
          <div className={cn('flex flex-col border-r bg-white transition-all duration-200', selectedEmail ? 'w-[380px] shrink-0' : 'flex-1')}>
            {/* Stats bar */}
            <div className="flex items-center justify-between px-4 py-2 border-b bg-slate-50/50">
              <span className="text-xs text-slate-500">
                {loading && displayEmails.length === 0 ? 'Loading...'
                  : `${totalCount.toLocaleString()} email${totalCount !== 1 ? 's' : ''}${folderFilter ? ` · ${folderFilter}` : ''}`}
              </span>
              {!isAnalyticsMode && totalCount > pageSize && (
                <div className="flex items-center gap-1">
                  <button onClick={() => { setPage(p => Math.max(1, p-1)); setSelectedEmail(null); }} disabled={page <= 1} className="p-1 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronLeft className="h-3.5 w-3.5" /></button>
                  <span className="text-xs text-slate-500 tabular-nums">{page}/{totalPages}</span>
                  <button onClick={() => { setPage(p => Math.min(totalPages, p+1)); setSelectedEmail(null); }} disabled={page >= totalPages} className="p-1 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronRight className="h-3.5 w-3.5" /></button>
                </div>
              )}
            </div>
            {/* Emails */}
            <div className="flex-1 overflow-y-auto">
              {(!isAnalyticsMode && mailboxesLoading) || (loading && displayEmails.length === 0) ? (
                <div className="p-4 space-y-4">{[1,2,3,4,5].map(i => <div key={i} className="flex gap-3"><div className="w-9 h-9 rounded-full bg-slate-100 animate-pulse" /><div className="flex-1 space-y-2"><div className="h-3 w-3/5 bg-slate-100 rounded animate-pulse" /><div className="h-3 w-4/5 bg-slate-100 rounded animate-pulse" /></div></div>)}</div>
              ) : !isAnalyticsMode && !mailboxName ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-400"><Mail className="h-10 w-10 mb-3" /><p className="text-sm">Select a mailbox</p></div>
              ) : displayEmails.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-400"><Mail className="h-10 w-10 mb-3" /><p className="text-sm">{isAnalyticsMode ? 'No emails linked' : 'No emails found'}</p></div>
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
    </div>
  );
};
