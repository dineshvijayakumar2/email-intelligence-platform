import api from './apiClient';

export interface Mailbox {
  id: string;
  name: string;
  email_address?: string;
  mailbox_type: 'mbox' | 'pst' | 'olm' | 'gmail' | 'outlook_live';
  is_active: boolean;
  total_emails: number;
  last_sync_at: string | null;
  created_at: string;
  client_id?: string | null;  // Stage 2: Assignment to client
  user_id?: string | null;     // Stage 2: Assignment to account manager
  connection_config?: {
    file_path?: string;
    file_source?: 'local' | 'google_drive';
    google_drive_file_id?: string;
    google_drive_file_name?: string;
    user_id?: string;
    // Gmail LIVE sync fields
    gmail_user_id?: string;
    gmail_sync_enabled?: boolean;
    gmail_email?: string;
    gmail_extended_at?: string;
    original_type?: string;
    initial_history_id?: string;
  };
  sync_enabled?: boolean;
}

export interface CreateMailboxData {
  name: string;
  email_address?: string;
  mailbox_type: 'mbox' | 'pst' | 'olm' | 'gmail' | 'outlook_live';
  is_active: boolean;
  connection_config?: Record<string, any>;
  // File path for file-based mailboxes (MBOX/PST/OLM)
  file_path?: string;
}

// Helper to check if mailbox has Gmail LIVE sync enabled
export const hasGmailLiveSync = (mailbox: Mailbox): boolean => {
  return !!(mailbox.connection_config?.gmail_sync_enabled);
};

// Helper to get mailbox source type label
export const getMailboxSourceLabel = (mailbox: Mailbox): { type: string; live: boolean } => {
  const isLive = hasGmailLiveSync(mailbox);
  const originalType = mailbox.connection_config?.original_type || mailbox.mailbox_type;
  return {
    type: originalType.toUpperCase(),
    live: isLive
  };
};

export interface CreateGoogleDriveMailboxData extends Omit<CreateMailboxData, 'file_path'> {
  // Google Drive specific fields
  google_drive_file_id: string;
  google_drive_file_name: string;
  user_id: string; // Required for OAuth2 token lookup
}

export const mailboxService = {
  // Get all mailboxes
  async getMailboxes(): Promise<Mailbox[]> {
    console.log('[MailboxService] Fetching mailboxes from /mailboxes...');
    try {
      const mailboxes = await api.get<Mailbox[]>('/mailboxes');
      console.log('[MailboxService] API response:', mailboxes);
      console.log('[MailboxService] Response type:', typeof mailboxes);
      console.log('[MailboxService] Is array:', Array.isArray(mailboxes));

      if (!mailboxes) {
        console.warn('[MailboxService] API returned null/undefined, returning empty array');
        return [];
      }

      console.log('[MailboxService] Returning', mailboxes.length, 'mailboxes');
      return mailboxes;
    } catch (error) {
      console.error('[MailboxService] Error fetching mailboxes:', error);
      return [];
    }
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
