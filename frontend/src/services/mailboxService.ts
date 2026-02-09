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
  // RBAC: Assignment fields
  client_id?: string | null;
  user_id?: string | null;
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
  assigned_user_id?: string | null; // For RBAC mailbox assignment
}

export const mailboxService = {
  // Get all mailboxes (with retry for auth race condition)
  async getMailboxes(): Promise<Mailbox[]> {
    const maxRetries = 2;
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const mailboxes = await api.get<Mailbox[]>('/mailboxes');

        if (!mailboxes) {
          // Null response might mean auth wasn't ready - retry after short delay
          if (attempt < maxRetries) {
            console.debug(`[MailboxService] Got null response, retrying (attempt ${attempt + 1}/${maxRetries + 1})...`);
            await new Promise(resolve => setTimeout(resolve, 500));
            continue;
          }
          console.warn('[MailboxService] API returned null after retries, returning empty array');
          return [];
        }

        return mailboxes;
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        if (attempt < maxRetries) {
          console.debug(`[MailboxService] Error, retrying (attempt ${attempt + 1}/${maxRetries + 1})...`);
          await new Promise(resolve => setTimeout(resolve, 500));
          continue;
        }
      }
    }

    console.error('[MailboxService] Error fetching mailboxes after retries:', lastError);
    return [];
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

    // Create mailbox data with RBAC user assignment
    const createData: any = {
      name: mailboxData.name,
      email_address: mailboxData.email_address,
      mailbox_type: mailboxData.mailbox_type,
      is_active: mailboxData.is_active,
      connection_config: connectionConfig,
      user_id: mailboxData.assigned_user_id || null // RBAC: assign mailbox to user
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
