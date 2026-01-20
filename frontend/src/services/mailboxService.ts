import api from './apiClient';

export interface Mailbox {
  id: string;
  name: string;
  email_address?: string;
  mailbox_type: 'mbox' | 'pst' | 'olm';
  is_active: boolean;
  total_emails: number;
  last_sync_at: string | null;
  created_at: string;
  connection_config?: Record<string, any>;
}

export interface CreateMailboxData {
  name: string;
  email_address?: string;
  mailbox_type: 'mbox' | 'pst' | 'olm';
  is_active: boolean;
  connection_config?: Record<string, any>;
  // File path for file-based mailboxes (MBOX/PST/OLM)
  file_path?: string;
}

export interface CreateGoogleDriveMailboxData extends Omit<CreateMailboxData, 'file_path'> {
  // Google Drive specific fields
  google_drive_file_id: string;
  google_drive_file_name: string;
  user_id: string; // Required for OAuth2 token lookup
}

export const mailboxService = {
  // Get all mailboxes
  async getMailboxes(): Promise<Mailbox[]> {
    const mailboxes = await api.get<Mailbox[]>('/mailboxes');
    return mailboxes || [];
  },

  // Get a single mailbox by ID
  async getMailbox(id: string): Promise<Mailbox | null> {
    return await api.get<Mailbox>(`/mailboxes/${id}`);
  },

  // Create a new mailbox
  async createMailbox(mailboxData: CreateMailboxData): Promise<Mailbox> {
    const mailbox = await api.post<Mailbox>('/mailboxes', mailboxData);
    if (!mailbox) {
      throw new Error('Failed to create mailbox');
    }
    return mailbox;
  },

  // Create a Google Drive mailbox with OAuth2 support
  async createGoogleDriveMailbox(mailboxData: CreateGoogleDriveMailboxData): Promise<Mailbox> {
    // Build connection config for Google Drive mailbox
    const connectionConfig = {
      file_source: 'google_drive',
      google_drive_file_id: mailboxData.google_drive_file_id,
      google_drive_file_name: mailboxData.google_drive_file_name,
      user_id: mailboxData.user_id // Include user_id for backend token lookup
    };

    // Create mailbox data
    const createData: CreateMailboxData = {
      name: mailboxData.name,
      email_address: mailboxData.email_address,
      mailbox_type: mailboxData.mailbox_type,
      is_active: mailboxData.is_active,
      connection_config: connectionConfig
    };

    return await this.createMailbox(createData);
  },

  // Update an existing mailbox
  async updateMailbox(id: string, updates: Partial<CreateMailboxData>): Promise<Mailbox> {
    const mailbox = await api.put<Mailbox>(`/mailboxes/${id}`, updates);
    if (!mailbox) {
      throw new Error('Failed to update mailbox');
    }
    return mailbox;
  },

  // Delete a mailbox
  async deleteMailbox(id: string): Promise<void> {
    await api.delete(`/mailboxes/${id}`);
  },

  // Trigger sync for a mailbox
  async syncMailbox(id: string): Promise<void> {
    await api.post(`/mailboxes/${id}/sync`);
  }
};
