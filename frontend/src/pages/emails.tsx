import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate } from 'react-router-dom';
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
  Dropdown,
  Skeleton,
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
} from "@ant-design/icons";
import { emailService, Email, EmailFilters } from '../services/emailService';
import { mailboxService, Mailbox } from '../services/mailboxService';
import SyncStatusBar from '../components/SyncStatusBar';
import { dashboardService } from '../services/dashboardService';
import {
  EmailDetailPanel,
  getCategoryColor,
  getCategoryLabel,
  getInitials,
  getAvatarColor,
  filterContentTags,
} from '../components/EmailDetailPanel';

const { Text, Title } = Typography;
const { Option } = Select;
const { Search } = Input;

// formatRelativeDate is local to this page (used only in EmailListItem)
const formatRelativeDate = (dateString: string) => {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 7) return `${diffDays}d`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

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
  // Router hooks for mailbox-based navigation
  const { mailboxId, emailId } = useParams<{ mailboxId?: string; emailId?: string }>();
  const navigate = useNavigate();

  // State
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(25); // Reduced from 50 for faster initial load
  const isLoadingMoreRef = useRef(false); // Track if we're loading more vs fresh load
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailExpanded, setDetailExpanded] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [accessibleMailboxes, setAccessibleMailboxes] = useState<Mailbox[]>([]);
  const [mailboxesLoading, setMailboxesLoading] = useState(true); // Track if mailboxes are still loading
  const [mailboxIdMap, setMailboxIdMap] = useState<Record<string, string>>({}); // name -> id mapping
  const [mailboxIdToNameMap, setMailboxIdToNameMap] = useState<Record<string, string>>({}); // id -> name mapping
  const [folders, setFolders] = useState<string[]>([]);
  const [foldersLoading, setFoldersLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [processingJobs, setProcessingJobs] = useState<any[]>([]);
  const processingJobsRef = useRef<any[]>([]); // Ref to prevent stale closure

  const [filters, setFilters] = useState<EmailFilters>({
    search: '',
    category: '',
    mailbox: '',
    folder: '',
    dateRange: null,
    isOutbound: '',
  });

  // System folders that always show — keys MUST be proper case to match DB folder_path values
  const systemFolders = useMemo(() => [
    { key: '', label: 'All Mail', icon: <AppstoreOutlined /> },
    { key: 'Inbox', label: 'Inbox', icon: <InboxOutlined /> },
    { key: 'Sent', label: 'Sent', icon: <SendOutlined /> },
    { key: 'Starred', label: 'Starred', icon: <StarOutlined /> },
    { key: 'Trash', label: 'Trash', icon: <DeleteOutlined /> },
  ], []);

  // Get current folder key for highlighting — must return proper case to match system folder keys
  const currentFolderKey = useMemo(() => {
    if (!filters.folder) return '';
    const lower = filters.folder.toLowerCase();
    if (lower.includes('inbox')) return 'Inbox';
    if (lower.includes('sent')) return 'Sent';
    if (lower.includes('starred') || lower.includes('flagged')) return 'Starred';
    if (lower.includes('trash') || lower.includes('deleted')) return 'Trash';
    return filters.folder;
  }, [filters.folder]);

  // Load emails
  const loadEmails = useCallback(async (append: boolean = false) => {
    // CRITICAL: Never load emails without a mailbox selected
    if (!filters.mailbox) {
      setLoading(false);
      setEmails([]);
      setTotalCount(0);
      return;
    }

    try {
      setLoading(true);
      const { emails: emailData, totalCount: total } = await emailService.getEmails(
        filters,
        currentPage,
        pageSize
      );
      // If appending (load more), add to existing emails; otherwise replace
      if (append && currentPage > 1) {
        setEmails(prev => [...prev, ...emailData]);
      } else {
        setEmails(emailData);
      }
      setTotalCount(total);
    } catch (error) {
      console.error('Error loading emails:', error);
      message.error('Failed to load emails');
    } finally {
      setLoading(false);
    }
  }, [filters, currentPage, pageSize]);

  // Load filter options (categories and mailboxes - static)
  const loadFilterOptions = useCallback(async () => {
    try {
      setMailboxesLoading(true);
      const [categoriesData, mailboxListResponse] = await Promise.all([
        emailService.getEmailCategories(),
        mailboxService.getMailboxes(),
        // Don't load folders initially - wait for mailbox selection
      ]);
      setCategories(categoriesData);

      // Store all mailboxes and create ID maps from ALL mailboxes
      // This allows navigation to any mailbox (active or not)
      setAccessibleMailboxes(mailboxListResponse);

      const idMap: Record<string, string> = {};
      const idToNameMap: Record<string, string> = {};
      mailboxListResponse.forEach((m: Mailbox) => {
        idMap[m.name] = m.id;
        idToNameMap[m.id] = m.name;
      });
      setMailboxIdMap(idMap);
      setMailboxIdToNameMap(idToNameMap);
      // Folders will be loaded after mailbox selection
    } catch (error) {
      console.error('[EmailList] Error loading filter options:', error);
      message.error('Failed to load mailboxes. Please refresh the page.');
    } finally {
      setMailboxesLoading(false);
    }
  }, []); // No dependencies - only run once on mount

  // Navigate to first mailbox if none is selected (separate effect)
  useEffect(() => {
    // Wait for mailboxes to be loaded
    if (accessibleMailboxes.length > 0 && !mailboxId) {
      navigate(`/emails/${accessibleMailboxes[0].id}`, { replace: true });
    }
  }, [accessibleMailboxes, mailboxId, navigate]);

  // Load folders for a specific mailbox (dynamic) - uses cached mailboxIdMap
  const loadFoldersForMailbox = useCallback(async (mailboxName: string) => {
    const mailboxId = mailboxIdMap[mailboxName];
    if (!mailboxId) {
      console.error('Mailbox ID not found for:', mailboxName);
      return;
    }

    try {
      setFoldersLoading(true);
      const foldersData = await emailService.getFolderNames(mailboxId);
      setFolders(foldersData);
    } catch (error) {
      console.error('Error loading folders for mailbox:', error);
    } finally {
      setFoldersLoading(false);
    }
  }, [mailboxIdMap]);

  // Load email details
  const loadEmailDetails = useCallback(async (emailId: string) => {
    try {
      setDetailLoading(true);
      setSelectedEmailId(emailId);
      const fullEmail = await emailService.getEmail(emailId);
      setSelectedEmail(fullEmail);
    } catch (error) {
      console.error('Error loading email details:', error);
      message.error('Failed to load email');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // Keep processingJobs ref in sync with state
  useEffect(() => {
    processingJobsRef.current = processingJobs;
  }, [processingJobs]);

  // Load processing jobs for sync status
  const loadProcessingJobs = useCallback(async () => {
    try {
      const jobs = await dashboardService._fetchProcessingJobs();
      // Preserve existing data if API returns empty (transient failure)
      const currentJobs = processingJobsRef.current;
      if (jobs && Array.isArray(jobs)) {
        // Only clear if we got a valid response - empty array when we have data might be transient
        if (jobs.length === 0 && currentJobs.length > 0) {
          // Keep existing data on empty response
          return;
        }
        setProcessingJobs(jobs);
      }
    } catch (error) {
      console.error('Error loading processing jobs:', error);
      // Don't clear existing data on error
    }
  }, []);

  useEffect(() => {
    // Don't call loadEmails() here - it will be called by the effect that watches filters
    loadFilterOptions();
    loadProcessingJobs();

    // Poll for job updates every 5 seconds
    const interval = setInterval(loadProcessingJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Only load emails if a mailbox is selected
    if (filters.mailbox) {
      loadEmails(isLoadingMoreRef.current);
      isLoadingMoreRef.current = false; // Reset after loading
    } else {
      setLoading(false);
    }
  }, [filters, currentPage, loadEmails]);

  // Reload folders when mailbox selection changes
  useEffect(() => {
    if (filters.mailbox && mailboxIdMap[filters.mailbox]) {
      loadFoldersForMailbox(filters.mailbox);
    }
  }, [filters.mailbox, mailboxIdMap, loadFoldersForMailbox]);

  // Sync URL param (mailboxId) with component state
  useEffect(() => {
    // Wait for mailboxes to be loaded before trying to sync
    if (mailboxesLoading) return;

    if (mailboxId && mailboxIdToNameMap[mailboxId]) {
      const mailboxName = mailboxIdToNameMap[mailboxId];

      // Update filters with the mailbox name (triggers email loading)
      setFilters(prev => ({ ...prev, mailbox: mailboxName }));

      // Clear any selected email when switching mailboxes (unless emailId is in URL)
      if (!emailId) {
        setSelectedEmail(null);
        setSelectedEmailId(null);
      }
      setCurrentPage(1);
    } else if (mailboxId && Object.keys(mailboxIdToNameMap).length > 0) {
      // Mailbox ID from URL not found in accessible mailboxes
      console.warn(`[EmailList] Mailbox ${mailboxId} not found in accessible mailboxes, redirecting to mailboxes page`);
      message.warning('Mailbox not found or not accessible');
      navigate('/mailboxes', { replace: true });
    }
  }, [mailboxId, mailboxIdToNameMap, emailId, mailboxesLoading, navigate]);

  // Load email detail when emailId changes in URL
  useEffect(() => {
    if (emailId && emailId !== selectedEmailId) {
      loadEmailDetails(emailId);
    } else if (!emailId && selectedEmailId) {
      // URL has no emailId but we have one selected - clear it
      setSelectedEmail(null);
      setSelectedEmailId(null);
    }
  }, [emailId, selectedEmailId, loadEmailDetails]);

  // Handlers
  const handleFilterChange = (key: keyof EmailFilters, value: any) => {
    // For filters that affect email list, show immediate feedback
    if (key === 'folder' || key === 'category' || key === 'isOutbound') {
      setEmails([]);
      setTotalCount(0); // Clear count to force skeleton display
      setLoading(true);
      setSelectedEmail(null);
      setSelectedEmailId(null);
    }
    setFilters(prev => ({ ...prev, [key]: value }));
    setCurrentPage(1);
  };

  const handleFolderSelect = (folderKey: string) => {
    // Optimistically clear emails and show loading for instant feedback
    setEmails([]);
    setTotalCount(0); // Clear count to force skeleton display
    setLoading(true);
    setSelectedEmail(null);
    setSelectedEmailId(null);
    setCurrentPage(1);

    if (folderKey === '') {
      setFilters(prev => ({ ...prev, folder: '' }));
    } else {
      // Try to find matching folder with increasing specificity:
      // 1. Exact match (case-sensitive)
      let matchedFolder = folders.find(f => f === folderKey);

      // 2. If no exact match, try case-insensitive exact match
      if (!matchedFolder) {
        matchedFolder = folders.find(f => f.toLowerCase() === folderKey.toLowerCase());
      }

      // 3. If still no match, try case-insensitive includes (for system folders like 'inbox', 'sent')
      if (!matchedFolder) {
        matchedFolder = folders.find(f => f.toLowerCase().includes(folderKey.toLowerCase()));
      }

      // Use matched folder if found, otherwise use the key itself for filtering
      setFilters(prev => ({ ...prev, folder: matchedFolder || folderKey }));
    }
  };

  const handleEmailSelect = (email: Email) => {
    // Navigate to email detail route - this will trigger the effect to load details
    if (mailboxId) {
      navigate(`/emails/${mailboxId}/${email.id}`);
    }
  };

  const handleCloseDetail = () => {
    // Navigate back to mailbox view - this will trigger the effect to clear details
    if (mailboxId) {
      navigate(`/emails/${mailboxId}`);
    }
  };

  const handleRefresh = () => {
    if (!filters.mailbox) {
      return;
    }
    setEmails([]);
    setLoading(true);
    setCurrentPage(1); // Reset to first page on refresh
    setSelectedEmail(null);
    setSelectedEmailId(null);
    loadEmails(false); // Fresh load, don't append
  };

  const handleLoadMore = () => {
    if (!loading && emails.length < totalCount) {
      isLoadingMoreRef.current = true; // Mark as load more operation
      setCurrentPage(prev => prev + 1);
    }
  };

  const hasActiveFilters = !!(filters.category || filters.isOutbound || filters.folder);

  // Get additional folders (not system folders)
  const additionalFolders = useMemo(() => {
    return folders.filter(f => {
      const lower = f.toLowerCase();
      return !['inbox', 'sent', 'starred', 'flagged', 'trash', 'deleted'].some(sys => lower.includes(sys));
    });
  }, [folders]);

  return (
    <div className="mail-client">
      {/* Left Sidebar */}
      <div className={`mail-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        {/* Sidebar Header */}
        <div className="mail-sidebar-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
            <Tooltip title="Back to Mailboxes">
              <Button
                type="text"
                size="small"
                icon={<LeftOutlined />}
                onClick={() => navigate('/mailboxes')}
                style={{ color: 'rgba(255,255,255,0.8)' }}
              />
            </Tooltip>
            {!sidebarCollapsed && (
              <Text strong style={{ fontSize: 14, color: 'white', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {filters.mailbox || 'Loading...'}
              </Text>
            )}
          </div>
          <Tooltip title={sidebarCollapsed ? 'Expand' : 'Collapse'}>
            <Button
              type="text"
              size="small"
              icon={sidebarCollapsed ? <ExpandOutlined /> : <CompressOutlined />}
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              style={{ color: 'rgba(255,255,255,0.8)' }}
            />
          </Tooltip>
        </div>

        {/* Folders Section */}
        <div className="mail-sidebar-section">
          <div className="mail-sidebar-section-title">
            {foldersLoading ? <SyncOutlined spin /> : <FolderOutlined />} {!sidebarCollapsed && 'Folders'}
          </div>
          <div className="mail-sidebar-items">
            {mailboxesLoading || (foldersLoading && !filters.mailbox) ? (
              // Skeleton loader while loading
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
            ) : !filters.mailbox ? (
              !sidebarCollapsed && (
                <div style={{ padding: '12px', textAlign: 'center', color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>
                  Select a mailbox
                </div>
              )
            ) : (
              <>
                {systemFolders.map(folder => (
                  <div
                    key={folder.key}
                    className={`mail-sidebar-item ${currentFolderKey === folder.key ? 'active' : ''}`}
                    onClick={() => handleFolderSelect(folder.key)}
                  >
                    {folder.icon}
                    {!sidebarCollapsed && <span>{folder.label}</span>}
                  </div>
                ))}
                {additionalFolders.length > 0 && (
                  <>
                    <div className="mail-sidebar-divider" />
                    {additionalFolders.map(folder => (
                      <div
                        key={folder}
                        className={`mail-sidebar-item ${filters.folder === folder ? 'active' : ''}`}
                        onClick={() => handleFilterChange('folder', folder)}
                      >
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

      {/* Main Content Area */}
      <div className="mail-main">
        {/* Top Bar - Search & Filters */}
        <div className="mail-topbar">
          <div className="mail-topbar-left">
            <Search
              placeholder="Search emails..."
              allowClear
              value={filters.search}
              onChange={(e) => handleFilterChange('search', e.target.value)}
              prefix={<SearchOutlined style={{ color: '#667eea' }} />}
              className="mail-search"
            />
          </div>

          <div className="mail-topbar-right">
            {/* Filter Button */}
            <Dropdown
              trigger={['click']}
              open={showFilters}
              onOpenChange={setShowFilters}
              dropdownRender={() => (
                <div className="mail-filters-dropdown">
                  <div className="filter-header">
                    <Text strong>Filters</Text>
                    {hasActiveFilters && (
                      <Button
                        type="link"
                        size="small"
                        onClick={() => {
                          setFilters({
                            search: filters.search,
                            category: '',
                            mailbox: filters.mailbox,
                            folder: '',
                            dateRange: null,
                            isOutbound: '',
                          });
                        }}
                      >
                        Clear
                      </Button>
                    )}
                  </div>

                  <div className="filter-group">
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 500 }}>Category</Text>
                    <Select
                      placeholder="All categories"
                      allowClear
                      style={{ width: '100%' }}
                      value={filters.category || undefined}
                      onChange={(v) => handleFilterChange('category', v)}
                    >
                      {categories.map(cat => (
                        <Option key={cat} value={cat}>{getCategoryLabel(cat)}</Option>
                      ))}
                    </Select>
                  </div>

                  <div className="filter-group">
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 500 }}>Direction</Text>
                    <Select
                      placeholder="All"
                      allowClear
                      style={{ width: '100%' }}
                      value={filters.isOutbound || undefined}
                      onChange={(v) => handleFilterChange('isOutbound', v)}
                    >
                      <Option value="inbound">Received</Option>
                      <Option value="outbound">Sent</Option>
                    </Select>
                  </div>
                </div>
              )}
            >
              <Badge dot={hasActiveFilters} offset={[-2, 2]}>
                <Button type={hasActiveFilters ? 'primary' : 'text'} icon={<FilterOutlined />}>
                  Filters
                </Button>
              </Badge>
            </Dropdown>

            {/* Refresh */}
            <Tooltip title="Refresh">
              <Button
                type="text"
                icon={<ReloadOutlined spin={loading} />}
                onClick={handleRefresh}
              />
            </Tooltip>
          </div>
        </div>

        {/* Sync Status Bar */}
        {filters.mailbox && mailboxIdMap[filters.mailbox] && (
          <SyncStatusBar
            selectedMailboxIds={[mailboxIdMap[filters.mailbox]]}
            jobs={processingJobs}
            onViewDetails={() => navigate('/processing')}
          />
        )}

        {/* Content Area - Key based on mailbox to ensure fresh mount */}
        <div className="mail-content" key={filters.mailbox || 'no-mailbox'}>
          {/* Email List */}
          <div className={`mail-list-panel ${selectedEmail ? 'has-detail' : ''}`}>
            {/* Stats bar */}
            <div className="mail-list-stats">
              <Text type="secondary" style={{ fontSize: 13 }}>
                {loading && emails.length === 0 ? (
                  'Loading emails...'
                ) : (
                  <>
                    {totalCount.toLocaleString()} email{totalCount !== 1 ? 's' : ''}
                    {filters.mailbox && ` in ${filters.mailbox}`}
                    {filters.folder && ` • ${filters.folder}`}
                  </>
                )}
              </Text>
            </div>

            {/* Email List */}
            <div className="mail-list-content">
              {mailboxesLoading || (loading && emails.length === 0) ? (
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
              ) : !filters.mailbox ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="Select a mailbox to view emails"
                  style={{ marginTop: 60 }}
                />
              ) : emails.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="No emails found"
                  style={{ marginTop: 60 }}
                />
              ) : (
                <>
                  {emails.map(email => (
                    <EmailListItem
                      key={email.id}
                      email={email}
                      isSelected={selectedEmailId === email.id}
                      onClick={() => handleEmailSelect(email)}
                    />
                  ))}

                  {emails.length < totalCount && (
                    <div className="mail-list-load-more">
                      <Button
                        type="link"
                        onClick={handleLoadMore}
                        loading={loading}
                      >
                        Load more ({totalCount - emails.length} remaining)
                      </Button>
                    </div>
                  )}
                </>
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
