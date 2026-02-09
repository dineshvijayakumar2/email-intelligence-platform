/**
 * useJobUpdates Hook
 *
 * Subscribes to real-time job updates via WebSocket with automatic
 * fallback to polling when WebSocket is disconnected.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import { JobUpdate } from '../services/websocketService';
import { processingService, ProcessingJob } from '../services/processingService';

interface UseJobUpdatesOptions {
  /** Subscribe to a specific job */
  jobId?: string;
  /** Subscribe to all jobs for a mailbox */
  mailboxId?: string;
  /** Subscribe to all jobs (default if no jobId or mailboxId) */
  allJobs?: boolean;
  /** Polling interval when WebSocket is disconnected (ms, default: 5000) */
  fallbackPollingMs?: number;
  /** Enable/disable the hook (default: true) */
  enabled?: boolean;
}

interface UseJobUpdatesResult {
  /** Current list of jobs */
  jobs: ProcessingJob[];
  /** Whether initial load is in progress */
  isLoading: boolean;
  /** Whether receiving real-time updates (true) or polling (false) */
  isRealtime: boolean;
  /** Last error if any */
  error: Error | null;
  /** Manually refresh jobs */
  refresh: () => Promise<void>;
}

/**
 * Merge a WebSocket job update into the existing jobs array.
 */
function mergeJobUpdate(jobs: ProcessingJob[], update: JobUpdate): ProcessingJob[] {
  const index = jobs.findIndex(j => j.id === update.job_id);

  const updatedJob: Partial<ProcessingJob> = {
    id: update.job_id,
    mailbox_id: update.mailbox_id,
    status: update.status,
    processed_records: update.processed_records,
    failed_records: update.failed_records,
    filtered_records: update.filtered_records,
    total_records: update.total_records,
    // Calculated fields
    progress: update.total_records > 0
      ? Math.round((update.processed_records / update.total_records) * 100)
      : 0,
  };

  if (index >= 0) {
    // Update existing job
    const newJobs = [...jobs];
    newJobs[index] = { ...newJobs[index], ...updatedJob };
    return newJobs;
  } else {
    // New job - prepend to list
    return [updatedJob as ProcessingJob, ...jobs];
  }
}

export function useJobUpdates(options: UseJobUpdatesOptions = {}): UseJobUpdatesResult {
  const {
    jobId,
    mailboxId,
    allJobs = !jobId && !mailboxId,
    fallbackPollingMs = 5000,
    enabled = true,
  } = options;

  const { isConnected, subscribe } = useWebSocket();
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const isMountedRef = useRef(true);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevMailboxIdRef = useRef<string | undefined>(mailboxId);

  // Clear jobs and show loading when mailboxId changes
  useEffect(() => {
    if (prevMailboxIdRef.current !== mailboxId) {
      setJobs([]);
      setIsLoading(true);
      prevMailboxIdRef.current = mailboxId;
    }
  }, [mailboxId]);

  // Load jobs from API
  const loadJobs = useCallback(async (showLoading = false) => {
    if (!enabled) return;

    try {
      if (showLoading && isMountedRef.current) {
        setIsLoading(true);
      }

      const jobsData = await processingService.getProcessingJobs(true, mailboxId);

      if (isMountedRef.current) {
        // Filter by jobId if specified
        if (jobId) {
          setJobs(jobsData.filter(j => j.id === jobId));
        } else {
          setJobs(jobsData);
        }
        setError(null);
      }
    } catch (err) {
      if (isMountedRef.current) {
        console.error('[useJobUpdates] Failed to load jobs:', err);
        setError(err instanceof Error ? err : new Error('Failed to load jobs'));
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [enabled, jobId, mailboxId]);

  // Initial load
  useEffect(() => {
    isMountedRef.current = true;
    if (enabled) {
      loadJobs(true);
    }

    return () => {
      isMountedRef.current = false;
    };
  }, [enabled, loadJobs]);

  // WebSocket subscription
  useEffect(() => {
    if (!enabled || !isConnected) return;

    // Determine which room to subscribe to
    const room = jobId
      ? `jobs:${jobId}`
      : mailboxId
        ? `mailbox:${mailboxId}`
        : 'jobs:all';

    const unsubscribe = subscribe(room, (update: JobUpdate) => {
      if (!isMountedRef.current) return;

      // Apply filter if needed
      if (jobId && update.job_id !== jobId) return;
      if (mailboxId && update.mailbox_id !== mailboxId) return;

      setJobs(prevJobs => mergeJobUpdate(prevJobs, update));
    });

    return unsubscribe;
  }, [enabled, isConnected, subscribe, jobId, mailboxId]);

  // Fallback polling when WebSocket is disconnected
  useEffect(() => {
    if (!enabled) return;

    if (isConnected) {
      // WebSocket connected - stop polling
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    } else {
      // WebSocket disconnected - start polling
      if (!pollingIntervalRef.current) {
        pollingIntervalRef.current = setInterval(() => {
          if (isMountedRef.current) {
            loadJobs(false);
          }
        }, fallbackPollingMs);
      }
    }

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [enabled, isConnected, fallbackPollingMs, loadJobs]);

  // Refresh function
  const refresh = useCallback(async () => {
    await loadJobs(true);
  }, [loadJobs]);

  return {
    jobs,
    isLoading,
    isRealtime: isConnected,
    error,
    refresh,
  };
}

export default useJobUpdates;
