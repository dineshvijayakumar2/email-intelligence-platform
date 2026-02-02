/**
 * Client Service - Stage 2 Business Hierarchy
 *
 * API client for client CRUD operations.
 */

// @ts-ignore
import config from '../config.js';

export type ClientStatus = 'active' | 'inactive' | 'prospect';

export interface AccountManagerSummary {
  id: string;
  name: string;
  email: string;
}

export interface Client {
  id: string;
  client_name: string;
  client_label?: string;
  industry?: string;
  status: ClientStatus;
  uses_quickbase: boolean;
  uses_printiq: boolean;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface ClientWithStats extends Client {
  account_managers: AccountManagerSummary[];
  total_customer_companies: number;
  total_customer_contacts: number;
  total_mailboxes: number;
  total_emails: number;
  total_rules: number;
}

export interface ClientSummary {
  id: string;
  client_name: string;
  client_label?: string;
  status: ClientStatus;
  account_managers: AccountManagerSummary[];
  customer_company_count: number;
  contact_count: number;
  mailbox_count: number;
  total_emails: number;
}

export interface ClientCreate {
  client_name: string;
  client_label?: string;
  industry?: string;
  status?: ClientStatus;
  notes?: string;
  uses_quickbase?: boolean;
  quickbase_realm?: string;
  quickbase_api_token?: string;
  uses_printiq?: boolean;
  printiq_api_url?: string;
  printiq_api_key?: string;
}

export interface ClientUpdate {
  client_name?: string;
  client_label?: string;
  industry?: string;
  status?: ClientStatus;
  notes?: string;
  uses_quickbase?: boolean;
  quickbase_realm?: string;
  quickbase_api_token?: string;
  uses_printiq?: boolean;
  printiq_api_url?: string;
  printiq_api_key?: string;
}

export interface ClientListResponse {
  clients: ClientSummary[];
  total: number;
}

export const clientService = {
  /**
   * Create a new client
   */
  async create(data: ClientCreate): Promise<Client> {
    const response = await fetch(`${config.apiBaseUrl}/clients/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create client');
    }

    return response.json();
  },

  /**
   * List all clients with optional filters
   */
  async list(
    accountManagerId?: string,
    status?: ClientStatus,
    limit: number = 100,
    offset: number = 0
  ): Promise<ClientListResponse> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });

    if (accountManagerId) {
      params.append('account_manager_id', accountManagerId);
    }
    if (status) {
      params.append('status', status);
    }

    const response = await fetch(`${config.apiBaseUrl}/clients/?${params}`);

    if (!response.ok) {
      throw new Error('Failed to fetch clients');
    }

    return response.json();
  },

  /**
   * Get a single client with statistics
   */
  async get(id: string): Promise<ClientWithStats> {
    const response = await fetch(`${config.apiBaseUrl}/clients/${id}`);

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Client not found');
      }
      throw new Error('Failed to fetch client');
    }

    return response.json();
  },

  /**
   * Update a client
   */
  async update(id: string, data: ClientUpdate): Promise<Client> {
    const response = await fetch(`${config.apiBaseUrl}/clients/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update client');
    }

    return response.json();
  },

  /**
   * Delete a client
   */
  async delete(id: string): Promise<void> {
    const response = await fetch(`${config.apiBaseUrl}/clients/${id}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete client');
    }
  },

  /**
   * Get client summary using database function
   */
  async getSummary(id: string): Promise<any> {
    const response = await fetch(`${config.apiBaseUrl}/clients/${id}/summary`);

    if (!response.ok) {
      throw new Error('Failed to fetch client summary');
    }

    return response.json();
  },

  /**
   * Get status display label
   */
  getStatusLabel(status: ClientStatus): string {
    const labels: Record<ClientStatus, string> = {
      active: 'Active',
      inactive: 'Inactive',
      prospect: 'Prospect',
    };
    return labels[status] || status;
  },

  /**
   * Get status color for tags
   */
  getStatusColor(status: ClientStatus): string {
    const colors: Record<ClientStatus, string> = {
      active: 'green',
      inactive: 'default',
      prospect: 'blue',
    };
    return colors[status] || 'default';
  },
};

export default clientService;
