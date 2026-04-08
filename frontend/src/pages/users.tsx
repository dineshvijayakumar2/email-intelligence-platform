/**
 * User Management Page — Zero antd.
 *
 * Admin-only page for managing users, roles, and client assignments.
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../services/apiClient';
import { clientService, ClientSummary } from '../services/clientService';
import { mailboxService, Mailbox } from '../services/mailboxService';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton, EmptyState } from '@/components/ui/empty-state';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Crown, Users, Briefcase, Pencil, Plus, Link2, Unlink,
  Search, RefreshCw, CheckCircle, Ban, Mail, Inbox, ShieldAlert,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';

interface MailboxSummary {
  id: string;
  name: string;
  email_address?: string;
  mailbox_type: string;
}

interface User {
  id: string;
  email: string;
  name: string;
  roles: Array<'admin' | 'client_manager' | 'account_manager'>;
  is_active: boolean;
  avatar_url?: string;
  created_at: string;
  updated_at: string;
  assigned_clients?: ClientSummary[];
  assigned_mailboxes?: MailboxSummary[];
}

// Role configuration
const roleConfig = {
  admin: {
    label: 'Admin',
    variant: 'warning' as const,
    icon: Crown,
    description: 'Full access to all mailboxes and settings',
  },
  client_manager: {
    label: 'Client Manager',
    variant: 'info' as const,
    icon: Users,
    description: 'Access to assigned client mailboxes',
  },
  account_manager: {
    label: 'Account Manager',
    variant: 'success' as const,
    icon: Briefcase,
    description: 'Access to own mailboxes only',
  },
};

const UsersPage: React.FC = () => {
  const { profile } = useAuth();
  const isAdmin = useMemo(() => profile?.roles?.includes('admin'), [profile?.roles]);

  const [users, setUsers] = useState<User[]>([]);
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [loading, setLoading] = useState(true);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [assignModalVisible, setAssignModalVisible] = useState(false);
  const [mailboxModalVisible, setMailboxModalVisible] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [searchText, setSearchText] = useState('');

  // Form state for Edit Roles modal
  const [formRoles, setFormRoles] = useState<string[]>([]);
  // Form state for Assign Clients modal
  const [formClientIds, setFormClientIds] = useState<string[]>([]);
  // Form state for Assign Mailboxes modal
  const [formMailboxIds, setFormMailboxIds] = useState<string[]>([]);

  useEffect(() => {
    loadUsers();
    loadClients();
    loadMailboxes();
  }, []);

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await api.get<User[]>('/auth/users', { timeout: 15000 });
      console.log('API Response:', data);
      console.log('First user:', data?.[0]);
      // Only update state if we got valid data (not null)
      if (data !== null) {
        setUsers(data || []);
      } else {
        console.warn('Received null from users API, keeping existing data');
      }
    } catch (error) {
      console.error('Failed to load users:', error);
      toast.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const loadClients = async () => {
    try {
      const response = await clientService.list();
      setClients(response.clients);
    } catch (error) {
      console.error('Failed to load clients:', error);
    }
  };

  const loadMailboxes = async () => {
    try {
      const data = await mailboxService.getMailboxes();
      setMailboxes(data);
    } catch (error) {
      console.error('Failed to load mailboxes:', error);
    }
  };

  const handleEditRole = (user: User) => {
    setSelectedUser(user);
    setFormRoles(user.roles || []);
    setEditModalVisible(true);
  };

  const handleManageAssignments = (user: User) => {
    setSelectedUser(user);
    setFormClientIds(user.assigned_clients?.map((c) => c.id) || []);
    setAssignModalVisible(true);
  };

  const handleUpdateRole = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;
    if (formRoles.length === 0) {
      toast.warning('Please select at least one role');
      return;
    }

    try {
      await api.patch(`/auth/users/${selectedUser.id}/roles`, { roles: formRoles });
      toast.success('User roles updated successfully');
      setEditModalVisible(false);
      setUsers(prev => prev.map(u =>
        u.id === selectedUser.id ? { ...u, roles: formRoles as User['roles'] } : u
      ));
    } catch (error: any) {
      toast.error(error.message || 'Failed to update user roles');
    }
  };

  const handleUpdateAssignments = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;

    try {
      await api.put(`/auth/users/${selectedUser.id}/client-assignments`, {
        client_ids: formClientIds,
      });

      const roleType = selectedUser.roles?.includes('client_manager') ? 'oversight' : 'operational';
      toast.success(`Client ${roleType} assignments updated successfully`);
      setAssignModalVisible(false);
      const newAssignedClients = clients.filter(c => formClientIds.includes(c.id));
      setUsers(prev => prev.map(u =>
        u.id === selectedUser.id ? { ...u, assigned_clients: newAssignedClients } : u
      ));
    } catch (error: any) {
      toast.error(error.message || 'Failed to update client assignments');
    }
  };

  const handleManageMailboxes = (user: User) => {
    setSelectedUser(user);
    setFormMailboxIds(user.assigned_mailboxes?.map((m) => m.id) || []);
    setMailboxModalVisible(true);
  };

  const handleUpdateMailboxAssignments = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;

    try {
      await api.put(`/auth/users/${selectedUser.id}/mailbox-assignments`, {
        mailbox_ids: formMailboxIds,
      });

      toast.success('Mailbox assignments updated successfully');
      setMailboxModalVisible(false);
      const newAssignedMailboxes: MailboxSummary[] = mailboxes
        .filter(m => formMailboxIds.includes(m.id))
        .map(m => ({ id: m.id, name: m.name, email_address: m.email_address, mailbox_type: m.mailbox_type }));
      setUsers(prev => prev.map(u =>
        u.id === selectedUser.id ? { ...u, assigned_mailboxes: newAssignedMailboxes } : u
      ));
    } catch (error: any) {
      toast.error(error.message || 'Failed to update mailbox assignments');
    }
  };

  const handleToggleActive = async (user: User) => {
    const action = user.is_active ? 'deactivate' : 'activate';
    if (!window.confirm(`Are you sure you want to ${action} ${user.name}?`)) return;

    try {
      await api.patch(`/auth/users/${user.id}/status`, { is_active: !user.is_active });
      toast.success(`User ${user.is_active ? 'deactivated' : 'activated'} successfully`);
      setUsers(prev => prev.map(u =>
        u.id === user.id ? { ...u, is_active: !user.is_active } : u
      ));
    } catch (error: any) {
      toast.error(error.message || 'Failed to update user status');
    }
  };

  // Filter users by search text
  const filteredUsers = users.filter(
    (user) =>
      user.name.toLowerCase().includes(searchText.toLowerCase()) ||
      user.email.toLowerCase().includes(searchText.toLowerCase())
  );

  // Multi-select toggle helper
  const toggleItem = (list: string[], item: string): string[] =>
    list.includes(item) ? list.filter(i => i !== item) : [...list, item];

  if (!isAdmin) {
    return (
      <PageShell>
        <div className="rounded-lg border bg-white shadow-sm">
          <EmptyState
            icon={<ShieldAlert className="h-10 w-10" />}
            title="Access Denied"
            description="You don't have permission to view this page"
          />
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="User Management"
        description="Manage user roles and client assignments"
        actions={
          <button
            onClick={loadUsers}
            disabled={loading}
            className="h-8 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            Refresh
          </button>
        }
      />

      {/* Search bar */}
      <div className="rounded-lg border bg-white shadow-sm p-3 mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search users..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="w-full max-w-[300px] h-9 pl-9 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
          {searchText && (
            <button
              onClick={() => setSearchText('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      {/* Users Table */}
      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        {loading && users.length === 0 ? (
          <ContentSkeleton rows={6} />
        ) : filteredUsers.length === 0 ? (
          <EmptyState
            icon={<Users className="h-10 w-10" />}
            title="No users found"
            description={searchText ? 'Try adjusting your search' : 'No users available'}
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-slate-50/50">
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">User</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Roles</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Assigned Clients</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Assigned Mailboxes</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Status</th>
                <th className="px-4 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {filteredUsers.map((record) => {
                const hasClientRole = record.roles?.includes('account_manager') || record.roles?.includes('client_manager');
                const clientCount = record.assigned_clients?.length || 0;
                const mailboxCount = record.assigned_mailboxes?.length || 0;

                return (
                  <tr key={record.id} className="hover:bg-slate-50/50">
                    {/* User column */}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        {record.avatar_url ? (
                          <img
                            src={record.avatar_url}
                            alt={record.name}
                            className="h-9 w-9 rounded-full object-cover"
                          />
                        ) : (
                          <div
                            className={cn(
                              'h-9 w-9 rounded-full flex items-center justify-center text-sm font-medium text-white',
                              record.is_active ? 'bg-primary' : 'bg-slate-300',
                            )}
                          >
                            {record.name?.charAt(0).toUpperCase() || 'U'}
                          </div>
                        )}
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-slate-900">{record.name}</span>
                            {!record.is_active && (
                              <StatusBadge variant="neutral" size="sm">Inactive</StatusBadge>
                            )}
                          </div>
                          <span className="text-xs text-slate-400">{record.email}</span>
                        </div>
                      </div>
                    </td>

                    {/* Roles column */}
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {record.roles?.map((role) => {
                          const config = roleConfig[role as keyof typeof roleConfig];
                          if (!config) return null;
                          const Icon = config.icon;
                          return (
                            <span key={role} title={config.description}>
                              <StatusBadge variant={config.variant} size="sm">
                                <Icon className="h-3 w-3 mr-1" />
                                {config.label}
                              </StatusBadge>
                            </span>
                          );
                        })}
                      </div>
                    </td>

                    {/* Assigned Clients column */}
                    <td className="px-4 py-2.5">
                      {!hasClientRole ? (
                        <span className="text-xs text-slate-400">-</span>
                      ) : clientCount === 0 ? (
                        <span className="text-xs text-slate-400">
                          No clients {record.roles?.includes('client_manager') ? 'manages' : 'assigned to'}
                        </span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {record.assigned_clients?.slice(0, 3).map((client) => (
                            <StatusBadge
                              key={client.id}
                              variant={record.roles?.includes('client_manager') ? 'info' : 'success'}
                              size="sm"
                            >
                              {client.client_name}
                            </StatusBadge>
                          ))}
                          {clientCount > 3 && (
                            <StatusBadge variant="neutral" size="sm">+{clientCount - 3} more</StatusBadge>
                          )}
                        </div>
                      )}
                    </td>

                    {/* Assigned Mailboxes column */}
                    <td className="px-4 py-2.5">
                      {mailboxCount === 0 ? (
                        <span className="text-xs text-slate-400">No mailboxes</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {record.assigned_mailboxes?.slice(0, 2).map((mailbox) => (
                            <StatusBadge key={mailbox.id} variant="purple" size="sm">
                              <Inbox className="h-3 w-3 mr-1" />
                              {mailbox.name}
                            </StatusBadge>
                          ))}
                          {mailboxCount > 2 && (
                            <StatusBadge variant="neutral" size="sm">+{mailboxCount - 2} more</StatusBadge>
                          )}
                        </div>
                      )}
                    </td>

                    {/* Status column */}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <span className={cn(
                          'h-2 w-2 rounded-full',
                          record.is_active ? 'bg-emerald-500' : 'bg-slate-300',
                        )} />
                        <span className={cn(
                          'text-xs',
                          record.is_active ? 'text-slate-700' : 'text-slate-400',
                        )}>
                          {record.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                    </td>

                    {/* Actions column */}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleEditRole(record)}
                          className="p-1.5 rounded hover:bg-slate-100"
                          title="Edit roles"
                        >
                          <Pencil className="h-3.5 w-3.5 text-slate-400" />
                        </button>
                        {(record.roles?.includes('client_manager') || record.roles?.includes('account_manager')) && (
                          <button
                            onClick={() => handleManageAssignments(record)}
                            className="p-1.5 rounded hover:bg-slate-100"
                            title={record.roles?.includes('client_manager') ? 'Manage client oversight' : 'Assign to clients'}
                          >
                            <Link2 className="h-3.5 w-3.5 text-slate-400" />
                          </button>
                        )}
                        <button
                          onClick={() => handleManageMailboxes(record)}
                          className="p-1.5 rounded hover:bg-slate-100"
                          title="Assign mailboxes"
                        >
                          <Mail className="h-3.5 w-3.5 text-slate-400" />
                        </button>
                        <button
                          onClick={() => handleToggleActive(record)}
                          className={cn(
                            'p-1.5 rounded',
                            record.is_active ? 'hover:bg-red-50' : 'hover:bg-emerald-50',
                          )}
                          title={record.is_active ? 'Deactivate' : 'Activate'}
                        >
                          {record.is_active ? (
                            <Ban className="h-3.5 w-3.5 text-slate-400 hover:text-destructive" />
                          ) : (
                            <CheckCircle className="h-3.5 w-3.5 text-slate-400 hover:text-emerald-600" />
                          )}
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

      <div className="mt-2 text-xs text-slate-400 px-1">
        {filteredUsers.length} of {users.length} users
      </div>

      {/* Edit Roles Dialog */}
      <Dialog open={editModalVisible} onOpenChange={setEditModalVisible}>
        <DialogContent className="sm:max-w-[460px]">
          <DialogHeader>
            <DialogTitle>Edit Roles &mdash; {selectedUser?.name}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleUpdateRole} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">User Roles</label>
              <p className="text-xs text-slate-400 mb-2">
                Users can have multiple roles. Example: Admin can also be Account Manager to monitor mailboxes.
              </p>
              <div className="space-y-2">
                {Object.entries(roleConfig).map(([value, config]) => {
                  const Icon = config.icon;
                  const isSelected = formRoles.includes(value);
                  return (
                    <label
                      key={value}
                      className={cn(
                        'flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors',
                        isSelected
                          ? 'border-primary bg-primary-subtle'
                          : 'border-slate-200 hover:bg-slate-50',
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => setFormRoles(prev => toggleItem(prev, value))}
                        className="sr-only"
                      />
                      <Icon className={cn('h-4 w-4', isSelected ? 'text-primary' : 'text-slate-400')} />
                      <div className="flex-1">
                        <span className={cn('text-sm font-medium', isSelected ? 'text-primary' : 'text-slate-700')}>
                          {config.label}
                        </span>
                        <p className="text-xs text-slate-400">{config.description}</p>
                      </div>
                      <div className={cn(
                        'h-4 w-4 rounded border flex items-center justify-center',
                        isSelected ? 'bg-primary border-primary' : 'border-slate-300',
                      )}>
                        {isSelected && (
                          <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
              {formRoles.length === 0 && (
                <p className="text-xs text-destructive mt-1">Please select at least one role</p>
              )}
            </div>
            <DialogFooter>
              <button
                type="button"
                onClick={() => setEditModalVisible(false)}
                className="h-9 px-4 text-sm rounded-md border border-slate-200 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={formRoles.length === 0}
                className="h-9 px-4 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark disabled:opacity-50"
              >
                Update Roles
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Assign Clients Dialog */}
      <Dialog open={assignModalVisible} onOpenChange={setAssignModalVisible}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Manage Client Assignments &mdash; {selectedUser?.name}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleUpdateAssignments} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">Assigned Clients</label>
              <p className="text-xs text-slate-400 mb-2">
                This user will have access to mailboxes belonging to these clients
              </p>
              <div className="max-h-[280px] overflow-y-auto border border-slate-200 rounded-lg divide-y divide-slate-100">
                {clients.length === 0 ? (
                  <div className="p-4 text-center text-xs text-slate-400">No clients available</div>
                ) : (
                  clients.map((client) => {
                    const isSelected = formClientIds.includes(client.id);
                    return (
                      <label
                        key={client.id}
                        className={cn(
                          'flex items-center gap-3 px-3 py-2.5 cursor-pointer transition-colors',
                          isSelected ? 'bg-primary-subtle' : 'hover:bg-slate-50',
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => setFormClientIds(prev => toggleItem(prev, client.id))}
                          className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary/20"
                        />
                        <Users className="h-4 w-4 text-slate-400 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <span className="text-sm text-slate-700">{client.client_name}</span>
                          {client.client_label && (
                            <span className="text-xs text-slate-400 ml-1.5">({client.client_label})</span>
                          )}
                        </div>
                      </label>
                    );
                  })
                )}
              </div>
              {formClientIds.length > 0 && (
                <p className="text-xs text-slate-500 mt-1.5">{formClientIds.length} client(s) selected</p>
              )}
            </div>
            <DialogFooter>
              <button
                type="button"
                onClick={() => setAssignModalVisible(false)}
                className="h-9 px-4 text-sm rounded-md border border-slate-200 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="h-9 px-4 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark"
              >
                Update Assignments
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Assign Mailboxes Dialog */}
      <Dialog open={mailboxModalVisible} onOpenChange={setMailboxModalVisible}>
        <DialogContent className="sm:max-w-[560px]">
          <DialogHeader>
            <DialogTitle>Manage Mailbox Assignments &mdash; {selectedUser?.name}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleUpdateMailboxAssignments} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-700 block mb-1">Assigned Mailboxes</label>
              <p className="text-xs text-slate-400 mb-2">
                Directly assign specific mailboxes to this user. This gives them access regardless of client assignments.
              </p>
              <div className="max-h-[300px] overflow-y-auto border border-slate-200 rounded-lg divide-y divide-slate-100">
                {mailboxes.length === 0 ? (
                  <div className="p-4 text-center text-xs text-slate-400">No mailboxes available</div>
                ) : (
                  mailboxes.map((mailbox) => {
                    const isSelected = formMailboxIds.includes(mailbox.id);
                    return (
                      <label
                        key={mailbox.id}
                        className={cn(
                          'flex items-center gap-3 px-3 py-2.5 cursor-pointer transition-colors',
                          isSelected ? 'bg-primary-subtle' : 'hover:bg-slate-50',
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => setFormMailboxIds(prev => toggleItem(prev, mailbox.id))}
                          className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary/20"
                        />
                        <Inbox className="h-4 w-4 text-slate-400 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <span className="text-sm text-slate-700">{mailbox.name}</span>
                          {mailbox.email_address && (
                            <span className="text-xs text-slate-400 ml-1.5">({mailbox.email_address})</span>
                          )}
                        </div>
                        <span className="text-[10px] uppercase tracking-wide font-medium text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded flex-shrink-0">
                          {mailbox.mailbox_type}
                        </span>
                      </label>
                    );
                  })
                )}
              </div>
              {formMailboxIds.length > 0 && (
                <p className="text-xs text-slate-500 mt-1.5">{formMailboxIds.length} mailbox(es) selected</p>
              )}
            </div>
            <DialogFooter>
              <button
                type="button"
                onClick={() => setMailboxModalVisible(false)}
                className="h-9 px-4 text-sm rounded-md border border-slate-200 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="h-9 px-4 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark"
              >
                Update Mailbox Assignments
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
};

export default UsersPage;
