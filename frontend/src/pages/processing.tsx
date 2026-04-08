import React, { useState, useEffect, useMemo } from "react";
import { useParams, useNavigate } from 'react-router-dom';
import { formatDate, formatTime, formatDateTime, formatElapsed } from '../utils/dateUtils';
import {
  Play,
  Pause,
  Square,
  Eye,
  RefreshCw,
  Trash2,
  Clock,
  CheckCircle2,
  AlertCircle,
  CirclePlay,
  CloudDownload,
  Wifi,
  Unplug,
  Calendar,
  RotateCw,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { processingService, ProcessingJob } from '../services/processingService';
import { ErrorDisplay } from '../components/ErrorDisplay';
import { MailboxSelector } from '../components/MailboxSelector';
import { mailboxService } from '../services/mailboxService';
import { useJobUpdates } from '../hooks/useJobUpdates';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { Spinner } from '@/lib/icons';
import { toast } from '@/lib/toast';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';

// Map processing status to StatusBadge variant
const statusVariantMap: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple'> = {
  pending: 'warning',
  downloading: 'purple',
  running: 'info',
  completed: 'success',
  failed: 'danger',
  paused: 'neutral',
  stopped: 'warning',
  interrupted: 'danger',
};

const getStatusVariant = (status: string) => statusVariantMap[status] || 'neutral';

const getStatusIcon = (status: string) => {
  const iconClass = "h-3 w-3";
  const icons: Record<string, React.ReactNode> = {
    pending: <Clock className={iconClass} />,
    downloading: <CloudDownload className={`${iconClass} animate-pulse`} />,
    running: <CirclePlay className={iconClass} />,
    completed: <CheckCircle2 className={iconClass} />,
    failed: <AlertCircle className={iconClass} />,
    paused: <Pause className={iconClass} />,
    stopped: <Square className={iconClass} />,
    interrupted: <AlertCircle className={iconClass} />,
  };
  return icons[status] || <Clock className={iconClass} />;
};

// Format processing speed - show per minute if less than 1/sec
const formatProcessingSpeed = (emailsPerSecond: number | undefined): string => {
  if (!emailsPerSecond || emailsPerSecond === 0) return '';

  if (emailsPerSecond >= 1) {
    return `${emailsPerSecond.toFixed(1)}/s`;
  } else {
    // Convert to per minute for slow processing
    const emailsPerMinute = emailsPerSecond * 60;
    return `${emailsPerMinute.toFixed(1)}/min`;
  }
};

// Progress bar component
function ProgressBar({
  percent,
  status,
  showLabel = true,
  color,
}: {
  percent: number;
  status?: 'active' | 'success' | 'exception';
  showLabel?: boolean;
  color?: string;
}) {
  const barColor =
    color ||
    (status === 'exception'
      ? 'bg-destructive'
      : status === 'success'
      ? 'bg-success'
      : 'bg-primary');
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1.5 rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-[11px] tabular-nums text-slate-500 min-w-[32px] text-right">
          {Math.round(percent)}%
        </span>
      )}
    </div>
  );
}

// Error popover component (hover-triggered)
function ErrorPopover({ errors, children }: { errors: string[]; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="relative inline-block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span className="cursor-pointer">{children}</span>
      {open && (
        <div className="absolute z-50 left-0 top-full mt-1 w-80 rounded-lg border bg-white shadow-lg p-3">
          <p className="text-xs font-semibold text-slate-700 mb-2">Error Details</p>
          <div className="max-h-60 overflow-y-auto space-y-1.5">
            {errors.map((error, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded-md bg-red-50 border border-red-100 px-2.5 py-1.5 text-xs text-red-700"
              >
                <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-red-500" />
                <span>{error}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Tooltip component (simple hover)
function Tip({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <span className="relative group/tip inline-flex">
      {children}
      <span className="pointer-events-none absolute z-40 bottom-full left-1/2 -translate-x-1/2 mb-1.5 whitespace-nowrap rounded bg-slate-800 px-2 py-1 text-[11px] text-white opacity-0 group-hover/tip:opacity-100 transition-opacity duration-150 shadow-lg">
        {text}
      </span>
    </span>
  );
}

export const ProcessingJobs: React.FC = () => {
  const { mailboxId } = useParams<{ mailboxId?: string }>();
  const navigate = useNavigate();

  const [selectedJob, setSelectedJob] = useState<ProcessingJob | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [reprocessingJobs, setReprocessingJobs] = useState<Set<string>>(new Set());
  const [restartingJobs, setRestartingJobs] = useState<Set<string>>(new Set());

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // Mailbox selection state
  const [selectedMailboxId, setSelectedMailboxId] = useState<string | null>(null);
  const [mailboxIdToNameMap, setMailboxIdToNameMap] = useState<Record<string, string>>({});

  // Use WebSocket-based job updates with polling fallback
  const { jobs, isLoading: loading, isRealtime, refresh: refreshJobs } = useJobUpdates({
    mailboxId: mailboxId || undefined,
    allJobs: !mailboxId, // Subscribe to all jobs if no specific mailbox
    fallbackPollingMs: 5000,
  });

  // Load mailboxes to build ID-to-name mapping
  useEffect(() => {
    const loadMailboxes = async () => {
      try {
        const mailboxes = await mailboxService.getMailboxes();
        const idToNameMap: Record<string, string> = {};
        mailboxes.forEach(mailbox => {
          idToNameMap[mailbox.id] = mailbox.name;
        });
        setMailboxIdToNameMap(idToNameMap);
      } catch (error) {
        console.error('Failed to load mailboxes:', error);
      }
    };
    loadMailboxes();
  }, []);

  // Sync URL parameter with mailbox selection
  useEffect(() => {
    if (mailboxId && mailboxIdToNameMap[mailboxId]) {
      setSelectedMailboxId(mailboxId);
    } else if (!mailboxId) {
      // No mailbox in URL - show all jobs
      setSelectedMailboxId(null);
    }
  }, [mailboxId, mailboxIdToNameMap]);

  const showJobDetails = (job: ProcessingJob) => {
    setSelectedJob(job);
    setModalVisible(true);
  };

  const handleJobAction = async (action: 'pause' | 'resume' | 'stop', jobId: string) => {
    try {
      await processingService.controlJob(jobId, action);
      toast.success(`${action.charAt(0).toUpperCase() + action.slice(1)} job ${jobId}`);
      refreshJobs(); // Reload jobs to show updated status
    } catch (error) {
      toast.error(`Failed to ${action} job`);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      await processingService.deleteJob(jobId);
      toast.success(`Deleted job ${jobId}`);
      refreshJobs(); // Reload jobs
    } catch (error) {
      toast.error('Failed to delete job');
    }
  };

  const handleReprocessJob = async (jobId: string) => {
    try {
      // Mark this job as being reprocessed
      setReprocessingJobs(prev => new Set(prev).add(jobId));

      await processingService.reprocessJob(jobId);

      toast.success(`Re-sync started! Attachment names & web links will be backfilled.`);

      // Reload jobs to show the new reprocessing job
      refreshJobs();

      // Remove from reprocessing set
      setReprocessingJobs(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
    } catch (error) {
      console.error('Failed to start reprocessing:', error);
      toast.error(`Failed to start reprocessing: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setReprocessingJobs(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
    }
  };

  const handleRestartJob = async (jobId: string) => {
    try {
      setRestartingJobs(prev => new Set(prev).add(jobId));
      const result = await processingService.restartJob(jobId);
      toast.success(`Job restarted! New job ID: ${result.new_job_id.substring(0, 8)}...`);
      if (result.cached_file_available) {
        toast.info('Using cached download - processing will start faster!');
      }
      refreshJobs();
    } catch (error) {
      console.error('Failed to restart job:', error);
      toast.error(`Failed to restart job: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setRestartingJobs(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
    }
  };

  const handleManualRefresh = () => {
    refreshJobs();
    toast.info('Refreshing job status...');
  };

  const runningJobs = jobs.filter(job => job.status === 'running');

  // Pagination logic
  const totalJobs = jobs.length;
  const totalPages = Math.max(1, Math.ceil(totalJobs / pageSize));
  const paginatedJobs = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return jobs.slice(start, start + pageSize);
  }, [jobs, currentPage, pageSize]);

  // Reset to page 1 when jobs change significantly
  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(1);
    }
  }, [totalPages, currentPage]);

  const rangeStart = totalJobs === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const rangeEnd = Math.min(currentPage * pageSize, totalJobs);

  // Handler for mailbox selection change
  const handleMailboxChange = (mailboxIds: string[]) => {
    if (mailboxIds.length === 1) {
      // Single mailbox selected - navigate to that mailbox's URL
      navigate(`/processing/${mailboxIds[0]}`);
    } else if (mailboxIds.length === 0) {
      // No mailbox selected - navigate to /processing (show all)
      navigate('/processing');
    } else {
      // Multiple mailboxes - just use the first one for now
      navigate(`/processing/${mailboxIds[0]}`);
    }
  };

  // --- Render helpers for table cells ---
  const renderJobId = (id: string) => (
    <code className="text-[11px] bg-slate-100 px-1.5 py-0.5 rounded font-mono text-slate-600">
      {id.substring(0, 8)}
    </code>
  );

  const renderJobType = (type: string) => (
    <StatusBadge variant="info" size="sm">
      {processingService.getJobTypeLabel(type)}
    </StatusBadge>
  );

  const renderStatus = (record: ProcessingJob) => {
    const badge = (
      <StatusBadge variant={getStatusVariant(record.status)} size="sm">
        <span className="flex items-center gap-1">
          {getStatusIcon(record.status)}
          {record.status.toUpperCase()}
        </span>
      </StatusBadge>
    );

    // Show error details in popover for failed jobs
    if (
      record.status === 'failed' &&
      record.error_log &&
      Array.isArray(record.error_log) &&
      record.error_log.length > 0
    ) {
      return (
        <ErrorPopover errors={record.error_log as string[]}>
          {badge}
        </ErrorPopover>
      );
    }

    return badge;
  };

  const renderProgress = (record: ProcessingJob) => {
    const { status, processed_records, total_records, failed_records, filtered_records, filter_start_date, filter_end_date } = record;
    const hasDateFilter = filter_start_date || filter_end_date;

    // Show download progress for downloading status
    if (status === 'downloading') {
      return (
        <div className="flex flex-col gap-1.5 w-[250px]">
          <ProgressBar percent={record.download_percent || 0} color="bg-accent" />
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-500 flex items-center gap-1">
              <CloudDownload className="h-3 w-3 text-accent" />
              Downloading...
            </span>
            <span className="font-medium text-accent">
              {record.download_percent || 0}%
            </span>
          </div>
          {record.download_speed_mbps && (
            <span className="text-[11px] text-slate-400">
              Speed: {record.download_speed_mbps.toFixed(1)} MB/s
            </span>
          )}
        </div>
      );
    }

    // Calculate effective progress
    const effectiveTotal = total_records > 0 ? total_records : (processed_records + (filtered_records || 0));
    const effectiveProgress = status === 'completed' ? 100 :
      (effectiveTotal > 0 ? Math.min(100, Math.round(((processed_records + (filtered_records || 0)) / effectiveTotal) * 100)) : 0);
    const isStreaming = total_records === 0 && status === 'running';

    return (
      <div className="flex flex-col gap-1.5 w-[250px]">
        <ProgressBar
          percent={effectiveProgress}
          status={status === 'failed' ? 'exception' : status === 'completed' ? 'success' : 'active'}
          showLabel={!isStreaming}
        />
        <span className="text-xs text-slate-500">
          {processed_records.toLocaleString('en-AU')} processed
          {total_records > 0 && (
            <span> / {total_records.toLocaleString('en-AU')}</span>
          )}
          {failed_records > 0 && (
            <span className="text-destructive"> ({failed_records.toLocaleString('en-AU')} failed)</span>
          )}
          {(filtered_records ?? 0) > 0 && (
            <span className="text-warning"> ({filtered_records!.toLocaleString('en-AU')} filtered)</span>
          )}
        </span>
        {hasDateFilter && (
          <Tip text={`Date filter: ${filter_start_date || 'any'} to ${filter_end_date || 'any'}`}>
            <StatusBadge variant="info" size="sm">
              <span className="flex items-center gap-1">
                <Calendar className="h-2.5 w-2.5" />
                Date Filter
              </span>
            </StatusBadge>
          </Tip>
        )}
        {status === 'running' && (record.emails_per_second || record.estimated_time_remaining) && (
          <div className="flex justify-between text-[11px] text-slate-400">
            <span>{formatProcessingSpeed(record.emails_per_second)}</span>
            <span>{record.estimated_time_remaining ? `ETA: ${record.estimated_time_remaining}` : ''}</span>
          </div>
        )}
      </div>
    );
  };

  const renderDate = (date: string | undefined, fallback: string = '-') => {
    if (!date) return <span className="text-slate-400">{fallback}</span>;
    return (
      <div className="flex flex-col">
        <span className="text-sm text-slate-700">{formatDate(date)}</span>
        <span className="text-xs text-slate-400">{formatTime(date)}</span>
      </div>
    );
  };

  const renderDuration = (record: ProcessingJob) => {
    const { started_at, completed_at, status } = record;
    if (!started_at) return <span className="text-slate-400">-</span>;

    // For terminal states (completed/failed/stopped), require completed_at
    const terminalStates = ['completed', 'failed', 'stopped'];
    if (terminalStates.includes(status) && !completed_at) {
      return <span className="text-slate-400">-</span>;
    }

    // Only use current time for running jobs; otherwise use completed_at
    const end = completed_at ? completed_at : (status === 'running' ? new Date().toISOString() : null);

    if (!end) return <span className="text-slate-400">-</span>;

    const duration = Math.round((new Date(end).getTime() - new Date(started_at).getTime()) / 1000);
    const minutes = Math.floor(duration / 60);
    const seconds = duration % 60;

    return (
      <span className="text-sm text-slate-500">
        {minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`}
        {status === 'running' && ' (ongoing)'}
        {status === 'stopped' && ' (stopped)'}
      </span>
    );
  };

  const renderActions = (record: ProcessingJob) => (
    <div className="flex items-center gap-0.5">
      <Tip text="View Details">
        <button
          className="p-1.5 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          onClick={() => showJobDetails(record)}
        >
          <Eye className="h-4 w-4" />
        </button>
      </Tip>

      {record.status === 'running' && (
        <Tip text="Pause Job">
          <button
            className="p-1.5 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            onClick={() => handleJobAction('pause', record.id)}
          >
            <Pause className="h-4 w-4" />
          </button>
        </Tip>
      )}

      {record.status === 'paused' && (
        <Tip text="Resume Job">
          <button
            className="p-1.5 rounded-md text-slate-500 hover:text-green-600 hover:bg-green-50 transition-colors"
            onClick={() => handleJobAction('resume', record.id)}
          >
            <Play className="h-4 w-4" />
          </button>
        </Tip>
      )}

      {(record.status === 'running' || record.status === 'paused') && (
        <Tip text="Stop Job">
          <button
            className="p-1.5 rounded-md text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors"
            onClick={() => handleJobAction('stop', record.id)}
          >
            <Square className="h-4 w-4" />
          </button>
        </Tip>
      )}

      {/* Restart button for interrupted/failed/stopped jobs */}
      {(['interrupted', 'failed', 'stopped'].includes(record.status)) && (
        <Tip text={restartingJobs.has(record.id) ? "Restarting..." : "Restart Job (will reuse cached download if available)"}>
          <button
            className="p-1.5 rounded-md text-green-500 hover:text-green-700 hover:bg-green-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            onClick={() => handleRestartJob(record.id)}
            disabled={restartingJobs.has(record.id)}
          >
            {restartingJobs.has(record.id) ? (
              <Spinner className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </button>
        </Tip>
      )}

      {record.status === 'completed' && (record.job_type.toLowerCase().includes('extraction') || record.job_type.toLowerCase().includes('sync')) && (
        <Tip text={reprocessingJobs.has(record.id) ? "Re-syncing..." : "Re-sync from mail provider (backfill attachments & links)"}>
          <button
            className="p-1.5 rounded-md text-slate-500 hover:text-primary hover:bg-primary-subtle transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            onClick={() => handleReprocessJob(record.id)}
            disabled={reprocessingJobs.has(record.id)}
          >
            {reprocessingJobs.has(record.id) ? (
              <Spinner className="h-4 w-4 animate-spin" />
            ) : (
              <RotateCw className="h-4 w-4" />
            )}
          </button>
        </Tip>
      )}

      {(record.status === 'completed' || record.status === 'failed' || record.status === 'interrupted' || record.status === 'stopped') && (
        <Tip text="Delete Job">
          <button
            className="p-1.5 rounded-md text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors"
            onClick={() => {
              if (window.confirm('Are you sure you want to delete this job?')) {
                handleDeleteJob(record.id);
              }
            }}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </Tip>
      )}
    </div>
  );

  // --- Modal: render job detail row ---
  const DetailRow = ({ label, children, span }: { label: string; children: React.ReactNode; span?: boolean }) => (
    <div className={`flex flex-col gap-0.5 ${span ? 'col-span-2' : ''}`}>
      <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{label}</span>
      <span className="text-sm text-slate-700">{children}</span>
    </div>
  );

  // Compute modal progress
  const modalProgress = selectedJob
    ? (selectedJob.total_records > 0
        ? Math.round((selectedJob.processed_records / selectedJob.total_records) * 100)
        : 0)
    : 0;

  return (
    <PageShell>
      {/* Header */}
      <PageHeader
        title="Processing Jobs"
        description="Monitor extraction and processing job status"
        actions={
          <div className="flex items-center gap-2">
            {/* Real-time indicator */}
            <Tip text={isRealtime ? 'Real-time updates via WebSocket' : 'Polling updates (WebSocket disconnected)'}>
              <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
                {isRealtime ? (
                  <>
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                    </span>
                    <Wifi className="h-3.5 w-3.5 text-green-500" />
                    <span>Live</span>
                  </>
                ) : (
                  <>
                    <Unplug className="h-3.5 w-3.5 text-slate-400" />
                    <span>Polling</span>
                  </>
                )}
              </span>
            </Tip>

            <MailboxSelector
              value={selectedMailboxId ? [selectedMailboxId] : []}
              onChange={handleMailboxChange}
              placeholder="Filter by mailbox"
              mode="single"
            />

            <button
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
              onClick={handleManualRefresh}
              disabled={loading}
            >
              {loading ? (
                <Spinner className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Refresh
            </button>
          </div>
        }
      />

      {/* Active Jobs Alert */}
      {runningJobs.length > 0 && (
        <div className="mb-5 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-blue-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-blue-800">Active Jobs Running</p>
            <p className="text-xs text-blue-600 mt-0.5">
              {runningJobs.length} job(s) currently processing. Avoid starting new extractions for the same mailboxes.
            </p>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="rounded-lg border bg-white shadow-sm">
        {loading && jobs.length === 0 ? (
          <div className="p-6">
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="flex gap-4 mb-4 items-center animate-pulse">
                <div className="h-4 w-16 bg-slate-200 rounded" />
                <div className="h-5 w-24 bg-slate-200 rounded-full" />
                <div className="h-4 w-28 bg-slate-200 rounded" />
                <div className="h-5 w-20 bg-slate-200 rounded-full" />
                <div className="h-4 w-48 bg-slate-200 rounded" />
                <div className="h-4 w-20 bg-slate-200 rounded" />
                <div className="h-4 w-20 bg-slate-200 rounded" />
                <div className="flex gap-1">
                  <div className="h-6 w-6 bg-slate-200 rounded" />
                  <div className="h-6 w-6 bg-slate-200 rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b bg-slate-50/50">
                    <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Job ID</th>
                    <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Job Type</th>
                    <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Mailbox</th>
                    <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Status</th>
                    <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Progress</th>
                    <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Created</th>
                    <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Started</th>
                    <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Duration</th>
                    <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {paginatedJobs.map(record => (
                    <tr
                      key={record.id}
                      className={
                        record.status === 'failed'
                          ? 'bg-red-50/50'
                          : record.status === 'running'
                          ? 'bg-blue-50/30'
                          : 'hover:bg-slate-50/50'
                      }
                    >
                      <td className="px-3 py-2.5">{renderJobId(record.id)}</td>
                      <td className="px-3 py-2.5">{renderJobType(record.job_type)}</td>
                      <td className="px-3 py-2.5 text-sm text-slate-700">{record.mailbox_name}</td>
                      <td className="px-3 py-2.5">{renderStatus(record)}</td>
                      <td className="px-3 py-2.5">{renderProgress(record)}</td>
                      <td className="px-3 py-2.5">{renderDate(record.created_at)}</td>
                      <td className="px-3 py-2.5">{renderDate(record.started_at, 'Not started')}</td>
                      <td className="px-3 py-2.5">{renderDuration(record)}</td>
                      <td className="px-3 py-2.5">{renderActions(record)}</td>
                    </tr>
                  ))}
                  {paginatedJobs.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-3 py-12 text-center text-sm text-slate-400">
                        No processing jobs found
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between border-t px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">
                  {rangeStart}-{rangeEnd} of {totalJobs} jobs
                </span>
                <select
                  className="rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 focus:outline-none focus:ring-1 focus:ring-primary"
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                >
                  <option value={10}>10 / page</option>
                  <option value={20}>20 / page</option>
                  <option value={50}>50 / page</option>
                </select>
              </div>
              <div className="flex items-center gap-1">
                <button
                  className="p-1 rounded text-slate-400 hover:text-slate-600 disabled:opacity-30 disabled:cursor-not-allowed"
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage <= 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter(p => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 1)
                  .map((p, idx, arr) => (
                    <React.Fragment key={p}>
                      {idx > 0 && arr[idx - 1] !== p - 1 && (
                        <span className="px-1 text-xs text-slate-300">...</span>
                      )}
                      <button
                        className={`min-w-[28px] h-7 rounded text-xs font-medium transition-colors ${
                          p === currentPage
                            ? 'bg-primary text-white'
                            : 'text-slate-600 hover:bg-slate-100'
                        }`}
                        onClick={() => setCurrentPage(p)}
                      >
                        {p}
                      </button>
                    </React.Fragment>
                  ))}
                <button
                  className="p-1 rounded text-slate-400 hover:text-slate-600 disabled:opacity-30 disabled:cursor-not-allowed"
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage >= totalPages}
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Job Details Dialog */}
      <Dialog open={modalVisible} onOpenChange={setModalVisible}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span>Job Details</span>
              {selectedJob && (
                <StatusBadge variant={getStatusVariant(selectedJob.status)} size="sm">
                  <span className="flex items-center gap-1">
                    {getStatusIcon(selectedJob.status)}
                    {selectedJob.status.toUpperCase()}
                  </span>
                </StatusBadge>
              )}
            </DialogTitle>
            <DialogDescription>Detailed information about this processing job</DialogDescription>
          </DialogHeader>

          {selectedJob && (
            <div className="space-y-5">
              {/* Job Information Grid */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-3">Job Information</h3>
                <div className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border bg-slate-50/50 p-4">
                  <DetailRow label="Job ID" span>
                    <code className="text-[11px] bg-slate-200 px-1.5 py-0.5 rounded font-mono text-slate-600">
                      {selectedJob.id}
                    </code>
                  </DetailRow>
                  <DetailRow label="Status">
                    <StatusBadge variant={getStatusVariant(selectedJob.status)} size="sm">
                      <span className="flex items-center gap-1">
                        {getStatusIcon(selectedJob.status)}
                        {selectedJob.status.toUpperCase()}
                      </span>
                    </StatusBadge>
                  </DetailRow>
                  <DetailRow label="Job Type">
                    {processingService.getJobTypeLabel(selectedJob.job_type)}
                  </DetailRow>
                  <DetailRow label="Mailbox">
                    {selectedJob.mailbox_name}
                  </DetailRow>
                  <DetailRow label="Total Records">
                    {selectedJob.total_records.toLocaleString('en-AU')}
                  </DetailRow>
                  <DetailRow label="Processed">
                    {selectedJob.processed_records.toLocaleString('en-AU')}
                  </DetailRow>
                  <DetailRow label="Failed Records">
                    <span className={selectedJob.failed_records > 0 ? 'text-destructive font-medium' : 'text-slate-400'}>
                      {selectedJob.failed_records.toLocaleString('en-AU')}
                    </span>
                  </DetailRow>

                  {(selectedJob.filtered_records !== undefined && selectedJob.filtered_records > 0) && (
                    <DetailRow label="Filtered Records" span>
                      <span className="text-warning">
                        {selectedJob.filtered_records.toLocaleString('en-AU')} (excluded by date filter)
                      </span>
                    </DetailRow>
                  )}

                  {(selectedJob.filter_start_date || selectedJob.filter_end_date) && (
                    <DetailRow label="Date Filter" span>
                      <StatusBadge variant="info" size="sm">
                        <span className="flex items-center gap-1">
                          <Calendar className="h-2.5 w-2.5" />
                          {selectedJob.filter_start_date || 'Any'} → {selectedJob.filter_end_date || 'Any'}
                        </span>
                      </StatusBadge>
                    </DetailRow>
                  )}

                  <DetailRow label="Progress" span>
                    <ProgressBar
                      percent={modalProgress}
                      status={
                        selectedJob.status === 'failed'
                          ? 'exception'
                          : selectedJob.status === 'completed'
                          ? 'success'
                          : 'active'
                      }
                    />
                  </DetailRow>

                  <DetailRow label="Started At">
                    {selectedJob.started_at ? formatDateTime(selectedJob.started_at) : 'Not started'}
                  </DetailRow>
                  <DetailRow label="Completed At">
                    {selectedJob.completed_at ? formatDateTime(selectedJob.completed_at) : 'Not completed'}
                  </DetailRow>
                </div>
              </div>

              {/* Error Log */}
              {selectedJob.error_log && Array.isArray(selectedJob.error_log) && selectedJob.error_log.length > 0 && (
                <div className="rounded-lg border bg-white shadow-sm">
                  <div className="px-4 py-2.5 border-b bg-slate-50/50">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">Error Log</h3>
                  </div>
                  <ul className="divide-y divide-slate-100">
                    {(selectedJob.error_log as string[]).map((error: string, index: number) => (
                      <li key={index} className="px-4 py-2.5 text-sm text-destructive flex items-start gap-2">
                        <span className="text-slate-400 text-xs mt-0.5 tabular-nums">{index + 1}.</span>
                        <span>{error}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Stage 2: Enhanced Error Display with detailed breakdown and retry */}
              {selectedJob.failed_records > 0 && (
                <ErrorDisplay
                  jobId={selectedJob.id}
                  failedCount={selectedJob.failed_records}
                  onRetryComplete={() => refreshJobs()}
                />
              )}
            </div>
          )}

          <DialogFooter>
            <button
              className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
              onClick={() => setModalVisible(false)}
            >
              Close
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
};
