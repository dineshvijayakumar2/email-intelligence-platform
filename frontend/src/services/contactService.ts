/**
 * Customer Contact Service - Stage 2 Business Hierarchy
 *
 * API client for customer contact CRUD operations.
 */

// @ts-ignore
import config from '../config.js';

export interface Contact {
  id: string;
  customer_company_id?: string;
  client_id?: string;
  email_address: string;
  full_name?: string;
  first_name?: string;
  last_name?: string;
  job_title?: string;
  company_name?: string;
  phone_number?: string;
  mobile_number?: string;
  linkedin_url?: string;
  notes?: string;
  first_contacted_at?: string;
  last_contacted_at?: string;
  total_emails_sent: number;
  total_emails_received: number;
  signature_data?: Record<string, any>;
  signature_last_updated?: string;
  created_at: string;
  updated_at: string;
}

export interface CompanyInfo {
  id: string;
  company_name: string;
  client_id: string;
  client_name?: string;
}

export interface ContactWithCompany extends Contact {
  company_info?: CompanyInfo;
}

export interface ContactSummary {
  id: string;
  email_address: string;
  full_name?: string;
  job_title?: string;
  company_name?: string;
  customer_company_id?: string;
  customer_company_name?: string;
  client_id?: string;
  last_contacted_at?: string;
  total_emails: number;
}

export interface ContactCreate {
  customer_company_id: string;
  client_id: string;
  email_address: string;
  full_name?: string;
  first_name?: string;
  last_name?: string;
  job_title?: string;
  company_name?: string;
  phone_number?: string;
  mobile_number?: string;
  linkedin_url?: string;
  notes?: string;
}

export interface ContactUpdate {
  full_name?: string;
  first_name?: string;
  last_name?: string;
  job_title?: string;
  company_name?: string;
  phone_number?: string;
  mobile_number?: string;
  linkedin_url?: string;
  notes?: string;
  customer_company_id?: string;
}

export interface ContactListResponse {
  contacts: ContactSummary[];
  total: number;
}

export interface SignatureData {
  raw_text?: string;
  full_name?: string;
  job_title?: string;
  company_name?: string;
  email?: string;
  phone?: string;
  mobile?: string;
  fax?: string;
  address?: string;
  website?: string;
  linkedin_url?: string;
  twitter_handle?: string;
  parsed_at?: string;
  confidence_score?: number;
}

export const contactService = {
  /**
   * Create a new contact
   */
  async create(data: ContactCreate): Promise<Contact> {
    const response = await fetch(`${config.apiBaseUrl}/contacts/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create contact');
    }

    return response.json();
  },

  /**
   * List contacts with optional filters
   */
  async list(
    clientId?: string,
    customerCompanyId?: string,
    search?: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<ContactListResponse> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });

    if (clientId) {
      params.append('client_id', clientId);
    }
    if (customerCompanyId) {
      params.append('customer_company_id', customerCompanyId);
    }
    if (search) {
      params.append('search', search);
    }

    const response = await fetch(`${config.apiBaseUrl}/contacts/?${params}`);

    if (!response.ok) {
      throw new Error('Failed to fetch contacts');
    }

    return response.json();
  },

  /**
   * Get a single contact with company information
   */
  async get(id: string): Promise<ContactWithCompany> {
    const response = await fetch(`${config.apiBaseUrl}/contacts/${id}`);

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Contact not found');
      }
      throw new Error('Failed to fetch contact');
    }

    return response.json();
  },

  /**
   * Find a contact by email address
   */
  async findByEmail(email: string): Promise<ContactWithCompany> {
    const params = new URLSearchParams({ email });
    const response = await fetch(`${config.apiBaseUrl}/contacts/by-email?${params}`);

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Contact not found');
      }
      throw new Error('Failed to find contact');
    }

    return response.json();
  },

  /**
   * Update a contact
   */
  async update(id: string, data: ContactUpdate): Promise<Contact> {
    const response = await fetch(`${config.apiBaseUrl}/contacts/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update contact');
    }

    return response.json();
  },

  /**
   * Delete a contact
   */
  async delete(id: string): Promise<void> {
    const response = await fetch(`${config.apiBaseUrl}/contacts/${id}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete contact');
    }
  },

  /**
   * Update contact signature data
   */
  async updateSignature(id: string, signatureData: SignatureData): Promise<Contact> {
    const response = await fetch(`${config.apiBaseUrl}/contacts/${id}/update-signature`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(signatureData),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update signature');
    }

    return response.json();
  },

  /**
   * Get display name for a contact
   */
  getDisplayName(contact: Contact | ContactSummary): string {
    if (contact.full_name) return contact.full_name;
    if ('first_name' in contact && contact.first_name) {
      return `${contact.first_name} ${('last_name' in contact && contact.last_name) || ''}`.trim();
    }
    return contact.email_address;
  },

  /**
   * Calculate total emails for a contact
   */
  getTotalEmails(contact: Contact): number {
    return (contact.total_emails_sent || 0) + (contact.total_emails_received || 0);
  },
};

export default contactService;
