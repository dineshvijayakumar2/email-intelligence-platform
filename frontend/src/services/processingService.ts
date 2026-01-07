// @ts-ignore
import config from '../config.js';

export interface ProcessingJob {
  id: string;
  job_type: string;
  mailbox_id: string;
  mailbox_name?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'stopped';
  total_records: number;
  processed_records: number;
  failed_records: number;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  error_log?: string[] | string | Record<string, any>;
  progress?: number;
}

export interface CreateProcessingJobData {
  job_type: string;
  mailbox_id: string;
  total_records?: number;
}

export const processingService = {
  // Create a new processing job
  async createProcessingJob(jobData: CreateProcessingJobData): Promise<ProcessingJob> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/mailboxes/${jobData.mailbox_id}/process`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          job_type: jobData.job_type,
          total_records: jobData.total_records || 1000,
          batch_size: 100,
          enable_categorization: true,
          enable_enrichment: false
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const job = await response.json();
      return {
        ...job,
        progress: 0,
        error_log: job.error_log || []
      };
    } catch (error) {
      console.error('Error creating processing job:', error);
      throw error;
    }
  },

  // Get all processing jobs
  async getProcessingJobs(): Promise<ProcessingJob[]> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/processing-jobs`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const jobs = await response.json();
      return jobs.map((job: any) => ({
        ...job,
        error_log: job.error_log || [],
        progress: job.progress || 0
      }));
    } catch (error) {
      console.error('Error fetching processing jobs:', error);
      throw error;
    }
  },

  // Control job actions (pause, resume, stop)
  async controlJob(jobId: string, action: 'pause' | 'resume' | 'stop'): Promise<void> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/processing-jobs/${jobId}/${action}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
    } catch (error) {
      console.error('Error controlling job:', error);
      throw error;
    }
  },

  // Delete a completed or failed job
  async deleteJob(jobId: string): Promise<void> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/processing-jobs/${jobId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
    } catch (error) {
      console.error('Error deleting job:', error);
      throw error;
    }
  },

  // Reprocess emails to add categorization
  async reprocessJob(jobId: string): Promise<ProcessingJob> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/processing-jobs/${jobId}/reprocess`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();
      return result;
    } catch (error) {
      console.error('Error reprocessing job:', error);
      throw error;
    }
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
      completed: 'green',
      failed: 'red',
      paused: 'default',
      stopped: 'volcano'  // Orange-red for manually stopped jobs
    };
    return colors[status as keyof typeof colors] || 'default';
  },

};