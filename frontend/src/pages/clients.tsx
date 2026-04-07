/**
 * Clients Page — Manage consulting clients. Zero antd.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  clientService, ClientSummary, ClientCreate, ClientUpdate, ClientStatus, InternalDomain,
} from '../services/clientService';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { KPICard, KPIStrip } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton, EmptyState } from '@/components/ui/empty-state';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Plus, Pencil, Trash2, RefreshCw, Building2, Globe, Users, X,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';

const ClientsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingClient, setEditingClient] = useState<ClientSummary | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Form state
  const [formName, setFormName] = useState('');
  const [formLabel, setFormLabel] = useState('');
  const [formStatus, setFormStatus] = useState('active');
  const [formIndustry, setFormIndustry] = useState('');
  const [formNotes, setFormNotes] = useState('');
  const [saving, setSaving] = useState(false);

  // Internal domains
  const [internalDomains, setInternalDomains] = useState<InternalDomain[]>([]);
  const [newDomain, setNewDomain] = useState('');

  const loadClients = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await clientService.list(undefined, statusFilter as ClientStatus || undefined);
      setClients(resp.clients); setTotal(resp.total);
    } catch { toast.error('Failed to load clients'); }
    finally { setLoading(false); }
  }, [statusFilter]);

  useEffect(() => { loadClients(); }, [loadClients]);

  const openCreate = () => {
    setEditingClient(null);
    setFormName(''); setFormLabel(''); setFormStatus('active'); setFormIndustry(''); setFormNotes('');
    setInternalDomains([]);
    setModalOpen(true);
  };

  const openEdit = (client: ClientSummary) => {
    setEditingClient(client);
    setFormName(client.client_name); setFormLabel(client.client_label || '');
    setFormStatus(client.status); setFormIndustry(''); setFormNotes('');
    setModalOpen(true);
    clientService.listInternalDomains(client.id).then(r => setInternalDomains(r.domains)).catch(() => setInternalDomains([]));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim()) { toast.warning('Client name required'); return; }
    setSaving(true);
    try {
      const payload = { client_name: formName, client_label: formLabel, status: formStatus, industry: formIndustry, notes: formNotes };
      if (editingClient) {
        await clientService.update(editingClient.id, payload as ClientUpdate);
        toast.success('Client updated');
      } else {
        await clientService.create(payload as ClientCreate);
        toast.success('Client created');
      }
      setModalOpen(false); loadClients();
    } catch (err: any) { toast.error(err.message || 'Failed to save'); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this client? This will also delete all customer companies, contacts, and rules.')) return;
    try { await clientService.delete(id); toast.success('Client deleted'); loadClients(); }
    catch (err: any) { toast.error(err.message || 'Failed to delete'); }
  };

  const handleAddDomain = async () => {
    if (!editingClient || !newDomain.trim()) return;
    try {
      await clientService.addInternalDomain(editingClient.id, newDomain.trim());
      setNewDomain('');
      const r = await clientService.listInternalDomains(editingClient.id);
      setInternalDomains(r.domains);
      toast.success(`Domain "${newDomain.trim()}" added`);
    } catch (err: any) { toast.error(err.message || 'Failed to add domain'); }
  };

  const handleRemoveDomain = async (domainId: string) => {
    if (!editingClient) return;
    try {
      await clientService.removeInternalDomain(editingClient.id, domainId);
      const r = await clientService.listInternalDomains(editingClient.id);
      setInternalDomains(r.domains);
    } catch { toast.error('Failed to remove domain'); }
  };

  const activeClients = clients.filter(c => c.status === 'active').length;
  const totalCompanies = clients.reduce((sum, c) => sum + c.customer_company_count, 0);
  const totalContacts = clients.reduce((sum, c) => sum + c.contact_count, 0);

  return (
    <PageShell>
      <PageHeader title="Clients" description="Manage consulting clients and customer companies"
        actions={
          <div className="flex items-center gap-2">
            <button onClick={loadClients} disabled={loading}
              className="h-8 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5">
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />Refresh
            </button>
            <button onClick={openCreate}
              className="h-8 px-3 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark inline-flex items-center gap-1.5">
              <Plus className="h-3.5 w-3.5" />Add Client
            </button>
          </div>
        }
      />

      <KPIStrip className="mb-4">
        <KPICard title="Total Clients" value={total} loading={loading} />
        <KPICard title="Active" value={activeClients} loading={loading} />
        <KPICard title="Companies" value={totalCompanies} loading={loading} />
        <KPICard title="Contacts" value={totalContacts} loading={loading} />
      </KPIStrip>

      {/* Filter */}
      <div className="flex items-center gap-2 mb-4">
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
          <option value="prospect">Prospect</option>
        </select>
      </div>

      {/* Table */}
      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        {loading && clients.length === 0 ? <ContentSkeleton rows={5} /> : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-slate-50/50">
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Client</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Status</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Account Managers</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Companies</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Contacts</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Emails</th>
                <th className="px-4 py-2.5 w-20"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {clients.map(client => {
                const statusVariant = client.status === 'active' ? 'success' : client.status === 'inactive' ? 'neutral' : 'info';
                return (
                  <tr key={client.id} className="hover:bg-slate-50/50">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <Building2 className="h-4 w-4 text-slate-400" />
                        <span className="font-medium text-slate-900">{client.client_name}</span>
                        {client.client_label && <span className="text-xs text-slate-400">{client.client_label}</span>}
                      </div>
                    </td>
                    <td className="px-4 py-2.5"><StatusBadge variant={statusVariant as any} size="sm">{clientService.getStatusLabel(client.status)}</StatusBadge></td>
                    <td className="px-4 py-2.5">
                      {client.account_managers?.length ? (
                        <div className="flex gap-1 flex-wrap">
                          {client.account_managers.map(am => (
                            <span key={am.id} className="inline-flex items-center gap-1 px-1.5 py-0 text-[11px] rounded bg-slate-100 text-slate-600" title={am.email}>
                              <Users className="h-3 w-3" />{am.name}
                            </span>
                          ))}
                        </div>
                      ) : <span className="text-xs text-slate-400">None assigned</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{client.customer_company_count}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{client.contact_count}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{client.total_emails.toLocaleString()}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1">
                        <button onClick={() => openEdit(client)} className="p-1 rounded hover:bg-slate-100" title="Edit">
                          <Pencil className="h-3.5 w-3.5 text-slate-400" />
                        </button>
                        <button onClick={() => handleDelete(client.id)} className="p-1 rounded hover:bg-red-50" title="Delete">
                          <Trash2 className="h-3.5 w-3.5 text-slate-400 hover:text-destructive" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Create/Edit Dialog */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle>{editingClient ? 'Edit Client' : 'Add Client'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">Client Name *</label>
              <input value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g., ABC Corporation" required
                className="w-full h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-slate-700 block mb-1">Short Label</label>
                <input value={formLabel} onChange={e => setFormLabel(e.target.value)} placeholder="e.g., ABC" maxLength={20}
                  className="w-full h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700 block mb-1">Status</label>
                <select value={formStatus} onChange={e => setFormStatus(e.target.value)}
                  className="w-full h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="prospect">Prospect</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">Industry</label>
              <input value={formIndustry} onChange={e => setFormIndustry(e.target.value)} placeholder="e.g., Manufacturing"
                className="w-full h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20" />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">Notes</label>
              <textarea value={formNotes} onChange={e => setFormNotes(e.target.value)} rows={2} placeholder="Additional notes..."
                className="w-full px-3 py-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20" />
            </div>

            {/* Internal Domains — edit mode only */}
            {editingClient && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Globe className="h-3.5 w-3.5 text-slate-500" />
                  <label className="text-sm font-medium text-slate-700">Internal Domains</label>
                </div>
                <p className="text-xs text-slate-400 mb-2">Email domains owned by this client (excluded from customer extraction)</p>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {internalDomains.map(d => (
                    <span key={d.id} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-warning-subtle text-warning">
                      {d.domain}
                      <button onClick={() => handleRemoveDomain(d.id)} className="hover:text-destructive"><X className="h-3 w-3" /></button>
                    </span>
                  ))}
                  {internalDomains.length === 0 && <span className="text-xs text-slate-400">No internal domains</span>}
                </div>
                <div className="flex gap-2">
                  <input value={newDomain} onChange={e => setNewDomain(e.target.value)} onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAddDomain())}
                    placeholder="e.g., carbon8.com.au"
                    className="flex-1 h-8 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20" />
                  <button type="button" onClick={handleAddDomain} disabled={!newDomain.trim()}
                    className="h-8 px-3 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark disabled:opacity-50">Add</button>
                </div>
              </div>
            )}

            <DialogFooter>
              <button type="button" onClick={() => setModalOpen(false)}
                className="h-9 px-4 text-sm rounded-md border border-slate-200 hover:bg-slate-50">Cancel</button>
              <button type="submit" disabled={saving}
                className="h-9 px-4 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark disabled:opacity-50 inline-flex items-center gap-2">
                {saving && <Spinner className="h-3.5 w-3.5 animate-spin" />}
                {editingClient ? 'Update' : 'Create'}
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
};

export default ClientsPage;
