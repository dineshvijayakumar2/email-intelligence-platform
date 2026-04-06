/**
 * Global client context — selected client ID available to all pages.
 * Set via the user dropdown in the layout header.
 */
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { clientService, ClientSummary } from '../services/clientService';

const STORAGE_KEY = 'analytics_client_id';
const CACHE_KEY = 'client_list_cache';

interface ClientContextValue {
  clientId: string;
  setClientId: (id: string) => void;
  clients: ClientSummary[];
  clientName: string;
  loading: boolean;
}

const ClientContext = createContext<ClientContextValue>({
  clientId: '',
  setClientId: () => {},
  clients: [],
  clientName: '',
  loading: true,
});

export const useClient = () => useContext(ClientContext);

export const ClientProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [clientId, setClientIdState] = useState(() => localStorage.getItem(STORAGE_KEY) || '');
  const [clients, setClients] = useState<ClientSummary[]>(() => {
    try {
      const cached = sessionStorage.getItem(CACHE_KEY);
      return cached ? JSON.parse(cached) : [];
    } catch { return []; }
  });
  const [loading, setLoading] = useState(clients.length === 0);

  const setClientId = useCallback((id: string) => {
    localStorage.setItem(STORAGE_KEY, id);
    setClientIdState(id);
  }, []);

  useEffect(() => {
    if (clients.length > 0) {
      setLoading(false);
      if (!clientId && clients.length > 0) setClientId(clients[0].id);
      return;
    }

    clientService.list().then(r => {
      const list = r.clients || [];
      setClients(list);
      try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(list)); } catch {}
      if (!clientId && list.length > 0) setClientId(list[0].id);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const clientName = clients.find(c => c.id === clientId)?.client_name || '';

  return (
    <ClientContext.Provider value={{ clientId, setClientId, clients, clientName, loading }}>
      {children}
    </ClientContext.Provider>
  );
};
