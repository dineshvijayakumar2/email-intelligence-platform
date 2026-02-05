/**
 * Outlook LIVE Integration Service
 *
 * Handles OAuth authentication, sync status, and email management
 * for Outlook/O365 LIVE email synchronization
 *
 * Supports both O365 (work/school) and personal Microsoft accounts
 */

import config from '../config';
import { getAccessToken } from '../lib/supabase';

// Declare MSAL types for TypeScript
declare global {
  interface Window {
    msal?: {
      PublicClientApplication: new (config: MsalConfig) => MsalClient;
    };
  }
}

interface MsalConfig {
  auth: {
    clientId: string;
    authority: string;
    redirectUri: string;
  };
  cache?: {
    cacheLocation: string;
    storeAuthStateInCookie?: boolean;
  };
}

interface MsalClient {
  loginPopup(request: { scopes: string[] }): Promise<{ code?: string }>;
  acquireTokenPopup(request: { scopes: string[] }): Promise<{ accessToken: string }>;
}

// Response interfaces
export interface OutlookConnectionStatus {
  user_id: string;
  connected: boolean;
  last_sync_at: string | null;
  sync_status: 'idle' | 'syncing' | 'error' | 'disconnected';
  email_count: number;
  error: string | null;
}

export interface OutlookSyncStatus {
  connected: boolean;
  last_sync_at: string | null;
  sync_status: string;
  email_count: number;
  error: string | null;
  has_delta_link: boolean;
  recent_jobs: Array<{
    id: string;
    status: string;
    processed_records: number;
    failed_records: number;
    started_at: string;
    completed_at: string | null;
  }>;
}

// Mailbox-specific Outlook status (per-mailbox integration)
export interface MailboxOutlookStatus {
  connected: boolean;
  outlook_email?: string;
  last_sync_at?: string;
  sync_status: 'idle' | 'syncing' | 'error' | 'disconnected';
  email_count: number;
  error?: string;
  connected_at?: string;
}

// Microsoft OAuth scopes
const OUTLOOK_SCOPES = [
  'openid',
  'profile',
  'email',
  'offline_access',
  'User.Read',
  'Mail.Read',
  'MailboxSettings.Read'
];

class OutlookService {
  private msalScriptLoaded = false;

  /**
   * Initialize MSAL (Microsoft Authentication Library) for OAuth
   */
  async initializeMsal(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!config.microsoftClientId || config.microsoftClientId === 'your-microsoft-client-id') {
        reject(new Error('Microsoft Client ID not configured. Please check your environment variables.'));
        return;
      }

      // Check if already loaded
      if (this.msalScriptLoaded && window.msal) {
        resolve();
        return;
      }

      console.log('[OutlookService] Loading MSAL library...');

      const msalScript = document.createElement('script');
      msalScript.src = 'https://alcdn.msauth.net/browser/2.38.0/js/msal-browser.min.js';
      msalScript.onload = () => {
        console.log('[OutlookService] MSAL library loaded');
        this.msalScriptLoaded = true;
        resolve();
      };
      msalScript.onerror = (error) => {
        console.error('[OutlookService] Failed to load MSAL library:', error);
        reject(error);
      };
      document.head.appendChild(msalScript);
    });
  }

  /**
   * Connect Outlook via OAuth2 authorization code flow
   * Uses MSAL popup for authentication
   */
  async connect(userId: string): Promise<{ success: boolean; message: string; outlook_email?: string }> {
    try {
      console.log('[OutlookService] Starting Outlook OAuth2 authorization code flow...');

      // Initialize if not already done
      await this.initializeMsal();

      // Create MSAL instance
      const msalConfig: MsalConfig = {
        auth: {
          clientId: config.microsoftClientId,
          authority: 'https://login.microsoftonline.com/common',
          redirectUri: config.microsoftRedirectUri
        },
        cache: {
          cacheLocation: 'sessionStorage',
          storeAuthStateInCookie: false
        }
      };

      // Use MSAL's built-in popup flow to get authorization code
      // Note: MSAL browser typically returns tokens directly, but we need the code
      // for our backend to exchange. We'll use a custom approach.

      // Build authorization URL manually for code flow
      const authUrl = new URL('https://login.microsoftonline.com/common/oauth2/v2.0/authorize');
      authUrl.searchParams.set('client_id', config.microsoftClientId);
      authUrl.searchParams.set('response_type', 'code');
      authUrl.searchParams.set('redirect_uri', config.microsoftRedirectUri);
      authUrl.searchParams.set('scope', OUTLOOK_SCOPES.join(' '));
      authUrl.searchParams.set('response_mode', 'query');
      authUrl.searchParams.set('state', userId); // Pass userId in state

      return new Promise((resolve, reject) => {
        // Open popup for authorization
        const width = 500;
        const height = 600;
        const left = window.screenX + (window.outerWidth - width) / 2;
        const top = window.screenY + (window.outerHeight - height) / 2;

        const popup = window.open(
          authUrl.toString(),
          'Outlook Login',
          `width=${width},height=${height},left=${left},top=${top}`
        );

        if (!popup) {
          reject(new Error('Failed to open popup. Please allow popups for this site.'));
          return;
        }

        // Poll for the redirect with authorization code
        const pollInterval = setInterval(() => {
          try {
            // Check if popup is closed
            if (popup.closed) {
              clearInterval(pollInterval);
              reject(new Error('Authentication cancelled'));
              return;
            }

            // Try to get the redirect URL
            const currentUrl = popup.location.href;

            if (currentUrl.startsWith(config.microsoftRedirectUri)) {
              clearInterval(pollInterval);
              popup.close();

              const urlParams = new URLSearchParams(new URL(currentUrl).search);
              const code = urlParams.get('code');
              const error = urlParams.get('error');
              const errorDescription = urlParams.get('error_description');

              if (error) {
                reject(new Error(`Authentication failed: ${errorDescription || error}`));
                return;
              }

              if (!code) {
                reject(new Error('No authorization code received'));
                return;
              }

              console.log('[OutlookService] Authorization code received');

              // Exchange code with backend
              this.exchangeCodeWithBackend(code, userId)
                .then(resolve)
                .catch(reject);
            }
          } catch (e) {
            // Cross-origin error - popup is still on Microsoft domain
            // This is expected, continue polling
          }
        }, 500);

        // Timeout after 5 minutes
        setTimeout(() => {
          clearInterval(pollInterval);
          if (!popup.closed) {
            popup.close();
          }
          reject(new Error('Authentication timed out'));
        }, 300000);
      });

    } catch (error) {
      console.error('[OutlookService] Outlook authentication failed:', error);
      throw error;
    }
  }

  /**
   * Exchange authorization code with backend
   */
  private async exchangeCodeWithBackend(
    code: string,
    userId: string
  ): Promise<{ success: boolean; message: string; outlook_email?: string }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/outlook/auth/exchange`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          code: code,
          user_id: userId,
          redirect_uri: config.microsoftRedirectUri
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Backend token exchange failed: ${response.status}`);
      }

      const result = await response.json();
      console.log('[OutlookService] Backend token exchange successful:', result);

      return {
        success: true,
        message: result.message || 'Outlook connected successfully!',
        outlook_email: result.outlook_email
      };
    } catch (error) {
      console.error('[OutlookService] Backend token exchange failed:', error);
      throw new Error(`Failed to store tokens: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  /**
   * Check Outlook connection status for a user
   */
  async getConnectionStatus(userId: string): Promise<OutlookConnectionStatus> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/outlook/auth/status/${userId}`);

      if (!response.ok) {
        throw new Error(`Failed to get connection status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[OutlookService] Failed to get connection status:', error);
      return {
        user_id: userId,
        connected: false,
        last_sync_at: null,
        sync_status: 'disconnected',
        email_count: 0,
        error: error instanceof Error ? error.message : 'Failed to check connection'
      };
    }
  }

  /**
   * Check if user is connected to Outlook
   */
  async isConnected(userId: string): Promise<boolean> {
    const status = await this.getConnectionStatus(userId);
    return status.connected;
  }

  /**
   * Disconnect Outlook integration
   */
  async disconnect(userId: string): Promise<{ success: boolean; message: string }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/outlook/auth/disconnect/${userId}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to disconnect: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        message: result.message || 'Outlook disconnected successfully'
      };
    } catch (error) {
      console.error('[OutlookService] Failed to disconnect Outlook:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to disconnect'
      };
    }
  }

  /**
   * Trigger manual sync for a user
   */
  async triggerSync(userId: string): Promise<{ success: boolean; message: string }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/outlook/${userId}/sync`, {
        method: 'POST'
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to trigger sync: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        message: result.message || 'Sync started'
      };
    } catch (error) {
      console.error('[OutlookService] Failed to trigger sync:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to trigger sync'
      };
    }
  }

  /**
   * Get detailed sync status including recent jobs
   */
  async getSyncStatus(userId: string): Promise<OutlookSyncStatus> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/outlook/${userId}/sync-status`);

      if (!response.ok) {
        throw new Error(`Failed to get sync status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[OutlookService] Failed to get sync status:', error);
      return {
        connected: false,
        last_sync_at: null,
        sync_status: 'error',
        email_count: 0,
        error: error instanceof Error ? error.message : 'Failed to get sync status',
        has_delta_link: false,
        recent_jobs: []
      };
    }
  }

  /**
   * Extend an archive-based mailbox with LIVE Outlook sync
   */
  async extendMailboxWithOutlook(
    mailboxId: string,
    userId: string
  ): Promise<{ success: boolean; message: string; mailbox?: Record<string, unknown> }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/outlook/extend-mailbox`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mailbox_id: mailboxId,
          user_id: userId
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to extend mailbox: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        message: result.message || 'Mailbox extended with Outlook LIVE sync',
        mailbox: result.mailbox
      };
    } catch (error) {
      console.error('[OutlookService] Failed to extend mailbox:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to extend mailbox'
      };
    }
  }

  /**
   * Fetch emails from Outlook for a specific date range
   */
  async fetchEmailsByDateRange(
    mailboxId: string,
    userId: string,
    startDate: string,
    endDate: string,
    maxEmails?: number
  ): Promise<{ success: boolean; message: string; job_id?: string }> {
    try {
      // Get auth token from Supabase session
      const token = await getAccessToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${config.apiBaseUrl}/outlook/fetch-date-range`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          mailbox_id: mailboxId,
          user_id: userId,
          start_date: startDate,
          end_date: endDate,
          max_emails: maxEmails
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to fetch emails: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        message: result.message || 'Email fetch started',
        job_id: result.job_id
      };
    } catch (error) {
      console.error('[OutlookService] Failed to fetch emails by date range:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to fetch emails'
      };
    }
  }

  /**
   * Get Outlook sync configuration
   */
  async getConfig(): Promise<{
    sync_interval_minutes: number;
    service_interval_minutes: number;
    max_emails_per_sync: number;
    sync_service_running: boolean;
    interval_synced: boolean;
  }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/outlook/config`);

      if (!response.ok) {
        throw new Error(`Failed to get config: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[OutlookService] Failed to get config:', error);
      return {
        sync_interval_minutes: 15,
        service_interval_minutes: 15,
        max_emails_per_sync: 500,
        sync_service_running: false,
        interval_synced: true
      };
    }
  }

  /**
   * Update Outlook sync configuration
   */
  async updateConfig(updates: {
    sync_interval_minutes?: number;
  }): Promise<{ success: boolean; message: string; current_config?: Record<string, unknown> }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/outlook/config`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updates)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to update config: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        message: result.message || 'Configuration updated',
        current_config: result.current_config
      };
    } catch (error) {
      console.error('[OutlookService] Failed to update config:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to update configuration'
      };
    }
  }

  // ============================================
  // MAILBOX-SPECIFIC OUTLOOK INTEGRATION METHODS
  // ============================================

  /**
   * Connect Outlook directly to a specific mailbox
   * Stores tokens in mailbox.connection_config, not user_integrations
   */
  async connectToMailbox(mailboxId: string): Promise<{
    success: boolean;
    outlook_email?: string;
    message: string;
  }> {
    try {
      console.log('[OutlookService] Starting Outlook OAuth2 for mailbox:', mailboxId);

      // Initialize if not already done
      await this.initializeMsal();

      // Build authorization URL
      const authUrl = new URL('https://login.microsoftonline.com/common/oauth2/v2.0/authorize');
      authUrl.searchParams.set('client_id', config.microsoftClientId);
      authUrl.searchParams.set('response_type', 'code');
      authUrl.searchParams.set('redirect_uri', config.microsoftRedirectUri);
      authUrl.searchParams.set('scope', OUTLOOK_SCOPES.join(' '));
      authUrl.searchParams.set('response_mode', 'query');
      authUrl.searchParams.set('state', `mailbox:${mailboxId}`);

      return new Promise((resolve, reject) => {
        const width = 500;
        const height = 600;
        const left = window.screenX + (window.outerWidth - width) / 2;
        const top = window.screenY + (window.outerHeight - height) / 2;

        const popup = window.open(
          authUrl.toString(),
          'Outlook Login',
          `width=${width},height=${height},left=${left},top=${top}`
        );

        if (!popup) {
          reject(new Error('Failed to open popup. Please allow popups for this site.'));
          return;
        }

        const pollInterval = setInterval(() => {
          try {
            if (popup.closed) {
              clearInterval(pollInterval);
              reject(new Error('Authentication cancelled'));
              return;
            }

            const currentUrl = popup.location.href;

            if (currentUrl.startsWith(config.microsoftRedirectUri)) {
              clearInterval(pollInterval);
              popup.close();

              const urlParams = new URLSearchParams(new URL(currentUrl).search);
              const code = urlParams.get('code');
              const error = urlParams.get('error');
              const errorDescription = urlParams.get('error_description');

              if (error) {
                reject(new Error(`Authentication failed: ${errorDescription || error}`));
                return;
              }

              if (!code) {
                reject(new Error('No authorization code received'));
                return;
              }

              console.log('[OutlookService] Authorization code received for mailbox');

              // Exchange code with backend for this mailbox
              this.exchangeCodeForMailbox(code, mailboxId)
                .then(resolve)
                .catch(reject);
            }
          } catch (e) {
            // Cross-origin error - continue polling
          }
        }, 500);

        setTimeout(() => {
          clearInterval(pollInterval);
          if (!popup.closed) {
            popup.close();
          }
          reject(new Error('Authentication timed out'));
        }, 300000);
      });

    } catch (error) {
      console.error('[OutlookService] Mailbox Outlook authentication failed:', error);
      throw error;
    }
  }

  /**
   * Exchange authorization code for mailbox connection
   */
  private async exchangeCodeForMailbox(
    code: string,
    mailboxId: string
  ): Promise<{ success: boolean; outlook_email?: string; message: string }> {
    try {
      const token = await getAccessToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${config.apiBaseUrl}/outlook/mailbox/${mailboxId}/connect`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          code: code,
          redirect_uri: config.microsoftRedirectUri
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Backend token exchange failed: ${response.status}`);
      }

      const result = await response.json();
      console.log('[OutlookService] Mailbox Outlook connection successful:', result);

      return {
        success: true,
        message: result.message || 'Outlook connected to mailbox successfully!',
        outlook_email: result.outlook_email
      };
    } catch (error) {
      console.error('[OutlookService] Mailbox Outlook connection failed:', error);
      throw new Error(`Failed to connect Outlook: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  /**
   * Disconnect Outlook from a specific mailbox
   */
  async disconnectFromMailbox(mailboxId: string): Promise<{ success: boolean; message: string }> {
    try {
      const token = await getAccessToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${config.apiBaseUrl}/outlook/mailbox/${mailboxId}/disconnect`, {
        method: 'DELETE',
        headers
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to disconnect: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        message: result.message || 'Outlook disconnected from mailbox'
      };
    } catch (error) {
      console.error('[OutlookService] Failed to disconnect Outlook from mailbox:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to disconnect'
      };
    }
  }

  /**
   * Get Outlook sync status for a specific mailbox
   */
  async getMailboxOutlookStatus(mailboxId: string): Promise<MailboxOutlookStatus> {
    try {
      const token = await getAccessToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${config.apiBaseUrl}/outlook/mailbox/${mailboxId}/status`, {
        headers
      });

      if (!response.ok) {
        throw new Error(`Failed to get mailbox Outlook status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[OutlookService] Failed to get mailbox Outlook status:', error);
      return {
        connected: false,
        sync_status: 'disconnected',
        email_count: 0,
        error: error instanceof Error ? error.message : 'Failed to check connection'
      };
    }
  }

  /**
   * Trigger manual sync for a specific mailbox
   */
  async triggerMailboxSync(mailboxId: string): Promise<{ success: boolean; message: string }> {
    try {
      const token = await getAccessToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(`${config.apiBaseUrl}/outlook/mailbox/${mailboxId}/sync`, {
        method: 'POST',
        headers
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to trigger sync: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        message: result.message || 'Sync started for mailbox'
      };
    } catch (error) {
      console.error('[OutlookService] Failed to trigger mailbox sync:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to trigger sync'
      };
    }
  }

  /**
   * Format relative time for display
   */
  formatRelativeTime(dateString: string | null): string {
    if (!dateString) return 'Never';

    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString();
  }
}

export const outlookService = new OutlookService();
export default outlookService;
