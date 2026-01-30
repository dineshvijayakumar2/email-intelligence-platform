/**
 * Mailbox Selector Component
 *
 * A dropdown component for selecting mailboxes.
 * Supports single and multi-select modes.
 * Only shows mailboxes accessible to the current user.
 */

import React, { useState, useEffect } from 'react';
import { Select, Space, Typography, Badge, Tooltip } from 'antd';
import { InboxOutlined, SyncOutlined, CloudOutlined, MailOutlined } from '@ant-design/icons';
import { mailboxService, Mailbox, hasGmailLiveSync } from '../services/mailboxService';

const { Text } = Typography;

interface MailboxSelectorProps {
  value?: string[];
  onChange?: (mailboxIds: string[]) => void;
  mode?: 'multiple' | 'single';
  placeholder?: string;
  style?: React.CSSProperties;
  className?: string;
  disabled?: boolean;
  allowClear?: boolean;
  maxTagCount?: number;
  size?: 'small' | 'middle' | 'large';
}

export const MailboxSelector: React.FC<MailboxSelectorProps> = ({
  value = [],
  onChange,
  mode = 'multiple',
  placeholder = 'Select mailbox(es)',
  style,
  className,
  disabled = false,
  allowClear = true,
  maxTagCount = 2,
  size = 'middle',
}) => {
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMailboxes();
  }, []);

  const loadMailboxes = async () => {
    try {
      setLoading(true);
      const data = await mailboxService.getMailboxes();
      // Filter to active mailboxes only
      setMailboxes(data.filter((m) => m.is_active));
    } catch (error) {
      console.error('Failed to load mailboxes:', error);
      setMailboxes([]);
    } finally {
      setLoading(false);
    }
  };

  const getMailboxIcon = (mailbox: Mailbox) => {
    if (hasGmailLiveSync(mailbox)) {
      return <SyncOutlined spin style={{ color: '#52c41a' }} />;
    }
    switch (mailbox.mailbox_type) {
      case 'gmail':
        return <CloudOutlined style={{ color: '#ea4335' }} />;
      case 'outlook_live':
        return <CloudOutlined style={{ color: '#0078d4' }} />;
      default:
        return <InboxOutlined style={{ color: '#667eea' }} />;
    }
  };

  const getMailboxLabel = (mailbox: Mailbox) => {
    const label = mailbox.name;
    if (mailbox.email_address && mailbox.email_address !== mailbox.name) {
      return `${label} (${mailbox.email_address})`;
    }
    return label;
  };

  const handleChange = (selectedValues: string | string[]) => {
    if (onChange) {
      if (mode === 'single') {
        onChange(selectedValues ? [selectedValues as string] : []);
      } else {
        onChange(selectedValues as string[]);
      }
    }
  };

  const selectValue = mode === 'single' ? (value.length > 0 ? value[0] : undefined) : value;

  return (
    <Select
      mode={mode === 'multiple' ? 'multiple' : undefined}
      value={selectValue}
      onChange={handleChange}
      placeholder={placeholder}
      loading={loading}
      disabled={disabled}
      allowClear={allowClear}
      style={{ minWidth: 240, ...style }}
      className={`mailbox-select ${className || ''}`}
      maxTagCount={maxTagCount}
      maxTagPlaceholder={(omitted) => `+${omitted.length} more`}
      optionFilterProp="label"
      showSearch
      size={size}
      notFoundContent={loading ? 'Loading...' : 'No mailboxes found'}
      optionLabelProp="label"
    >
      {mailboxes.map((mailbox) => (
        <Select.Option key={mailbox.id} value={mailbox.id} label={getMailboxLabel(mailbox)}>
          <div
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}
          >
            <Space size={8}>
              {getMailboxIcon(mailbox)}
              <span style={{ fontWeight: 500 }}>{mailbox.name}</span>
              {mailbox.email_address && mailbox.email_address !== mailbox.name && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {mailbox.email_address}
                </Text>
              )}
            </Space>
            <Space size={4}>
              {hasGmailLiveSync(mailbox) && (
                <Tooltip title="Gmail LIVE sync enabled">
                  <Badge
                    status="success"
                    text={<Text type="secondary" style={{ fontSize: 11 }}>LIVE</Text>}
                  />
                </Tooltip>
              )}
              <Text type="secondary" style={{ fontSize: 11 }}>
                {mailbox.total_emails.toLocaleString()} emails
              </Text>
            </Space>
          </div>
        </Select.Option>
      ))}
    </Select>
  );
};

/**
 * Hook to manage mailbox selection state with persistence
 */
export const useMailboxSelection = (defaultValue: string[] = []) => {
  const storageKey = 'selectedMailboxIds';

  const [selectedMailboxIds, setSelectedMailboxIds] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      return stored ? JSON.parse(stored) : defaultValue;
    } catch {
      return defaultValue;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(selectedMailboxIds));
    } catch {
      // Ignore storage errors
    }
  }, [selectedMailboxIds]);

  return [selectedMailboxIds, setSelectedMailboxIds] as const;
};

export default MailboxSelector;
