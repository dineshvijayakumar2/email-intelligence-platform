/**
 * QBLinkWidget — Inline widget to view/update QB links. Zero antd.
 */

import React, { useState, useRef } from 'react';
import { Link2, CheckCircle, Search, Unlink } from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { StatusBadge } from '@/components/ui/status-badge';
import { toast } from '@/lib/toast';
import api from '../services/apiClient';

interface Props {
  mode: 'company' | 'contact';
  entityId: string;
  clientId: string;
  qbLinkedId?: string;
  qbMatchMethod?: string;
  qbDisplayName?: string;
  onLinked?: () => void;
}

interface QBOption { value: string; label: string }

const methodVariant: Record<string, 'success' | 'info' | 'warning' | 'purple' | 'neutral'> = {
  exact_name: 'success',
  domain_root: 'info',
  fuzzy: 'warning',
  manual: 'purple',
  email: 'info',
};

export default function QBLinkWidget({
  mode, entityId, clientId, qbLinkedId, qbMatchMethod, qbDisplayName, onLinked,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [options, setOptions] = useState<QBOption[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedQbId, setSelectedQbId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [unlinking, setUnlinking] = useState(false);
  const [searchText, setSearchText] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isCompany = mode === 'company';
  const entityLabel = isCompany ? 'QB Customer' : 'QB Contact';

  const handleUnlink = async () => {
    if (!qbLinkedId || !isCompany) return;
    setUnlinking(true);
    try {
      const params = new URLSearchParams({ client_id: clientId, qb_record_id: qbLinkedId });
      await api.post(`/v1/quickbase/unmatch-company?${params}`);
      toast.success(`${entityLabel} unlinked`);
      onLinked?.();
    } catch {
      toast.error('Failed to unlink');
    }
    setUnlinking(false);
  };

  const handleSearch = (query: string) => {
    setSearchText(query);
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
            label: `${c.customer_name}${c.total_invoiced ? ` ($${Number(c.total_invoiced).toLocaleString('en-AU')})` : ''}`,
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
        const params = new URLSearchParams({ client_id: clientId, sb_company_id: entityId, qb_record_id: selectedQbId });
        await api.post(`/v1/quickbase/link-company?${params}`);
      } else {
        const params = new URLSearchParams({ client_id: clientId, sb_contact_id: entityId, qb_record_id: selectedQbId });
        await api.post(`/v1/quickbase/link-contact?${params}`);
      }
      toast.success(`${entityLabel} linked`);
      setEditing(false);
      setSelectedQbId(null);
      onLinked?.();
    } catch {
      toast.error('Failed to link');
    }
    setSaving(false);
  };

  if (!editing) {
    return (
      <div className="inline-flex items-center gap-2 flex-wrap">
        {qbLinkedId ? (
          <>
            <span title={`Matched via ${qbMatchMethod || 'unknown'}`}>
              <StatusBadge variant={methodVariant[qbMatchMethod || ''] || 'neutral'} size="sm">
                <Link2 className="h-3 w-3 mr-1 inline" />
                {qbDisplayName || qbLinkedId}
              </StatusBadge>
            </span>
            <button onClick={() => setEditing(true)} className="text-xs text-primary hover:underline">Change</button>
            {isCompany && (
              <button
                onClick={handleUnlink}
                disabled={unlinking}
                className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50 inline-flex items-center gap-0.5"
              >
                {unlinking ? <Spinner className="h-3 w-3 animate-spin" /> : <Unlink className="h-3 w-3" />}
                Unlink
              </button>
            )}
          </>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="inline-flex items-center gap-1.5 h-7 px-2.5 text-xs rounded-md border border-dashed border-slate-300 text-slate-500 hover:border-primary hover:text-primary transition-colors"
          >
            <Unlink className="h-3 w-3" /> Link to {entityLabel}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="inline-flex items-center gap-2">
      <div className="relative">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
        <input
          type="text"
          placeholder={`Search ${entityLabel.toLowerCase()}...`}
          value={searchText}
          onChange={e => handleSearch(e.target.value)}
          className="h-7 pl-7 pr-2 text-xs rounded border border-slate-200 bg-white w-64 focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
        {searching && <Spinner className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 animate-spin text-slate-400" />}
      </div>
      {options.length > 0 && (
        <select
          value={selectedQbId || ''}
          onChange={e => setSelectedQbId(e.target.value || null)}
          className="h-7 px-2 text-xs rounded border border-slate-200 bg-white max-w-[200px]"
        >
          <option value="">Select...</option>
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )}
      <button
        onClick={handleLink}
        disabled={!selectedQbId || saving}
        className="h-7 px-2.5 text-xs font-medium text-white bg-primary rounded hover:bg-primary-dark disabled:opacity-50 inline-flex items-center gap-1"
      >
        {saving ? <Spinner className="h-3 w-3 animate-spin" /> : <CheckCircle className="h-3 w-3" />}
        Link
      </button>
      <button onClick={() => { setEditing(false); setSelectedQbId(null); setSearchText(''); setOptions([]); }}
        className="h-7 px-2 text-xs text-slate-500 hover:text-slate-700">
        Cancel
      </button>
    </div>
  );
}
