import React, { useState } from 'react';
import {
  Typography,
  Tag,
  Button,
  Tooltip,
  Spin,
  Avatar,
  Alert,
} from 'antd';
import {
  MailOutlined,
  FolderOutlined,
  LeftOutlined,
  ExpandOutlined,
  CompressOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import type { Email } from '../services/emailService';

const { Text, Title } = Typography;

// ============================================================================
// Helper functions (shared with EmailListItem in emails.tsx)
// ============================================================================

export const getCategoryColor = (category: string) => {
  const colors: Record<string, string> = {
    promotional: '#f50',
    transactional: '#2db7f5',
    conversation: '#87d068',
    internal: '#722ed1',
    system: '#fa8c16',
  };
  return colors[category] || '#d9d9d9';
};

export const getCategoryLabel = (category: string) => {
  const labels: Record<string, string> = {
    promotional: 'Promotional',
    transactional: 'Transactional',
    conversation: 'Conversation',
    internal: 'Internal',
    system: 'System',
  };
  return labels[category] || category;
};

export const getInitials = (name: string, email: string) => {
  if (name) {
    const parts = name.split(' ');
    return parts.length > 1
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : parts[0].substring(0, 2).toUpperCase();
  }
  return email?.substring(0, 2).toUpperCase() || '??';
};

export const getAvatarColor = (email: string) => {
  const colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe', '#43e97b', '#fa709a'];
  const index = email?.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % colors.length || 0;
  return colors[index];
};

export const filterContentTags = (tags: string[]) => {
  if (!tags) return [];
  const folderTags = ['inbox', 'sent', 'spam', 'trash', 'archive', 'drafts', 'other'];
  return tags.filter(tag => !folderTags.includes(tag.toLowerCase()));
};

// ============================================================================
// EmailDetailPanel Component
// ============================================================================

export interface EmailDetailPanelProps {
  email: Email | null;
  loading: boolean;
  onClose: () => void;
  expanded: boolean;
  onToggleExpand: () => void;
  /** Called to request AI summary for the email. Returns summary text. */
  onSummarize?: (emailId: string) => Promise<string>;
}

export const EmailDetailPanel: React.FC<EmailDetailPanelProps> = ({
  email,
  loading,
  onClose,
  expanded,
  onToggleExpand,
  onSummarize,
}) => {
  const [bodyView, setBodyView] = useState<'html' | 'text'>('html');
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryEmailId, setSummaryEmailId] = useState<string | null>(null);

  const handleSummarize = async () => {
    if (!email || !onSummarize || summaryLoading) return;
    // If already summarized this email, don't re-fetch
    if (summaryEmailId === email.id && summary) return;
    setSummaryLoading(true);
    try {
      const result = await onSummarize(email.id);
      setSummary(result);
      setSummaryEmailId(email.id);
    } catch {
      setSummary('Failed to generate summary.');
      setSummaryEmailId(email.id);
    } finally {
      setSummaryLoading(false);
    }
  };

  // Clear summary when email changes
  if (email && summaryEmailId && summaryEmailId !== email.id) {
    setSummary(null);
    setSummaryEmailId(null);
  }

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
            {onSummarize && (
              <Tooltip title="AI Summary">
                <Button
                  type="text"
                  size="small"
                  loading={summaryLoading}
                  onClick={handleSummarize}
                  disabled={!!(summaryEmailId === email.id && summary)}
                >
                  Summarise
                </Button>
              </Tooltip>
            )}
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

        {/* AI Summary */}
        {summary && summaryEmailId === email.id && (
          <Alert
            type="info"
            showIcon
            message="AI Summary"
            description={summary}
            style={{ marginBottom: 12 }}
          />
        )}

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
