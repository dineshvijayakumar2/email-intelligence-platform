import React, { useState, useEffect, useRef } from 'react';
import { Building2 } from 'lucide-react';
import { clientService, ClientSummary } from '../../services/clientService';

const STORAGE_KEY = 'analytics_client_id';

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

    if (_cachedClients) {
      setClients(_cachedClients);
      setLoading(false);
      if (!value && _cachedClients.length > 0) {
        const initial = (saved && _cachedClients.some(c => c.id === saved)) ? saved : _cachedClients[0].id;
        onChange(initial);
      }
      return;
    }

    if (!value && saved) onChange(saved);

    getClients().then(list => {
      setClients(list);
      setLoading(false);
      if (!value && list.length > 0) {
        const initial = (saved && list.some(c => c.id === saved)) ? saved : list[0].id;
        if (initial !== saved) onChange(initial);
      }
    });
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    localStorage.setItem(STORAGE_KEY, id);
    onChange(id);
  };

  return (
    <div className="inline-flex items-center gap-2" style={style}>
      <Building2 className="h-4 w-4 text-primary" />
      <span className="text-sm font-medium text-slate-700">Client:</span>
      <select
        value={value}
        onChange={handleChange}
        disabled={loading}
        className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary min-w-[180px]"
      >
        {loading && <option>Loading...</option>}
        {clients.map(c => <option key={c.id} value={c.id}>{c.client_name}</option>)}
      </select>
    </div>
  );
};
