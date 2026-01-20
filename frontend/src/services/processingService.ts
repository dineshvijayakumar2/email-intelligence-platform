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
      download_first: jobData.download_first ?? false,
      download_threads: jobData.download_threads ?? 8
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

  // Get all processing jobs (with silent network error handling for polling)
  async getProcessingJobs(silent: boolean = false): Promise<ProcessingJob[]> {
    const jobs = await api.get<ProcessingJob[]>('/processing-jobs', {
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

};
