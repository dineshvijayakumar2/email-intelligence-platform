/**
 * Mailbox Selector Component — Zero antd.
 */

import React, { useState, useEffect } from 'react';
import { Inbox, RefreshCw, Cloud } from 'lucide-react';
import { mailboxService, Mailbox, hasGmailLiveSync } from '../services/mailboxService';

export { useMailboxSelection } from '../hooks/useMailboxSelection';

interface MailboxSelectorProps {
  value?: string[];
  onChange?: (mailboxIds: string[]) => void;
  mode?: 'multiple' | 'single';
  placeholder?: string;
  style?: React.CSSProperties;
  className?: string;
  disabled?: boolean;
  size?: 'small' | 'middle' | 'large';
}

export const MailboxSelector: React.FC<MailboxSelectorProps> = ({
  value = [],
  onChange,
  mode = 'multiple',
  placeholder = 'Select mailbox(es)',
  className,
  disabled = false,
  size = 'middle',
}) => {
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const data = await mailboxService.getMailboxes();
        if (data && data.length > 0) {
          setMailboxes(data.filter(m => m.is_active));
        }
      } catch {
        // keep existing data on error
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const getMailboxLabel = (mailbox: Mailbox) => {
    const label = mailbox.name;
    if (mailbox.email_address && mailbox.email_address !== mailbox.name) {
      return `${label} (${mailbox.email_address})`;
    }
    return label;
  };

  const sizeClass = size === 'small' ? 'h-7 text-xs' : 'h-8 text-sm';

  if (mode === 'single') {
    return (
      <select
        value={value[0] || ''}
        onChange={e => onChange?.(e.target.value ? [e.target.value] : [])}
        disabled={disabled || loading}
        className={`${sizeClass} px-2 rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 min-w-[240px] ${className || ''}`}
      >
        <option value="">{loading ? 'Loading...' : placeholder}</option>
        {mailboxes.map(m => (
          <option key={m.id} value={m.id}>
            {getMailboxLabel(m)} ({m.total_emails.toLocaleString('en-AU')} emails)
          </option>
        ))}
      </select>
    );
  }

  // Multiple mode: checkboxes in a dropdown-like list
  return (
    <div className={`inline-flex flex-col ${className || ''}`}>
      <div className="flex flex-wrap gap-1.5">
        {mailboxes.map(m => {
          const isSelected = value.includes(m.id);
          return (
            <label
              key={m.id}
              className={`inline-flex items-center gap-1.5 px-2 py-1 text-xs rounded-md border cursor-pointer transition-colors ${
                isSelected
                  ? 'border-primary bg-primary/5 text-primary'
                  : 'border-slate-200 text-slate-600 hover:border-slate-300'
              } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <input
                type="checkbox"
                checked={isSelected}
                disabled={disabled}
                onChange={() => {
                  if (!onChange) return;
                  if (isSelected) {
                    onChange(value.filter(v => v !== m.id));
                  } else {
                    onChange([...value, m.id]);
                  }
                }}
                className="sr-only"
              />
              {hasGmailLiveSync(m) ? (
                <RefreshCw className="h-3 w-3 text-success" />
              ) : m.mailbox_type === 'gmail' ? (
                <Cloud className="h-3 w-3 text-red-500" />
              ) : m.mailbox_type === 'outlook_live' ? (
                <Cloud className="h-3 w-3 text-blue-500" />
              ) : (
                <Inbox className="h-3 w-3" />
              )}
              <span className="font-medium">{m.name}</span>
              {hasGmailLiveSync(m) && <span className="text-[10px] text-success font-medium">LIVE</span>}
              <span className="text-slate-400">{m.total_emails.toLocaleString('en-AU')}</span>
            </label>
          );
        })}
        {loading && <span className="text-xs text-slate-400">Loading...</span>}
        {!loading && mailboxes.length === 0 && <span className="text-xs text-slate-400">No mailboxes found</span>}
      </div>
    </div>
  );
};

export default MailboxSelector;
