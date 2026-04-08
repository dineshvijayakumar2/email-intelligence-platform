import React, { useState, useEffect } from 'react';
import { CheckCircle2, AlertCircle, Unplug } from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { toast } from '@/lib/toast';
import { StatusBadge } from '@/components/ui/status-badge';
import googleDriveService from '../services/googleDriveService';

/* Google "G" icon — inline SVG so we don't need @ant-design/icons */
const GoogleIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor">
    <path d="M21.35 11.1h-9.18v2.73h5.51c-.24 1.27-.97 2.35-2.05 3.07l3.32 2.58c1.93-1.78 3.05-4.41 3.05-7.52 0-.57-.05-1.12-.14-1.65l-.51-.21z" fill="#4285F4"/>
    <path d="M12.17 22c2.78 0 5.11-.92 6.81-2.52l-3.32-2.58c-.92.62-2.1.99-3.49.99-2.68 0-4.95-1.81-5.76-4.24l-3.42 2.64C4.73 19.78 8.17 22 12.17 22z" fill="#34A853"/>
    <path d="M6.41 14.15a5.96 5.96 0 010-3.82L2.99 7.69a10.01 10.01 0 000 9.1l3.42-2.64z" fill="#FBBC05"/>
    <path d="M12.17 5.98c1.51 0 2.87.52 3.94 1.54l2.95-2.95C17.27 2.99 14.95 2 12.17 2 8.17 2 4.73 4.22 2.99 7.69l3.42 2.64c.81-2.43 3.08-4.35 5.76-4.35z" fill="#EA4335"/>
  </svg>
);

interface GoogleDriveConnectionProps {
  userId: string; // Current user ID
  onConnectionChange?: (connected: boolean) => void;
}

const GoogleDriveConnection: React.FC<GoogleDriveConnectionProps> = ({
  userId,
  onConnectionChange
}) => {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    checkConnectionStatus();
  }, [userId]);

  const checkConnectionStatus = async () => {
    if (!userId) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const isConnected = await googleDriveService.isConnectedToBackend(userId);
      setConnected(isConnected);
      onConnectionChange?.(isConnected);
    } catch (error) {
      console.error('Failed to check Google Drive connection:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async () => {
    if (!userId) {
      toast.error('User ID is required for Google Drive connection');
      return;
    }

    try {
      setConnecting(true);

      const result = await googleDriveService.authenticateForBackend(userId);

      if (result.success) {
        toast.success(result.message);
        setConnected(true);
        onConnectionChange?.(true);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to connect Google Drive';
      toast.error(errorMessage);
      console.error('Google Drive connection failed:', error);
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!userId) return;

    try {
      setConnecting(true);

      const result = await googleDriveService.disconnectFromBackend(userId);

      if (result.success) {
        toast.success(result.message);
        setConnected(false);
        onConnectionChange?.(false);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to disconnect Google Drive';
      toast.error(errorMessage);
      console.error('Google Drive disconnect failed:', error);
    } finally {
      setConnecting(false);
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border bg-white shadow-sm p-4">
        <div className="flex items-center gap-2">
          <Spinner className="h-4 w-4 animate-spin text-slate-400" />
          <span className="text-sm text-slate-500">Checking Google Drive connection...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-white shadow-sm p-4">
      <div className="flex flex-col gap-3 w-full">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            <GoogleIcon className="text-base text-[#4285f4]" />
            <span className="font-semibold text-sm text-slate-900">Google Drive</span>
            {connected ? (
              <StatusBadge variant="success" size="sm">
                <CheckCircle2 className="mr-1 h-3 w-3" />
                Connected
              </StatusBadge>
            ) : (
              <StatusBadge variant="warning" size="sm">
                <AlertCircle className="mr-1 h-3 w-3" />
                Not Connected
              </StatusBadge>
            )}
          </div>

          {connected ? (
            <button
              className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
              onClick={handleDisconnect}
              disabled={connecting}
            >
              {connecting ? <Spinner className="h-3 w-3 animate-spin" /> : <Unplug className="h-3 w-3" />}
              Disconnect
            </button>
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

        {connected ? (
          <p className="text-xs text-slate-500">
            You can now select any file from your Google Drive
          </p>
        ) : (
          <p className="text-xs text-slate-500">
            Connect your Google Drive to access email archive files directly
          </p>
        )}
      </div>
    </div>
  );
};

export default GoogleDriveConnection;
