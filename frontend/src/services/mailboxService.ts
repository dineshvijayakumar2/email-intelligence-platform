// @ts-ignore
import config from '../config.js';

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
    try {
      const response = await fetch(`${config.apiBaseUrl}/mailboxes`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const mailboxes = await response.json();
      return mailboxes;
    } catch (error) {
      console.error('Error fetching mailboxes:', error);
      throw error;
    }
  },

  // Get a single mailbox by ID
  async getMailbox(id: string): Promise<Mailbox | null> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/mailboxes/${id}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const mailbox = await response.json();
      return mailbox;
    } catch (error) {
      console.error('Error fetching mailbox:', error);
      throw error;
    }
  },

  // Create a new mailbox
  async createMailbox(mailboxData: CreateMailboxData): Promise<Mailbox> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/mailboxes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(mailboxData),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const mailbox = await response.json();
      return mailbox;
    } catch (error) {
      console.error('Error creating mailbox:', error);
      throw error;
    }
  },

  // Create a Google Drive mailbox with OAuth2 support
  async createGoogleDriveMailbox(mailboxData: CreateGoogleDriveMailboxData): Promise<Mailbox> {
    try {
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
    } catch (error) {
      console.error('Error creating Google Drive mailbox:', error);
      throw error;
    }
  },

  // Update an existing mailbox
  async updateMailbox(id: string, updates: Partial<CreateMailboxData>): Promise<Mailbox> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/mailboxes/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updates),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const mailbox = await response.json();
      return mailbox;
    } catch (error) {
      console.error('Error updating mailbox:', error);
      throw error;
    }
  },

  // Delete a mailbox
  async deleteMailbox(id: string): Promise<void> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/mailboxes/${id}`, {
        method: 'DELETE',
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
    } catch (error) {
      console.error('Error deleting mailbox:', error);
      throw error;
    }
  },

  // Trigger sync for a mailbox
  async syncMailbox(id: string): Promise<void> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/mailboxes/${id}/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
    } catch (error) {
      console.error('Error syncing mailbox:', error);
      throw error;
    }
  }
};