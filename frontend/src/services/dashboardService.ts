import config from '../config';

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
  // Get dashboard statistics - now uses backend API
  async getDashboardStats(): Promise<DashboardStats> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/dashboard/stats`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const stats = await response.json();
      return stats;
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

  // Get email volume data for the last 7 days - now uses backend API
  async getVolumeData(): Promise<VolumeData[]> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/dashboard/volume`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const volumeData = await response.json();
      return volumeData;
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

  // Get email category distribution - now uses backend API
  async getCategoryData(): Promise<CategoryData[]> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/dashboard/categories`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const categoryData = await response.json();
      return categoryData;
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

  // Get recent emails - now uses backend API
  async getRecentEmails(): Promise<RecentEmail[]> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/dashboard/recent-emails`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const recentEmails = await response.json();
      return recentEmails;
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