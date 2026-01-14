import config from '../config';

export interface Email {
  id: string;
  subject: string;
  sender_email: string;
  sender_name?: string;
  recipients?: Array<{ email: string; name?: string }>;
  cc_list?: Array<{ email: string; name?: string }>;
  bcc_list?: Array<{ email: string; name?: string }>;
  sent_date: string;
  received_date?: string;
  category?: string; // This will come from email_categories join
  is_outbound: boolean;
  is_reply: boolean;
  folder_path: string;
  message_size: number;
  mailbox_name: string;
  mailbox_id: string;
  body_text?: string;
  body_html?: string;
  // New tagging fields
  tags?: string[];
  is_spam?: boolean;
  is_marketing?: boolean;
  priority_score?: number;
  sender_type?: string;
}

export interface EmailFilters {
  search?: string;
  category?: string;
  mailbox?: string;
  folder?: string;
  dateRange?: [string, string] | null;
  isOutbound?: string;
  // New tag-based filters
  tags?: string[];
  isSpam?: boolean;
  isMarketing?: boolean;
  minPriority?: number;
  maxPriority?: number;
}

export const emailService = {
  // Get emails with filters and pagination - now uses backend API
  async getEmails(filters: EmailFilters = {}, page = 1, pageSize = 20): Promise<{ emails: Email[]; totalCount: number }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/emails`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          filters,
          page,
          pageSize
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching emails:', error);
      return { emails: [], totalCount: 0 };
    }
  },


  // Get a single email by ID - now uses backend API
  async getEmail(id: string): Promise<Email | null> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/emails/${id}`);

      if (!response.ok) {
        if (response.status === 404) {
          return null;
        }
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const email = await response.json();
      return email;
    } catch (error) {
      console.error('Error fetching email:', error);
      return null;
    }
  },

  // Get email categories for filter dropdown - now uses backend API
  async getEmailCategories(): Promise<string[]> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/emails/categories`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const categories = await response.json();
      console.log('Loaded categories from backend:', categories);
      return categories;
    } catch (error) {
      console.error('Error fetching email categories:', error);
      return ['spam', 'marketing', 'inbox', 'sent', 'trash'];
    }
  },

  // Get mailbox names for filter dropdown - now uses backend API
  async getMailboxNames(): Promise<string[]> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/mailbox-names`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const names = await response.json();
      return names;
    } catch (error) {
      console.error('Error fetching mailbox names:', error);
      return [];
    }
  },

  // Get folder names for filter dropdown - now uses backend API
  async getFolderNames(): Promise<string[]> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/emails/folders`);

      if (!response.ok) {
        console.error('Error fetching folder names:', response.statusText);
        return [];
      }

      const folders = await response.json();
      console.log('Loaded folders from backend:', folders);
      return folders;
    } catch (error) {
      console.error('Error fetching folder names:', error);
      return [];
    }
  }
};