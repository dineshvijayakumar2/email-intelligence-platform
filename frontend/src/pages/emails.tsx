import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Typography,
  Tag,
  Input,
  Select,
  Button,
  Tooltip,
  message,
  Spin,
  Empty,
  Badge,
  Avatar,
  Skeleton,
  DatePicker,
  Space,
  Pagination,
} from "antd";
import {
  SearchOutlined,
  MailOutlined,
  SendOutlined,
  DeleteOutlined,
  StarOutlined,
  InboxOutlined,
  FolderOutlined,
  FilterOutlined,
  ReloadOutlined,
  LeftOutlined,
  PaperClipOutlined,
  ExpandOutlined,
  CompressOutlined,
  AppstoreOutlined,
  CloseOutlined,
  SyncOutlined,
  CalendarOutlined,
  SwapOutlined,
  UserOutlined,
} from "@ant-design/icons";
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

const { Text, Title } = Typography;
const { Option } = Select;
const { Search } = Input;
const { RangePicker } = DatePicker;

// Email List Item Component
const EmailListItem: React.FC<{
  email: Email;
  isSelected: boolean;
  onClick: () => void;
}> = React.memo(({ email, isSelected, onClick }) => {
  const contentTags = filterContentTags(email.tags || []);
  const hasAttachments = email.message_size > 50000;

  return (
    <div
      className={`email-list-item ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
    >
      <Avatar
        size={40}
        style={{
          backgroundColor: getAvatarColor(email.sender_email),
          flexShrink: 0,
          fontSize: 14,
          fontWeight: 500,
        }}
      >
        {getInitials(email.sender_name || '', email.sender_email)}
      </Avatar>

      <div className="email-list-item-content">
        <div className="email-list-item-header">
          <Text strong className="email-sender" ellipsis>
            {email.sender_name || email.sender_email}
          </Text>
          <Text type="secondary" className="email-date">
            {formatRelativeDate(email.sent_date)}
          </Text>
        </div>

        <Text className="email-subject" ellipsis>
          {email.subject || '(No subject)'}
        </Text>

        <div className="email-list-item-footer">
          <div className="email-tags">
            {email.is_outbound && (
              <Tag color="green" style={{ margin: 0, fontSize: 10, padding: '0 4px', lineHeight: '16px' }}>
                Sent
              </Tag>
            )}
            {contentTags.slice(0, 2).map(tag => (
              <Tag
                key={tag}
                color={getCategoryColor(tag)}
                style={{ margin: 0, fontSize: 10, padding: '0 4px', lineHeight: '16px' }}
              >
                {getCategoryLabel(tag)}
              </Tag>
            ))}
          </div>
          <div className="email-indicators">
            {hasAttachments && <PaperClipOutlined style={{ fontSize: 12, color: '#8c8c8c' }} />}
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
  const [showFilters, setShowFilters] = useState(false);

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
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(searchText);
      setDebouncedSender(senderSearch);
      setPage(1);
    }, 400);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [searchText, senderSearch]);

  // Build filters for TanStack Query
  const queryFilters: EmailFilters = useMemo(() => ({
    search: debouncedSearch || undefined,
    sender: debouncedSender || undefined,
    mailbox: mailboxName || undefined,
    folder: folderFilter || undefined,
    category: categoryFilter || undefined,
    isOutbound: directionFilter || undefined,
    dateRange: dateRange || undefined,
  }), [debouncedSearch, debouncedSender, mailboxName, folderFilter, categoryFilter, directionFilter, dateRange]);

  // TanStack Query for emails (standard mode only)
  const emailsQuery = useEmails({
    filters: queryFilters,
    page,
    pageSize,
    sort_by: sortBy,
    sort_dir: sortDir,
  });

  const emails = isAnalyticsMode ? analyticsEmails : (emailsQuery.data?.emails || []);
  const totalCount = isAnalyticsMode ? analyticsTotal : (emailsQuery.data?.totalCount || 0);
  const loading = isAnalyticsMode ? analyticsLoading : emailsQuery.isLoading;

  // System folders
  const systemFolders = useMemo(() => [
    { key: '', label: 'All Mail', icon: <AppstoreOutlined /> },
    { key: 'Inbox', label: 'Inbox', icon: <InboxOutlined /> },
    { key: 'Sent', label: 'Sent', icon: <SendOutlined /> },
    { key: 'Starred', label: 'Starred', icon: <StarOutlined /> },
    { key: 'Trash', label: 'Trash', icon: <DeleteOutlined /> },
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

  // Load filter options (categories + mailboxes) — once on mount
  useEffect(() => {
    if (isAnalyticsMode) { setMailboxesLoading(false); return; }
    (async () => {
      try {
        setMailboxesLoading(true);
        const [cats, mbs] = await Promise.all([
          emailService.getEmailCategories(),
          mailboxService.getMailboxes(),
        ]);
        setCategories(cats);
        setAccessibleMailboxes(mbs);
        const idMap: Record<string, string> = {};
        const nameMap: Record<string, string> = {};
        mbs.forEach((m: Mailbox) => { idMap[m.name] = m.id; nameMap[m.id] = m.name; });
        setMailboxIdMap(idMap);
        setMailboxIdToNameMap(nameMap);
      } catch (e) {
        console.error('Failed to load mailboxes:', e);
      } finally {
        setMailboxesLoading(false);
      }
    })();
  }, [isAnalyticsMode]);

  // Navigate to first mailbox if none selected
  useEffect(() => {
    if (isAnalyticsMode || mailboxesLoading) return;
    if (accessibleMailboxes.length > 0 && !mailboxId) {
      navigate(`/emails/${accessibleMailboxes[0].id}`, { replace: true });
    }
  }, [accessibleMailboxes, mailboxId, navigate, isAnalyticsMode, mailboxesLoading]);

  // Sync mailboxId URL param → mailboxName filter
  useEffect(() => {
    if (mailboxesLoading || isAnalyticsMode) return;
    if (mailboxId && mailboxIdToNameMap[mailboxId]) {
      const name = mailboxIdToNameMap[mailboxId];
      if (name !== mailboxName) {
        setMailboxName(name);
        setPage(1);
        if (!emailId) { setSelectedEmail(null); setSelectedEmailId(null); }
      }
    } else if (mailboxId && Object.keys(mailboxIdToNameMap).length > 0) {
      navigate('/mailboxes', { replace: true });
    }
  }, [mailboxId, mailboxIdToNameMap, emailId, mailboxesLoading, isAnalyticsMode]);

  // Load folders when mailbox changes
  useEffect(() => {
    if (!mailboxName || !mailboxIdMap[mailboxName]) return;
    (async () => {
      setFoldersLoading(true);
      try {
        const f = await emailService.getFolderNames(mailboxIdMap[mailboxName]);
        setFolders(f);
      } catch { /* ignore */ } finally { setFoldersLoading(false); }
    })();
  }, [mailboxName, mailboxIdMap]);

  // Load email detail
  const loadEmailDetails = useCallback(async (id: string) => {
    setDetailLoading(true);
    setSelectedEmailId(id);
    try {
      const full = await emailService.getEmail(id);
      setSelectedEmail(full);
    } catch { message.error('Failed to load email'); } finally { setDetailLoading(false); }
  }, []);

  // URL emailId → detail panel (only in standard mode — analytics mode manages its own detail)
  useEffect(() => {
    if (isAnalyticsMode) return;
    if (emailId && emailId !== selectedEmailId) loadEmailDetails(emailId);
    else if (!emailId && selectedEmailId) { setSelectedEmail(null); setSelectedEmailId(null); }
  }, [emailId, selectedEmailId, loadEmailDetails, isAnalyticsMode]);

  // Analytics mode: load emails
  useEffect(() => {
    if (!isAnalyticsMode) return;
    (async () => {
      setAnalyticsLoading(true);
      try {
        if (analyticsEmailId) {
          const full = await emailService.getEmail(analyticsEmailId);
          if (full) {
            setAnalyticsEmails([full as Email]);
            setAnalyticsTotal(1);
            setSelectedEmail(full as Email);
            setSelectedEmailId(analyticsEmailId);
          }
        } else if (analyticsThreadId) {
          const detail = await threadsApi.getDetail(analyticsThreadId);
          const threadEmails = (detail?.emails || []).map((e: any) => ({
            id: e.id, subject: e.subject || '', sender_email: e.sender_email || '',
            sender_name: e.sender_name || '', recipients: e.recipients || [],
            sent_date: e.sent_date || '', is_outbound: e.is_outbound ?? false,
            body_text: e.body_text || '', folder_path: e.folder_path || '',
          })) as Email[];
          setAnalyticsEmails(threadEmails);
          setAnalyticsTotal(threadEmails.length);
        } else {
          const result = analyticsContactId
            ? await contactsApi.getEmails(analyticsContactId, 100, 0)
            : await companiesApi.getEmails(analyticsCompanyId!, 100, 0);
          setAnalyticsEmails((result.emails || []) as Email[]);
          setAnalyticsTotal(result.total || 0);
        }
      } catch { message.error('Failed to load emails'); }
      finally { setAnalyticsLoading(false); }
    })();
  }, [isAnalyticsMode, analyticsContactId, analyticsCompanyId, analyticsThreadId, analyticsEmailId]);

  // Processing jobs for sync status
  useEffect(() => {
    if (isAnalyticsMode) return;
    const load = async () => {
      try {
        const jobs = await dashboardService._fetchProcessingJobs();
        if (jobs?.length) setProcessingJobs(jobs);
      } catch { /* ignore */ }
    };
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [isAnalyticsMode]);

  // Keep ref in sync
  useEffect(() => { processingJobsRef.current = processingJobs; }, [processingJobs]);

  // Handlers
  const handleFolderSelect = (key: string) => {
    setPage(1);
    setSelectedEmail(null);
    setSelectedEmailId(null);
    if (key === '') { setFolderFilter(''); return; }
    const matched = folders.find(f => f === key)
      || folders.find(f => f.toLowerCase() === key.toLowerCase())
      || folders.find(f => f.toLowerCase().includes(key.toLowerCase()));
    setFolderFilter(matched || key);
  };

  const handleEmailSelect = (email: Email) => {
    if (isAnalyticsMode) { loadEmailDetails(email.id); }
    else if (mailboxId) { navigate(`/emails/${mailboxId}/${email.id}`); }
  };

  const handleCloseDetail = () => {
    if (isAnalyticsMode) { setSelectedEmail(null); setSelectedEmailId(null); }
    else if (mailboxId) { navigate(`/emails/${mailboxId}`); }
  };

  const handleRefresh = () => {
    setSelectedEmail(null);
    setSelectedEmailId(null);
    emailsQuery.refetch();
  };

  const clearFilters = () => {
    setCategoryFilter('');
    setDirectionFilter('');
    setFolderFilter('');
    setDateRange(null);
    setSenderSearch('');
    setPage(1);
  };

  // Client-side search for analytics mode
  const displayEmails = useMemo(() => {
    if (!isAnalyticsMode || !searchText) return emails;
    const q = searchText.toLowerCase();
    return emails.filter(e =>
      (e.subject || '').toLowerCase().includes(q) ||
      (e.sender_name || '').toLowerCase().includes(q) ||
      (e.sender_email || '').toLowerCase().includes(q)
    );
  }, [isAnalyticsMode, emails, searchText]);

  return (
    <div className="mail-client">
      {/* Left Sidebar — hidden in analytics mode */}
      {!isAnalyticsMode && (
        <div className={`mail-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
          <div className="mail-sidebar-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
              <Tooltip title="Back to Mailboxes">
                <Button type="text" size="small" icon={<LeftOutlined />}
                  onClick={() => navigate('/mailboxes')} style={{ color: 'rgba(255,255,255,0.8)' }} />
              </Tooltip>
              {!sidebarCollapsed && (
                <Text strong style={{ fontSize: 14, color: 'white', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {mailboxName || 'Loading...'}
                </Text>
              )}
            </div>
            <Tooltip title={sidebarCollapsed ? 'Expand' : 'Collapse'}>
              <Button type="text" size="small"
                icon={sidebarCollapsed ? <ExpandOutlined /> : <CompressOutlined />}
                onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                style={{ color: 'rgba(255,255,255,0.8)' }} />
            </Tooltip>
          </div>

          <div className="mail-sidebar-section">
            <div className="mail-sidebar-section-title">
              {foldersLoading ? <SyncOutlined spin /> : <FolderOutlined />} {!sidebarCollapsed && 'Folders'}
            </div>
            <div className="mail-sidebar-items">
              {mailboxesLoading || (foldersLoading && !mailboxName) ? (
                !sidebarCollapsed && (
                  <div style={{ padding: '8px 12px' }}>
                    {[1, 2, 3, 4, 5].map(i => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                        <Skeleton.Avatar active size={16} shape="square" style={{ opacity: 0.3 }} />
                        <Skeleton.Input active size="small" style={{ width: 80, height: 14, opacity: 0.3 }} />
                      </div>
                    ))}
                  </div>
                )
              ) : !mailboxName ? (
                !sidebarCollapsed && (
                  <div style={{ padding: '12px', textAlign: 'center', color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>
                    Select a mailbox
                  </div>
                )
              ) : (
                <>
                  {systemFolders.map(folder => (
                    <div key={folder.key}
                      className={`mail-sidebar-item ${currentFolderKey === folder.key ? 'active' : ''}`}
                      onClick={() => handleFolderSelect(folder.key)}>
                      {folder.icon}
                      {!sidebarCollapsed && <span>{folder.label}</span>}
                    </div>
                  ))}
                  {additionalFolders.length > 0 && (
                    <>
                      <div className="mail-sidebar-divider" />
                      {additionalFolders.map(folder => (
                        <div key={folder}
                          className={`mail-sidebar-item ${folderFilter === folder ? 'active' : ''}`}
                          onClick={() => { setFolderFilter(folder); setPage(1); }}>
                          <FolderOutlined />
                          {!sidebarCollapsed && <span>{folder}</span>}
                        </div>
                      ))}
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="mail-main">
        {/* Analytics Mode Banner */}
        {isAnalyticsMode && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '10px 16px',
            background: 'linear-gradient(135deg, rgba(102,126,234,0.12), rgba(118,75,162,0.08))',
            borderBottom: '1px solid rgba(102,126,234,0.2)',
          }}>
            <Button type="text" icon={<LeftOutlined />} onClick={() => navigate(-1)} style={{ color: '#667eea' }}>Back</Button>
            <MailOutlined style={{ color: '#667eea', fontSize: 16 }} />
            <Text strong style={{ fontSize: 14 }}>Emails for {analyticsLabel}</Text>
            <Tag color="purple">{totalCount} email{totalCount !== 1 ? 's' : ''} across all mailboxes</Tag>
          </div>
        )}

        {/* Top Bar - Search & Filters */}
        <div className="mail-topbar">
          <div className="mail-topbar-left" style={{ flex: 1 }}>
            <Search
              placeholder="Search subject, sender..."
              allowClear
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              prefix={<SearchOutlined style={{ color: '#667eea' }} />}
              className="mail-search"
              style={{ maxWidth: 300 }}
            />
          </div>

          {!isAnalyticsMode && (
            <div className="mail-topbar-right" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {/* People filter (from, to, cc, bcc) */}
              <Input
                placeholder="From / To / CC..."
                prefix={<UserOutlined />}
                allowClear
                value={senderSearch}
                onChange={e => setSenderSearch(e.target.value)}
                style={{ width: 170 }}
                size="small"
              />

              {/* Direction filter */}
              <Select
                placeholder="Direction"
                allowClear
                value={directionFilter || undefined}
                onChange={v => { setDirectionFilter(v || ''); setPage(1); }}
                style={{ width: 110 }}
                size="small"
                options={[
                  { value: 'inbound', label: 'Received' },
                  { value: 'outbound', label: 'Sent' },
                ]}
              />

              {/* Category filter */}
              {categories.length > 0 && (
                <Select
                  placeholder="Category"
                  allowClear
                  value={categoryFilter || undefined}
                  onChange={v => { setCategoryFilter(v || ''); setPage(1); }}
                  style={{ width: 130 }}
                  size="small"
                >
                  {categories.map(cat => (
                    <Option key={cat} value={cat}>{getCategoryLabel(cat)}</Option>
                  ))}
                </Select>
              )}

              {/* Date range */}
              <RangePicker
                size="small"
                onChange={(_, dateStrings) => {
                  if (dateStrings[0] && dateStrings[1]) {
                    setDateRange([dateStrings[0], dateStrings[1]]);
                  } else {
                    setDateRange(null);
                  }
                  setPage(1);
                }}
                style={{ width: 220 }}
              />

              {/* Sort */}
              <Select
                value={`${sortBy}_${sortDir}`}
                onChange={v => {
                  const [col, dir] = v.split('_');
                  setSortBy(col);
                  setSortDir(dir as 'asc' | 'desc');
                  setPage(1);
                }}
                style={{ width: 140 }}
                size="small"
                options={[
                  { value: 'sent_date_desc', label: 'Newest first' },
                  { value: 'sent_date_asc', label: 'Oldest first' },
                  { value: 'sender_name_asc', label: 'Sender A→Z' },
                  { value: 'sender_name_desc', label: 'Sender Z→A' },
                  { value: 'subject_asc', label: 'Subject A→Z' },
                ]}
              />

              {hasActiveFilters && (
                <Button type="link" size="small" onClick={clearFilters} icon={<CloseOutlined />}>Clear</Button>
              )}

              <Tooltip title="Refresh">
                <Button type="text" icon={<ReloadOutlined spin={loading} />} onClick={handleRefresh} />
              </Tooltip>
            </div>
          )}
        </div>

        {/* Sync Status Bar */}
        {!isAnalyticsMode && mailboxName && mailboxIdMap[mailboxName] && (
          <SyncStatusBar
            selectedMailboxIds={[mailboxIdMap[mailboxName]]}
            jobs={processingJobs}
            onViewDetails={() => navigate('/processing')}
          />
        )}

        {/* Content Area */}
        <div className="mail-content" key={isAnalyticsMode ? 'analytics' : (mailboxName || 'no-mailbox')}>
          {/* Email List */}
          <div className={`mail-list-panel ${selectedEmail ? 'has-detail' : ''}`}>
            {/* Stats + Pagination bar */}
            <div className="mail-list-stats" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
              <Text type="secondary" style={{ fontSize: 13 }}>
                {loading && displayEmails.length === 0 ? 'Loading emails...'
                  : isAnalyticsMode ? (
                    <>{displayEmails.length} email{displayEmails.length !== 1 ? 's' : ''}
                      {searchText && ` matching "${searchText}"`}</>
                  ) : (
                    <>{totalCount.toLocaleString()} email{totalCount !== 1 ? 's' : ''}
                      {mailboxName && ` in ${mailboxName}`}
                      {folderFilter && ` • ${folderFilter}`}</>
                  )}
              </Text>
              {!isAnalyticsMode && totalCount > pageSize && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Pagination
                    current={page}
                    total={totalCount}
                    pageSize={pageSize}
                    size="small"
                    showSizeChanger={false}
                    showTotal={(total, range) => <Text type="secondary" style={{ fontSize: 12 }}>{range[0]}-{range[1]}</Text>}
                    onChange={p => { setPage(p); setSelectedEmail(null); setSelectedEmailId(null); }}
                  />
                </div>
              )}
            </div>

            {/* Email List */}
            <div className="mail-list-content">
              {(!isAnalyticsMode && mailboxesLoading) || (loading && displayEmails.length === 0) ? (
                <div className="mail-list-loading">
                  {[1, 2, 3, 4, 5].map(i => (
                    <div key={i} className="email-skeleton">
                      <Skeleton.Avatar active size={40} />
                      <div style={{ flex: 1 }}>
                        <Skeleton.Input active size="small" style={{ width: '60%', marginBottom: 8 }} />
                        <Skeleton.Input active size="small" style={{ width: '90%' }} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : !isAnalyticsMode && !mailboxName ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Select a mailbox to view emails" style={{ marginTop: 60 }} />
              ) : displayEmails.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={isAnalyticsMode ? 'No emails linked yet' : 'No emails found'}
                  style={{ marginTop: 60 }} />
              ) : (
                displayEmails.map(email => (
                  <EmailListItem
                    key={email.id}
                    email={email}
                    isSelected={selectedEmailId === email.id}
                    onClick={() => handleEmailSelect(email)}
                  />
                ))
              )}
            </div>
          </div>

          {/* Email Detail */}
          <EmailDetailPanel
            email={selectedEmail}
            loading={detailLoading}
            onClose={handleCloseDetail}
            expanded={detailExpanded}
            onToggleExpand={() => setDetailExpanded(!detailExpanded)}
          />
        </div>
      </div>
    </div>
  );
};
