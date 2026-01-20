/**
 * Error Service - Stage 2 Error Handling
 *
 * Provides API methods for fetching and managing processing errors
 */

import api from './apiClient';

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
   * Get error summary for a processing job
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

  /**
   * Get error type label for display
   */
  getErrorTypeLabel(errorType: string): string {
    const labels: Record<string, string> = {
      encoding_error: 'Encoding Error',
      parse_error: 'Parse Error',
      timeout_error: 'Timeout',
      connection_error: 'Connection Error',
      duplicate_error: 'Duplicate',
      memory_error: 'Memory Error',
      permission_error: 'Permission Error',
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
      duplicate_error: 'cyan',
      memory_error: 'volcano',
      permission_error: 'purple',
      other_error: 'default',
    };
    return colors[errorType] || 'default';
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
