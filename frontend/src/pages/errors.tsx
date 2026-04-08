/**
 * Errors Page - Stage 2 Error Handling
 *
 * Dedicated page to view all processing errors across all jobs
 * with filtering, search, and retry capabilities.
 *
 * Two views:
 * 1. All Errors - From job_errors table (download, extraction, processing, etc.)
 * 2. Failed Emails - From emails table (email-specific failures with retry)
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  AlertCircle,
  RefreshCw,
  Info,
  Home,
  AlertTriangle,
  CheckCircle2,
  Cloud,
  File,
  Bot,
  ChevronDown,
  ChevronRight,
  Spinner,
} from '@/lib/icons';
import { Database, Tags, RefreshCw as SyncIcon } from 'lucide-react';
import { Link, useSearchParams, useParams, useNavigate } from 'react-router-dom';
import {
  errorService,
  ErrorSummary,
  FailedEmail,
  JobError,
  JobErrorsSummary,
  JobErrorLog,
} from '../services/errorService';
import { dashboardService } from '../services/dashboardService';
import { formatDateTime, formatDate } from '../utils/dateUtils';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton, EmptyState } from '@/components/ui/empty-state';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { notify } from '@/lib/toast';
import { cn } from '@/lib/utils';

interface ProcessingJob {
  id: string;
  mailbox_id: string;
  status: string;
  total_records: number;
  processed_records: number;
  failed_records: number;
  created_at: string;
  mailbox_name?: string;
}

interface MailboxOption {
  id: string;
  name: string;
}

// Phase icon mapping
const phaseIcons: Record<string, React.ReactNode> = {
  download: <Cloud className="h-3.5 w-3.5" />,
  extraction: <File className="h-3.5 w-3.5" />,
  normalization: <SyncIcon className="h-3.5 w-3.5" />,
  tagging: <Tags className="h-3.5 w-3.5" />,
  database: <Database className="h-3.5 w-3.5" />,
  categorization: <Bot className="h-3.5 w-3.5" />,
};

// Map antd color names to StatusBadge variants
function phaseToVariant(color: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple'> = {
    blue: 'info',
    green: 'success',
    orange: 'warning',
    red: 'danger',
    gold: 'warning',
    purple: 'purple',
    cyan: 'info',
    default: 'neutral',
    magenta: 'danger',
    volcano: 'danger',
    geekblue: 'info',
    lime: 'success',
  };
  return map[color] || 'neutral';
}

// Collapsible section component
function CollapsibleSection({
  header,
  children,
  defaultOpen = false,
}: {
  header: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border bg-white">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
        {header}
      </button>
      {open && <div className="border-t px-4 py-3">{children}</div>}
    </div>
  );
}

const ErrorsPage: React.FC = () => {
  // URL params for mailbox filtering
  const { mailboxId: mailboxIdFromUrl } = useParams<{ mailboxId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const jobIdFromUrl = searchParams.get('jobId');
  const tabFromUrl = searchParams.get('tab') || 'all';

  // State
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [mailboxes, setMailboxes] = useState<MailboxOption[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(jobIdFromUrl);
  const [selectedMailboxId, setSelectedMailboxId] = useState<string | null>(mailboxIdFromUrl || null);
  const [activeTab, setActiveTab] = useState<string>(tabFromUrl);

  // Job Errors state (from job_errors table)
  const [jobErrors, setJobErrors] = useState<JobError[]>([]);
  const [jobErrorsSummary, setJobErrorsSummary] = useState<JobErrorsSummary | null>(null);
  const [totalJobErrors, setTotalJobErrors] = useState(0);
  const [hasMoreJobErrors, setHasMoreJobErrors] = useState(false);
  const [selectedJobError, setSelectedJobError] = useState<JobError | null>(null);
  const [phaseFilter, setPhaseFilter] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  // Failed Emails state (from emails table - legacy)
  const [errors, setErrors] = useState<FailedEmail[]>([]);
  const [errorSummary, setErrorSummary] = useState<ErrorSummary | null>(null);
  const [totalErrors, setTotalErrors] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [selectedError, setSelectedError] = useState<FailedEmail | null>(null);

  // Batch Error Log state (from processing_jobs.error_log)
  const [errorLog, setErrorLog] = useState<JobErrorLog | null>(null);

  // Load all jobs (any job may have errors logged, even if not marked as failed)
  const loadJobsWithErrors = useCallback(async () => {
    setLoading(true);
    try {
      const allJobs: ProcessingJob[] = await dashboardService._fetchProcessingJobs();

      // Show all jobs with valid mailbox_id (any job may have errors logged)
      const validJobs = allJobs.filter(j => j.mailbox_id);
      setJobs(validJobs);

      // Get unique mailboxes from these jobs
      const mailboxIds = [...new Set(validJobs.map(j => j.mailbox_id))];
      const mailboxList: MailboxOption[] = [];
      for (const mbId of mailboxIds) {
        if (!mbId) continue;
        const job = validJobs.find(j => j.mailbox_id === mbId);
        if (job?.mailbox_name) {
          mailboxList.push({ id: mbId, name: job.mailbox_name });
        }
      }
      setMailboxes(mailboxList);
    } catch {
      notify.error('Failed to load processing jobs');
    } finally {
      setLoading(false);
    }
  }, []);

  // Load job errors from job_errors table (ALL error types)
  const loadJobErrors = useCallback(async (jobId: string, phase?: string | null, errorType?: string | null) => {
    setLoading(true);
    try {
      const [errorsData, summaryData] = await Promise.all([
        errorService.getJobErrors(jobId, {
          phase: phase || undefined,
          error_type: errorType || undefined,
          limit: 100,
          offset: 0,
        }),
        errorService.getJobErrorsSummary(jobId),
      ]);

      setJobErrors(errorsData.errors || []);
      setTotalJobErrors(errorsData.total_errors || 0);
      setHasMoreJobErrors(errorsData.has_more || false);
      setJobErrorsSummary(summaryData);
    } catch {
      // Silently handle errors - the batch error log will still show
      setJobErrors([]);
      setTotalJobErrors(0);
      setHasMoreJobErrors(false);
      setJobErrorsSummary(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load failed emails from emails table (legacy)
  const loadErrors = useCallback(async (jobId: string) => {
    setLoading(true);
    try {
      const [errorsData, summaryData] = await Promise.all([
        errorService.getProcessingErrors(jobId, 100, 0),
        errorService.getErrorSummary(jobId),
      ]);

      setErrors(errorsData.emails || []);
      setTotalErrors(errorsData.total_failed || 0);
      setHasMore(errorsData.has_more || false);
      setErrorSummary(summaryData);
    } catch {
      // Silently handle errors - the batch error log will still show
      setErrors([]);
      setTotalErrors(0);
      setHasMore(false);
      setErrorSummary(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load batch error log from processing_jobs.error_log
  const loadErrorLog = useCallback(async (jobId: string) => {
    try {
      const logData = await errorService.getJobErrorLog(jobId);
      setErrorLog(logData);
    } catch {
      setErrorLog(null);
    }
  }, []);

  // Initial load - run once on mount
  useEffect(() => {
    loadJobsWithErrors();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-select job from URL when jobs are loaded
  useEffect(() => {
    if (jobIdFromUrl && jobs.length > 0 && jobs.some(j => j.id === jobIdFromUrl)) {
      setSelectedJobId(jobIdFromUrl);
    }
  }, [jobIdFromUrl, jobs]);

  // Auto-select mailbox from URL param when jobs are loaded
  useEffect(() => {
    if (mailboxIdFromUrl && jobs.length > 0) {
      setSelectedMailboxId(mailboxIdFromUrl);
      // Find first job with errors for this mailbox
      const jobsForMailbox = jobs.filter(j => j.mailbox_id === mailboxIdFromUrl);
      const jobWithErrors = jobsForMailbox.find(j => j.failed_records > 0) || jobsForMailbox[0];
      if (jobWithErrors && !selectedJobId) {
        setSelectedJobId(jobWithErrors.id);
      }
    }
  }, [mailboxIdFromUrl, jobs, selectedJobId]);

  // Load errors when job selected
  useEffect(() => {
    if (selectedJobId) {
      // Load job errors, failed emails, and batch error log
      loadJobErrors(selectedJobId, phaseFilter, typeFilter);
      loadErrors(selectedJobId);
      loadErrorLog(selectedJobId);
      // Update URL
      setSearchParams({ jobId: selectedJobId, tab: activeTab });
    } else {
      // Reset all states
      setJobErrors([]);
      setJobErrorsSummary(null);
      setTotalJobErrors(0);
      setErrors([]);
      setErrorSummary(null);
      setTotalErrors(0);
      setErrorLog(null);
      setSearchParams({});
    }
  }, [selectedJobId, loadJobErrors, loadErrors, loadErrorLog, setSearchParams, phaseFilter, typeFilter, activeTab]);

  // Handle job selection
  const handleJobSelect = (jobId: string) => {
    setSelectedJobId(jobId);
    setSelectedMailboxId(null);
  };

  // Handle mailbox filter
  const handleMailboxFilter = (mailboxId: string | null) => {
    setSelectedMailboxId(mailboxId);
    if (mailboxId) {
      // Navigate to URL with mailbox filter
      navigate(`/manage/errors/${mailboxId}`);
      // Find first job with errors for this mailbox
      const job = jobs.find(j => j.mailbox_id === mailboxId && j.failed_records > 0);
      if (job) {
        setSelectedJobId(job.id);
      }
    } else {
      // Clear mailbox filter - navigate to base errors page
      navigate('/errors');
      setSelectedJobId(null);
    }
  };

  // Handle tab change
  const handleTabChange = (key: string) => {
    setActiveTab(key);
    if (selectedJobId) {
      setSearchParams({ jobId: selectedJobId, tab: key });
    }
  };

  // Handle phase filter change
  const handlePhaseFilterChange = (phase: string | null) => {
    setPhaseFilter(phase);
    if (selectedJobId) {
      loadJobErrors(selectedJobId, phase, typeFilter);
    }
  };

  // Handle type filter change
  const handleTypeFilterChange = (errorType: string | null) => {
    setTypeFilter(errorType);
    if (selectedJobId) {
      loadJobErrors(selectedJobId, phaseFilter, errorType);
    }
  };

  // Handle resolve job error
  const handleResolveJobError = async (errorId: string) => {
    if (!selectedJobId) return;
    try {
      await errorService.resolveJobError(selectedJobId, errorId, 'manual_fix');
      notify.success('Error marked as resolved');
      loadJobErrors(selectedJobId, phaseFilter, typeFilter);
    } catch {
      notify.error('Failed to resolve error');
    }
  };

  // Handle retry
  const handleRetry = async () => {
    if (!selectedJobId) return;

    setRetrying(true);
    try {
      const result = await errorService.retryFailedEmails(selectedJobId, 3);
      notify.success(result.message);

      if (result.emails_reset > 0) {
        // Refresh data
        await loadErrors(selectedJobId);
        await loadJobsWithErrors();
      }
    } catch {
      notify.error('Failed to retry failed emails');
    } finally {
      setRetrying(false);
    }
  };

  // Load more job errors
  const loadMoreJobErrors = async () => {
    if (!selectedJobId) return;

    setLoading(true);
    try {
      const moreErrors = await errorService.getJobErrors(selectedJobId, {
        phase: phaseFilter || undefined,
        error_type: typeFilter || undefined,
        limit: 100,
        offset: jobErrors.length,
      });
      setJobErrors([...jobErrors, ...moreErrors.errors]);
      setHasMoreJobErrors(moreErrors.has_more);
    } catch {
      // Silently handle
    } finally {
      setLoading(false);
    }
  };

  // Load more failed emails
  const loadMore = async () => {
    if (!selectedJobId) return;

    setLoading(true);
    try {
      const moreErrors = await errorService.getProcessingErrors(
        selectedJobId,
        100,
        errors.length
      );
      setErrors([...errors, ...moreErrors.emails]);
      setHasMore(moreErrors.has_more);
    } catch {
      // Silently handle
    } finally {
      setLoading(false);
    }
  };

  // Calculate stats
  // Filter jobs by mailbox if selected (computed first so stats can use it)
  const filteredJobs = selectedMailboxId
    ? jobs.filter(j => j.mailbox_id === selectedMailboxId)
    : jobs;

  // When coming from a specific mailbox URL, scope stats to that mailbox
  const statsJobs = mailboxIdFromUrl ? filteredJobs : jobs;
  const totalFailedAcrossJobs = statsJobs.reduce((sum, j) => sum + (j.failed_records || 0), 0);
  const failedJobsCount = statsJobs.filter(j => j.status === 'failed' || j.failed_records > 0).length;
  const jobsWithErrorsCount = statsJobs.length;

  return (
    <PageShell>
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-slate-500 mb-4">
        <Link to="/" className="flex items-center gap-1 hover:text-slate-700 transition-colors">
          <Home className="h-3.5 w-3.5" />
          <span>Home</span>
        </Link>
        <span className="text-slate-300">/</span>
        <Link to="/processing" className="hover:text-slate-700 transition-colors">
          Processing
        </Link>
        <span className="text-slate-300">/</span>
        <span className="flex items-center gap-1 text-slate-700 font-medium">
          <AlertCircle className="h-3.5 w-3.5" />
          Errors
        </span>
      </nav>

      {/* Header */}
      <PageHeader
        title="Processing Errors"
        description="View and manage processing errors across all jobs"
        actions={
          <button
            className="inline-flex items-center gap-2 rounded-lg border bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors disabled:opacity-50"
            onClick={() => {
              loadJobsWithErrors();
              if (selectedJobId) {
                loadJobErrors(selectedJobId, phaseFilter, typeFilter);
                loadErrors(selectedJobId);
                loadErrorLog(selectedJobId);
              }
            }}
            disabled={loading}
          >
            {loading ? <Spinner className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </button>
        }
      />

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="rounded-lg border bg-white shadow-sm p-5">
          <p className="text-xs font-medium text-slate-500 mb-1">
            {mailboxIdFromUrl ? 'Jobs with Issues' : 'Total Jobs'}
          </p>
          <p className={cn(
            'text-2xl font-semibold',
            (mailboxIdFromUrl ? failedJobsCount : jobsWithErrorsCount) > 0
              ? 'text-primary'
              : 'text-emerald-600'
          )}>
            <AlertTriangle className="inline h-5 w-5 mr-1.5 -mt-0.5" />
            {(mailboxIdFromUrl ? failedJobsCount : jobsWithErrorsCount).toLocaleString('en-AU')}
          </p>
        </div>
        <div className="rounded-lg border bg-white shadow-sm p-5">
          <p className="text-xs font-medium text-slate-500 mb-1">Failed Emails</p>
          <p className={cn(
            'text-2xl font-semibold',
            totalFailedAcrossJobs > 0 ? 'text-red-600' : 'text-emerald-600'
          )}>
            {totalFailedAcrossJobs.toLocaleString('en-AU')}
          </p>
          {totalFailedAcrossJobs === 0 && failedJobsCount > 0 && (
            <p className="text-xs text-slate-400 mt-0.5">(see error log)</p>
          )}
        </div>
        {selectedJobId && jobErrorsSummary && (
          <>
            <div className="rounded-lg border bg-white shadow-sm p-5">
              <p className="text-xs font-medium text-slate-500 mb-1">All Job Errors</p>
              <p className={cn(
                'text-2xl font-semibold',
                jobErrorsSummary.total_errors > 0 ? 'text-red-600' : 'text-emerald-600'
              )}>
                {jobErrorsSummary.total_errors.toLocaleString('en-AU')}
              </p>
              {jobErrorsSummary.unresolved_errors > 0 && (
                <p className="text-xs text-slate-400 mt-0.5">
                  ({jobErrorsSummary.unresolved_errors.toLocaleString('en-AU')} unresolved)
                </p>
              )}
            </div>
            <div className="rounded-lg border bg-white shadow-sm p-5">
              <p className="text-xs font-medium text-slate-500 mb-1">By Phase</p>
              <p className="text-2xl font-semibold text-slate-900">
                {Object.keys(jobErrorsSummary.by_phase || {}).length}
              </p>
              <p className="text-xs text-slate-400 mt-0.5">phases</p>
            </div>
          </>
        )}
      </div>

      {/* Filters */}
      <div className="rounded-lg border bg-white shadow-sm p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">Filter by Mailbox</label>
            <select
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              value={selectedMailboxId || ''}
              onChange={(e) => handleMailboxFilter(e.target.value || null)}
            >
              <option value="">All Mailboxes</option>
              {mailboxes.map(mb => (
                <option key={mb.id} value={mb.id}>
                  {mb.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">Select Job</label>
            <select
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              value={selectedJobId || ''}
              onChange={(e) => handleJobSelect(e.target.value)}
            >
              <option value="">Select a job to view errors</option>
              {filteredJobs.map(job => (
                <option key={job.id} value={job.id}>
                  {job.mailbox_name || 'Unknown'} -{' '}
                  {job.failed_records > 0
                    ? `${job.failed_records} failed emails`
                    : job.status === 'failed'
                      ? 'job failed (see error log)'
                      : `${job.failed_records} failed`
                  }{' '}({formatDate(job.created_at)})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Error Breakdown by Phase (Job Errors) */}
      {selectedJobId && jobErrorsSummary && Object.keys(jobErrorsSummary.by_phase || {}).length > 0 && (
        <div className="rounded-lg border bg-white shadow-sm p-5 mb-6">
          <p className="text-sm font-semibold text-slate-700 mb-4">Errors by Phase</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {Object.entries(jobErrorsSummary.by_phase).map(([phase, count]) => (
              <button
                key={phase}
                type="button"
                className={cn(
                  'rounded-lg border p-3 text-left transition-all hover:shadow-md cursor-pointer',
                  phaseFilter === phase
                    ? 'border-primary bg-primary-subtle ring-1 ring-primary'
                    : 'bg-white hover:bg-slate-50'
                )}
                onClick={() => handlePhaseFilterChange(phaseFilter === phase ? null : phase)}
              >
                <div className="flex items-center gap-1.5 mb-2">
                  {phaseIcons[phase]}
                  <StatusBadge variant={phaseToVariant(errorService.getErrorPhaseColor(phase))} size="sm">
                    {errorService.getErrorPhaseLabel(phase)}
                  </StatusBadge>
                </div>
                <p className={cn(
                  'text-xl font-semibold',
                  phaseFilter === phase ? 'text-primary' : 'text-slate-900'
                )}>
                  {count.toLocaleString('en-AU')}
                </p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Batch Error Log (from processing_jobs.error_log) */}
      {selectedJobId && errorLog && errorLog.error_count > 0 && (
        <div className="rounded-lg border bg-white shadow-sm p-5 mb-6">
          <p className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            Batch Processing Error Log ({errorLog.failed_records} failed emails)
          </p>

          {/* Error Analysis Breakdown */}
          {errorLog.error_analysis && Object.keys(errorLog.error_analysis).length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
              {Object.entries(errorLog.error_analysis).map(([errorType, count]) => (
                <div key={errorType} className="rounded-lg border bg-white p-3">
                  <StatusBadge
                    variant={
                      errorType === 'timeout' ? 'warning' :
                      errorType === 'duplicate_in_batch' ? 'warning' :
                      errorType === 'constraint_violation' ? 'danger' : 'neutral'
                    }
                    size="sm"
                    className="mb-2"
                  >
                    {errorType === 'duplicate_in_batch' ? 'Duplicate in Batch' :
                     errorType === 'constraint_violation' ? 'Constraint Violation' :
                     errorType.charAt(0).toUpperCase() + errorType.slice(1)}
                  </StatusBadge>
                  <p className="text-lg font-semibold text-slate-900">{count.toLocaleString('en-AU')}</p>
                </div>
              ))}
            </div>
          )}

          {/* Error Messages */}
          {errorLog.errors && errorLog.errors.length > 0 && (
            <div className="mb-4">
              <CollapsibleSection header={`View Error Messages (${errorLog.errors.length} shown)`}>
                <div className="max-h-[200px] overflow-auto space-y-2">
                  {errorLog.errors.map((err, idx) => (
                    <div
                      key={idx}
                      className="rounded bg-red-50 border border-red-200 p-2 text-xs text-red-700"
                    >
                      {err}
                    </div>
                  ))}
                </div>
              </CollapsibleSection>
            </div>
          )}

          {/* Failed Message IDs */}
          {errorLog.failed_message_ids_count > 0 && (
            <CollapsibleSection
              header={`Failed Message IDs (${errorLog.failed_message_ids_count} total, showing ${errorLog.failed_message_ids_sample?.length || 0})`}
            >
              <div className="max-h-[200px] overflow-auto flex flex-wrap gap-1.5">
                {errorLog.failed_message_ids_sample?.map((msgId, idx) => (
                  <span
                    key={idx}
                    className="inline-block rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-600"
                  >
                    {msgId.length > 60 ? msgId.substring(0, 60) + '...' : msgId}
                  </span>
                ))}
              </div>
              {errorLog.failed_message_ids_count > (errorLog.failed_message_ids_sample?.length || 0) && (
                <p className="text-xs text-slate-400 mt-2">
                  ... and {errorLog.failed_message_ids_count - (errorLog.failed_message_ids_sample?.length || 0)} more
                </p>
              )}
            </CollapsibleSection>
          )}
        </div>
      )}

      {/* Errors Tabs */}
      <div className="rounded-lg border bg-white shadow-sm">
        {/* Tab bar */}
        <div className="flex border-b">
          <button
            type="button"
            className={cn(
              'flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === 'all'
                ? 'border-primary text-primary'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            )}
            onClick={() => handleTabChange('all')}
          >
            <AlertCircle className="h-4 w-4" />
            All Errors ({totalJobErrors.toLocaleString('en-AU')})
          </button>
          <button
            type="button"
            className={cn(
              'flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === 'emails'
                ? 'border-primary text-primary'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            )}
            onClick={() => handleTabChange('emails')}
          >
            <AlertTriangle className="h-4 w-4" />
            Failed Emails ({totalErrors.toLocaleString('en-AU')})
          </button>
        </div>

        <div className="p-4">
          {/* All Job Errors Tab */}
          {activeTab === 'all' && (
            <>
              {/* Filters for job errors */}
              {selectedJobId && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Filter by Phase</label>
                    <select
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                      value={phaseFilter || ''}
                      onChange={(e) => handlePhaseFilterChange(e.target.value || null)}
                    >
                      <option value="">All Phases</option>
                      <option value="download">Download</option>
                      <option value="extraction">Extraction</option>
                      <option value="normalization">Normalization</option>
                      <option value="tagging">Tagging</option>
                      <option value="database">Database</option>
                      <option value="categorization">Categorization</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Filter by Type</label>
                    <select
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                      value={typeFilter || ''}
                      onChange={(e) => handleTypeFilterChange(e.target.value || null)}
                    >
                      <option value="">All Types</option>
                      <option value="network_error">Network Error</option>
                      <option value="timeout_error">Timeout</option>
                      <option value="encoding_error">Encoding Error</option>
                      <option value="parse_error">Parse Error</option>
                      <option value="connection_error">Connection Error</option>
                      <option value="auth_error">Auth Error</option>
                      <option value="file_error">File Error</option>
                      <option value="chunk_error">Chunk Error</option>
                      <option value="other_error">Other</option>
                    </select>
                  </div>
                </div>
              )}

              {loading && jobErrors.length === 0 ? (
                <ContentSkeleton rows={5} />
              ) : !selectedJobId ? (
                <EmptyState
                  icon={<AlertCircle className="h-10 w-10" />}
                  title="No job selected"
                  description="Select a processing job above to view its errors"
                />
              ) : jobErrors.length === 0 ? (
                <EmptyState
                  icon={<CheckCircle2 className="h-10 w-10" />}
                  title="No errors found"
                  description="No errors found for this job"
                />
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[10%]">Phase</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[8%]">Severity</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[12%]">Type</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[30%]">Message</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[15%]">Context</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[12%]">Time</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[13%]"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {jobErrors.map((record) => (
                          <tr key={record.id} className="hover:bg-slate-50 transition-colors">
                            <td className="px-3 py-2.5">
                              <StatusBadge
                                variant={phaseToVariant(errorService.getErrorPhaseColor(record.error_phase))}
                                size="sm"
                                className="inline-flex items-center gap-1"
                              >
                                {phaseIcons[record.error_phase]}
                                {errorService.getErrorPhaseLabel(record.error_phase)}
                              </StatusBadge>
                            </td>
                            <td className="px-3 py-2.5">
                              <StatusBadge
                                variant={phaseToVariant(errorService.getErrorSeverityColor(record.error_severity))}
                                size="sm"
                              >
                                {errorService.getErrorSeverityLabel(record.error_severity)}
                              </StatusBadge>
                            </td>
                            <td className="px-3 py-2.5">
                              <StatusBadge
                                variant={phaseToVariant(errorService.getErrorTypeColor(record.error_type))}
                                size="sm"
                              >
                                {errorService.getErrorTypeLabel(record.error_type)}
                              </StatusBadge>
                            </td>
                            <td className="px-3 py-2.5">
                              <span
                                className="text-xs text-red-600 truncate block max-w-[300px]"
                                title={record.error_message}
                              >
                                {errorService.formatErrorMessage(record.error_message, 60)}
                              </span>
                            </td>
                            <td className="px-3 py-2.5">
                              <span className="text-xs text-slate-500 truncate block">
                                {record.context_type ? `${record.context_type}: ${record.context_id || 'N/A'}` : '-'}
                              </span>
                            </td>
                            <td className="px-3 py-2.5 text-xs text-slate-600">
                              {record.created_at ? formatDateTime(record.created_at) : 'Unknown'}
                            </td>
                            <td className="px-3 py-2.5">
                              <div className="flex items-center gap-1">
                                <button
                                  type="button"
                                  className="rounded p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                                  title="View Details"
                                  onClick={() => setSelectedJobError(record)}
                                >
                                  <Info className="h-4 w-4" />
                                </button>
                                {!record.resolved_at && (
                                  <button
                                    type="button"
                                    className="rounded p-1 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 transition-colors"
                                    title="Mark as Resolved"
                                    onClick={() => handleResolveJobError(record.id)}
                                  >
                                    <CheckCircle2 className="h-4 w-4" />
                                  </button>
                                )}
                                {record.resolved_at && (
                                  <StatusBadge variant="success" size="sm">Resolved</StatusBadge>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {hasMoreJobErrors && (
                    <div className="text-center mt-4">
                      <button
                        className="inline-flex items-center gap-2 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors disabled:opacity-50"
                        onClick={loadMoreJobErrors}
                        disabled={loading}
                      >
                        {loading && <Spinner className="h-4 w-4 animate-spin" />}
                        Load More ({(totalJobErrors - jobErrors.length).toLocaleString('en-AU')} remaining)
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          )}

          {/* Failed Emails Tab */}
          {activeTab === 'emails' && (
            <>
              {/* Error Type Breakdown */}
              {selectedJobId && errorSummary && errorSummary.error_types && Object.keys(errorSummary.error_types).length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
                  {Object.entries(errorSummary.error_types).map(([type, data]) => {
                    const count = typeof data === 'number' ? data : data.count;
                    return (
                      <div key={type} className="rounded-lg border bg-white p-3">
                        <StatusBadge
                          variant={phaseToVariant(errorService.getErrorTypeColor(type))}
                          size="sm"
                          className="mb-2"
                        >
                          {errorService.getErrorTypeLabel(type)}
                        </StatusBadge>
                        <p className="text-base font-semibold text-slate-900">{count.toLocaleString('en-AU')}</p>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Retry button */}
              {selectedJobId && totalErrors > 0 && (
                <div className="mb-4">
                  <button
                    className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-red-700 transition-colors disabled:opacity-50"
                    onClick={handleRetry}
                    disabled={retrying}
                    title="Reset failed emails to pending for retry (max 3 attempts per email)"
                  >
                    {retrying ? <Spinner className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    Retry Failed Emails ({totalErrors.toLocaleString('en-AU')})
                  </button>
                </div>
              )}

              {loading && errors.length === 0 ? (
                <ContentSkeleton rows={5} />
              ) : !selectedJobId ? (
                <EmptyState
                  icon={<AlertCircle className="h-10 w-10" />}
                  title="No job selected"
                  description="Select a processing job above to view its errors"
                />
              ) : errors.length === 0 ? (
                <EmptyState
                  icon={<CheckCircle2 className="h-10 w-10" />}
                  title="No failed emails"
                  description="No failed emails found for this job"
                />
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[25%]">Subject</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[20%]">From</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[12%]">Date</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[12%]">Error Type</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[20%]">Error</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[6%]">Attempts</th>
                          <th className="text-xs font-bold uppercase tracking-wider text-slate-600 text-left px-3 py-2.5 w-[5%]"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {errors.map((record) => {
                          const errorType = errorService.classifyError(record.processing_error);
                          return (
                            <tr key={record.id} className="hover:bg-slate-50 transition-colors">
                              <td className="px-3 py-2.5">
                                <span className="text-xs text-slate-700 truncate block max-w-[200px]">
                                  {record.subject || '(No Subject)'}
                                </span>
                              </td>
                              <td className="px-3 py-2.5">
                                <span className="text-xs text-slate-600 truncate block max-w-[150px]">
                                  {record.sender_email || 'Unknown'}
                                </span>
                              </td>
                              <td className="px-3 py-2.5 text-xs text-slate-600">
                                {record.sent_date ? formatDate(record.sent_date) : 'Unknown'}
                              </td>
                              <td className="px-3 py-2.5">
                                <StatusBadge
                                  variant={phaseToVariant(errorService.getErrorTypeColor(errorType))}
                                  size="sm"
                                >
                                  {errorService.getErrorTypeLabel(errorType)}
                                </StatusBadge>
                              </td>
                              <td className="px-3 py-2.5">
                                <span
                                  className="text-xs text-red-600 truncate block max-w-[200px]"
                                  title={record.processing_error}
                                >
                                  {errorService.formatErrorMessage(record.processing_error, 40)}
                                </span>
                              </td>
                              <td className="px-3 py-2.5">
                                <StatusBadge
                                  variant={record.processing_attempts >= 3 ? 'danger' : 'warning'}
                                  size="sm"
                                >
                                  {record.processing_attempts}
                                </StatusBadge>
                              </td>
                              <td className="px-3 py-2.5">
                                <button
                                  type="button"
                                  className="rounded p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                                  title="View Details"
                                  onClick={() => setSelectedError(record)}
                                >
                                  <Info className="h-4 w-4" />
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {hasMore && (
                    <div className="text-center mt-4">
                      <button
                        className="inline-flex items-center gap-2 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors disabled:opacity-50"
                        onClick={loadMore}
                        disabled={loading}
                      >
                        {loading && <Spinner className="h-4 w-4 animate-spin" />}
                        Load More ({(totalErrors - errors.length).toLocaleString('en-AU')} remaining)
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Error Detail Modal (Failed Emails) */}
      <Dialog open={!!selectedError} onOpenChange={() => setSelectedError(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Error Details</DialogTitle>
          </DialogHeader>

          {selectedError && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Subject</p>
                  <p className="text-sm text-slate-900">{selectedError.subject || '(No Subject)'}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">From</p>
                  <p className="text-sm text-slate-900">{selectedError.sender_email || 'Unknown'}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Message ID</p>
                  <code className="text-[11px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-700">
                    {selectedError.message_id || 'Unknown'}
                  </code>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Sent Date</p>
                  <p className="text-sm text-slate-900">
                    {selectedError.sent_date
                      ? formatDateTime(selectedError.sent_date)
                      : 'Unknown'}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Processing Attempts</p>
                  <StatusBadge
                    variant={selectedError.processing_attempts >= 3 ? 'danger' : 'warning'}
                  >
                    {selectedError.processing_attempts} attempts
                  </StatusBadge>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Last Attempt</p>
                  <p className="text-sm text-slate-900">
                    {selectedError.last_processing_attempt
                      ? formatDateTime(selectedError.last_processing_attempt)
                      : 'Unknown'}
                  </p>
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold text-slate-500 mb-1">Error Type</p>
                <StatusBadge
                  variant={phaseToVariant(errorService.getErrorTypeColor(errorService.classifyError(selectedError.processing_error || '')))}
                >
                  {errorService.getErrorTypeLabel(errorService.classifyError(selectedError.processing_error || ''))}
                </StatusBadge>
              </div>

              <div>
                <p className="text-xs font-semibold text-slate-500 mb-1">Error Message</p>
                <div className="rounded bg-red-50 border border-red-200 p-3 mt-1">
                  <p className="text-xs text-red-700 whitespace-pre-wrap">
                    {selectedError.processing_error || 'No error message'}
                  </p>
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <button
              className="inline-flex items-center rounded-lg border bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors"
              onClick={() => setSelectedError(null)}
            >
              Close
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Job Error Detail Modal */}
      <Dialog open={!!selectedJobError} onOpenChange={() => setSelectedJobError(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Job Error Details</DialogTitle>
          </DialogHeader>

          {selectedJobError && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Phase</p>
                  <StatusBadge
                    variant={phaseToVariant(errorService.getErrorPhaseColor(selectedJobError.error_phase))}
                    className="inline-flex items-center gap-1"
                  >
                    {phaseIcons[selectedJobError.error_phase]}
                    {errorService.getErrorPhaseLabel(selectedJobError.error_phase)}
                  </StatusBadge>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Type</p>
                  <StatusBadge
                    variant={phaseToVariant(errorService.getErrorTypeColor(selectedJobError.error_type))}
                  >
                    {errorService.getErrorTypeLabel(selectedJobError.error_type)}
                  </StatusBadge>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Severity</p>
                  <StatusBadge
                    variant={phaseToVariant(errorService.getErrorSeverityColor(selectedJobError.error_severity))}
                  >
                    {errorService.getErrorSeverityLabel(selectedJobError.error_severity)}
                  </StatusBadge>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Context Type</p>
                  <p className="text-sm text-slate-900">{selectedJobError.context_type || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Context ID</p>
                  <code className="text-[11px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-700">
                    {selectedJobError.context_id || 'N/A'}
                  </code>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Created</p>
                  <p className="text-sm text-slate-900">
                    {selectedJobError.created_at
                      ? formatDateTime(selectedJobError.created_at)
                      : 'Unknown'}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Retryable</p>
                  <StatusBadge variant={selectedJobError.is_retryable ? 'success' : 'danger'}>
                    {selectedJobError.is_retryable ? 'Yes' : 'No'}
                  </StatusBadge>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Retry Count</p>
                  <p className="text-sm text-slate-900">{selectedJobError.retry_count}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Status</p>
                  {selectedJobError.resolved_at ? (
                    <StatusBadge variant="success">
                      Resolved at {formatDateTime(selectedJobError.resolved_at)}
                    </StatusBadge>
                  ) : (
                    <StatusBadge variant="danger">Unresolved</StatusBadge>
                  )}
                </div>
              </div>

              {selectedJobError.context_details && Object.keys(selectedJobError.context_details).length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Context Details</p>
                  <CollapsibleSection header="View Details">
                    <pre className="bg-slate-50 p-3 rounded text-xs overflow-auto max-h-[200px] text-slate-700">
                      {JSON.stringify(selectedJobError.context_details, null, 2)}
                    </pre>
                  </CollapsibleSection>
                </div>
              )}

              <div>
                <p className="text-xs font-semibold text-slate-500 mb-1">Error Message</p>
                <div className="rounded bg-red-50 border border-red-200 p-3 mt-1">
                  <p className="text-xs text-red-700 whitespace-pre-wrap">
                    {selectedJobError.error_message || 'No error message'}
                  </p>
                </div>
              </div>

              {selectedJobError.error_stack && (
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Stack Trace</p>
                  <CollapsibleSection header="View Stack Trace">
                    <pre className="bg-slate-50 p-3 rounded text-[11px] overflow-auto max-h-[300px] text-slate-700">
                      {selectedJobError.error_stack}
                    </pre>
                  </CollapsibleSection>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            {selectedJobError && !selectedJobError.resolved_at && (
              <button
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary/90 transition-colors"
                onClick={() => {
                  handleResolveJobError(selectedJobError.id);
                  setSelectedJobError(null);
                }}
              >
                <CheckCircle2 className="h-4 w-4" />
                Mark as Resolved
              </button>
            )}
            <button
              className="inline-flex items-center rounded-lg border bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors"
              onClick={() => setSelectedJobError(null)}
            >
              Close
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
};

export default ErrorsPage;
