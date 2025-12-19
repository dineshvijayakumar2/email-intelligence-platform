import { supabaseClient } from '../supabase';

export interface Email {
  id: string;
  subject: string;
  sender_email: string;
  sender_name?: string;
  sent_date: string;
  category?: string; // This will come from email_categories join
  is_outbound: boolean;
  is_reply: boolean;
  folder_path: string;
  message_size: number;
  mailbox_name: string;
  mailbox_id: string;
  body_text?: string;
  body_html?: string;
}

export interface EmailFilters {
  search?: string;
  category?: string;
  mailbox?: string;
  dateRange?: [string, string] | null;
  isOutbound?: string;
}

export const emailService = {
  // Get emails with filters and pagination
  async getEmails(filters: EmailFilters = {}, page = 1, pageSize = 20): Promise<{ emails: Email[]; totalCount: number }> {
    try {
      // Build the query to join emails with mailboxes and categories
      let query = supabaseClient
        .from('emails')
        .select(`
          id,
          subject,
          sender_email,
          sender_name,
          sent_date,
          is_outbound,
          is_reply,
          folder_path,
          message_size,
          body_text,
          body_html,
          mailbox_id,
          mailboxes!inner(name),
          email_categories(category)
        `, { count: 'exact' });

      // Apply filters
      if (filters.search) {
        query = query.or(`subject.ilike.%${filters.search}%,sender_email.ilike.%${filters.search}%,sender_name.ilike.%${filters.search}%`);
      }

      if (filters.category) {
        query = query.eq('email_categories.category', filters.category);
      }

      if (filters.mailbox) {
        query = query.eq('mailboxes.name', filters.mailbox);
      }

      if (filters.isOutbound === 'outbound') {
        query = query.eq('is_outbound', true);
      } else if (filters.isOutbound === 'inbound') {
        query = query.eq('is_outbound', false);
      }

      if (filters.dateRange && filters.dateRange.length === 2) {
        query = query.gte('sent_date', filters.dateRange[0]).lte('sent_date', filters.dateRange[1]);
      }

      // Add pagination
      const from = (page - 1) * pageSize;
      const to = from + pageSize - 1;
      query = query.range(from, to);

      // Order by sent date descending
      query = query.order('sent_date', { ascending: false });

      const { data, error, count } = await query;

      if (error) {
        console.error('Error fetching emails:', error);
        throw error;
      }

      // Transform the data to match expected format
      const emails: Email[] = (data || []).map(item => ({
        id: item.id,
        subject: item.subject,
        sender_email: item.sender_email,
        sender_name: item.sender_name,
        sent_date: item.sent_date,
        category: item.email_categories?.[0]?.category || 'unassigned',
        is_outbound: item.is_outbound,
        is_reply: item.is_reply,
        folder_path: item.folder_path,
        message_size: item.message_size,
        body_text: item.body_text,
        body_html: item.body_html,
        mailbox_id: item.mailbox_id,
        mailbox_name: (item as any).mailboxes?.name || 'Unknown'
      }));

      return {
        emails,
        totalCount: count || 0
      };
    } catch (error) {
      console.error('Error fetching emails:', error);
      // Return empty result instead of throwing
      return { emails: [], totalCount: 0 };
    }
  },

  // Get a single email by ID
  async getEmail(id: string): Promise<Email | null> {
    try {
      const { data, error } = await supabaseClient
        .from('emails')
        .select(`
          id,
          subject,
          sender_email,
          sender_name,
          sent_date,
          is_outbound,
          is_reply,
          folder_path,
          message_size,
          body_text,
          body_html,
          mailbox_id,
          mailboxes!inner(name),
          email_categories(category)
        `)
        .eq('id', id)
        .single();

      if (error) {
        console.error('Error fetching email:', error);
        throw error;
      }

      if (!data) return null;

      return {
        id: data.id,
        subject: data.subject,
        sender_email: data.sender_email,
        sender_name: data.sender_name,
        sent_date: data.sent_date,
        category: data.email_categories?.[0]?.category || 'unassigned',
        is_outbound: data.is_outbound,
        is_reply: data.is_reply,
        folder_path: data.folder_path,
        message_size: data.message_size,
        body_text: data.body_text,
        body_html: data.body_html,
        mailbox_id: data.mailbox_id,
        mailbox_name: (data as any).mailboxes?.name || 'Unknown'
      };
    } catch (error) {
      console.error('Error fetching email:', error);
      return null;
    }
  },

  // Get email categories for filter dropdown
  async getEmailCategories(): Promise<string[]> {
    try {
      const { data, error } = await supabaseClient
        .from('email_categories')
        .select('category')
        .not('category', 'is', null);

      if (error) {
        console.error('Error fetching email categories:', error);
        return ['unassigned', 'system', 'spam', 'marketing', 'transactional', 'conversation'];
      }

      // Get unique categories
      const categorySet = new Set(data?.map(item => item.category).filter(Boolean));
      const categories = Array.from(categorySet);
      return categories.sort();
    } catch (error) {
      console.error('Error fetching email categories:', error);
      return ['unassigned', 'system', 'spam', 'marketing', 'transactional', 'conversation'];
    }
  },

  // Get mailbox names for filter dropdown
  async getMailboxNames(): Promise<string[]> {
    try {
      const { data, error } = await supabaseClient
        .from('mailboxes')
        .select('name')
        .eq('is_active', true);

      if (error) {
        console.error('Error fetching mailbox names:', error);
        return [];
      }

      return data?.map(item => item.name) || [];
    } catch (error) {
      console.error('Error fetching mailbox names:', error);
      return [];
    }
  }
};