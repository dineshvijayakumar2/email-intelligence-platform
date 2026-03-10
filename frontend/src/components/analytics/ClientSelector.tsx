import React, { useState, useEffect, useRef } from 'react';
import { Select, Space, Typography } from 'antd';
import { BankOutlined } from '@ant-design/icons';
import { clientService, ClientSummary } from '../../services/clientService';

const { Text } = Typography;

const STORAGE_KEY = 'analytics_client_id';

// Module-level cache: fetched once, shared across all ClientSelector instances
let _cachedClients: ClientSummary[] | null = null;
let _fetchPromise: Promise<ClientSummary[]> | null = null;

function getClients(): Promise<ClientSummary[]> {
  if (_cachedClients) return Promise.resolve(_cachedClients);
  if (_fetchPromise) return _fetchPromise;
  _fetchPromise = clientService.list().then(r => {
    _cachedClients = r.clients || [];
    _fetchPromise = null;
    return _cachedClients;
  }).catch(() => {
    _fetchPromise = null;
    return [] as ClientSummary[];
  });
  return _fetchPromise;
}

interface ClientSelectorProps {
  value?: string;
  onChange: (clientId: string) => void;
  style?: React.CSSProperties;
}

export const ClientSelector: React.FC<ClientSelectorProps> = ({ value, onChange, style }) => {
  const [clients, setClients] = useState<ClientSummary[]>(_cachedClients || []);
  const [loading, setLoading] = useState(!_cachedClients);
  const calledRef = useRef(false);

  useEffect(() => {
    if (calledRef.current) return;
    calledRef.current = true;

    const saved = localStorage.getItem(STORAGE_KEY);

    // If cache is ready, use it immediately (no network call)
    if (_cachedClients) {
      setClients(_cachedClients);
      setLoading(false);
      if (!value && _cachedClients.length > 0) {
        const initial = (saved && _cachedClients.some(c => c.id === saved)) ? saved : _cachedClients[0].id;
        onChange(initial);
      }
      return;
    }

    // Optimistic: fire onChange with saved ID immediately so page can start loading data
    if (!value && saved) {
      onChange(saved);
    }

    // Then fetch the list (deduped across all instances)
    getClients().then(list => {
      setClients(list);
      setLoading(false);
      if (!value && list.length > 0) {
        const initial = (saved && list.some(c => c.id === saved)) ? saved : list[0].id;
        if (initial !== saved) {
          onChange(initial);
        }
      }
    });
  }, []);

  const handleChange = (id: string) => {
    localStorage.setItem(STORAGE_KEY, id);
    onChange(id);
  };

  return (
    <Space>
      <BankOutlined style={{ color: '#667eea' }} />
      <Text strong>Client:</Text>
      <Select
        value={value}
        onChange={handleChange}
        loading={loading}
        placeholder="Select client"
        style={{ minWidth: 200, ...style }}
        options={clients.map(c => ({ value: c.id, label: c.client_name }))}
      />
    </Space>
  );
};
