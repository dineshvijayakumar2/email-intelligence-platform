import { supabaseClient } from '../supabase';

export interface DashboardStats {
  totalEmails: number;
  totalMailboxes: number;
  todayEmails: number;
  processingJobs: number;
}

export interface VolumeData {
  date: string;
  inbound: number;
  outbound: number;
}

export interface CategoryData {
  name: string;
  value: number;
  color: string;
  [key: string]: any; // Add index signature for chart compatibility
}

export interface RecentEmail {
  id: string;
  subject: string;
  sender: string;
  category: string;
  received: string;
}

export const dashboardService = {
  // Get dashboard statistics
  async getDashboardStats(): Promise<DashboardStats> {
    try {
      // Get total emails
      const { count: totalEmails } = await supabaseClient
        .from('emails')
        .select('*', { count: 'exact', head: true });

      // Get total mailboxes
      const { count: totalMailboxes } = await supabaseClient
        .from('mailboxes')
        .select('*', { count: 'exact', head: true });

      // Get today's emails
      const today = new Date().toISOString().split('T')[0];
      const { count: todayEmails } = await supabaseClient
        .from('emails')
        .select('*', { count: 'exact', head: true })
        .gte('sent_date', today);

      // Get processing jobs count (if table exists)
      const { count: processingJobs } = await supabaseClient
        .from('processing_jobs')
        .select('*', { count: 'exact', head: true })
        .in('status', ['pending', 'running']);

      return {
        totalEmails: totalEmails || 0,
        totalMailboxes: totalMailboxes || 0,
        todayEmails: todayEmails || 0,
        processingJobs: processingJobs || 0,
      };
    } catch (error) {
      console.error('Error fetching dashboard stats:', error);
      // Return default values if there's an error
      return {
        totalEmails: 0,
        totalMailboxes: 0,
        todayEmails: 0,
        processingJobs: 0,
      };
    }
  },

  // Get email volume data for the last 7 days
  async getVolumeData(): Promise<VolumeData[]> {
    try {
      // Use the daily_email_volume view from your schema
      const sevenDaysAgo = new Date();
      sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 6);
      
      const { data, error } = await supabaseClient
        .from('daily_email_volume')
        .select('*')
        .gte('date', sevenDaysAgo.toISOString().split('T')[0])
        .lte('date', new Date().toISOString().split('T')[0])
        .order('date', { ascending: true });

      if (error) {
        console.error('Error fetching volume data:', error);
        return this.getMockVolumeData();
      }

      // Transform to match expected format
      return (data || []).map(item => ({
        date: item.date,
        inbound: item.inbound || 0,
        outbound: item.outbound || 0
      }));
    } catch (error) {
      console.error('Error fetching volume data:', error);
      return this.getMockVolumeData();
    }
  },

  // Fallback mock data for volume chart
  getMockVolumeData(): VolumeData[] {
    const data = [];
    for (let i = 6; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      data.push({
        date: date.toISOString().split('T')[0],
        inbound: Math.floor(Math.random() * 50) + 30,
        outbound: Math.floor(Math.random() * 30) + 15,
      });
    }
    return data;
  },

  // Get email category distribution
  async getCategoryData(): Promise<CategoryData[]> {
    try {
      const { data, error } = await supabaseClient
        .from('email_categories')
        .select('category');

      if (error) {
        console.error('Error fetching category data:', error);
        return this.getMockCategoryData();
      }

      // Count categories
      const categoryCounts: { [key: string]: number } = {};
      data?.forEach(item => {
        if (item.category) {
          categoryCounts[item.category] = (categoryCounts[item.category] || 0) + 1;
        }
      });

      const colors = ['#8884d8', '#82ca9d', '#ffc658', '#ff8042', '#0088fe'];
      
      return Object.entries(categoryCounts)
        .map(([name, value], index) => ({
          name: this.getCategoryLabel(name),
          value,
          color: colors[index % colors.length]
        }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 5); // Top 5 categories
    } catch (error) {
      console.error('Error fetching category data:', error);
      return this.getMockCategoryData();
    }
  },

  // Fallback mock data for category chart
  getMockCategoryData(): CategoryData[] {
    return [
      { name: 'Promotional', value: 45, color: '#8884d8' },
      { name: 'Transactional', value: 25, color: '#82ca9d' },
      { name: 'Social', value: 15, color: '#ffc658' },
      { name: 'Updates', value: 15, color: '#ff8042' },
    ];
  },

  // Get recent emails
  async getRecentEmails(): Promise<RecentEmail[]> {
    try {
      const { data, error } = await supabaseClient
        .from('emails')
        .select(`
          id, 
          subject, 
          sender_email, 
          sender_name, 
          sent_date,
          email_categories(category)
        `)
        .order('sent_date', { ascending: false })
        .limit(5);

      if (error) {
        console.error('Error fetching recent emails:', error);
        return [];
      }

      return (data || []).map(email => ({
        id: email.id,
        subject: email.subject,
        sender: email.sender_name || email.sender_email,
        category: this.getCategoryLabel(email.email_categories?.[0]?.category),
        received: this.formatRelativeTime(email.sent_date),
      }));
    } catch (error) {
      console.error('Error fetching recent emails:', error);
      return [];
    }
  },

  // Helper function to format category labels
  getCategoryLabel(category: string): string {
    const labels: { [key: string]: string } = {
      promotional: 'Promotional',
      transactional: 'Transactional',
      conversation: 'Conversation',
      internal: 'Internal',
      system: 'System',
      social: 'Social',
      updates: 'Updates',
    };
    return labels[category?.toLowerCase()] || category || 'Unknown';
  },

  // Helper function to format relative time
  formatRelativeTime(dateString: string): string {
    const date = new Date(dateString);
    const now = new Date();
    const diffInMinutes = Math.floor((now.getTime() - date.getTime()) / (1000 * 60));

    if (diffInMinutes < 60) {
      return `${diffInMinutes} minutes ago`;
    } else if (diffInMinutes < 24 * 60) {
      const hours = Math.floor(diffInMinutes / 60);
      return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
    } else {
      const days = Math.floor(diffInMinutes / (24 * 60));
      return `${days} day${days !== 1 ? 's' : ''} ago`;
    }
  }
};