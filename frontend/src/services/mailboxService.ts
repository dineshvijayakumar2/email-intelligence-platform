import { supabaseClient } from '../supabase';

export interface Mailbox {
  id: string;
  name: string;
  email_address: string;
  mailbox_type: 'outlook' | 'mbox' | 'imap' | 'pop3';
  is_active: boolean;
  total_emails: number;
  last_sync_at: string | null;
  created_at: string;
  connection_config?: Record<string, any>;
}

export interface CreateMailboxData {
  name: string;
  email_address: string;
  mailbox_type: 'outlook' | 'mbox' | 'imap' | 'pop3';
  is_active: boolean;
  connection_config?: Record<string, any>;
  // Additional fields for form (will be moved to connection_config)
  file_path?: string;
  imap_server?: string;
  imap_port?: number;
  pop3_server?: string;
  pop3_port?: number;
  use_ssl?: boolean;
  username?: string;
  password?: string;
  client_id?: string;
  tenant_id?: string;
}

export const mailboxService = {
  // Get all mailboxes
  async getMailboxes(): Promise<Mailbox[]> {
    const { data, error } = await supabaseClient
      .from('mailboxes')
      .select('*')
      .order('created_at', { ascending: false });
    
    if (error) {
      console.error('Error fetching mailboxes:', error);
      throw error;
    }
    
    return data || [];
  },

  // Get a single mailbox by ID
  async getMailbox(id: string): Promise<Mailbox | null> {
    const { data, error } = await supabaseClient
      .from('mailboxes')
      .select('*')
      .eq('id', id)
      .single();
    
    if (error) {
      console.error('Error fetching mailbox:', error);
      throw error;
    }
    
    return data;
  },

  // Create a new mailbox
  async createMailbox(mailboxData: CreateMailboxData): Promise<Mailbox> {
    const { data, error } = await supabaseClient
      .from('mailboxes')
      .insert([{
        ...mailboxData,
        total_emails: 0,
        created_at: new Date().toISOString()
      }])
      .select()
      .single();
    
    if (error) {
      console.error('Error creating mailbox:', error);
      throw error;
    }
    
    return data;
  },

  // Update an existing mailbox
  async updateMailbox(id: string, updates: Partial<CreateMailboxData>): Promise<Mailbox> {
    const { data, error } = await supabaseClient
      .from('mailboxes')
      .update(updates)
      .eq('id', id)
      .select()
      .single();
    
    if (error) {
      console.error('Error updating mailbox:', error);
      throw error;
    }
    
    return data;
  },

  // Delete a mailbox
  async deleteMailbox(id: string): Promise<void> {
    const { error } = await supabaseClient
      .from('mailboxes')
      .delete()
      .eq('id', id);
    
    if (error) {
      console.error('Error deleting mailbox:', error);
      throw error;
    }
  },

  // Trigger sync for a mailbox
  async syncMailbox(id: string): Promise<void> {
    // TODO: This would typically trigger a background job
    // For now, we'll just update the last_sync_at timestamp
    const { error } = await supabaseClient
      .from('mailboxes')
      .update({ last_sync_at: new Date().toISOString() })
      .eq('id', id);
    
    if (error) {
      console.error('Error updating sync timestamp:', error);
      throw error;
    }
  }
};