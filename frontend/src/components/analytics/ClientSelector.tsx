import React, { useState, useEffect, useRef } from 'react';
import { Building2 } from 'lucide-react';
import { clientService, ClientSummary } from '../../services/clientService';

const STORAGE_KEY = 'analytics_client_id';
const CACHE_KEY = 'client_list_cache';

// Module-level + sessionStorage cache
let _cachedClients: ClientSummary[] | null = null;

function loadFromSession(): ClientSummary[] | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return null;
}

// Initialize from sessionStorage immediately (sync, no network)
if (!_cachedClients) {
  _cachedClients = loadFromSession();
}

let _fetchPromise: Promise<ClientSummary[]> | null = null;

function getClients(): Promise<ClientSummary[]> {
  if (_cachedClients) return Promise.resolve(_cachedClients);
  if (_fetchPromise) return _fetchPromise;
  _fetchPromise = clientService.list().then(r => {
    _cachedClients = r.clients || [];
    _fetchPromise = null;
    try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(_cachedClients)); } catch { /* full */ }
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

    if (_cachedClients && _cachedClients.length > 0) {
      setClients(_cachedClients);
      setLoading(false);
      if (!value && _cachedClients.length > 0) {
        const initial = (saved && _cachedClients.some(c => c.id === saved)) ? saved : _cachedClients[0].id;
        onChange(initial);
      }
      return;
    }

    // Fire immediately with saved ID (no waiting for fetch)
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

  // Show saved client name while loading
  const savedId = localStorage.getItem(STORAGE_KEY);
  const showValue = value || savedId || '';

  return (
    <div className="inline-flex items-center gap-2" style={style}>
      <Building2 className="h-4 w-4 text-primary" />
      <span className="text-sm font-medium text-slate-700">Client:</span>
      <select
        value={showValue}
        onChange={handleChange}
        disabled={loading && clients.length === 0}
        className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary min-w-[180px]"
      >
        {clients.length === 0 && loading && <option value={showValue}>Loading...</option>}
        {clients.map(c => <option key={c.id} value={c.id}>{c.client_name}</option>)}
      </select>
    </div>
  );
};
