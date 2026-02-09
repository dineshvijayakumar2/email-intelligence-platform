import api from './apiClient';

export interface ProcessingJob {
  id: string;
  job_type: string;
  mailbox_id: string;
  mailbox_name?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'stopped' | 'interrupted' | 'downloading';
  total_records: number;
  processed_records: number;
  failed_records: number;
  filtered_records?: number;  // Stage 2: Emails filtered by date range
  started_at?: string;
  completed_at?: string;
  created_at: string;
  error_log?: string[] | string | Record<string, any>;
  progress?: number;
  emails_per_second?: number;
  estimated_time_remaining?: string;
  estimated_seconds_remaining?: number;
  // Download progress (for parallel download mode)
  download_percent?: number;
  download_speed_mbps?: number;
  // Stage 2: Date range filter parameters
  filter_start_date?: string;
  filter_end_date?: string;
}

export interface CreateProcessingJobData {
  job_type: string;
  mailbox_id: string;
  total_records?: number;
  max_emails?: number;
  start_date?: string;
  end_date?: string;
  enable_categorization?: boolean;
  download_first?: boolean;
  download_threads?: number;
  use_cached_file?: boolean;
  keep_downloaded_file?: boolean;
}

export interface CachedDownload {
  cached: boolean;
  reason?: string;
  cache_id?: string;
  file_name?: string;
  file_size?: number;
  file_size_formatted?: string;
  storage_type?: string;
  storage_path?: string;
  downloaded_at?: string;
  age_hours?: number;
  age_formatted?: string;
  last_used_at?: string;
}

export const processingService = {
  // Create a new processing job
  async createProcessingJob(jobData: CreateProcessingJobData): Promise<ProcessingJob> {
    const job = await api.post<ProcessingJob>(`/mailboxes/${jobData.mailbox_id}/process`, {
      job_type: jobData.job_type,
      max_emails: jobData.max_emails || null,
      start_date: jobData.start_date || null,
      end_date: jobData.end_date || null,
      enable_categorization: jobData.enable_categorization ?? true,
      download_first: jobData.download_first ?? true,
      download_threads: jobData.download_threads ?? 8,
      use_cached_file: jobData.use_cached_file ?? true,
      keep_downloaded_file: jobData.keep_downloaded_file ?? true
    });

    if (!job) {
      throw new Error('Failed to create processing job');
    }

    return {
      ...job,
      progress: 0,
      error_log: job.error_log || []
    };
  },

  // Get processing jobs (with silent network error handling for polling)
  // Optional mailbox_id parameter to filter by specific mailbox at the backend level
  async getProcessingJobs(silent: boolean = false, mailboxId?: string): Promise<ProcessingJob[]> {
    const url = mailboxId ? `/processing-jobs?mailbox_id=${mailboxId}` : '/processing-jobs';
    const jobs = await api.get<ProcessingJob[]>(url, {
      silentOnNetworkError: silent,
      timeout: 5000, // Shorter timeout for polling
    });

    if (!jobs) {
      // Network error in silent mode - return empty array
      return [];
    }

    return jobs.map((job: any) => ({
      ...job,
      error_log: job.error_log || [],
      progress: job.progress || 0
    }));
  },

  // Control job actions (pause, resume, stop)
  async controlJob(jobId: string, action: 'pause' | 'resume' | 'stop'): Promise<void> {
    await api.post(`/processing-jobs/${jobId}/${action}`);
  },

  // Delete a completed or failed job
  async deleteJob(jobId: string): Promise<void> {
    await api.delete(`/processing-jobs/${jobId}`);
  },

  // Reprocess emails to add categorization
  async reprocessJob(jobId: string): Promise<ProcessingJob> {
    const result = await api.post<ProcessingJob>(`/processing-jobs/${jobId}/reprocess`);
    if (!result) {
      throw new Error('Failed to reprocess job');
    }
    return result;
  },

  // Restart an interrupted/failed/stopped job
  async restartJob(jobId: string): Promise<{
    message: string;
    new_job_id: string;
    original_job_id: string;
    cached_file_available: boolean;
    cached_file_path?: string;
  }> {
    const result = await api.post<{
      message: string;
      new_job_id: string;
      original_job_id: string;
      cached_file_available: boolean;
      cached_file_path?: string;
    }>(`/processing-jobs/${jobId}/restart`);
    if (!result) {
      throw new Error('Failed to restart job');
    }
    return result;
  },

  // Get job status labels
  getJobTypeLabel(jobType: string): string {
    const labels = {
      mbox_extraction: 'MBOX Extraction',
      outlook_extraction: 'Outlook Extraction',
      extraction: 'Email Extraction',
      reprocessing: 'Reprocessing (Categorization)',
      categorization: 'Email Categorization',
      enrichment: 'AI Enrichment',
      cleanup: 'Data Cleanup'
    };
    return labels[jobType as keyof typeof labels] || jobType;
  },

  getStatusColor(status: string): string {
    const colors = {
      pending: 'orange',
      running: 'blue',
      downloading: 'purple',
      completed: 'green',
      failed: 'red',
      paused: 'default',
      stopped: 'volcano',  // Orange-red for manually stopped jobs
      interrupted: 'magenta'  // Server restart interrupted the job
    };
    return colors[status as keyof typeof colors] || 'default';
  },

  // Check if there's a cached download available for a mailbox
  async checkCachedDownload(mailboxId: string): Promise<CachedDownload> {
    const result = await api.get<CachedDownload>(`/mailboxes/${mailboxId}/cached-download`, {
      silentOnNetworkError: true,
      timeout: 5000,
    });

    if (!result) {
      return { cached: false, reason: 'Network error' };
    }

    return result;
  },

  // Invalidate (delete) a cached download
  async invalidateCachedDownload(cacheId: string): Promise<void> {
    await api.delete(`/cached-downloads/${cacheId}`);
  },

};
