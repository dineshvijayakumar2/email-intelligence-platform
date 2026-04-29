import { useState, useEffect, useRef, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { EmailFilters } from '../services/emailService';

export interface EmailFilterState {
  search: string;
  sender: string;
  folder: string;
  category: string;
  direction: string;
  sortBy: string;
  sortDir: 'asc' | 'desc';
}

export interface AnalyticsMode {
  isActive: boolean;
  contactId: string | null;
  companyId: string | null;
  threadId: string | null;
  emailId: string | null;
  label: string;
}

const DEFAULTS: EmailFilterState = {
  search: '', sender: '', folder: '', category: '',
  direction: '', sortBy: 'sent_date', sortDir: 'desc',
};

export function useEmailFilters() {
  const [searchParams, setSearchParams] = useSearchParams();

  const analyticsMode: AnalyticsMode = useMemo(() => {
    const contactId = searchParams.get('contact_id');
    const companyId = searchParams.get('company_id');
    const threadId = searchParams.get('thread_id');
    const emailId = searchParams.get('email_id');
    return {
      isActive: !!(contactId || companyId || threadId || emailId),
      contactId, companyId, threadId, emailId,
      label: searchParams.get('name') || 'Contact',
    };
  }, [searchParams]);

  const [filters, setFiltersState] = useState<EmailFilterState>(() => ({
    search: searchParams.get('q') || DEFAULTS.search,
    sender: searchParams.get('sender') || DEFAULTS.sender,
    folder: searchParams.get('folder') || DEFAULTS.folder,
    category: searchParams.get('cat') || DEFAULTS.category,
    direction: searchParams.get('dir') || DEFAULTS.direction,
    sortBy: searchParams.get('sort') || DEFAULTS.sortBy,
    sortDir: (searchParams.get('order') as 'asc' | 'desc') || DEFAULTS.sortDir,
  }));

  const [page, setPage] = useState(() => {
    const p = parseInt(searchParams.get('page') || '1', 10);
    return isNaN(p) || p < 1 ? 1 : p;
  });
  const pageSize = 25;

  const setFilter = (key: keyof EmailFilterState, value: string) => {
    setFiltersState(prev => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const clearFilters = () => {
    setFiltersState(DEFAULTS);
    setPage(1);
  };

  // Debounced search/sender
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState(filters.search);
  const [debouncedSender, setDebouncedSender] = useState(filters.sender);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setDebouncedSearch(filters.search);
      setDebouncedSender(filters.sender);
    }, 400);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [filters.search, filters.sender]);

  // Sync filters + page to URL (debounced values only)
  useEffect(() => {
    if (analyticsMode.isActive) return;
    const params = new URLSearchParams(searchParams);
    const map: Record<string, string> = {
      q: debouncedSearch, sender: debouncedSender,
      folder: filters.folder, cat: filters.category, dir: filters.direction,
      sort: filters.sortBy, order: filters.sortDir,
      page: page > 1 ? String(page) : '',
    };
    let changed = false;
    for (const [k, v] of Object.entries(map)) {
      const cur = params.get(k) || '';
      if (v && v !== DEFAULTS[k as keyof EmailFilterState]?.toString() && (k !== 'page' || v !== '')) {
        if (cur !== v) { params.set(k, v); changed = true; }
      } else if (cur) {
        params.delete(k);
        changed = true;
      }
    }
    if (changed) setSearchParams(params, { replace: true });
  }, [debouncedSearch, debouncedSender, filters.folder, filters.category, filters.direction, filters.sortBy, filters.sortDir, page, analyticsMode.isActive]);

  const hasActiveFilters = !!(filters.direction || filters.folder || debouncedSender);

  const queryFilters: EmailFilters = useMemo(() => ({
    search: debouncedSearch || undefined,
    sender: debouncedSender || undefined,
    folder: filters.folder || undefined,
    category: filters.category || undefined,
    isOutbound: filters.direction || undefined,
  }), [debouncedSearch, debouncedSender, filters.folder, filters.category, filters.direction]);

  return {
    filters, setFilter, clearFilters, hasActiveFilters,
    debouncedSearch, debouncedSender,
    page, setPage, pageSize,
    queryFilters,
    analyticsMode,
  };
}
