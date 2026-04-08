import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  PlayCircle,
  PauseCircle,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Clock,
  Settings,
  Folder,
  Calendar,
  HelpCircle,
  CloudDownload,
  Unplug,
  Loader2,
  ChevronDown,
  Info,
  AlertTriangle,
} from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { mailboxService, Mailbox } from "../services/mailboxService";
import {
  processingService,
  ProcessingJob,
  CachedDownload,
} from "../services/processingService";
import { useConnectionStatus } from "../hooks/useConnectionStatus";
import { formatDateTime } from "../utils/dateUtils";
import { PageShell, PageHeader } from "@/components/ui/page-shell";
import { StatusBadge } from "@/components/ui/status-badge";
import { ContentSkeleton } from "@/components/ui/empty-state";
import { notify } from "@/lib/toast";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Form state type                                                    */
/* ------------------------------------------------------------------ */

interface FormValues {
  job_type: string;
  max_emails: number | undefined;
  enable_categorization: boolean;
  download_first: boolean;
  download_threads: number;
  date_range_start: string;
  date_range_end: string;
}

const defaultFormValues: FormValues = {
  job_type: "extraction",
  max_emails: undefined,
  enable_categorization: true,
  download_first: true,
  download_threads: 4,
  date_range_start: "",
  date_range_end: "",
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const MailboxProcess: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [formValues, setFormValues] = useState<FormValues>(defaultFormValues);
  const [mailbox, setMailbox] = useState<Mailbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [currentJob, setCurrentJob] = useState<ProcessingJob | null>(null);
  const [jobHistory, setJobHistory] = useState<ProcessingJob[]>([]);
  const [cachedDownload, setCachedDownload] = useState<CachedDownload | null>(
    null,
  );
  const [checkingCache, setCheckingCache] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // Track connection status
  const { isConnected, isChecking, checkNow } = useConnectionStatus({
    reconnectInterval: 3000,
    checkOnMount: true,
  });

  // Track if we need to refresh after reconnection
  const wasDisconnectedRef = useRef(false);

  useEffect(() => {
    if (id) {
      loadMailboxData();
      loadJobHistory();
    }
  }, [id]);

  // Handle reconnection - refresh data when connection is restored
  useEffect(() => {
    if (!isConnected) {
      wasDisconnectedRef.current = true;
    } else if (wasDisconnectedRef.current) {
      console.log("[UI] Connection restored, refreshing data...");
      wasDisconnectedRef.current = false;
      loadJobHistory();
    }
  }, [isConnected]);

  // Polling effect with connection awareness
  useEffect(() => {
    let interval: NodeJS.Timeout;

    if (isConnected && currentJob) {
      let pollInterval = 5000;

      if (["pending", "running", "downloading"].includes(currentJob.status)) {
        pollInterval = 2000;
      } else if (currentJob.status === "paused") {
        pollInterval = 10000;
      } else {
        return;
      }

      interval = setInterval(() => {
        loadJobHistory(true);
      }, pollInterval);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [currentJob, isConnected]);

  /* ---------- data loaders ---------- */

  const loadMailboxData = async () => {
    try {
      if (!id) return;
      const data = await mailboxService.getMailbox(id);
      setMailbox(data);

      if (data?.connection_config?.file_source === "google_drive") {
        checkCachedDownload();
      }
    } catch (error) {
      console.error("Error loading mailbox:", error);
      notify.error("Failed to load mailbox data");
      navigate("/mailboxes");
    } finally {
      setLoading(false);
    }
  };

  const checkCachedDownload = async () => {
    if (!id) return;
    try {
      setCheckingCache(true);
      const cache = await processingService.checkCachedDownload(id);
      setCachedDownload(cache);
    } catch (error) {
      console.error("Error checking cached download:", error);
    } finally {
      setCheckingCache(false);
    }
  };

  const handleInvalidateCache = async () => {
    if (!cachedDownload?.cache_id) return;
    try {
      await processingService.invalidateCachedDownload(
        cachedDownload.cache_id,
      );
      notify.success(
        "Cache invalidated. File will be re-downloaded on next processing.",
      );
      setCachedDownload({ cached: false, reason: "Invalidated by user" });
    } catch (error) {
      console.error("Error invalidating cache:", error);
      notify.error("Failed to invalidate cache");
    }
  };

  const loadJobHistory = useCallback(
    async (silent: boolean = false) => {
      try {
        if (!id) return;
        const jobs = await processingService.getProcessingJobs(silent);

        if (silent && jobs.length === 0 && jobHistory.length > 0) {
          return;
        }

        const mailboxJobs = jobs.filter((job) => job.mailbox_id === id);
        setJobHistory(mailboxJobs);

        const activeJob = mailboxJobs.find((job) =>
          ["pending", "running", "downloading"].includes(job.status),
        );
        setCurrentJob(activeJob || null);
      } catch (error) {
        if (!silent) {
          console.error("Error loading job history:", error);
        }
      }
    },
    [id, jobHistory.length],
  );

  /* ---------- form handling ---------- */

  const updateForm = (patch: Partial<FormValues>) =>
    setFormValues((prev) => ({ ...prev, ...patch }));

  const startProcessing = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (!id || !mailbox) return;

      setProcessing(true);

      const jobData: any = {
        mailbox_id: id,
        job_type: formValues.job_type || "extraction",
        max_emails: formValues.max_emails || null,
        enable_categorization: formValues.enable_categorization ?? true,
      };

      if (formValues.date_range_start && formValues.date_range_end) {
        jobData.start_date = formValues.date_range_start;
        jobData.end_date = formValues.date_range_end;
      }

      if (mailbox?.connection_config?.file_source === "google_drive") {
        jobData.download_first = formValues.download_first ?? false;
        jobData.download_threads = formValues.download_threads ?? 8;
        jobData.use_cached_file = true;
        jobData.keep_downloaded_file = true;
      }

      const job = await processingService.createProcessingJob(jobData);
      setCurrentJob(job);
      notify.success("Processing job started successfully");

      loadJobHistory();
    } catch (error) {
      console.error("Error starting processing:", error);
      notify.error("Failed to start processing job");
    } finally {
      setProcessing(false);
    }
  };

  /* ---------- helpers ---------- */

  const getJobStatusIcon = (status: string) => {
    switch (status) {
      case "pending":
        return <Clock className="h-4 w-4 text-amber-500" />;
      case "running":
        return <RefreshCw className="h-4 w-4 animate-spin text-blue-500" />;
      case "downloading":
        return (
          <CloudDownload className="h-4 w-4 animate-pulse text-purple-500" />
        );
      case "completed":
        return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
      case "failed":
        return <AlertCircle className="h-4 w-4 text-red-500" />;
      case "stopped":
        return <PauseCircle className="h-4 w-4 text-slate-500" />;
      case "interrupted":
        return <AlertCircle className="h-4 w-4 text-orange-500" />;
      default:
        return null;
    }
  };

  const getJobStatusVariant = (
    status: string,
  ): "warning" | "info" | "purple" | "success" | "danger" | "neutral" => {
    switch (status) {
      case "pending":
        return "warning";
      case "running":
        return "info";
      case "downloading":
        return "purple";
      case "completed":
        return "success";
      case "failed":
        return "danger";
      case "stopped":
        return "neutral";
      case "interrupted":
        return "warning";
      default:
        return "neutral";
    }
  };

  const hasDownloadPhase =
    (currentJob?.download_percent !== undefined &&
      currentJob.download_percent > 0) ||
    currentJob?.status === "downloading";

  const getCurrentStep = () => {
    if (!currentJob) return 0;

    if (hasDownloadPhase) {
      switch (currentJob.status) {
        case "pending":
          return 0;
        case "downloading":
          return 1;
        case "running":
          return 2;
        case "completed":
          return 3;
        case "failed":
          return 3;
        case "stopped":
          return 3;
        case "interrupted":
          return 3;
        default:
          return 0;
      }
    }

    switch (currentJob.status) {
      case "pending":
        return 0;
      case "running":
        return 1;
      case "completed":
        return 2;
      case "failed":
        return 2;
      case "stopped":
        return 2;
      case "interrupted":
        return 2;
      default:
        return 0;
    }
  };

  const formatProcessingSpeed = (
    emailsPerSecond: number | undefined,
  ): string => {
    if (!emailsPerSecond || emailsPerSecond === 0)
      return "Calculating speed...";

    if (emailsPerSecond >= 1) {
      return `${emailsPerSecond.toFixed(1)} emails/sec`;
    } else {
      const emailsPerMinute = emailsPerSecond * 60;
      return `${emailsPerMinute.toFixed(1)} emails/min`;
    }
  };

  /* ---------- loading / not-found ---------- */

  if (loading) {
    return (
      <PageShell>
        <ContentSkeleton rows={6} />
      </PageShell>
    );
  }

  if (!mailbox) {
    return (
      <PageShell>
        <div className="flex items-center justify-center py-12">
          <p className="text-sm text-slate-500">Mailbox not found</p>
        </div>
      </PageShell>
    );
  }

  /* ---------- stepper helper ---------- */

  const renderSteps = () => {
    const isFailed = currentJob?.status === "failed";
    const isInterrupted = currentJob?.status === "interrupted";
    const isStopped = currentJob?.status === "stopped";
    const isError = isFailed || isInterrupted;

    const finalTitle = isFailed
      ? "Failed"
      : isInterrupted
        ? "Interrupted"
        : isStopped
          ? "Stopped"
          : "Completed";
    const finalDesc = isFailed
      ? "Processing failed"
      : isInterrupted
        ? "Server restarted"
        : isStopped
          ? "Stopped by user"
          : "All emails processed";

    const steps =
      hasDownloadPhase || currentJob?.status === "downloading"
        ? [
            { title: "Queued", desc: "Job created and waiting" },
            {
              title: "Downloading",
              desc: "Parallel download from Google Drive",
            },
            { title: "Processing", desc: "Extracting and analyzing emails" },
            { title: finalTitle, desc: finalDesc },
          ]
        : [
            { title: "Queued", desc: "Job created and waiting" },
            { title: "Processing", desc: "Extracting and analyzing emails" },
            { title: finalTitle, desc: finalDesc },
          ];

    const current = getCurrentStep();

    return (
      <div className="flex items-start gap-0">
        {steps.map((step, i) => {
          const isActive = i === current;
          const isDone = i < current;
          const isLast = i === steps.length - 1;
          const isStepError = isLast && isError && (isDone || isActive);

          return (
            <React.Fragment key={i}>
              <div className="flex flex-col items-center text-center min-w-[100px] flex-1">
                <div
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold border-2 transition-colors",
                    isStepError
                      ? "border-red-500 bg-red-50 text-red-600"
                      : isDone
                        ? "border-primary bg-primary text-white"
                        : isActive
                          ? "border-primary bg-primary-subtle text-primary"
                          : "border-slate-200 bg-white text-slate-400",
                  )}
                >
                  {isDone && !isStepError ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : isStepError ? (
                    <AlertCircle className="h-4 w-4" />
                  ) : (
                    i + 1
                  )}
                </div>
                <span
                  className={cn(
                    "mt-1.5 text-xs font-medium",
                    isActive || isDone
                      ? "text-slate-900"
                      : "text-slate-400",
                  )}
                >
                  {step.title}
                </span>
                <span className="text-[10px] text-slate-400 mt-0.5 max-w-[120px]">
                  {step.desc}
                </span>
              </div>
              {!isLast && (
                <div className="flex-1 mt-3.5 min-w-[24px]">
                  <div
                    className={cn(
                      "h-0.5 w-full rounded-full",
                      isDone ? "bg-primary" : "bg-slate-200",
                    )}
                  />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    );
  };

  /* ---------- progress bar helper ---------- */

  const ProgressBar = ({
    percent,
    variant = "default",
  }: {
    percent: number;
    variant?: "default" | "purple" | "success" | "error";
  }) => {
    const colorMap = {
      default: "bg-primary",
      purple: "bg-purple-500",
      success: "bg-emerald-500",
      error: "bg-red-500",
    };
    return (
      <div className="h-1.5 rounded-full bg-slate-100">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            colorMap[variant],
          )}
          style={{ width: `${Math.min(100, percent)}%` }}
        />
      </div>
    );
  };

  /* ---------- inline tooltip helper ---------- */

  const HelpTip = ({ text }: { text: string }) => (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <HelpCircle className="inline h-3.5 w-3.5 text-slate-400 cursor-help ml-1" />
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs text-xs">
          {text}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  return (
    <PageShell>
      <div className="space-y-5">
        {/* Connection Status Banner */}
        {!isConnected && (
          <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm">
            <div className="flex items-center gap-2 text-amber-800">
              <Unplug className="h-4 w-4" />
              <span className="font-medium">Backend Disconnected</span>
              {isChecking && (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              )}
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-amber-600">
                Unable to connect to the server. Attempting to reconnect
                automatically...
              </span>
              <button
                onClick={checkNow}
                disabled={isChecking}
                className="rounded-md border border-amber-300 bg-white px-3 py-1 text-xs font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-50"
              >
                {isChecking ? "Retrying..." : "Retry Now"}
              </button>
            </div>
          </div>
        )}

        {/* Page Header */}
        <PageHeader
          title={`Process Mailbox: ${mailbox.name}`}
          description="Configure and initiate email processing for this mailbox"
        />

        {/* Mailbox Information */}
        <div className="rounded-lg border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b px-5 py-3">
            <Settings className="h-4 w-4 text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-900">
              Mailbox Information
            </h3>
          </div>
          <div className="px-5 py-4">
            <div className="grid grid-cols-2 gap-y-3 gap-x-8 text-sm">
              <div>
                <span className="text-slate-500">Name</span>
                <p className="font-medium text-slate-900">{mailbox.name}</p>
              </div>
              <div>
                <span className="text-slate-500">Email</span>
                <p className="font-medium text-slate-900">
                  {mailbox.email_address}
                </p>
              </div>
              <div>
                <span className="text-slate-500">Type</span>
                <p className="mt-0.5">
                  <StatusBadge variant="info">
                    {mailbox.mailbox_type.toUpperCase()}
                  </StatusBadge>
                </p>
              </div>
              <div>
                <span className="text-slate-500">Status</span>
                <p className="mt-0.5">
                  <StatusBadge
                    variant={mailbox.is_active ? "success" : "neutral"}
                  >
                    {mailbox.is_active ? "Active" : "Inactive"}
                  </StatusBadge>
                </p>
              </div>
              <div>
                <span className="text-slate-500">Total Emails</span>
                <p className="font-medium text-slate-900">
                  {mailbox.total_emails?.toLocaleString("en-AU") || "0"}
                </p>
              </div>
              <div>
                <span className="text-slate-500">Last Sync</span>
                <p className="font-medium text-slate-900">
                  {mailbox.last_sync_at
                    ? formatDateTime(mailbox.last_sync_at)
                    : "Never"}
                </p>
              </div>
            </div>

            {/* File path for file-based types */}
            {["mbox", "pst", "olm"].includes(mailbox.mailbox_type) &&
              mailbox.connection_config?.file_path && (
                <div className="mt-4 pt-3 border-t">
                  <span className="text-sm font-medium text-slate-700">
                    File Path:
                  </span>
                  <div className="mt-1.5 flex items-center gap-2 text-sm">
                    <Folder className="h-4 w-4 text-slate-400" />
                    <code className="rounded bg-slate-50 px-2 py-0.5 text-xs font-mono text-slate-700">
                      {mailbox.connection_config.file_path}
                    </code>
                  </div>
                </div>
              )}
          </div>
        </div>

        {/* Current Job Status */}
        {currentJob && (
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b px-5 py-3">
              <PlayCircle className="h-4 w-4 text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-900">
                Current Processing Job
              </h3>
            </div>
            <div className="px-5 py-4 space-y-5">
              {/* Steps */}
              {renderSteps()}

              {/* Status line */}
              <div className="flex items-center justify-between pt-2">
                <div className="flex items-center gap-2">
                  {getJobStatusIcon(currentJob.status)}
                  <span className="text-sm font-semibold text-slate-900">
                    Status: {currentJob.status.toUpperCase()}
                  </span>
                </div>
                <span className="text-xs text-slate-500">
                  Job Type: {currentJob.job_type}
                </span>
              </div>

              {/* Download progress */}
              {currentJob.status === "downloading" && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm">
                      <CloudDownload className="h-4 w-4 text-purple-500" />
                      <span className="text-slate-700">
                        Downloading from Google Drive...
                      </span>
                    </div>
                    <span className="text-sm font-semibold text-slate-900">
                      {currentJob.download_percent || 0}%
                    </span>
                  </div>
                  <ProgressBar
                    percent={currentJob.download_percent || 0}
                    variant="purple"
                  />
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>
                      {currentJob.download_speed_mbps
                        ? `${currentJob.download_speed_mbps.toFixed(1)} MB/s`
                        : "Calculating speed..."}
                    </span>
                    <span className="italic">
                      Using parallel download for faster processing
                    </span>
                  </div>
                </div>
              )}

              {/* Processing progress */}
              {currentJob.status !== "downloading" &&
                (() => {
                  const processed = currentJob.processed_records || 0;
                  const filtered = currentJob.filtered_records || 0;
                  const total = currentJob.total_records || 0;
                  const isCompleted = currentJob.status === "completed";
                  const isFailed = currentJob.status === "failed";

                  let progressPercent = 0;
                  let showIndeterminate = false;

                  if (isCompleted || isFailed) {
                    progressPercent = 100;
                  } else if (total > 0) {
                    progressPercent = Math.min(
                      100,
                      Math.round(((processed + filtered) / total) * 100),
                    );
                  } else if (currentJob.status === "running") {
                    showIndeterminate = true;
                  }

                  return (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-700">Progress</span>
                        <span className="text-slate-900">
                          <strong>
                            {processed.toLocaleString("en-AU")}
                          </strong>{" "}
                          processed
                          {filtered > 0 && (
                            <span className="ml-2 text-amber-500">
                              <strong>
                                {filtered.toLocaleString("en-AU")}
                              </strong>{" "}
                              filtered by date
                            </span>
                          )}
                          {total > 0 && (
                            <span className="ml-2 text-slate-400">
                              / {total.toLocaleString("en-AU")} total
                            </span>
                          )}
                        </span>
                      </div>
                      {showIndeterminate ? (
                        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                          <div className="h-full w-1/3 rounded-full bg-primary animate-pulse" />
                        </div>
                      ) : (
                        <ProgressBar
                          percent={progressPercent}
                          variant={
                            isFailed
                              ? "error"
                              : isCompleted
                                ? "success"
                                : "default"
                          }
                        />
                      )}
                      {currentJob.status === "running" && (
                        <div className="flex items-center justify-between text-xs text-slate-500">
                          <span>
                            {formatProcessingSpeed(
                              currentJob.emails_per_second,
                            )}
                          </span>
                          <span>
                            {currentJob.estimated_time_remaining
                              ? `ETA: ${currentJob.estimated_time_remaining}`
                              : ""}
                          </span>
                        </div>
                      )}
                      {isCompleted && processed > 0 && (
                        <p className="text-xs text-emerald-600">
                          {processed.toLocaleString("en-AU")} emails inserted to
                          database
                        </p>
                      )}
                    </div>
                  );
                })()}

              {/* Failed alert */}
              {currentJob.status === "failed" && currentJob.error_log && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="mt-0.5 h-4 w-4 text-red-500 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-red-800">
                        Processing Failed
                      </p>
                      <p className="mt-1 text-xs text-red-700">
                        {typeof currentJob.error_log === "string"
                          ? currentJob.error_log
                          : JSON.stringify(currentJob.error_log)}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Interrupted alert */}
              {currentJob.status === "interrupted" && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-500 shrink-0" />
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-amber-800">
                        Job Interrupted
                      </p>
                      <p className="text-xs text-amber-700">
                        This job was interrupted by a server restart.{" "}
                        {currentJob.processed_records || 0} emails were already
                        processed.
                      </p>
                      <p className="text-xs text-amber-600">
                        You can start a new job - previously processed emails
                        will be skipped automatically (deduplication).
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Timestamps */}
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>
                  Started:{" "}
                  {currentJob.started_at
                    ? formatDateTime(currentJob.started_at)
                    : "Not started"}
                </span>
                {currentJob.completed_at && (
                  <span>Completed: {formatDateTime(currentJob.completed_at)}</span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* LIVE mailbox notice */}
        {["gmail", "outlook_live"].includes(mailbox.mailbox_type) && (
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b px-5 py-3">
              <RefreshCw className="h-4 w-4 text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-900">
                LIVE Sync Active
              </h3>
            </div>
            <div className="px-5 py-4 space-y-4">
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-500 shrink-0" />
                  <div className="space-y-2 text-sm">
                    <p className="font-medium text-emerald-800">
                      This mailbox syncs automatically
                    </p>
                    <p className="text-emerald-700">
                      New emails are fetched every{" "}
                      {mailbox.mailbox_type === "gmail" ? "15" : "30"} minutes
                      via{" "}
                      {mailbox.mailbox_type === "gmail" ? "Gmail" : "Outlook"}{" "}
                      API. Contacts and companies are extracted automatically
                      after each sync.
                    </p>
                    <p className="text-emerald-700">
                      <strong>To run AI analysis:</strong> Go to{" "}
                      <a
                        href="/insights/inbox"
                        className="text-emerald-800 underline underline-offset-2 hover:text-emerald-900"
                      >
                        Smart Inbox
                      </a>{" "}
                      and click "Analyze New Emails".
                    </p>
                    <p className="text-emerald-700">
                      <strong>To run full extraction</strong> (engagement
                      scoring, company stats): Go to{" "}
                      <a
                        href="/manage/extraction"
                        className="text-emerald-800 underline underline-offset-2 hover:text-emerald-900"
                      >
                        Extraction
                      </a>{" "}
                      and trigger a full run for this mailbox.
                    </p>
                  </div>
                </div>
              </div>
              <button
                onClick={() => navigate("/mailboxes")}
                className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
              >
                Back to Mailboxes
              </button>
            </div>
          </div>
        )}

        {/* Processing Configuration — archive mailboxes only */}
        {!["gmail", "outlook_live"].includes(mailbox.mailbox_type) &&
        (!currentJob ||
          ["completed", "failed", "stopped", "interrupted"].includes(
            currentJob.status,
          )) ? (
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b px-5 py-3">
              <PlayCircle className="h-4 w-4 text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-900">
                Start New Processing Job
              </h3>
            </div>
            <div className="px-5 py-4">
              <form onSubmit={startProcessing} className="space-y-5">
                {/* Processing Type */}
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-slate-700">
                    Processing Type <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={formValues.job_type}
                    onChange={(e) => updateForm({ job_type: e.target.value })}
                    required
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    <option value="extraction">
                      Email Extraction (with Auto-Tagging)
                    </option>
                  </select>
                </div>

                {/* Email Limit */}
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-slate-700 flex items-center">
                    Email Limit
                    <HelpTip text="Maximum number of emails to process. Leave empty to process all emails in the mailbox." />
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={100000}
                    placeholder="All emails"
                    value={formValues.max_emails ?? ""}
                    onChange={(e) =>
                      updateForm({
                        max_emails: e.target.value
                          ? Number(e.target.value)
                          : undefined,
                      })
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                </div>

                {/* Date Range Filter */}
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-slate-700 flex items-center">
                    <Calendar className="mr-1.5 h-3.5 w-3.5 text-slate-400" />
                    Date Range Filter
                    <HelpTip text="Only process emails sent within this date range. Leave empty to process all emails regardless of date." />
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      type="date"
                      value={formValues.date_range_start}
                      onChange={(e) =>
                        updateForm({ date_range_start: e.target.value })
                      }
                      placeholder="Start Date"
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    />
                    <input
                      type="date"
                      value={formValues.date_range_end}
                      onChange={(e) =>
                        updateForm({ date_range_end: e.target.value })
                      }
                      placeholder="End Date"
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    />
                  </div>
                </div>

                {/* Google Drive Download Options */}
                {mailbox?.connection_config?.file_source === "google_drive" && (
                  <>
                    <div className="relative flex items-center gap-3 py-2">
                      <div className="h-px flex-1 bg-slate-200" />
                      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                        <CloudDownload className="h-3.5 w-3.5 text-purple-500" />
                        Google Drive Processing Mode
                      </div>
                      <div className="h-px flex-1 bg-slate-200" />
                    </div>

                    {/* Download First toggle */}
                    <div className="space-y-1.5">
                      <label className="text-sm font-medium text-slate-700 flex items-center">
                        Download Before Processing
                        <StatusBadge
                          variant="success"
                          size="sm"
                          className="ml-2"
                        >
                          Recommended
                        </StatusBadge>
                        <HelpTip text="Download the entire file first using parallel threads, then process locally. Typically 3-5x faster than streaming for large files." />
                      </label>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={formValues.download_first}
                        onClick={() =>
                          updateForm({
                            download_first: !formValues.download_first,
                          })
                        }
                        className={cn(
                          "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors",
                          formValues.download_first
                            ? "bg-primary"
                            : "bg-slate-200",
                        )}
                      >
                        <span
                          className={cn(
                            "pointer-events-none block h-4 w-4 rounded-full bg-white shadow-sm ring-0 transition-transform",
                            formValues.download_first
                              ? "translate-x-4"
                              : "translate-x-0",
                          )}
                        />
                      </button>
                    </div>

                    {/* Conditional: cache info or download threads or streaming notice */}
                    {formValues.download_first ? (
                      <>
                        {checkingCache ? (
                          <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Checking for cached download...
                          </div>
                        ) : cachedDownload?.cached ? (
                          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
                            <div className="flex items-start gap-2">
                              <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-500 shrink-0" />
                              <div className="space-y-1.5 text-sm">
                                <p className="font-medium text-emerald-800">
                                  Using Cached File (No Download Needed)
                                </p>
                                <p className="text-emerald-700">
                                  <strong>{cachedDownload.file_name}</strong> (
                                  {cachedDownload.file_size_formatted})
                                </p>
                                <p className="text-xs text-emerald-600">
                                  Downloaded {cachedDownload.age_formatted}{" "}
                                  &bull; Last used:{" "}
                                  {cachedDownload.last_used_at
                                    ? formatDateTime(
                                        cachedDownload.last_used_at,
                                      )
                                    : "Never"}
                                </p>
                                <p className="text-[11px] text-emerald-600 font-mono">
                                  Path: {cachedDownload.storage_path}
                                </p>
                                <div className="flex items-center gap-2 pt-1">
                                  <button
                                    type="button"
                                    onClick={handleInvalidateCache}
                                    className="rounded-md border border-red-200 bg-white px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                                  >
                                    Clear Cache (Force Re-download)
                                  </button>
                                  <button
                                    type="button"
                                    onClick={checkCachedDownload}
                                    className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
                                  >
                                    Refresh
                                  </button>
                                </div>
                              </div>
                            </div>
                          </div>
                        ) : (
                          /* Download threads slider */
                          <div className="space-y-1.5">
                            <label className="text-sm font-medium text-slate-700 flex items-center">
                              Download Threads
                              <HelpTip text="Number of parallel download threads. Limited to 4 for memory efficiency when downloading large files (50GB+). Each thread streams directly to disk." />
                            </label>
                            <div className="space-y-2">
                              <input
                                type="range"
                                min={1}
                                max={4}
                                step={1}
                                value={formValues.download_threads}
                                onChange={(e) =>
                                  updateForm({
                                    download_threads: Number(e.target.value),
                                  })
                                }
                                className="w-full h-1.5 rounded-full bg-slate-200 appearance-none cursor-pointer accent-primary"
                              />
                              <div className="flex justify-between text-xs text-slate-400">
                                <span>1</span>
                                <span>2</span>
                                <span>3</span>
                                <span>4</span>
                              </div>
                              <p className="text-xs text-slate-500">
                                {formValues.download_threads} thread
                                {formValues.download_threads > 1 ? "s" : ""}
                              </p>
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm">
                        <Info className="mt-0.5 h-4 w-4 text-blue-500 shrink-0" />
                        <div>
                          <p className="font-medium text-blue-800">
                            Streaming Mode
                          </p>
                          <p className="mt-0.5 text-xs text-blue-700">
                            Emails will be processed directly from Google Drive
                            without downloading the file first. This is slower
                            but uses less disk space.
                          </p>
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* Advanced Options (collapsible) */}
                <div className="border rounded-lg">
                  <button
                    type="button"
                    onClick={() => setAdvancedOpen(!advancedOpen)}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50 rounded-lg"
                  >
                    <Settings className="h-3.5 w-3.5" />
                    <span>Advanced Options</span>
                    <ChevronDown
                      className={cn(
                        "ml-auto h-4 w-4 transition-transform",
                        advancedOpen && "rotate-180",
                      )}
                    />
                  </button>
                  {advancedOpen && (
                    <div className="border-t px-4 py-3">
                      <div className="space-y-1.5">
                        <label className="text-sm font-medium text-slate-700 flex items-center">
                          Enable Auto-Tagging
                          <HelpTip text="Automatically categorize emails with tags like Newsletter, Receipt, Meeting, etc." />
                        </label>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={formValues.enable_categorization}
                          onClick={() =>
                            updateForm({
                              enable_categorization:
                                !formValues.enable_categorization,
                            })
                          }
                          className={cn(
                            "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors",
                            formValues.enable_categorization
                              ? "bg-primary"
                              : "bg-slate-200",
                          )}
                        >
                          <span
                            className={cn(
                              "pointer-events-none block h-4 w-4 rounded-full bg-white shadow-sm ring-0 transition-transform",
                              formValues.enable_categorization
                                ? "translate-x-4"
                                : "translate-x-0",
                            )}
                          />
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Info banner */}
                <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm">
                  <Info className="mt-0.5 h-4 w-4 text-blue-500 shrink-0" />
                  <div>
                    <p className="font-medium text-blue-800">
                      Processing Information
                    </p>
                    <p className="mt-0.5 text-xs text-blue-700">
                      This will start processing emails from the configured
                      source. You can optionally filter by date range and limit
                      the number of emails processed.
                    </p>
                  </div>
                </div>

                {/* Submit */}
                <div className="flex items-center gap-3">
                  <button
                    type="submit"
                    disabled={processing || !mailbox.is_active}
                    className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {processing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <PlayCircle className="h-4 w-4" />
                    )}
                    Start Processing
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate("/mailboxes")}
                    className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
                  >
                    Back to Mailboxes
                  </button>
                </div>
              </form>
            </div>
          </div>
        ) : !["gmail", "outlook_live"].includes(mailbox.mailbox_type) ? (
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b px-5 py-3">
              <PauseCircle className="h-4 w-4 text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-900">
                Processing In Progress
              </h3>
            </div>
            <div className="px-5 py-4 space-y-4">
              <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm">
                <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-500 shrink-0" />
                <div>
                  <p className="font-medium text-amber-800">
                    Processing job is currently running
                  </p>
                  <p className="mt-0.5 text-xs text-amber-700">
                    Please wait for the current job to complete before starting a
                    new one.
                  </p>
                </div>
              </div>
              <button
                onClick={() => navigate("/mailboxes")}
                className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
              >
                Back to Mailboxes
              </button>
            </div>
          </div>
        ) : null}

        {/* Job History */}
        {jobHistory.length > 0 && (
          <div className="rounded-lg border bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b px-5 py-3">
              <Clock className="h-4 w-4 text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-900">
                Recent Processing Jobs
              </h3>
            </div>
            <div className="divide-y">
              {jobHistory.slice(0, 5).map((job) => (
                <div key={job.id} className="flex items-start gap-3 px-5 py-3">
                  <div className="mt-0.5">{getJobStatusIcon(job.status)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-900">
                        {job.job_type}
                      </span>
                      <StatusBadge variant={getJobStatusVariant(job.status)}>
                        {job.status}
                      </StatusBadge>
                    </div>
                    <div className="mt-1 space-y-0.5">
                      <p className="text-xs text-slate-500">
                        Created: {formatDateTime(job.created_at)}
                      </p>
                      {job.total_records > 0 && (
                        <p className="text-xs text-slate-500">
                          Processed: {(job.processed_records || 0).toLocaleString("en-AU")} /{" "}
                          {job.total_records.toLocaleString("en-AU")} emails
                        </p>
                      )}
                      {job.failed_records > 0 && (
                        <p className="text-xs text-red-500">
                          Failed: {job.failed_records.toLocaleString("en-AU")}{" "}
                          emails
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </PageShell>
  );
};
