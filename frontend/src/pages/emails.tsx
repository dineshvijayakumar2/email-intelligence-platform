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
import { useAuth } from '../contexts/AuthContext';
import SyncStatusBar from '../components/SyncStatusBar';
import { dashboardService } from '../services/dashboardService';
import MailboxSelector from '../components/MailboxSelector';

const { Text, Title } = Typography;
const { Option } = Select;
const { Search } = Input;

// Helper functions
const getCategoryColor = (category: string) => {
  const colors: Record<string, string> = {
    promotional: '#f50',
    transactional: '#2db7f5',
    conversation: '#87d068',
    internal: '#722ed1',
    system: '#fa8c16',
  };
  return colors[category] || '#d9d9d9';
};

const getCategoryLabel = (category: string) => {
  const labels: Record<string, string> = {
    promotional: 'Promotional',
    transactional: 'Transactional',
    conversation: 'Conversation',
    internal: 'Internal',
    system: 'System',
  };
  return labels[category] || category;
};

const getInitials = (name: string, email: string) => {
  if (name) {
    const parts = name.split(' ');
    return parts.length > 1
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : parts[0].substring(0, 2).toUpperCase();
  }
  return email?.substring(0, 2).toUpperCase() || '??';
};

const getAvatarColor = (email: string) => {
  const colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe', '#43e97b', '#fa709a'];
  const index = email?.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % colors.length || 0;
  return colors[index];
};

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

const filterContentTags = (tags: string[]) => {
  if (!tags) return [];
  const folderTags = ['inbox', 'sent', 'spam', 'trash', 'archive', 'drafts', 'other'];
  return tags.filter(tag => !folderTags.includes(tag.toLowerCase()));
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

// Email Detail Panel Component
const EmailDetailPanel: React.FC<{
  email: Email | null;
  loading: boolean;
  onClose: () => void;
  expanded: boolean;
  onToggleExpand: () => void;
}> = ({ email, loading, onClose, expanded, onToggleExpand }) => {
  const [bodyView, setBodyView] = useState<'html' | 'text'>('html');

  if (loading) {
    return (
      <div className="email-detail-panel">
        <div className="email-detail-loading">
          <Spin size="large" />
          <Text type="secondary" style={{ marginTop: 16 }}>Loading email...</Text>
        </div>
      </div>
    );
  }

  if (!email) {
    return (
      <div className="email-detail-panel">
        <div className="email-detail-empty">
          <MailOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />
          <Text type="secondary" style={{ marginTop: 16, fontSize: 16 }}>
            Select an email to view
          </Text>
        </div>
      </div>
    );
  }

  const contentTags = filterContentTags(email.tags || []);

  return (
    <div className={`email-detail-panel ${expanded ? 'expanded' : ''}`}>
      {/* Header */}
      <div className="email-detail-header">
        <div className="email-detail-header-top">
          <Button
            type="text"
            icon={<LeftOutlined />}
            onClick={onClose}
            className="mobile-back-btn"
          />
          <div className="email-detail-actions">
            <Tooltip title={expanded ? 'Collapse' : 'Expand'}>
              <Button
                type="text"
                icon={expanded ? <CompressOutlined /> : <ExpandOutlined />}
                onClick={onToggleExpand}
              />
            </Tooltip>
            <Tooltip title="Close">
              <Button
                type="text"
                icon={<CloseOutlined />}
                onClick={onClose}
                className="desktop-close-btn"
              />
            </Tooltip>
          </div>
        </div>

        <Title level={4} style={{ margin: '16px 0 12px', lineHeight: 1.3 }}>
          {email.subject || '(No subject)'}
        </Title>

        <div className="email-detail-meta">
          <Avatar
            size={48}
            style={{
              backgroundColor: getAvatarColor(email.sender_email),
              flexShrink: 0,
            }}
          >
            {getInitials(email.sender_name || '', email.sender_email)}
          </Avatar>

          <div className="email-detail-meta-info">
            <div className="email-detail-from">
              <Text strong>{email.sender_name || email.sender_email}</Text>
              {email.sender_name && (
                <Text type="secondary" style={{ fontSize: 13 }}>
                  &lt;{email.sender_email}&gt;
                </Text>
              )}
            </div>
            <div className="email-detail-to">
              <Text type="secondary" style={{ fontSize: 13 }}>
                To: {email.recipients?.map(r => r.name || r.email).join(', ') || 'Unknown'}
              </Text>
            </div>
          </div>

          <div className="email-detail-date">
            <Text type="secondary" style={{ fontSize: 13 }}>
              {new Date(email.sent_date).toLocaleString()}
            </Text>
          </div>
        </div>

        {/* Tags */}
        {contentTags.length > 0 && (
          <div className="email-detail-tags">
            {contentTags.map(tag => (
              <Tag key={tag} color={getCategoryColor(tag)}>
                {getCategoryLabel(tag)}
              </Tag>
            ))}
          </div>
        )}

        {/* Info badges */}
        <div className="email-detail-badges">
          <Tag icon={<FolderOutlined />} color="default">
            {email.folder_path || 'Inbox'}
          </Tag>
          <Tag icon={<MailOutlined />} color="default">
            {email.mailbox_name}
          </Tag>
          {email.is_outbound && (
            <Tag color="green">Sent</Tag>
          )}
          {email.is_reply && (
            <Tag color="blue">Reply</Tag>
          )}
        </div>
      </div>

      {/* View Toggle */}
      {email.body_html && email.body_text && (
        <div className="email-detail-view-toggle">
          <Button
            size="small"
            type={bodyView === 'html' ? 'primary' : 'default'}
            onClick={() => setBodyView('html')}
          >
            HTML
          </Button>
          <Button
            size="small"
            type={bodyView === 'text' ? 'primary' : 'default'}
            onClick={() => setBodyView('text')}
          >
            Plain Text
          </Button>
        </div>
      )}

      {/* Body */}
      <div className="email-detail-body">
        {email.body_html && bodyView === 'html' ? (
          <iframe
            srcDoc={`
              <!DOCTYPE html>
              <html>
              <head>
                <meta charset="UTF-8">
                <base target="_blank">
                <style>
                  html, body { margin: 0; padding: 0; }
                  body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: #333;
                    padding: 24px;
                  }
                  img { max-width: 100%; height: auto; }
                  a { color: #667eea; }
                  blockquote {
                    border-left: 3px solid #d9d9d9;
                    padding-left: 16px;
                    margin-left: 0;
                    color: #666;
                  }
                  pre {
                    background: #f5f5f5;
                    padding: 12px;
                    border-radius: 4px;
                    overflow-x: auto;
                  }
                </style>
              </head>
              <body>${email.body_html}</body>
              </html>
            `}
            className="email-body-iframe"
            sandbox="allow-same-origin allow-scripts allow-popups"
            title="Email Content"
          />
        ) : email.body_text ? (
          <div className="email-body-text">
            {email.body_text}
          </div>
        ) : (
          <div className="email-body-empty">
            <Text type="secondary">No email content available</Text>
          </div>
        )}
      </div>
    </div>
  );
};

// Main Email List Component
export const EmailList: React.FC = () => {
  // Router hooks for mailbox-based navigation
  const { mailboxId } = useParams<{ mailboxId?: string }>();
  const navigate = useNavigate();

  // Auth context for user's accessible mailboxes
  const { profile } = useAuth();

  // State
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtersLoading, setFiltersLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(50);
  const isLoadingMoreRef = useRef(false); // Track if we're loading more vs fresh load
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailExpanded, setDetailExpanded] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [accessibleMailboxes, setAccessibleMailboxes] = useState<Mailbox[]>([]);
  const [mailboxIdMap, setMailboxIdMap] = useState<Record<string, string>>({}); // name -> id mapping
  const [mailboxIdToNameMap, setMailboxIdToNameMap] = useState<Record<string, string>>({}); // id -> name mapping
  const [selectedMailboxIds, setSelectedMailboxIds] = useState<string[]>([]); // For MailboxSelector component
  const [folders, setFolders] = useState<string[]>([]);
  const [foldersLoading, setFoldersLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [processingJobs, setProcessingJobs] = useState<any[]>([]);
  const [filters, setFilters] = useState<EmailFilters>({
    search: '',
    category: '',
    mailbox: '',
    folder: '',
    dateRange: null,
    isOutbound: '',
  });

  // System folders that always show
  const systemFolders = useMemo(() => [
    { key: '', label: 'All Mail', icon: <AppstoreOutlined /> },
    { key: 'inbox', label: 'Inbox', icon: <InboxOutlined /> },
    { key: 'sent', label: 'Sent', icon: <SendOutlined /> },
    { key: 'starred', label: 'Starred', icon: <StarOutlined /> },
    { key: 'trash', label: 'Trash', icon: <DeleteOutlined /> },
  ], []);

  // Get current folder key for highlighting
  const currentFolderKey = useMemo(() => {
    if (!filters.folder) return '';
    const lower = filters.folder.toLowerCase();
    if (lower.includes('inbox')) return 'inbox';
    if (lower.includes('sent')) return 'sent';
    if (lower.includes('starred') || lower.includes('flagged')) return 'starred';
    if (lower.includes('trash') || lower.includes('deleted')) return 'trash';
    return filters.folder;
  }, [filters.folder]);

  // Load emails
  const loadEmails = useCallback(async (append: boolean = false) => {
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
      setFiltersLoading(true);
      console.log('[EmailList] Loading filter options...');
      const [categoriesData, mailboxListResponse] = await Promise.all([
        emailService.getEmailCategories(),
        mailboxService.getMailboxes(),
        // Don't load folders initially - wait for mailbox selection
      ]);
      console.log('[EmailList] Raw mailbox response:', mailboxListResponse);
      setCategories(categoriesData);

      // Filter to active mailboxes and create ID maps
      const activeMailboxes = mailboxListResponse.filter((m: Mailbox) => m.is_active);
      console.log('[EmailList] Active mailboxes after filtering:', activeMailboxes);
      console.log('[EmailList] All mailboxes (including inactive):', mailboxListResponse);
      setAccessibleMailboxes(activeMailboxes);

      const idMap: Record<string, string> = {};
      const idToNameMap: Record<string, string> = {};
      activeMailboxes.forEach((m: Mailbox) => {
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
      setFiltersLoading(false);
    }
  }, []); // No dependencies - only run once on mount

  // Navigate to first mailbox if none is selected (separate effect)
  useEffect(() => {
    // Wait for mailboxes to be loaded
    if (accessibleMailboxes.length > 0 && !mailboxId) {
      console.log('[EmailList] No mailbox in URL, navigating to first mailbox:', accessibleMailboxes[0]);
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

  // Load processing jobs for sync status
  const loadProcessingJobs = useCallback(async () => {
    try {
      const jobs = await dashboardService._fetchProcessingJobs();
      setProcessingJobs(jobs || []);
    } catch (error) {
      console.error('Error loading processing jobs:', error);
    }
  }, []);

  useEffect(() => {
    loadEmails();
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
      console.log('[EmailList] No mailbox selected, skipping email load');
      setLoading(false);
    }
  }, [filters, currentPage, loadEmails]);

  // Reload folders when mailbox selection changes
  useEffect(() => {
    if (filters.mailbox && mailboxIdMap[filters.mailbox]) {
      loadFoldersForMailbox(filters.mailbox);
      // Reset folder filter when mailbox changes
      setFilters(prev => ({ ...prev, folder: '' }));
    }
  }, [filters.mailbox, mailboxIdMap, loadFoldersForMailbox]);

  // Sync selectedMailboxIds with filters.mailbox (for initial load)
  useEffect(() => {
    if (filters.mailbox && mailboxIdMap[filters.mailbox]) {
      const mailboxId = mailboxIdMap[filters.mailbox];
      if (!selectedMailboxIds.includes(mailboxId)) {
        setSelectedMailboxIds([mailboxId]);
      }
    }
  }, [filters.mailbox, mailboxIdMap]);

  // Sync URL param (mailboxId) with component state
  useEffect(() => {
    if (mailboxId && mailboxIdToNameMap[mailboxId]) {
      const mailboxName = mailboxIdToNameMap[mailboxId];
      console.log('[EmailList] URL mailbox changed:', mailboxId, '->', mailboxName);

      // Update selected mailbox IDs for the dropdown
      setSelectedMailboxIds([mailboxId]);

      // Update filters with the mailbox name (triggers email loading)
      setFilters(prev => ({ ...prev, mailbox: mailboxName }));

      // Clear any selected email when switching mailboxes
      setSelectedEmail(null);
      setSelectedEmailId(null);
      setCurrentPage(1);
    }
  }, [mailboxId, mailboxIdToNameMap]);

  // Handlers
  const handleFilterChange = (key: keyof EmailFilters, value: any) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setCurrentPage(1);
  };

  const handleFolderSelect = (folderKey: string) => {
    if (folderKey === '') {
      handleFilterChange('folder', '');
    } else {
      // Find matching folder from the folders list, or use the key directly
      const matchedFolder = folders.find(f => f.toLowerCase().includes(folderKey.toLowerCase()));
      // Use matched folder if found, otherwise use the key itself for filtering
      handleFilterChange('folder', matchedFolder || folderKey);
    }
  };

  const handleMailboxSelect = (mailbox: string) => {
    // Clear emails immediately to avoid showing stale data
    setEmails([]);
    setLoading(true);
    setSelectedEmail(null);
    setSelectedEmailId(null);
    // Reset page to 1
    setCurrentPage(1);
    // Update mailbox filter
    handleFilterChange('mailbox', mailbox);
  };

  // Handler for MailboxSelector component (uses IDs) - navigates to new route
  const handleMailboxSelectorChange = (mailboxIds: string[]) => {
    console.log('[EmailList] Mailbox selector changed:', mailboxIds);
    if (mailboxIds.length === 0) return; // Don't allow empty selection

    const selectedMailboxId = mailboxIds[0];
    console.log('[EmailList] Navigating to /emails/' + selectedMailboxId);

    // Optimistically update UI immediately for instant feedback
    setEmails([]);
    setLoading(true);
    setSelectedEmail(null);
    setSelectedEmailId(null);
    setSelectedMailboxIds([selectedMailboxId]);
    setCurrentPage(1);
    setFolders([]); // Clear folders until new ones load

    // Navigate to the mailbox-specific route
    navigate(`/emails/${selectedMailboxId}`);
  };

  const handleEmailSelect = (email: Email) => {
    loadEmailDetails(email.id);
  };

  const handleCloseDetail = () => {
    setSelectedEmail(null);
    setSelectedEmailId(null);
  };

  const handleRefresh = () => {
    setCurrentPage(1); // Reset to first page on refresh
    loadEmails(false); // Fresh load, don't append
    setSelectedEmail(null);
    setSelectedEmailId(null);
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
          <Text strong style={{ fontSize: 16, color: 'white' }}>Folders</Text>
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
            {!filters.mailbox ? (
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
            {/* Mailbox Selector */}
            <MailboxSelector
              value={selectedMailboxIds}
              onChange={handleMailboxSelectorChange}
              mode="single"
              placeholder="Select mailbox"
              size="middle"
              allowClear={false}
            />

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
            onViewDetails={() => window.location.href = '/processing'}
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
              {!filters.mailbox ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="Select a mailbox to view emails"
                  style={{ marginTop: 60 }}
                />
              ) : loading && emails.length === 0 ? (
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
