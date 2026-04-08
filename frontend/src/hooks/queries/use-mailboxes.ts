import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { mailboxService, Mailbox } from '../../services/mailboxService';
import { dashboardService } from '../../services/dashboardService';

const MAILBOX_KEY = ['mailboxes'] as const;
const PROCESSING_JOBS_KEY = ['processing-jobs'] as const;

/** All mailboxes — auto-refetch every 30s */
export function useMailboxes() {
  return useQuery({
    queryKey: MAILBOX_KEY,
    queryFn: () => mailboxService.getMailboxes(),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

/** Active processing jobs — poll every 5s */
export function useProcessingJobs(enabled = true) {
  return useQuery({
    queryKey: PROCESSING_JOBS_KEY,
    queryFn: () => dashboardService._fetchProcessingJobs(),
    staleTime: 3_000,
    refetchInterval: enabled ? 5_000 : false,
  });
}

/** Invalidate mailbox cache after mutations */
export function useInvalidateMailboxes() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: MAILBOX_KEY });
    qc.invalidateQueries({ queryKey: PROCESSING_JOBS_KEY });
  };
}
