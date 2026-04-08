/**
 * EmailDetailPanel — Zero antd.
 */

import React, { useState } from 'react';
import { formatDateTime } from '../utils/dateUtils';
import { Mail, Folder, ArrowLeft, Maximize2, Minimize2, X, Link2, Paperclip } from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { StatusBadge } from '@/components/ui/status-badge';
import type { Email } from '../services/emailService';

// ============================================================================
// Helper functions (shared with EmailListItem in emails.tsx)
// ============================================================================

export const getCategoryColor = (category: string) => {
  const colors: Record<string, string> = {
    promotional: '#f50', transactional: '#2db7f5', conversation: '#87d068',
    internal: '#722ed1', system: '#fa8c16',
  };
  return colors[category] || '#d9d9d9';
};

export const getCategoryLabel = (category: string) => {
  const labels: Record<string, string> = {
    promotional: 'Promotional', transactional: 'Transactional', conversation: 'Conversation',
    internal: 'Internal', system: 'System',
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
  onSummarize?: (emailId: string) => Promise<string>;
}

export const EmailDetailPanel: React.FC<EmailDetailPanelProps> = ({
  email, loading, onClose, expanded, onToggleExpand, onSummarize,
}) => {
  const [bodyView, setBodyView] = useState<'html' | 'text'>('html');
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryEmailId, setSummaryEmailId] = useState<string | null>(null);

  const handleSummarize = async () => {
    if (!email || !onSummarize || summaryLoading) return;
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

  if (email && summaryEmailId && summaryEmailId !== email.id) {
    setSummary(null);
    setSummaryEmailId(null);
  }

  if (loading) {
    return (
      <div className="email-detail-panel flex items-center justify-center h-full">
        <div className="text-center">
          <Spinner className="h-8 w-8 text-primary animate-spin mx-auto" />
          <p className="text-sm text-slate-400 mt-4">Loading email...</p>
        </div>
      </div>
    );
  }

  if (!email) {
    return (
      <div className="email-detail-panel flex items-center justify-center h-full">
        <div className="text-center">
          <Mail className="h-16 w-16 text-slate-200 mx-auto" />
          <p className="text-sm text-slate-400 mt-4">Select an email to view</p>
        </div>
      </div>
    );
  }

  const contentTags = filterContentTags(email.tags || []);

  return (
    <div className={`email-detail-panel ${expanded ? 'expanded' : ''}`}>
      {/* Header */}
      <div className="email-detail-header">
        <div className="email-detail-header-top flex items-center justify-between">
          <button onClick={onClose} className="mobile-back-btn p-1 rounded hover:bg-slate-100 lg:hidden">
            <ArrowLeft className="h-4 w-4 text-slate-500" />
          </button>
          <div className="email-detail-actions flex items-center gap-1">
            {onSummarize && (
              <button
                onClick={handleSummarize}
                disabled={summaryLoading || !!(summaryEmailId === email.id && summary)}
                className="h-7 px-2.5 text-xs rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-50 inline-flex items-center gap-1"
                title="AI Summary"
              >
                {summaryLoading && <Spinner className="h-3 w-3 animate-spin" />}
                Summarise
              </button>
            )}
            <button onClick={onToggleExpand} className="p-1.5 rounded hover:bg-slate-100" title={expanded ? 'Collapse' : 'Expand'}>
              {expanded ? <Minimize2 className="h-4 w-4 text-slate-400" /> : <Maximize2 className="h-4 w-4 text-slate-400" />}
            </button>
            <button onClick={onClose} className="desktop-close-btn p-1.5 rounded hover:bg-slate-100 hidden lg:block" title="Close">
              <X className="h-4 w-4 text-slate-400" />
            </button>
          </div>
        </div>

        <h2 className="text-base font-semibold text-slate-900 mt-4 mb-3 leading-snug">
          {email.subject || '(No subject)'}
        </h2>

        {/* AI Summary */}
        {summary && summaryEmailId === email.id && (
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 mb-3">
            <p className="text-xs font-medium text-primary mb-1">AI Summary</p>
            <p className="text-sm text-slate-700">{summary}</p>
          </div>
        )}

        <div className="email-detail-meta flex gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-medium shrink-0"
            style={{ backgroundColor: getAvatarColor(email.sender_email) }}
          >
            {getInitials(email.sender_name || '', email.sender_email)}
          </div>

          <div className="flex-1 min-w-0 text-[13px]">
            <div className="mb-0.5">
              <span className="text-slate-400 w-9 inline-block">From</span>
              <span className="font-medium text-slate-900">{email.sender_name || email.sender_email}</span>
              {email.sender_name && <span className="text-slate-400 text-xs ml-1">&lt;{email.sender_email}&gt;</span>}
            </div>
            <div className="mb-0.5">
              <span className="text-slate-400 w-9 inline-block">To</span>
              <span className="text-slate-600 break-all">
                {email.recipients?.map(r => r.name ? `${r.name} <${r.email}>` : r.email).join(', ') || '—'}
              </span>
            </div>
            {(email.cc_list?.length ?? 0) > 0 && (
              <div className="mb-0.5">
                <span className="text-slate-400 w-9 inline-block">CC</span>
                <span className="text-slate-600 break-all">
                  {email.cc_list!.map(r => r.name ? `${r.name} <${r.email}>` : r.email).join(', ')}
                </span>
              </div>
            )}
            {(email.bcc_list?.length ?? 0) > 0 && (
              <div className="mb-0.5">
                <span className="text-slate-400 w-9 inline-block">BCC</span>
                <span className="text-slate-600 break-all">
                  {email.bcc_list!.map(r => r.name ? `${r.name} <${r.email}>` : r.email).join(', ')}
                </span>
              </div>
            )}
            <div>
              <span className="text-slate-400 w-9 inline-block">Date</span>
              <span className="text-slate-500">{formatDateTime(email.sent_date)}</span>
            </div>
          </div>
        </div>

        {/* Tags */}
        {contentTags.length > 0 && (
          <div className="email-detail-tags flex flex-wrap gap-1 mt-3">
            {contentTags.map(tag => (
              <span key={tag} className="inline-block px-2 py-0.5 text-xs rounded-full text-white" style={{ backgroundColor: getCategoryColor(tag) }}>
                {getCategoryLabel(tag)}
              </span>
            ))}
          </div>
        )}

        {/* Info badges */}
        <div className="email-detail-badges flex flex-wrap gap-1.5 mt-3">
          <StatusBadge variant="neutral" size="sm"><Folder className="h-3 w-3 mr-1 inline" />{email.folder_path || 'Inbox'}</StatusBadge>
          <StatusBadge variant="neutral" size="sm"><Mail className="h-3 w-3 mr-1 inline" />{email.mailbox_name}</StatusBadge>
          {email.is_outbound && <StatusBadge variant="success" size="sm">Sent</StatusBadge>}
          {email.is_reply && <StatusBadge variant="info" size="sm">Reply</StatusBadge>}
          {(email.attachments?.length ?? 0) > 0 && (
            <StatusBadge variant="neutral" size="sm">
              <Paperclip className="h-3 w-3 mr-1 inline" />{email.attachments!.length} attachment{email.attachments!.length !== 1 ? 's' : ''}
            </StatusBadge>
          )}
          {email.provider_web_link && (
            <a href={email.provider_web_link} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 h-6 px-2 text-xs rounded border border-slate-200 hover:bg-slate-50 text-primary"
              title="Open in email client">
              <Link2 className="h-3 w-3" />
              Open in {email.mailbox_type === 'gmail' ? 'Gmail' : 'Outlook'}
            </a>
          )}
        </div>

        {/* Attachments list */}
        {(email.attachments?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {email.attachments!.map((att, i) => (
              <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded bg-slate-100 text-slate-600">
                <Paperclip className="h-3 w-3" />
                {att.filename}{att.size ? ` (${Math.round(att.size / 1024)}KB)` : ''}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* View Toggle */}
      {email.body_html && email.body_text && (
        <div className="email-detail-view-toggle flex gap-1 px-4 py-2">
          <button onClick={() => setBodyView('html')}
            className={`h-7 px-3 text-xs rounded ${bodyView === 'html' ? 'bg-primary text-white' : 'border border-slate-200 hover:bg-slate-50'}`}>
            HTML
          </button>
          <button onClick={() => setBodyView('text')}
            className={`h-7 px-3 text-xs rounded ${bodyView === 'text' ? 'bg-primary text-white' : 'border border-slate-200 hover:bg-slate-50'}`}>
            Plain Text
          </button>
        </div>
      )}

      {/* Body */}
      <div className="email-detail-body">
        {email.body_html && bodyView === 'html' ? (
          <iframe
            srcDoc={`<!DOCTYPE html><html><head><meta charset="UTF-8"><base target="_blank"><style>
              html, body { margin: 0; padding: 0; }
              body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.6; color: #333; padding: 24px; }
              img { max-width: 100%; height: auto; }
              a { color: #667eea; }
              blockquote { border-left: 3px solid #d9d9d9; padding-left: 16px; margin-left: 0; color: #666; }
              pre { background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }
            </style></head><body>${email.body_html}</body></html>`}
            className="email-body-iframe"
            sandbox="allow-same-origin allow-scripts allow-popups"
            title="Email Content"
          />
        ) : email.body_text ? (
          <div className="email-body-text">{email.body_text}</div>
        ) : (
          <div className="email-body-empty">
            <p className="text-sm text-slate-400">No email content available</p>
          </div>
        )}
      </div>
    </div>
  );
};
