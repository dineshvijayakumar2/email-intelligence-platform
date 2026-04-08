/**
 * ErrorDisplay Component — Zero antd.
 * Collapsible panel showing failed emails with error details.
 */

import React, { useState, useEffect } from 'react';
import { AlertTriangle, RefreshCw, Info, ChevronDown, ChevronRight, X } from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { StatusBadge } from '@/components/ui/status-badge';
import { toast } from '@/lib/toast';
import { formatDateTime } from '../utils/dateUtils';
import {
  errorService, ErrorSummary, FailedEmail, FailedEmailsResponse,
} from '../services/errorService';

interface ErrorDisplayProps {
  jobId: string;
  failedCount: number;
  onRetryComplete?: () => void;
}

export const ErrorDisplay: React.FC<ErrorDisplayProps> = ({
  jobId,
  failedCount,
  onRetryComplete,
}) => {
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<ErrorSummary | null>(null);
  const [errors, setErrors] = useState<FailedEmail[]>([]);
  const [totalFailed, setTotalFailed] = useState(failedCount);
  const [hasMore, setHasMore] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [selectedError, setSelectedError] = useState<FailedEmail | null>(null);

  useEffect(() => {
    if (expanded && failedCount > 0) loadErrors();
  }, [expanded, jobId, failedCount]);

  const loadErrors = async () => {
    setLoading(true);
    try {
      const [summaryData, errorsData] = await Promise.all([
        errorService.getErrorSummary(jobId),
        errorService.getProcessingErrors(jobId, 50, 0),
      ]);
      setSummary(summaryData);
      setErrors(errorsData.emails);
      setTotalFailed(errorsData.total_failed);
      setHasMore(errorsData.has_more);
    } catch {
      toast.error('Failed to load error details');
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const result = await errorService.retryFailedEmails(jobId, 3);
      toast.success(result.message);
      if (result.emails_reset > 0) {
        await loadErrors();
        onRetryComplete?.();
      }
    } catch {
      toast.error('Failed to retry failed emails');
    } finally {
      setRetrying(false);
    }
  };

  const loadMore = async () => {
    setLoading(true);
    try {
      const moreErrors = await errorService.getProcessingErrors(jobId, 50, errors.length);
      setErrors([...errors, ...moreErrors.emails]);
      setHasMore(moreErrors.has_more);
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  if (failedCount === 0) return null;

  return (
    <>
      {/* Collapsible header */}
      <div className="mt-4 rounded-lg border border-destructive/20 overflow-hidden">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between px-4 py-3 bg-destructive/5 hover:bg-destructive/10 transition-colors"
        >
          <div className="flex items-center gap-2">
            {expanded ? <ChevronDown className="h-4 w-4 text-destructive" /> : <ChevronRight className="h-4 w-4 text-destructive" />}
            <AlertTriangle className="h-4 w-4 text-destructive" />
            <span className="text-sm font-medium text-slate-900">
              {totalFailed.toLocaleString('en-AU')} Failed Emails
            </span>
            {loading && <Spinner className="h-3.5 w-3.5 animate-spin text-slate-400" />}
          </div>
          {expanded && (
            <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
              <button onClick={loadErrors} disabled={loading}
                className="h-7 px-2 text-xs rounded border border-slate-200 hover:bg-white inline-flex items-center gap-1">
                <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} /> Refresh
              </button>
              <button onClick={handleRetry} disabled={retrying}
                className="h-7 px-2 text-xs font-medium text-white bg-destructive rounded hover:bg-destructive/90 inline-flex items-center gap-1"
                title="Reset failed emails to pending for retry (max 3 attempts)">
                <RefreshCw className={`h-3 w-3 ${retrying ? 'animate-spin' : ''}`} /> Retry Failed
              </button>
            </div>
          )}
        </button>

        {expanded && (
          <div className="p-4">
            {loading && errors.length === 0 ? (
              <div className="flex justify-center py-8">
                <Spinner className="h-6 w-6 animate-spin text-slate-400" />
              </div>
            ) : errors.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-6">No error details available</p>
            ) : (
              <>
                {/* Error type stats */}
                {summary?.error_types && Object.keys(summary.error_types).length > 0 && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                    {Object.entries(summary.error_types).map(([type, data]) => {
                      const count = typeof data === 'number' ? data : data.count;
                      return (
                        <div key={type} className="rounded-lg border bg-white p-3 text-center">
                          <StatusBadge variant={errorService.getErrorTypeColor(type) === 'red' ? 'danger' : 'warning'} size="sm">
                            {errorService.getErrorTypeLabel(type)}
                          </StatusBadge>
                          <p className="text-xl font-semibold tabular-nums mt-1">{count}</p>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Sample errors warning */}
                {summary?.sample_errors && summary.sample_errors.length > 0 && (
                  <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 mb-4">
                    <p className="text-xs font-medium text-warning mb-1">Recent Error Samples</p>
                    <ul className="text-xs text-slate-600 space-y-0.5 list-disc list-inside">
                      {summary.sample_errors.slice(0, 3).map((err, idx) => (
                        <li key={idx}>
                          <span className="text-slate-400">[{errorService.getErrorTypeLabel(err.error_type)}]</span>{' '}
                          {errorService.formatErrorMessage(err.error_message, 80)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Failed emails table */}
                <div className="rounded-lg border overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-slate-50/50">
                        <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Subject</th>
                        <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">From</th>
                        <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Error</th>
                        <th className="px-3 py-2 text-center text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Tries</th>
                        <th className="px-3 py-2 w-10"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {errors.map(err => (
                        <tr key={err.id} className="hover:bg-slate-50/50">
                          <td className="px-3 py-2 truncate max-w-[200px]">{err.subject || '(No Subject)'}</td>
                          <td className="px-3 py-2 truncate max-w-[150px] text-slate-500">{err.sender_email || 'Unknown'}</td>
                          <td className="px-3 py-2 truncate max-w-[250px] text-destructive" title={err.processing_error}>
                            {errorService.formatErrorMessage(err.processing_error, 50)}
                          </td>
                          <td className="px-3 py-2 text-center">
                            <StatusBadge variant={err.processing_attempts >= 3 ? 'danger' : 'warning'} size="sm">
                              {err.processing_attempts}
                            </StatusBadge>
                          </td>
                          <td className="px-3 py-2">
                            <button onClick={() => setSelectedError(err)} className="p-1 rounded hover:bg-slate-100" title="View Details">
                              <Info className="h-3.5 w-3.5 text-slate-400" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {hasMore && (
                  <div className="text-center mt-3">
                    <button onClick={loadMore} disabled={loading}
                      className="h-8 px-4 text-sm rounded-md border border-slate-200 hover:bg-slate-50 disabled:opacity-50">
                      Load More ({totalFailed - errors.length} remaining)
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Error Detail Modal */}
      {selectedError && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setSelectedError(null)}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <h3 className="text-sm font-semibold text-slate-900">Error Details</h3>
              <button onClick={() => setSelectedError(null)} className="p-1 rounded hover:bg-slate-100">
                <X className="h-4 w-4 text-slate-400" />
              </button>
            </div>
            <div className="p-4 space-y-3 text-sm">
              <div><span className="font-medium text-slate-500">Subject:</span> <span>{selectedError.subject || '(No Subject)'}</span></div>
              <div><span className="font-medium text-slate-500">From:</span> <span>{selectedError.sender_email || 'Unknown'}</span></div>
              <div><span className="font-medium text-slate-500">Message ID:</span> <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">{selectedError.message_id || 'Unknown'}</code></div>
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-500">Attempts:</span>
                <StatusBadge variant={selectedError.processing_attempts >= 3 ? 'danger' : 'warning'} size="sm">
                  {selectedError.processing_attempts}
                </StatusBadge>
              </div>
              <div><span className="font-medium text-slate-500">Last Attempt:</span> <span>{selectedError.last_processing_attempt ? formatDateTime(selectedError.last_processing_attempt) : 'Unknown'}</span></div>
              <div>
                <span className="font-medium text-slate-500">Error Message:</span>
                <div className="mt-1 p-3 rounded bg-slate-50 text-destructive text-xs font-mono whitespace-pre-wrap">
                  {selectedError.processing_error || 'No error message'}
                </div>
              </div>
            </div>
            <div className="flex justify-end px-4 py-3 border-t">
              <button onClick={() => setSelectedError(null)} className="h-8 px-4 text-sm rounded-md border border-slate-200 hover:bg-slate-50">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default ErrorDisplay;
