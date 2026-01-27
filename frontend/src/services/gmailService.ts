/**
 * Gmail LIVE Integration Service
 *
 * Handles OAuth authentication, sync status, and filter management
 * for Gmail LIVE email synchronization (Stage 2 Epic 1.3)
 */

import config from '../config';

// Response interfaces
export interface GmailConnectionStatus {
  user_id: string;
  connected: boolean;
  last_sync_at: string | null;
  sync_status: 'idle' | 'syncing' | 'error' | 'disconnected';
  email_count: number;
  error: string | null;
}

export interface GmailSyncStatus {
  connected: boolean;
  last_sync_at: string | null;
  sync_status: string;
  email_count: number;
  error: string | null;
  recent_syncs: Array<{
    id: string;
    status: string;
    processed_records: number;
    failed_records: number;
    started_at: string;
    completed_at: string | null;
  }>;
}

export interface GmailFilter {
  id: string;
  filter_id: string;
  criteria: Record<string, unknown>;
  action: Record<string, unknown>;
  is_active: boolean;
}

class GmailService {
  /**
   * Initialize Google Identity Services for Gmail OAuth
   */
  async initializeGoogleApi(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!config.googleClientId || config.googleClientId === 'your-google-client-id') {
        reject(new Error('Google Client ID not configured. Please check your environment variables.'));
        return;
      }

      // Check if already loaded
      if (window.google?.accounts?.oauth2) {
        resolve();
        return;
      }

      console.log('[GmailService] Loading Google Identity Services...');

      const gisScript = document.createElement('script');
      gisScript.src = 'https://accounts.google.com/gsi/client';
      gisScript.onload = () => {
        console.log('[GmailService] Google Identity Services loaded');
        resolve();
      };
      gisScript.onerror = (error) => {
        console.error('[GmailService] Failed to load Google Identity Services:', error);
        reject(error);
      };
      document.head.appendChild(gisScript);
    });
  }

  /**
   * Connect Gmail via OAuth2 authorization code flow
   * Exchanges code with backend for token storage
   */
  async connect(userId: string): Promise<{ success: boolean; message: string; gmail_email?: string }> {
    try {
      console.log('[GmailService] Starting Gmail OAuth2 authorization code flow...');

      // Initialize if not already done
      await this.initializeGoogleApi();

      return new Promise((resolve, reject) => {
        const client = window.google.accounts.oauth2.initCodeClient({
          client_id: config.googleClientId,
          scope: [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.settings.basic',
            'https://www.googleapis.com/auth/userinfo.email',
            'openid'
          ].join(' '),
          ux_mode: 'popup',
          callback: async (response: { code?: string; error?: string; scope?: string }) => {
            if (response.error) {
              console.error('[GmailService] OAuth error:', response);
              reject(new Error(`Authentication failed: ${response.error}`));
              return;
            }

            if (!response.code) {
              reject(new Error('No authorization code received'));
              return;
            }

            console.log('[GmailService] Authorization code received');

            try {
              // Send authorization code to backend for token exchange
              const backendResponse = await fetch(`${config.apiBaseUrl}/gmail/auth/exchange`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                  code: response.code,
                  user_id: userId
                })
              });

              if (!backendResponse.ok) {
                const errorData = await backendResponse.json().catch(() => ({}));
                throw new Error(errorData.detail || `Backend token exchange failed: ${backendResponse.status}`);
              }

              const result = await backendResponse.json();
              console.log('[GmailService] Backend token exchange successful:', result);

              resolve({
                success: true,
                message: result.message || 'Gmail connected successfully!',
                gmail_email: result.gmail_email
              });

            } catch (error) {
              console.error('[GmailService] Backend token exchange failed:', error);
              reject(new Error(`Failed to store tokens: ${error instanceof Error ? error.message : 'Unknown error'}`));
            }
          }
        });

        // Request authorization code
        client.requestCode();
      });

    } catch (error) {
      console.error('[GmailService] Gmail authentication failed:', error);
      throw error;
    }
  }

  /**
   * Check Gmail connection status for a user
   */
  async getConnectionStatus(userId: string): Promise<GmailConnectionStatus> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/gmail/auth/status/${userId}`);

      if (!response.ok) {
        throw new Error(`Failed to get connection status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[GmailService] Failed to get connection status:', error);
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
   * Check if user is connected to Gmail
   */
  async isConnected(userId: string): Promise<boolean> {
    const status = await this.getConnectionStatus(userId);
    return status.connected;
  }

  /**
   * Disconnect Gmail integration
   */
  async disconnect(userId: string): Promise<{ success: boolean; message: string }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/gmail/auth/disconnect/${userId}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to disconnect: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        message: result.message || 'Gmail disconnected successfully'
      };
    } catch (error) {
      console.error('[GmailService] Failed to disconnect Gmail:', error);
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
      const response = await fetch(`${config.apiBaseUrl}/gmail/${userId}/sync`, {
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
      console.error('[GmailService] Failed to trigger sync:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to trigger sync'
      };
    }
  }

  /**
   * Get detailed sync status including recent jobs
   */
  async getSyncStatus(userId: string): Promise<GmailSyncStatus> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/gmail/${userId}/sync-status`);

      if (!response.ok) {
        throw new Error(`Failed to get sync status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[GmailService] Failed to get sync status:', error);
      return {
        connected: false,
        last_sync_at: null,
        sync_status: 'error',
        email_count: 0,
        error: error instanceof Error ? error.message : 'Failed to get sync status',
        recent_syncs: []
      };
    }
  }

  /**
   * Get imported Gmail filters
   */
  async getFilters(userId: string): Promise<{ filters: GmailFilter[]; count: number }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/gmail/${userId}/filters`);

      if (!response.ok) {
        throw new Error(`Failed to get filters: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[GmailService] Failed to get filters:', error);
      return { filters: [], count: 0 };
    }
  }

  /**
   * Import filters from Gmail
   */
  async importFilters(userId: string): Promise<{ success: boolean; imported_count: number; filters: GmailFilter[] }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/gmail/${userId}/import-filters`, {
        method: 'POST'
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to import filters: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        imported_count: result.imported_count,
        filters: result.filters
      };
    } catch (error) {
      console.error('[GmailService] Failed to import filters:', error);
      return {
        success: false,
        imported_count: 0,
        filters: []
      };
    }
  }

  /**
   * Extend an archive-based mailbox with LIVE Gmail sync
   */
  async extendMailboxWithGmail(mailboxId: string, userId: string): Promise<{ success: boolean; message: string; mailbox?: Record<string, unknown> }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/gmail/extend-mailbox`, {
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
        message: result.message || 'Mailbox extended with Gmail LIVE sync',
        mailbox: result.mailbox
      };
    } catch (error) {
      console.error('[GmailService] Failed to extend mailbox:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to extend mailbox'
      };
    }
  }

  /**
   * Fetch emails from Gmail for a specific date range
   * This allows pulling historical emails on-demand without processing archive files
   */
  async fetchEmailsByDateRange(
    mailboxId: string,
    userId: string,
    startDate: string,
    endDate: string,
    maxEmails?: number
  ): Promise<{ success: boolean; message: string; job_id?: string }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/gmail/fetch-date-range`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
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
      console.error('[GmailService] Failed to fetch emails by date range:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to fetch emails'
      };
    }
  }

  /**
   * Get Gmail sync configuration
   */
  async getConfig(): Promise<{
    sync_interval_minutes: number;
    service_interval_minutes: number;
    max_emails_per_sync: number;
    sync_service_running: boolean;
    interval_synced: boolean;
  }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/gmail/config`);

      if (!response.ok) {
        throw new Error(`Failed to get config: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[GmailService] Failed to get config:', error);
      // Return defaults on error
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
   * Update Gmail sync configuration
   */
  async updateConfig(updates: {
    sync_interval_minutes?: number;
  }): Promise<{ success: boolean; message: string; current_config?: any }> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/gmail/config`, {
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
      console.error('[GmailService] Failed to update config:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to update configuration'
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

export const gmailService = new GmailService();
export default gmailService;
