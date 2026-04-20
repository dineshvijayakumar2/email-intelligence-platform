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
    gmail_sync_status?: string;
    gmail_sync_error?: string;
    gmail_last_sync_at?: string;
    gmail_email_count?: number;
    original_type?: string;
    initial_history_id?: string;
    sync_interval_minutes?: number;
    // Outlook LIVE sync fields
    outlook_user_id?: string;
    outlook_sync_enabled?: boolean;
    outlook_email?: string;
    outlook_extended_at?: string;
    outlook_sync_status?: string;
    outlook_sync_error?: string;
    outlook_last_sync_at?: string;
    outlook_email_count?: number;
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

// Helper to check if mailbox has Outlook LIVE sync enabled
export const hasOutlookLiveSync = (mailbox: Mailbox): boolean => {
  return !!(mailbox.connection_config?.outlook_sync_enabled);
};

// Helper to check if mailbox has any LIVE sync enabled (Gmail or Outlook)
export const hasLiveSync = (mailbox: Mailbox): boolean => {
  return hasGmailLiveSync(mailbox) || hasOutlookLiveSync(mailbox);
};

// Helper to get the LIVE sync type ('gmail', 'outlook', or null)
export const getLiveSyncType = (mailbox: Mailbox): 'gmail' | 'outlook' | null => {
  if (hasGmailLiveSync(mailbox)) return 'gmail';
  if (hasOutlookLiveSync(mailbox)) return 'outlook';
  // Check mailbox type for pure LIVE mailboxes
  if (mailbox.mailbox_type === 'gmail') return 'gmail';
  if (mailbox.mailbox_type === 'outlook_live') return 'outlook';
  return null;
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

// Module-level cache for mailboxes (30s TTL - avoids redundant API calls on same page)
let _mailboxCache: { data: Mailbox[] | null; timestamp: number } = { data: null, timestamp: 0 };
const MAILBOX_CACHE_TTL = 30000;
// In-flight deduplication: parallel callers (MailboxSelector + page) share one request
let _mailboxInFlight: Promise<Mailbox[]> | null = null;

export const mailboxService = {
  // Clear mailbox cache (call after mutations: create/update/delete)
  clearCache() {
    _mailboxCache = { data: null, timestamp: 0 };
  },

  // Get all mailboxes (with in-flight deduplication + caching)
  async getMailboxes(): Promise<Mailbox[]> {
    const now = Date.now();
    if (_mailboxCache.data && (now - _mailboxCache.timestamp) < MAILBOX_CACHE_TTL) {
      return _mailboxCache.data;
    }

    // Deduplicate: if a fetch is already in-flight, all callers wait for it
    if (_mailboxInFlight) {
      return _mailboxInFlight;
    }

    const doFetch = async (): Promise<Mailbox[]> => {
      try {
        // Single call - apiClient handles retries internally (2 retries, 300ms delay)
        const mailboxes = await api.get<Mailbox[]>('/mailboxes', { timeout: 10000 });

        if (!mailboxes) {
          console.warn('[MailboxService] API returned null');
          return _mailboxCache.data || [];
        }

        _mailboxCache = { data: mailboxes, timestamp: Date.now() };
        return mailboxes;
      } catch (error) {
        console.error('[MailboxService] Error fetching mailboxes:', error);
        // Return cached data if available, empty array otherwise
        return _mailboxCache.data || [];
      }
    };

    _mailboxInFlight = doFetch().finally(() => {
      _mailboxInFlight = null;
    });

    return _mailboxInFlight;
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
    this.clearCache();
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
    this.clearCache();
    return mailbox;
  },

  // Delete a mailbox
  async deleteMailbox(id: string): Promise<void> {
    await api.delete(`/mailboxes/${id}`);
    this.clearCache();
  },

  // Trigger sync for a mailbox
  async syncMailbox(id: string): Promise<void> {
    await api.post(`/mailboxes/${id}/sync`);
  },

  async resyncMetadata(id: string): Promise<{ message: string; job_id: string }> {
    return api.post<{ message: string; job_id: string }>(`/mailboxes/${id}/resync-metadata`);
  },
};
