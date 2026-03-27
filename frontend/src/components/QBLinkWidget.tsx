/**
 * QBLinkWidget — Inline widget to view/update the QB customer link on company or contact detail pages.
 * Shows current link status with a searchable QB customer selector to change/set the mapping.
 */

import React, { useState, useRef } from 'react';
import { Space, Typography, Tag, Select, Button, Spin, message, Tooltip } from 'antd';
import { LinkOutlined, CheckCircleOutlined, SearchOutlined, DisconnectOutlined } from '@ant-design/icons';
import api from '../services/apiClient';

const { Text } = Typography;

interface Props {
  companyId: string;           // SB customer_companies.id
  clientId: string;
  qbCustomerId?: string;       // Current qb_customer_id (if linked)
  qbMatchMethod?: string;      // 'exact_name' | 'domain_root' | 'fuzzy' | 'manual'
  qbCustomerName?: string;     // Display name of linked QB customer
  onLinked?: () => void;       // Callback after successful link/unlink
}

interface QBOption { value: string; label: string; revenue?: number }

const methodColors: Record<string, string> = {
  exact_name: 'green',
  domain_root: 'blue',
  fuzzy: 'orange',
  manual: 'purple',
};

export default function QBLinkWidget({
  companyId, clientId, qbCustomerId, qbMatchMethod, qbCustomerName, onLinked,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [options, setOptions] = useState<QBOption[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedQbId, setSelectedQbId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearch = (query: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query || query.length < 2) { setOptions([]); return; }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await api.get(
          `/v1/quickbase/customers?client_id=${clientId}&search=${encodeURIComponent(query)}&limit=20`
        ) as { customers: any[] };
        setOptions((data.customers || []).map((c: any) => ({
          value: c.qb_record_id,
          label: `${c.customer_name}${c.total_invoiced ? ` ($${Number(c.total_invoiced).toLocaleString()})` : ''}`,
          revenue: c.total_invoiced,
        })));
      } catch { /* silent */ }
      setSearching(false);
    }, 300);
  };

  const handleLink = async () => {
    if (!selectedQbId) return;
    setSaving(true);
    try {
      // Use the match candidate review endpoint pattern — link QB customer to SB company
      // We need a direct link endpoint. For now, update customer_companies directly.
      const params = new URLSearchParams({
        client_id: clientId,
        sb_company_id: companyId,
        qb_record_id: selectedQbId,
      });
      await api.post(`/v1/quickbase/link-company?${params}`);
      message.success('QB customer linked');
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
        {qbCustomerId ? (
          <>
            <Tooltip title={`QB ID: ${qbCustomerId} · Matched via ${qbMatchMethod || 'unknown'}`}>
              <Tag color={methodColors[qbMatchMethod || ''] || 'default'} icon={<LinkOutlined />}>
                QB: {qbCustomerName || qbCustomerId}
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
            Link to QB Customer
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
        placeholder="Search QB customer..."
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
