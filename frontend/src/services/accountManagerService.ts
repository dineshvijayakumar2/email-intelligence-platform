/**
 * Account Manager Service - Stage 2 Business Hierarchy
 *
 * API client for account manager CRUD operations.
 */

// @ts-ignore
import config from '../config.js';

export type AccountManagerRole = 'admin' | 'account_manager' | 'viewer';

export interface AccountManager {
  id: string;
  name: string;
  email: string;
  role: AccountManagerRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AccountManagerWithStats extends AccountManager {
  total_clients: number;
  total_mailboxes: number;
  active_clients: number;
}

export interface AccountManagerCreate {
  name: string;
  email: string;
  role?: AccountManagerRole;
  password?: string;
}

export interface AccountManagerUpdate {
  name?: string;
  email?: string;
  role?: AccountManagerRole;
  is_active?: boolean;
}

export interface AccountManagerListResponse {
  account_managers: AccountManager[];
  total: number;
}

export const accountManagerService = {
  /**
   * Create a new account manager
   */
  async create(data: AccountManagerCreate): Promise<AccountManager> {
    const response = await fetch(`${config.apiBaseUrl}/account-managers/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create account manager');
    }

    return response.json();
  },

  /**
   * List all account managers
   */
  async list(activeOnly: boolean = true, limit: number = 100, offset: number = 0): Promise<AccountManagerListResponse> {
    const params = new URLSearchParams({
      active_only: String(activeOnly),
      limit: String(limit),
      offset: String(offset),
    });

    const response = await fetch(`${config.apiBaseUrl}/account-managers/?${params}`);

    if (!response.ok) {
      throw new Error('Failed to fetch account managers');
    }

    return response.json();
  },

  /**
   * Get a single account manager with statistics
   */
  async get(id: string): Promise<AccountManagerWithStats> {
    const response = await fetch(`${config.apiBaseUrl}/account-managers/${id}`);

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Account manager not found');
      }
      throw new Error('Failed to fetch account manager');
    }

    return response.json();
  },

  /**
   * Update an account manager
   */
  async update(id: string, data: AccountManagerUpdate): Promise<AccountManager> {
    const response = await fetch(`${config.apiBaseUrl}/account-managers/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update account manager');
    }

    return response.json();
  },

  /**
   * Delete an account manager
   */
  async delete(id: string): Promise<void> {
    const response = await fetch(`${config.apiBaseUrl}/account-managers/${id}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete account manager');
    }
  },

  /**
   * Get role display label
   */
  getRoleLabel(role: AccountManagerRole): string {
    const labels: Record<AccountManagerRole, string> = {
      admin: 'Admin',
      account_manager: 'Account Manager',
      viewer: 'Viewer',
    };
    return labels[role] || role;
  },

  /**
   * Get role color for tags
   */
  getRoleColor(role: AccountManagerRole): string {
    const colors: Record<AccountManagerRole, string> = {
      admin: 'red',
      account_manager: 'blue',
      viewer: 'green',
    };
    return colors[role] || 'default';
  },
};

export default accountManagerService;
