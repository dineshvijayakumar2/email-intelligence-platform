import config from '../config';

export interface DashboardStats {
  totalEmails: number;
  totalMailboxes: number;
  todayEmails: number;
  processingJobs: number;
}

export interface ProcessingOverview {
  activeJobs: number;
  completedToday: number;
  failedToday: number;
  totalProcessed: number;
  successRate: number;
}

export interface MailboxSummary {
  id: string;
  name: string;
  emailCount: number;
  lastSync: string | null;
  isActive: boolean;
  type: string;
}

export interface RecentJob {
  id: string;
  mailboxName: string;
  status: string;
  processedCount: number;
  failedCount: number;
  completedAt: string | null;
  createdAt: string;
  jobType: string;
}

// Cache for processing jobs to avoid duplicate API calls
let processingJobsCache: { data: any[] | null; timestamp: number } = { data: null, timestamp: 0 };
const CACHE_TTL = 5000; // 5 seconds cache

export const dashboardService = {
  // Get dashboard statistics
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
      return {
        totalEmails: 0,
        totalMailboxes: 0,
        todayEmails: 0,
        processingJobs: 0,
      };
    }
  },

  // Internal: Fetch processing jobs with caching to avoid duplicate calls
  async _fetchProcessingJobs(): Promise<any[]> {
    const now = Date.now();

    // Return cached data if still valid
    if (processingJobsCache.data && (now - processingJobsCache.timestamp) < CACHE_TTL) {
      return processingJobsCache.data;
    }

    try {
      const response = await fetch(`${config.apiBaseUrl}/processing-jobs`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const jobs = await response.json();
      processingJobsCache = { data: jobs, timestamp: now };
      return jobs;
    } catch (error) {
      console.error('Error fetching processing jobs:', error);
      return processingJobsCache.data || [];
    }
  },

  // Get processing overview for dashboard
  async getProcessingOverview(): Promise<ProcessingOverview> {
    try {
      const jobs = await this._fetchProcessingJobs();
      const today = new Date().toISOString().split('T')[0];

      const activeJobs = jobs.filter((j: any) =>
        j.status === 'running' || j.status === 'pending' || j.status === 'downloading'
      ).length;

      const completedToday = jobs.filter((j: any) =>
        j.status === 'completed' && j.completed_at?.startsWith(today)
      ).length;

      const failedToday = jobs.filter((j: any) =>
        j.status === 'failed' && (j.completed_at?.startsWith(today) || j.created_at?.startsWith(today))
      ).length;

      const completedJobs = jobs.filter((j: any) => j.status === 'completed' || j.status === 'failed');
      const totalProcessed = completedJobs.reduce((sum: number, j: any) => sum + (j.processed_records || 0), 0);

      const successfulJobs = jobs.filter((j: any) => j.status === 'completed').length;
      const successRate = completedJobs.length > 0
        ? Math.round((successfulJobs / completedJobs.length) * 100)
        : 100;

      return {
        activeJobs,
        completedToday,
        failedToday,
        totalProcessed,
        successRate,
      };
    } catch (error) {
      console.error('Error fetching processing overview:', error);
      return {
        activeJobs: 0,
        completedToday: 0,
        failedToday: 0,
        totalProcessed: 0,
        successRate: 100,
      };
    }
  },

  // Get mailbox summaries
  async getMailboxSummaries(): Promise<MailboxSummary[]> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/mailboxes`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const mailboxes = await response.json();

      return mailboxes.map((m: any) => ({
        id: m.id,
        name: m.name,
        emailCount: m.total_emails || 0,
        lastSync: m.last_sync_at,
        isActive: m.is_active,
        type: m.mailbox_type,
      }));
    } catch (error) {
      console.error('Error fetching mailbox summaries:', error);
      return [];
    }
  },

  // Get recent processing jobs (uses cached data)
  async getRecentJobs(limit: number = 5): Promise<RecentJob[]> {
    try {
      const jobs = await this._fetchProcessingJobs();

      // Sort by created_at descending and take limit
      const sorted = [...jobs].sort((a: any, b: any) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      ).slice(0, limit);

      return sorted.map((j: any) => ({
        id: j.id,
        mailboxName: j.mailbox_name || 'Unknown',
        status: j.status,
        processedCount: j.processed_records || 0,
        failedCount: j.failed_records || 0,
        completedAt: j.completed_at,
        createdAt: j.created_at,
        jobType: j.job_type,
      }));
    } catch (error) {
      console.error('Error fetching recent jobs:', error);
      return [];
    }
  },

  // Combined method for dashboard - fetches all data efficiently
  async getAllDashboardData(): Promise<{
    stats: DashboardStats;
    processingOverview: ProcessingOverview;
    mailboxes: MailboxSummary[];
    recentJobs: RecentJob[];
  }> {
    // Fetch all data in parallel
    const [stats, mailboxes] = await Promise.all([
      this.getDashboardStats(),
      this.getMailboxSummaries(),
    ]);

    // These two share the same API call via cache
    const [processingOverview, recentJobs] = await Promise.all([
      this.getProcessingOverview(),
      this.getRecentJobs(5),
    ]);

    return { stats, processingOverview, mailboxes, recentJobs };
  },

  // Clear cache (call when data is mutated)
  clearCache() {
    processingJobsCache = { data: null, timestamp: 0 };
  },

  // Format relative time
  formatRelativeTime(dateString: string | null): string {
    if (!dateString) return 'Never';

    const date = new Date(dateString);
    const now = new Date();
    const diffInMinutes = Math.floor((now.getTime() - date.getTime()) / (1000 * 60));

    if (diffInMinutes < 1) return 'Just now';
    if (diffInMinutes < 60) return `${diffInMinutes}m ago`;

    const diffInHours = Math.floor(diffInMinutes / 60);
    if (diffInHours < 24) return `${diffInHours}h ago`;

    const diffInDays = Math.floor(diffInHours / 24);
    if (diffInDays < 7) return `${diffInDays}d ago`;

    return date.toLocaleDateString();
  },

  // Get job type label
  getJobTypeLabel(jobType: string): string {
    const labels: Record<string, string> = {
      mbox_extraction: 'MBOX Extraction',
      outlook_extraction: 'Outlook Extraction',
      extraction: 'Email Extraction',
      reprocessing: 'Reprocessing',
      categorization: 'Categorization',
    };
    return labels[jobType] || jobType;
  },

  // Get status color for processing jobs
  getStatusColor(status: string): string {
    const colors: Record<string, string> = {
      pending: 'orange',
      running: 'blue',
      downloading: 'purple',
      completed: 'green',
      failed: 'red',
      paused: 'default',
      stopped: 'volcano',
    };
    return colors[status] || 'default';
  },
};
