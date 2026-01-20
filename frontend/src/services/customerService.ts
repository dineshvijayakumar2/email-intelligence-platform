/**
 * Customer Company Service - Stage 2 Business Hierarchy
 *
 * API client for customer company CRUD operations.
 */

// @ts-ignore
import config from '../config.js';

export type EngagementStatus = 'active' | 'quiet' | 'at_risk' | 'unknown';

export interface CustomerCompany {
  id: string;
  client_id: string;
  company_name: string;
  email_domains: string[];
  industry?: string;
  website?: string;
  notes?: string;
  first_contact_date?: string;
  last_contact_date?: string;
  total_emails: number;
  total_inbound: number;
  total_outbound: number;
  created_at: string;
  updated_at: string;
}

export interface ContactSummary {
  id: string;
  email_address: string;
  full_name?: string;
  job_title?: string;
  total_emails_sent: number;
  total_emails_received: number;
  last_contacted_at?: string;
}

export interface CustomerCompanyWithContacts extends CustomerCompany {
  contacts: ContactSummary[];
  contact_count: number;
}

export interface CustomerCompanySummary {
  id: string;
  company_name: string;
  client_id: string;
  client_name?: string;
  email_domains: string[];
  industry?: string;
  first_contact_date?: string;
  last_contact_date?: string;
  total_emails: number;
  contact_count: number;
  engagement_status?: EngagementStatus;
}

export interface CustomerCompanyCreate {
  client_id: string;
  company_name: string;
  email_domains?: string[];
  industry?: string;
  website?: string;
  notes?: string;
}

export interface CustomerCompanyUpdate {
  company_name?: string;
  email_domains?: string[];
  industry?: string;
  website?: string;
  notes?: string;
}

export interface CustomerCompanyListResponse {
  customer_companies: CustomerCompanySummary[];
  total: number;
}

export const customerService = {
  /**
   * Create a new customer company
   */
  async create(data: CustomerCompanyCreate): Promise<CustomerCompany> {
    const response = await fetch(`${config.apiBaseUrl}/customers/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create customer company');
    }

    return response.json();
  },

  /**
   * List customer companies with optional filters
   */
  async list(
    clientId?: string,
    engagementStatus?: EngagementStatus,
    search?: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<CustomerCompanyListResponse> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });

    if (clientId) {
      params.append('client_id', clientId);
    }
    if (engagementStatus) {
      params.append('engagement_status', engagementStatus);
    }
    if (search) {
      params.append('search', search);
    }

    const response = await fetch(`${config.apiBaseUrl}/customers/?${params}`);

    if (!response.ok) {
      throw new Error('Failed to fetch customer companies');
    }

    return response.json();
  },

  /**
   * Get a single customer company with contacts
   */
  async get(id: string): Promise<CustomerCompanyWithContacts> {
    const response = await fetch(`${config.apiBaseUrl}/customers/${id}`);

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Customer company not found');
      }
      throw new Error('Failed to fetch customer company');
    }

    return response.json();
  },

  /**
   * Update a customer company
   */
  async update(id: string, data: CustomerCompanyUpdate): Promise<CustomerCompany> {
    const response = await fetch(`${config.apiBaseUrl}/customers/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update customer company');
    }

    return response.json();
  },

  /**
   * Delete a customer company
   */
  async delete(id: string): Promise<void> {
    const response = await fetch(`${config.apiBaseUrl}/customers/${id}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete customer company');
    }
  },

  /**
   * Add an email domain to a customer company
   */
  async addDomain(companyId: string, domain: string): Promise<{ company_id: string; email_domains: string[] }> {
    const params = new URLSearchParams({ domain });
    const response = await fetch(`${config.apiBaseUrl}/customers/${companyId}/add-domain?${params}`, {
      method: 'POST',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to add domain');
    }

    return response.json();
  },

  /**
   * Remove an email domain from a customer company
   */
  async removeDomain(companyId: string, domain: string): Promise<{ company_id: string; email_domains: string[] }> {
    const params = new URLSearchParams({ domain });
    const response = await fetch(`${config.apiBaseUrl}/customers/${companyId}/remove-domain?${params}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to remove domain');
    }

    return response.json();
  },

  /**
   * Refresh engagement metrics for a customer company
   */
  async refreshEngagement(companyId: string): Promise<{ company_id: string; metrics: any }> {
    const response = await fetch(`${config.apiBaseUrl}/customers/${companyId}/refresh-engagement`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error('Failed to refresh engagement metrics');
    }

    return response.json();
  },

  /**
   * Get engagement status display label
   */
  getEngagementLabel(status?: EngagementStatus): string {
    if (!status) return 'Unknown';
    const labels: Record<EngagementStatus, string> = {
      active: 'Active',
      quiet: 'Quiet',
      at_risk: 'At Risk',
      unknown: 'Unknown',
    };
    return labels[status] || status;
  },

  /**
   * Get engagement status color for tags
   */
  getEngagementColor(status?: EngagementStatus): string {
    if (!status) return 'default';
    const colors: Record<EngagementStatus, string> = {
      active: 'green',
      quiet: 'orange',
      at_risk: 'red',
      unknown: 'default',
    };
    return colors[status] || 'default';
  },
};

export default customerService;
