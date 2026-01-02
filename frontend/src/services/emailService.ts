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
  // Get emails with filters and pagination
  async getEmails(filters: EmailFilters = {}, page = 1, pageSize = 20): Promise<{ emails: Email[]; totalCount: number }> {
    try {
      // For category filter with many results, batch the IDs
      let emailIdBatches: string[][] = [];
      if (filters.category) {
        const { data: categoryData, error: categoryError } = await supabaseClient
          .from('email_categories')
          .select('email_id')
          .eq('category', filters.category);

        if (categoryError) {
          console.error('Error fetching category filter:', categoryError);
          throw categoryError;
        }

        const emailIds = categoryData?.map(item => item.email_id) || [];
        console.log(`Category filter "${filters.category}": ${emailIds.length} emails`);

        if (emailIds.length === 0) {
          return { emails: [], totalCount: 0 };
        }

        // Split IDs into batches of 100 to avoid URL length issues
        const batchSize = 100;
        for (let i = 0; i < emailIds.length; i += batchSize) {
          emailIdBatches.push(emailIds.slice(i, i + batchSize));
        }
      }

      // If we have category filter, we need to query in batches and combine results
      if (emailIdBatches.length > 0) {
        return await this.getEmailsInBatches(emailIdBatches, filters, page, pageSize);
      }

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
          email_categories(category, tag_type)
        `, { count: 'exact' });

      // Apply other filters
      if (filters.search) {
        query = query.or(`subject.ilike.%${filters.search}%,sender_email.ilike.%${filters.search}%,sender_name.ilike.%${filters.search}%`);
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

      // Order by sent date descending
      query = query.order('sent_date', { ascending: false });

      // Add pagination
      const from = (page - 1) * pageSize;
      const to = from + pageSize - 1;
      query = query.range(from, to);

      const { data, error, count } = await query;

      if (error) {
        console.error('Error fetching emails:', error);
        throw error;
      }

      // Transform the data to match expected format
      const emails: Email[] = (data || []).map(item => {
        // Extract tags and metadata from email_categories
        const categories = item.email_categories || [];
        const tags = categories
          .filter((cat: any) => !cat.category.startsWith('_meta_'))
          .map((cat: any) => cat.category);

        // Extract metadata
        const isSpam = categories.some((cat: any) => cat.category === '_meta_spam');
        const isMarketing = categories.some((cat: any) => cat.category === '_meta_marketing');

        // Extract priority score
        const priorityTag = categories.find((cat: any) => cat.category.startsWith('_meta_priority_'));
        const priorityScore = priorityTag ? parseInt(priorityTag.category.replace('_meta_priority_', '')) : 5;

        // Extract sender type
        const senderTag = categories.find((cat: any) => cat.category.startsWith('_meta_sender_'));
        const senderType = senderTag ? senderTag.category.replace('_meta_sender_', '') : 'unknown';

        return {
          id: item.id,
          subject: item.subject,
          sender_email: item.sender_email,
          sender_name: item.sender_name,
          sent_date: item.sent_date,
          category: categories[0]?.category || 'unassigned',
          is_outbound: item.is_outbound,
          is_reply: item.is_reply,
          folder_path: item.folder_path,
          message_size: item.message_size,
          body_text: item.body_text,
          body_html: item.body_html,
          mailbox_id: item.mailbox_id,
          mailbox_name: (item as any).mailboxes?.name || 'Unknown',
          tags,
          is_spam: isSpam,
          is_marketing: isMarketing,
          priority_score: priorityScore,
          sender_type: senderType
        };
      });

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

  // Helper function to get emails in batches when filtering by category
  async getEmailsInBatches(
    emailIdBatches: string[][],
    filters: EmailFilters,
    page: number,
    pageSize: number
  ): Promise<{ emails: Email[]; totalCount: number }> {
    try {
      // We need to fetch all matching emails across batches, then paginate client-side
      // This is necessary because pagination needs to happen after combining results
      let allEmails: any[] = [];

      for (const batch of emailIdBatches) {
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
            email_categories(category, tag_type)
          `)
          .in('id', batch);

        // Apply other filters
        if (filters.search) {
          query = query.or(`subject.ilike.%${filters.search}%,sender_email.ilike.%${filters.search}%,sender_name.ilike.%${filters.search}%`);
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

        const { data, error } = await query;

        if (error) {
          console.error('Error fetching email batch:', error);
          throw error;
        }

        if (data) {
          allEmails.push(...data);
        }
      }

      // Sort by sent_date descending (same as main query)
      allEmails.sort((a, b) => new Date(b.sent_date).getTime() - new Date(a.sent_date).getTime());

      // Apply pagination client-side
      const totalCount = allEmails.length;
      const from = (page - 1) * pageSize;
      const to = from + pageSize;
      const paginatedEmails = allEmails.slice(from, to);

      // Transform the data to match expected format
      const emails: Email[] = paginatedEmails.map(item => {
        const categories = item.email_categories || [];
        const tags = categories
          .filter((cat: any) => !cat.category.startsWith('_meta_'))
          .map((cat: any) => cat.category);

        const isSpam = categories.some((cat: any) => cat.category === '_meta_spam');
        const isMarketing = categories.some((cat: any) => cat.category === '_meta_marketing');

        const priorityTag = categories.find((cat: any) => cat.category.startsWith('_meta_priority_'));
        const priorityScore = priorityTag ? parseInt(priorityTag.category.replace('_meta_priority_', '')) : 5;

        const senderTag = categories.find((cat: any) => cat.category.startsWith('_meta_sender_'));
        const senderType = senderTag ? senderTag.category.replace('_meta_sender_', '') : 'unknown';

        return {
          id: item.id,
          subject: item.subject,
          sender_email: item.sender_email,
          sender_name: item.sender_name,
          sent_date: item.sent_date,
          category: categories[0]?.category || 'unassigned',
          is_outbound: item.is_outbound,
          is_reply: item.is_reply,
          folder_path: item.folder_path,
          message_size: item.message_size,
          body_text: item.body_text,
          body_html: item.body_html,
          mailbox_id: item.mailbox_id,
          mailbox_name: (item as any).mailboxes?.name || 'Unknown',
          tags,
          is_spam: isSpam,
          is_marketing: isMarketing,
          priority_score: priorityScore,
          sender_type: senderType
        };
      });

      return {
        emails,
        totalCount
      };
    } catch (error) {
      console.error('Error fetching emails in batches:', error);
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
          email_categories(category, tag_type)
        `)
        .eq('id', id)
        .single();

      if (error) {
        console.error('Error fetching email:', error);
        throw error;
      }

      if (!data) return null;

      // Extract tags and metadata from email_categories
      const categories = data.email_categories || [];
      const tags = categories
        .filter((cat: any) => !cat.category.startsWith('_meta_'))
        .map((cat: any) => cat.category);

      // Extract metadata
      const isSpam = categories.some((cat: any) => cat.category === '_meta_spam');
      const isMarketing = categories.some((cat: any) => cat.category === '_meta_marketing');

      // Extract priority score
      const priorityTag = categories.find((cat: any) => cat.category.startsWith('_meta_priority_'));
      const priorityScore = priorityTag ? parseInt(priorityTag.category.replace('_meta_priority_', '')) : 5;

      // Extract sender type
      const senderTag = categories.find((cat: any) => cat.category.startsWith('_meta_sender_'));
      const senderType = senderTag ? senderTag.category.replace('_meta_sender_', '') : 'unknown';

      return {
        id: data.id,
        subject: data.subject,
        sender_email: data.sender_email,
        sender_name: data.sender_name,
        sent_date: data.sent_date,
        category: categories[0]?.category || 'unassigned',
        is_outbound: data.is_outbound,
        is_reply: data.is_reply,
        folder_path: data.folder_path,
        message_size: data.message_size,
        body_text: data.body_text,
        body_html: data.body_html,
        mailbox_id: data.mailbox_id,
        mailbox_name: (data as any).mailboxes?.name || 'Unknown',
        tags,
        is_spam: isSpam,
        is_marketing: isMarketing,
        priority_score: priorityScore,
        sender_type: senderType
      };
    } catch (error) {
      console.error('Error fetching email:', error);
      return null;
    }
  },

  // Get email categories for filter dropdown (exclude metadata tags)
  async getEmailCategories(): Promise<string[]> {
    try {
      // Fetch all categories without server-side filtering
      const { data, error } = await supabaseClient
        .from('email_categories')
        .select('category');

      if (error) {
        console.error('Error fetching email categories:', error);
        return ['spam', 'marketing', 'inbox', 'sent', 'trash'];
      }

      console.log('Raw data from Supabase:', data?.length, 'rows'); // Debug

      // Get unique categories (tags), filter out nulls and metadata client-side
      const categorySet = new Set(
        data?.map(item => item.category)
          .filter(Boolean)
          .filter(cat => !cat.startsWith('_meta_'))
      );
      const categories = Array.from(categorySet).sort();

      console.log('Loaded categories:', categories); // Debug log

      return categories;
    } catch (error) {
      console.error('Error fetching email categories:', error);
      return ['spam', 'marketing', 'inbox', 'sent', 'trash'];
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