/**
 * QBLinkWidget — Inline widget to view/update QB links on company or contact detail pages.
 * Supports two modes: 'company' (search QB customers) and 'contact' (search QB contacts).
 */

import React, { useState, useRef } from 'react';
import { Space, Typography, Tag, Select, Button, Spin, message, Tooltip } from 'antd';
import { LinkOutlined, CheckCircleOutlined, SearchOutlined, DisconnectOutlined } from '@ant-design/icons';
import api from '../services/apiClient';

const { Text } = Typography;

interface Props {
  mode: 'company' | 'contact';
  entityId: string;              // SB customer_companies.id or customer_contacts.id
  clientId: string;
  qbLinkedId?: string;           // Current qb_customer_id or qb_contact matched status
  qbMatchMethod?: string;        // 'exact_name' | 'domain_root' | 'fuzzy' | 'manual' | 'email'
  qbDisplayName?: string;        // Display name of linked QB record
  onLinked?: () => void;
}

interface QBOption { value: string; label: string }

const methodColors: Record<string, string> = {
  exact_name: 'green',
  domain_root: 'blue',
  fuzzy: 'orange',
  manual: 'purple',
  email: 'cyan',
};

export default function QBLinkWidget({
  mode, entityId, clientId, qbLinkedId, qbMatchMethod, qbDisplayName, onLinked,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [options, setOptions] = useState<QBOption[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedQbId, setSelectedQbId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isCompany = mode === 'company';
  const entityLabel = isCompany ? 'QB Customer' : 'QB Contact';

  const handleSearch = (query: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query || query.length < 2) { setOptions([]); return; }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        if (isCompany) {
          const data = await api.get(
            `/v1/quickbase/customers?client_id=${clientId}&search=${encodeURIComponent(query)}&limit=20`
          ) as { customers: any[] };
          setOptions((data.customers || []).map((c: any) => ({
            value: c.qb_record_id,
            label: `${c.customer_name}${c.total_invoiced ? ` ($${Number(c.total_invoiced).toLocaleString()})` : ''}`,
          })));
        } else {
          const data = await api.get(
            `/v1/quickbase/contacts?client_id=${clientId}&search=${encodeURIComponent(query)}&limit=20`
          ) as { contacts: any[] };
          setOptions((data.contacts || []).map((c: any) => ({
            value: c.qb_record_id,
            label: `${c.first_name || ''} ${c.surname || ''}`.trim() + (c.email ? ` (${c.email})` : ''),
          })));
        }
      } catch { /* silent */ }
      setSearching(false);
    }, 300);
  };

  const handleLink = async () => {
    if (!selectedQbId) return;
    setSaving(true);
    try {
      if (isCompany) {
        const params = new URLSearchParams({
          client_id: clientId, sb_company_id: entityId, qb_record_id: selectedQbId,
        });
        await api.post(`/v1/quickbase/link-company?${params}`);
      } else {
        const params = new URLSearchParams({
          client_id: clientId, sb_contact_id: entityId, qb_record_id: selectedQbId,
        });
        await api.post(`/v1/quickbase/link-contact?${params}`);
      }
      message.success(`${entityLabel} linked`);
      setEditing(false);
      setSelectedQbId(null);
      onLinked?.();
    } catch {
      message.error('Failed to link');
    }
    setSaving(false);
  };

  if (!editing) {
    return (
      <Space size={4} wrap>
        {qbLinkedId ? (
          <>
            <Tooltip title={`Matched via ${qbMatchMethod || 'unknown'}`}>
              <Tag color={methodColors[qbMatchMethod || ''] || 'default'} icon={<LinkOutlined />}>
                {qbDisplayName || qbLinkedId}
              </Tag>
            </Tooltip>
            <Button type="link" size="small" onClick={() => setEditing(true)} style={{ padding: 0, fontSize: 12 }}>
              Change
            </Button>
          </>
        ) : (
          <Button
            type="dashed"
            size="small"
            icon={<DisconnectOutlined />}
            onClick={() => setEditing(true)}
          >
            Link to {entityLabel}
          </Button>
        )}
      </Space>
    );
  }

  return (
    <Space size={4}>
      <Select
        showSearch
        size="small"
        style={{ width: 280 }}
        placeholder={`Search ${entityLabel.toLowerCase()}...`}
        suffixIcon={<SearchOutlined />}
        loading={searching}
        options={options}
        filterOption={false}
        onSearch={handleSearch}
        onChange={(val) => setSelectedQbId(val)}
        notFoundContent={searching ? <Spin size="small" /> : <Text type="secondary">Type 2+ chars</Text>}
      />
      <Button
        type="primary"
        size="small"
        icon={<CheckCircleOutlined />}
        loading={saving}
        disabled={!selectedQbId}
        onClick={handleLink}
      >
        Link
      </Button>
      <Button size="small" type="text" onClick={() => { setEditing(false); setSelectedQbId(null); }}>
        Cancel
      </Button>
    </Space>
  );
}
