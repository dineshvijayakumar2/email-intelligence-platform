/**
 * Gmail LIVE Connection Component
 *
 * Displays Gmail connection status, sync information, and controls
 * for Stage 2 Epic 1.3 (S1-07, S1-10)
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Mail,
  Clock,
  Settings,
  Save,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Unplug,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { toast } from '@/lib/toast';
import { StatusBadge } from '@/components/ui/status-badge';
import gmailService, { GmailConnectionStatus } from '../services/gmailService';

/* Google "G" icon — inline SVG so we don't need @ant-design/icons */
const GoogleIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor">
    <path d="M21.35 11.1h-9.18v2.73h5.51c-.24 1.27-.97 2.35-2.05 3.07l3.32 2.58c1.93-1.78 3.05-4.41 3.05-7.52 0-.57-.05-1.12-.14-1.65l-.51-.21z" fill="#4285F4"/>
    <path d="M12.17 22c2.78 0 5.11-.92 6.81-2.52l-3.32-2.58c-.92.62-2.1.99-3.49.99-2.68 0-4.95-1.81-5.76-4.24l-3.42 2.64C4.73 19.78 8.17 22 12.17 22z" fill="#34A853"/>
    <path d="M6.41 14.15a5.96 5.96 0 010-3.82L2.99 7.69a10.01 10.01 0 000 9.1l3.42-2.64z" fill="#FBBC05"/>
    <path d="M12.17 5.98c1.51 0 2.87.52 3.94 1.54l2.95-2.95C17.27 2.99 14.95 2 12.17 2 8.17 2 4.73 4.22 2.99 7.69l3.42 2.64c.81-2.43 3.08-4.35 5.76-4.35z" fill="#EA4335"/>
  </svg>
);

interface GmailConnectionProps {
  userId: string;
  onConnectionChange?: (connected: boolean) => void;
  compact?: boolean; // For dashboard view
}

const GmailConnection: React.FC<GmailConnectionProps> = ({
  userId,
  onConnectionChange,
  compact = false
}) => {
  const [status, setStatus] = useState<GmailConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Configuration state
  const [showSettings, setShowSettings] = useState(false);
  const [syncInterval, setSyncInterval] = useState<number>(15);
  const [savingConfig, setSavingConfig] = useState(false);

  const checkStatus = useCallback(async () => {
    if (!userId) {
      setLoading(false);
      return;
    }

    try {
      const connectionStatus = await gmailService.getConnectionStatus(userId);
      setStatus(connectionStatus);
      onConnectionChange?.(connectionStatus.connected);
    } catch (error) {
      console.error('[GmailConnection] Failed to check status:', error);
    } finally {
      setLoading(false);
    }
  }, [userId, onConnectionChange]);

  // Load config on mount
  const loadConfig = useCallback(async () => {
    try {
      const config = await gmailService.getConfig();
      setSyncInterval(config.sync_interval_minutes);
    } catch (error) {
      console.error('[GmailConnection] Failed to load config:', error);
    }
  }, []);

  useEffect(() => {
    checkStatus();
    loadConfig();

    // Poll status every 30 seconds when syncing
    const interval = setInterval(() => {
      if (status?.sync_status === 'syncing') {
        checkStatus();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [checkStatus, loadConfig, status?.sync_status]);

  const handleConnect = async () => {
    if (!userId) {
      toast.error('User ID is required for Gmail connection');
      return;
    }

    try {
      setConnecting(true);
      const result = await gmailService.connect(userId);

      if (result.success) {
        toast.success(result.message);
        await checkStatus();
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to connect Gmail';
      toast.error(errorMessage);
      console.error('[GmailConnection] Connection failed:', error);
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!userId) return;

    try {
      setConnecting(true);
      const result = await gmailService.disconnect(userId);

      if (result.success) {
        toast.success(result.message);
        await checkStatus();
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to disconnect Gmail';
      toast.error(errorMessage);
      console.error('[GmailConnection] Disconnect failed:', error);
    } finally {
      setConnecting(false);
    }
  };

  const handleSyncNow = async () => {
    if (!userId || !status?.connected) return;

    try {
      setSyncing(true);
      const result = await gmailService.triggerSync(userId);

      if (result.success) {
        toast.success('Sync started in background');
        // Update status to show syncing
        setStatus(prev => prev ? { ...prev, sync_status: 'syncing' } : null);
        // Poll for completion
        setTimeout(checkStatus, 5000);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to trigger sync';
      toast.error(errorMessage);
    } finally {
      setSyncing(false);
    }
  };

  const handleSaveConfig = async () => {
    try {
      setSavingConfig(true);
      const result = await gmailService.updateConfig({
        sync_interval_minutes: syncInterval
      });

      if (result.success) {
        toast.success(`Sync interval updated to ${syncInterval} minutes`);
        setShowSettings(false);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to save config';
      toast.error(errorMessage);
    } finally {
      setSavingConfig(false);
    }
  };

  const isAuthExpired = status?.sync_status === 'auth_expired' || status?.requires_reauth === true;

  const getSyncStatusBadge = () => {
    if (!status) return null;

    switch (status.sync_status) {
      case 'syncing':
        return (
          <StatusBadge variant="info">
            <RefreshCw className="mr-1 h-3 w-3 animate-spin" />
            Syncing
          </StatusBadge>
        );
      case 'auth_expired':
        return (
          <StatusBadge variant="warning">
            <AlertCircle className="mr-1 h-3 w-3" />
            Reconnect Required
          </StatusBadge>
        );
      case 'error':
        return (
          <span title={status.error || ''}>
            <StatusBadge variant="danger">
              <AlertCircle className="mr-1 h-3 w-3" />
              Error
            </StatusBadge>
          </span>
        );
      case 'idle':
        return (
          <StatusBadge variant="success">
            <CheckCircle2 className="mr-1 h-3 w-3" />
            Ready
          </StatusBadge>
        );
      default:
        return (
          <StatusBadge variant="neutral">
            <Clock className="mr-1 h-3 w-3" />
            {status.sync_status}
          </StatusBadge>
        );
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border bg-white shadow-sm p-4">
        <div className="flex items-center gap-2">
          <Spinner className="h-4 w-4 animate-spin text-slate-400" />
          <span className="text-sm text-slate-500">Checking Gmail connection...</span>
        </div>
      </div>
    );
  }

  // Compact view for dashboard
  if (compact) {
    return (
      <div
        className={`rounded-xl p-5 ${
          status?.connected
            ? 'bg-gradient-to-br from-blue-50 to-green-50 border border-blue-200'
            : 'bg-gradient-to-br from-blue-50/60 to-green-50/60 border border-dashed border-blue-200'
        }`}
      >
        <div className="flex items-center gap-3 mb-3">
          <GoogleIcon className="text-2xl text-[#4285f4]" />
          <div className="flex-1">
            <span className="font-semibold text-[#4285f4]">Gmail LIVE Sync</span>
            {status?.connected && (
              <div className="mt-1">
                {getSyncStatusBadge()}
              </div>
            )}
          </div>
          {status?.connected ? (
            isAuthExpired ? (
              <button
                className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                onClick={handleConnect}
                disabled={connecting}
              >
                {connecting ? <Spinner className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                Reconnect
              </button>
            ) : (
              <div className="flex items-center gap-1">
                <button
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  onClick={handleSyncNow}
                  disabled={syncing || status.sync_status === 'syncing'}
                >
                  {syncing ? (
                    <Spinner className="h-3 w-3 animate-spin" />
                  ) : (
                    <RefreshCw className={`h-3 w-3 ${status.sync_status === 'syncing' ? 'animate-spin' : ''}`} />
                  )}
                  Sync Now
                </button>
                <button
                  className="inline-flex items-center rounded-md p-1.5 text-red-500 hover:bg-red-50 disabled:opacity-50"
                  onClick={handleDisconnect}
                  disabled={connecting}
                  title="Disconnect Gmail"
                >
                  {connecting ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <Unplug className="h-3.5 w-3.5" />}
                </button>
              </div>
            )
          ) : (
            <button
              className="inline-flex items-center gap-1.5 rounded-md bg-[#4285f4] px-3 py-1.5 text-xs font-medium text-white hover:bg-[#3367d6] disabled:opacity-50"
              onClick={handleConnect}
              disabled={connecting}
            >
              {connecting ? <Spinner className="h-3 w-3 animate-spin" /> : <GoogleIcon className="h-3 w-3" />}
              Connect
            </button>
          )}
        </div>

        {status?.connected ? (
          isAuthExpired ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
              <p className="text-sm font-medium text-amber-800">Authentication expired</p>
              <p className="mt-1 text-xs text-amber-700">
                Your Gmail token has been revoked. Reconnect to restore automatic sync.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-1 w-full">
              <div className="flex justify-between items-center">
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Mail className="h-3 w-3" />
                  {status.email_count.toLocaleString()} emails synced
                </span>
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {gmailService.formatRelativeTime(status.last_sync_at)}
                </span>
              </div>
              {status.sync_status === 'syncing' && (
                <div className="w-full bg-slate-100 rounded-full h-1.5 mt-1 overflow-hidden">
                  <div className="bg-[#4285f4] h-1.5 rounded-full animate-pulse" style={{ width: '99%' }} />
                </div>
              )}
            </div>
          )
        ) : (
          <p className="text-[13px] text-slate-500">
            Connect Gmail for real-time email sync. Auto-sync every {syncInterval} minutes.
          </p>
        )}
      </div>
    );
  }

  // Full view for dedicated Gmail settings page
  return (
    <div className="rounded-lg border bg-white shadow-sm">
      {/* Card Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-2">
          <GoogleIcon className="text-xl text-[#4285f4]" />
          <span className="font-semibold text-slate-900">Gmail LIVE Sync</span>
          {status?.connected ? (
            <StatusBadge variant="success">
              <CheckCircle2 className="mr-1 h-3 w-3" />
              Connected
            </StatusBadge>
          ) : (
            <StatusBadge variant="warning">
              <AlertCircle className="mr-1 h-3 w-3" />
              Not Connected
            </StatusBadge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {status?.connected ? (
            isAuthExpired ? (
              <button
                className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                onClick={handleConnect}
                disabled={connecting}
              >
                {connecting ? <Spinner className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Reconnect Gmail
              </button>
            ) : (
              <>
                <button
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  onClick={handleSyncNow}
                  disabled={syncing || status.sync_status === 'syncing'}
                >
                  {syncing ? (
                    <Spinner className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className={`h-4 w-4 ${status.sync_status === 'syncing' ? 'animate-spin' : ''}`} />
                  )}
                  Sync Now
                </button>
                <button
                  className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                  onClick={handleDisconnect}
                  disabled={connecting}
                >
                  {connecting ? <Spinner className="h-4 w-4 animate-spin" /> : <Unplug className="h-4 w-4" />}
                  Disconnect
                </button>
              </>
            )
          ) : (
            <button
              className="inline-flex items-center gap-1.5 rounded-md bg-[#4285f4] px-4 py-2 text-sm font-medium text-white hover:bg-[#3367d6] disabled:opacity-50"
              onClick={handleConnect}
              disabled={connecting}
            >
              {connecting ? <Spinner className="h-4 w-4 animate-spin" /> : <GoogleIcon className="h-4 w-4" />}
              Connect Gmail
            </button>
          )}
        </div>
      </div>

      {/* Card Body */}
      <div className="px-6 py-5">
        {status?.connected ? (
          <div className="flex flex-col gap-6">
            {/* Auth Expired Banner */}
            {isAuthExpired && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-amber-800">Gmail authentication has expired</p>
                    <p className="mt-1 text-sm text-amber-700">
                      Your refresh token has been revoked or expired. Automatic sync has stopped. Click 'Reconnect Gmail' to restore sync.
                    </p>
                  </div>
                  <button
                    className="ml-4 inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                    onClick={handleConnect}
                    disabled={connecting}
                  >
                    {connecting ? <Spinner className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                    Reconnect Gmail
                  </button>
                </div>
              </div>
            )}

            {/* Stats Row */}
            <div className="flex gap-6 flex-wrap">
              <div>
                <p className="text-xs text-slate-500">Emails Synced</p>
                <p className="mt-1 text-2xl font-semibold text-[#667eea] flex items-center gap-2">
                  <Mail className="h-5 w-5" />
                  {status.email_count.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Last Sync</p>
                <p className="mt-1 text-2xl font-semibold text-slate-700 flex items-center gap-2">
                  <Clock className="h-5 w-5" />
                  {gmailService.formatRelativeTime(status.last_sync_at)}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Sync Status</p>
                <div className="mt-2">
                  {getSyncStatusBadge()}
                </div>
              </div>
            </div>

            {/* Sync Progress */}
            {status.sync_status === 'syncing' && (
              <div>
                <p className="text-sm text-slate-500 mb-2">Syncing new emails...</p>
                <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                  <div className="bg-[#4285f4] h-2 rounded-full animate-pulse" style={{ width: '99%' }} />
                </div>
              </div>
            )}

            {/* Error Display */}
            {status.sync_status === 'error' && status.error && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                <p className="text-sm text-red-700 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  {status.error}
                </p>
              </div>
            )}

            {/* Settings Section */}
            <hr className="border-slate-200" />
            <div>
              <div className={`flex items-center justify-between ${showSettings ? 'mb-4' : ''}`}>
                <div className="flex items-center gap-2">
                  <Settings className="h-4 w-4 text-slate-500" />
                  <span className="font-medium text-slate-900">Sync Settings</span>
                </div>
                <button
                  className="text-sm text-slate-500 hover:text-slate-700"
                  onClick={() => setShowSettings(!showSettings)}
                >
                  {showSettings ? 'Hide' : 'Configure'}
                </button>
              </div>

              {showSettings && (
                <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-4">
                  <div className="flex flex-col gap-4">
                    <div>
                      <label className="block text-sm text-slate-500 mb-2">
                        Sync Interval (minutes)
                      </label>
                      <div className="flex items-center gap-3">
                        <input
                          type="number"
                          min={1}
                          max={1440}
                          value={syncInterval}
                          onChange={(e) => setSyncInterval(Number(e.target.value) || 15)}
                          className="w-24 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-900 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                        />
                        <span className="text-xs text-slate-500">(1 min - 24 hours)</span>
                      </div>
                    </div>
                    <button
                      className="inline-flex w-fit items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                      onClick={handleSaveConfig}
                      disabled={savingConfig}
                    >
                      {savingConfig ? <Spinner className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                      Save Settings
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Info */}
            {!showSettings && (
              <p className="text-[13px] text-slate-500">
                Gmail syncs automatically every {syncInterval} minutes. Only new emails are fetched using incremental sync.
              </p>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-slate-700">
              Connect your Gmail account to enable real-time email synchronization.
            </p>
            <ul className="list-disc pl-5 text-sm text-slate-500 space-y-1">
              <li>Automatic sync every {syncInterval} minutes (configurable)</li>
              <li>Incremental sync - only fetches new emails</li>
              <li>Read-only access - we never modify your emails</li>
              <li>Secure OAuth 2.0 authentication</li>
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};

export default GmailConnection;
