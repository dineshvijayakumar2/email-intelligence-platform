import React, { useState, useEffect } from 'react';
import { Select, Space, Typography } from 'antd';
import { BankOutlined } from '@ant-design/icons';
import { clientService, ClientSummary } from '../../services/clientService';

const { Text } = Typography;

const STORAGE_KEY = 'analytics_client_id';

interface ClientSelectorProps {
  value?: string;
  onChange: (clientId: string) => void;
  style?: React.CSSProperties;
}

export const ClientSelector: React.FC<ClientSelectorProps> = ({ value, onChange, style }) => {
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const result = await clientService.list();
        const list = result.clients || [];
        setClients(list);

        // Auto-select: use saved value, or first client
        if (!value && list.length > 0) {
          const saved = localStorage.getItem(STORAGE_KEY);
          const initial = (saved && list.some(c => c.id === saved)) ? saved : list[0].id;
          onChange(initial);
        }
      } catch {
        setClients([]);
      } finally {
        setLoading(false);
      }
    };
    load();
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
