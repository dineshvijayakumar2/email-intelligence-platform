import { supabaseClient } from '../supabase';

export interface ProcessingJob {
  id: string;
  job_type: string;
  mailbox_id: string;
  mailbox_name?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused';
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
      const apiBaseUrl = process.env.REACT_APP_API_BASE_URL;
      
      if (apiBaseUrl) {
        // Use backend API
        const response = await fetch(`${apiBaseUrl}/mailboxes/${jobData.mailbox_id}/process`, {
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
      } else {
        // Fallback to direct Supabase
        const { data, error } = await supabaseClient
          .from('processing_jobs')
          .insert([{
            ...jobData,
            status: 'pending',
            processed_records: 0,
            failed_records: 0,
            created_at: new Date().toISOString()
          }])
          .select()
          .single();

        if (error) {
          console.error('Error creating processing job:', error);
          throw error;
        }

        return {
          ...data,
          progress: 0,
          error_log: []
        };
      }
    } catch (error) {
      console.error('Error creating processing job:', error);
      throw error;
    }
  },

  // Get all processing jobs
  async getProcessingJobs(): Promise<ProcessingJob[]> {
    try {
      const apiBaseUrl = process.env.REACT_APP_API_BASE_URL;
      
      if (apiBaseUrl) {
        // Use backend API
        const response = await fetch(`${apiBaseUrl}/processing-jobs`);
        
        if (!response.ok) {
          console.error('Error fetching processing jobs from API:', response.status);
          return this.getMockProcessingJobs();
        }

        const jobs = await response.json();
        return jobs.map((job: any) => ({
          ...job,
          error_log: job.error_log || [],
          progress: job.progress || 0
        }));
      } else {
        // Fallback to direct Supabase
        let { data, error } = await supabaseClient
          .from('processing_jobs')
          .select(`
            id,
            job_type,
            mailbox_id,
            status,
            total_records,
            processed_records,
            failed_records,
            started_at,
            completed_at,
            created_at,
            error_log,
            mailboxes(name)
          `)
          .order('created_at', { ascending: false });

        if (error) {
          console.error('Error fetching processing jobs with mailbox join:', error);
          
          // Fallback to basic table without join
          const fallback = await supabaseClient
            .from('processing_jobs')
            .select('*')
            .order('created_at', { ascending: false });
            
          if (fallback.error) {
            console.error('Error fetching processing jobs:', fallback.error);
            return this.getMockProcessingJobs();
          }
          
          data = fallback.data;
        }

        return (data || []).map(job => ({
          ...job,
          mailbox_name: (job as any).mailboxes?.name || 'Unknown Mailbox',
          error_log: job.error_log || [],
          progress: job.total_records > 0 
            ? Math.round((job.processed_records / job.total_records) * 100) 
            : 0
        }));
      }
    } catch (error) {
      console.error('Error fetching processing jobs:', error);
      return this.getMockProcessingJobs();
    }
  },

  // Control job actions (pause, resume, stop)
  async controlJob(jobId: string, action: 'pause' | 'resume' | 'stop'): Promise<void> {
    try {
      let newStatus: ProcessingJob['status'];
      
      switch (action) {
        case 'pause':
          newStatus = 'paused';
          break;
        case 'resume':
          newStatus = 'running';
          break;
        case 'stop':
          newStatus = 'failed'; // or 'cancelled' if you have that status
          break;
        default:
          throw new Error(`Invalid action: ${action}`);
      }

      const { error } = await supabaseClient
        .from('processing_jobs')
        .update({ status: newStatus })
        .eq('id', jobId);

      if (error) {
        console.error('Error controlling job:', error);
        throw error;
      }
    } catch (error) {
      console.error('Error controlling job:', error);
      throw error;
    }
  },

  // Delete a completed or failed job
  async deleteJob(jobId: string): Promise<void> {
    try {
      const { error } = await supabaseClient
        .from('processing_jobs')
        .delete()
        .eq('id', jobId);

      if (error) {
        console.error('Error deleting job:', error);
        throw error;
      }
    } catch (error) {
      console.error('Error deleting job:', error);
      throw error;
    }
  },

  // Get job status labels
  getJobTypeLabel(jobType: string): string {
    const labels = {
      mbox_extraction: 'MBOX Extraction',
      outlook_extraction: 'Outlook Extraction',
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
      paused: 'default'
    };
    return colors[status as keyof typeof colors] || 'default';
  },

  // Fallback mock data when database is not available
  getMockProcessingJobs(): ProcessingJob[] {
    return [
      {
        id: '1',
        job_type: 'mbox_extraction',
        mailbox_id: 'mb_1',
        mailbox_name: 'Marketing Archive',
        status: 'running',
        total_records: 5000,
        processed_records: 3250,
        failed_records: 15,
        started_at: '2024-12-06T10:30:00Z',
        created_at: '2024-12-06T10:29:00Z',
        error_log: ['Failed to parse 3 emails with invalid headers', 'Encoding issue with 12 emails'],
        progress: 65
      },
      {
        id: '2',
        job_type: 'categorization',
        mailbox_id: 'mb_2',
        mailbox_name: 'Primary Business',
        status: 'completed',
        total_records: 8420,
        processed_records: 8420,
        failed_records: 0,
        started_at: '2024-12-06T08:15:00Z',
        completed_at: '2024-12-06T09:45:00Z',
        created_at: '2024-12-06T08:14:00Z',
        error_log: [],
        progress: 100
      },
      {
        id: '3',
        job_type: 'outlook_extraction',
        mailbox_id: 'mb_1',
        mailbox_name: 'Support Inbox',
        status: 'failed',
        total_records: 1200,
        processed_records: 245,
        failed_records: 955,
        started_at: '2024-12-05T16:00:00Z',
        completed_at: '2024-12-05T16:15:00Z',
        created_at: '2024-12-05T15:59:00Z',
        error_log: ['Authentication failed: Invalid credentials', 'Connection timeout after 5 minutes'],
        progress: 20
      },
      {
        id: '4',
        job_type: 'mbox_extraction',
        mailbox_id: 'mb_3',
        mailbox_name: 'Archive 2023',
        status: 'pending',
        total_records: 15000,
        processed_records: 0,
        failed_records: 0,
        created_at: '2024-12-06T11:00:00Z',
        error_log: [],
        progress: 0
      }
    ];
  }
};