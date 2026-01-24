/**
 * Error Service - Stage 2 Error Handling
 *
 * Provides API methods for fetching and managing processing errors.
 *
 * Two types of errors:
 * 1. Job Errors (job_errors table) - ALL errors: download, extraction, processing, etc.
 * 2. Failed Emails (emails table) - Email-specific failures with retry capability
 */

import api from './apiClient';

// =========================================================================
// Job Errors (from job_errors table) - Comprehensive error logging
// =========================================================================

export interface JobError {
  id: string;
  error_phase: string;  // download, extraction, normalization, tagging, database, categorization
  error_type: string;   // encoding_error, parse_error, network_error, etc.
  error_severity: string;  // warning, error, critical
  error_message: string;
  error_stack?: string;
  context_type?: string;  // file, chunk, email, batch
  context_id?: string;
  context_details?: Record<string, any>;
  is_retryable: boolean;
  retry_count: number;
  resolved_at?: string;
  created_at: string;
}

export interface JobErrorsResponse {
  job_id: string;
  total_errors: number;
  unresolved_errors: number;
  errors: JobError[];
  has_more: boolean;
}

export interface JobErrorsSummary {
  total_errors: number;
  unresolved_errors: number;
  retryable_errors: number;
  by_phase: Record<string, number>;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  recent_errors: Array<{
    id: string;
    phase: string;
    type: string;
    severity: string;
    message: string;
    context_type?: string;
    context_id?: string;
    created_at: string;
  }>;
}

// =========================================================================
// Failed Emails (from emails table) - Legacy email-specific errors
// =========================================================================

export interface FailedEmail {
  id: string;
  message_id?: string;
  subject?: string;
  sender_email?: string;
  sent_date?: string;
  processing_error?: string;
  processing_attempts: number;
  last_processing_attempt?: string;
}

export interface ErrorType {
  count: number;
  description: string;
}

export interface ErrorSummary {
  total_errors: number;
  error_types: Record<string, ErrorType | number>;
  sample_errors: Array<{
    error_type: string;
    error_message: string;
    timestamp: string;
    message_id?: string;
    subject?: string;
    sender_email?: string;
  }>;
  has_more_errors: boolean;
}

export interface FailedEmailsResponse {
  job_id: string;
  mailbox_id: string;
  total_failed: number;
  emails: FailedEmail[];
  has_more: boolean;
}

export interface RetryResponse {
  job_id: string;
  mailbox_id: string;
  emails_reset: number;
  message: string;
}

export const errorService = {
  // =========================================================================
  // Job Errors API (from job_errors table) - ALL error types
  // =========================================================================

  /**
   * Get all job errors (download, extraction, processing, etc.)
   */
  async getJobErrors(
    jobId: string,
    options: {
      phase?: string;
      error_type?: string;
      unresolved_only?: boolean;
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<JobErrorsResponse> {
    const params = new URLSearchParams();
    if (options.phase) params.append('phase', options.phase);
    if (options.error_type) params.append('error_type', options.error_type);
    if (options.unresolved_only) params.append('unresolved_only', 'true');
    params.append('limit', String(options.limit || 50));
    params.append('offset', String(options.offset || 0));

    const result = await api.get<JobErrorsResponse>(
      `/processing-jobs/${jobId}/job-errors?${params.toString()}`
    );
    if (!result) {
      throw new Error('Failed to fetch job errors');
    }
    return result;
  },

  /**
   * Get comprehensive job errors summary
   */
  async getJobErrorsSummary(jobId: string): Promise<JobErrorsSummary> {
    const result = await api.get<JobErrorsSummary>(
      `/processing-jobs/${jobId}/job-errors/summary`
    );
    if (!result) {
      throw new Error('Failed to fetch job errors summary');
    }
    return result;
  },

  /**
   * Mark a job error as resolved
   */
  async resolveJobError(
    jobId: string,
    errorId: string,
    resolutionType: string = 'manual_fix'
  ): Promise<{ success: boolean; error_id: string; resolution_type: string }> {
    const result = await api.post<{ success: boolean; error_id: string; resolution_type: string }>(
      `/processing-jobs/${jobId}/job-errors/${errorId}/resolve?resolution_type=${resolutionType}`
    );
    if (!result) {
      throw new Error('Failed to resolve job error');
    }
    return result;
  },

  // =========================================================================
  // Failed Emails API (from emails table) - Legacy email-specific errors
  // =========================================================================

  /**
   * Get failed emails for a processing job
   */
  async getProcessingErrors(
    jobId: string,
    limit: number = 50,
    offset: number = 0
  ): Promise<FailedEmailsResponse> {
    const result = await api.get<FailedEmailsResponse>(
      `/processing-jobs/${jobId}/errors?limit=${limit}&offset=${offset}`
    );
    if (!result) {
      throw new Error('Failed to fetch processing errors');
    }
    return result;
  },

  /**
   * Get error summary for a processing job (legacy)
   */
  async getErrorSummary(jobId: string): Promise<ErrorSummary> {
    const result = await api.get<ErrorSummary>(
      `/processing-jobs/${jobId}/errors/summary`
    );
    if (!result) {
      throw new Error('Failed to fetch error summary');
    }
    return result;
  },

  /**
   * Retry failed emails for a processing job
   */
  async retryFailedEmails(
    jobId: string,
    maxAttempts: number = 3
  ): Promise<RetryResponse> {
    const result = await api.post<RetryResponse>(
      `/processing-jobs/${jobId}/retry-failed?max_attempts=${maxAttempts}`
    );
    if (!result) {
      throw new Error('Failed to retry failed emails');
    }
    return result;
  },

  // =========================================================================
  // Display Helpers
  // =========================================================================

  /**
   * Get error type label for display
   */
  getErrorTypeLabel(errorType: string): string {
    const labels: Record<string, string> = {
      encoding_error: 'Encoding Error',
      parse_error: 'Parse Error',
      timeout_error: 'Timeout',
      connection_error: 'Connection Error',
      network_error: 'Network Error',
      auth_error: 'Auth Error',
      duplicate_error: 'Duplicate',
      memory_error: 'Memory Error',
      permission_error: 'Permission Error',
      file_error: 'File Error',
      chunk_error: 'Chunk Error',
      validation_error: 'Validation Error',
      other_error: 'Other Error',
    };
    return labels[errorType] || errorType;
  },

  /**
   * Get error type color for display
   */
  getErrorTypeColor(errorType: string): string {
    const colors: Record<string, string> = {
      encoding_error: 'orange',
      parse_error: 'red',
      timeout_error: 'gold',
      connection_error: 'magenta',
      network_error: 'blue',
      auth_error: 'volcano',
      duplicate_error: 'cyan',
      memory_error: 'volcano',
      permission_error: 'purple',
      file_error: 'geekblue',
      chunk_error: 'lime',
      validation_error: 'warning',
      other_error: 'default',
    };
    return colors[errorType] || 'default';
  },

  /**
   * Get error phase label for display
   */
  getErrorPhaseLabel(phase: string): string {
    const labels: Record<string, string> = {
      download: 'Download',
      extraction: 'Extraction',
      normalization: 'Normalization',
      tagging: 'Tagging',
      database: 'Database',
      categorization: 'Categorization',
    };
    return labels[phase] || phase;
  },

  /**
   * Get error phase color for display
   */
  getErrorPhaseColor(phase: string): string {
    const colors: Record<string, string> = {
      download: 'blue',
      extraction: 'cyan',
      normalization: 'green',
      tagging: 'purple',
      database: 'orange',
      categorization: 'magenta',
    };
    return colors[phase] || 'default';
  },

  /**
   * Get error severity label for display
   */
  getErrorSeverityLabel(severity: string): string {
    const labels: Record<string, string> = {
      warning: 'Warning',
      error: 'Error',
      critical: 'Critical',
    };
    return labels[severity] || severity;
  },

  /**
   * Get error severity color for display
   */
  getErrorSeverityColor(severity: string): string {
    const colors: Record<string, string> = {
      warning: 'gold',
      error: 'red',
      critical: 'volcano',
    };
    return colors[severity] || 'default';
  },

  /**
   * Format error message for display (truncate if too long)
   */
  formatErrorMessage(message: string, maxLength: number = 100): string {
    if (!message) return 'No error message';
    if (message.length <= maxLength) return message;
    return message.substring(0, maxLength) + '...';
  },

  /**
   * Classify error type from error message
   */
  classifyError(errorMessage: string): string {
    if (!errorMessage) return 'other_error';

    const errorLower = errorMessage.toLowerCase();

    if (errorLower.includes('encoding') || errorLower.includes('decode') || errorLower.includes('codec')) {
      return 'encoding_error';
    }
    if (errorLower.includes('parse') || errorLower.includes('parsing')) {
      return 'parse_error';
    }
    if (errorLower.includes('timeout') || errorLower.includes('timed out')) {
      return 'timeout_error';
    }
    if (errorLower.includes('connection') || errorLower.includes('connect')) {
      return 'connection_error';
    }
    if (errorLower.includes('duplicate') || errorLower.includes('unique')) {
      return 'duplicate_error';
    }
    if (errorLower.includes('memory') || errorLower.includes('oom')) {
      return 'memory_error';
    }
    if (errorLower.includes('permission') || errorLower.includes('access')) {
      return 'permission_error';
    }

    return 'other_error';
  },
};
