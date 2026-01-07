import config from '../config';

interface GoogleAuthResponse {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
}

interface GoogleDriveFile {
  id: string;
  name: string;
  mimeType: string;
  size?: string;
  modifiedTime?: string;
  webViewLink?: string;
  parents?: string[];
}

class GoogleDriveService {
  private accessToken: string | null = null;
  private tokenExpiry: Date | null = null;

  // Initialize Google API client with new Google Identity Services
  async initializeGoogleApi(): Promise<void> {
    return new Promise((resolve, reject) => {
      // Verify client ID is configured
      if (!config.googleClientId || config.googleClientId === 'your-google-client-id') {
        reject(new Error('Google Client ID not configured. Please check your environment variables.'));
        return;
      }

      console.log('🔧 Loading Google Identity Services...');
      
      // Load Google Identity Services (GIS)
      const gisScript = document.createElement('script');
      gisScript.src = 'https://accounts.google.com/gsi/client';
      gisScript.onload = () => {
        console.log('✅ Google Identity Services loaded');
        
        // Load Google API client
        const apiScript = document.createElement('script');
        apiScript.src = 'https://apis.google.com/js/api.js';
        apiScript.onload = () => {
          window.gapi.load('client', () => {
            window.gapi.client.init({
              discoveryDocs: ['https://www.googleapis.com/discovery/v1/apis/drive/v3/rest'],
            }).then(() => {
              console.log('✅ Google API client initialized');
              resolve();
            }).catch((error) => {
              console.error('❌ Google API client initialization failed:', error);
              reject(error);
            });
          });
        };
        apiScript.onerror = (error) => {
          console.error('❌ Failed to load Google API script:', error);
          reject(error);
        };
        document.head.appendChild(apiScript);
      };
      gisScript.onerror = (error) => {
        console.error('❌ Failed to load Google Identity Services:', error);
        reject(error);
      };
      document.head.appendChild(gisScript);
    });
  }

  // OAuth2 Authorization Code Flow for Backend Token Storage
  async authenticateForBackend(userId: string): Promise<{success: boolean, message: string}> {
    try {
      console.log('🔐 Starting Google Drive OAuth2 authorization code flow...');
      console.log('🔑 Client ID:', config.googleClientId);
      
      // Initialize if not already done
      if (!window.gapi || !window.google) {
        console.log('📚 Loading Google APIs...');
        await this.initializeGoogleApi();
      }

      // Use Google Identity Services for OAuth2 authorization code flow
      return new Promise((resolve, reject) => {
        const client = window.google.accounts.oauth2.initCodeClient({
          client_id: config.googleClientId,
          scope: 'https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/userinfo.email',
          ux_mode: 'popup',
          callback: async (response: any) => {
            if (response.error) {
              console.error('❌ OAuth error:', response);
              reject(new Error(`Authentication failed: ${response.error}`));
              return;
            }
            
            console.log('✅ Authorization code received:', {
              hasCode: !!response.code,
              scope: response.scope
            });

            try {
              // Send authorization code to backend for token exchange
              const backendResponse = await fetch(`${config.apiBaseUrl}/auth/google/exchange`, {
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
                throw new Error(`Backend token exchange failed: ${backendResponse.status}`);
              }

              const result = await backendResponse.json();
              console.log('✅ Backend token exchange successful:', result);

              resolve({
                success: true,
                message: 'Google Drive connected successfully!'
              });

            } catch (error) {
              console.error('❌ Backend token exchange failed:', error);
              reject(new Error(`Failed to store tokens: ${error instanceof Error ? error.message : 'Unknown error'}`));
            }
          }
        });

        // Request authorization code
        client.requestCode();
      });

    } catch (error) {
      console.error('❌ Google Drive authentication failed:', error);
      throw error;
    }
  }

  // Legacy method for direct token access (keeping for backward compatibility)
  async authenticate(): Promise<GoogleAuthResponse> {
    try {
      console.log('🔐 Starting Google Drive authentication with GIS...');
      console.log('🔑 Client ID:', config.googleClientId);
      
      // Initialize if not already done
      if (!window.gapi || !window.google) {
        console.log('📚 Loading Google APIs...');
        await this.initializeGoogleApi();
      }

      // Use Google Identity Services for authentication
      return new Promise((resolve, reject) => {
        const tokenClient = window.google.accounts.oauth2.initTokenClient({
          client_id: config.googleClientId,
          scope: 'https://www.googleapis.com/auth/drive.readonly',
          callback: (response: any) => {
            if (response.error) {
              console.error('❌ OAuth error:', response);
              reject(new Error(`Authentication failed: ${response.error}`));
              return;
            }
            
            console.log('✅ Token received:', {
              hasToken: !!response.access_token,
              tokenType: response.token_type,
              scope: response.scope,
              expiresIn: response.expires_in
            });

            // Store token information
            this.accessToken = response.access_token;
            this.tokenExpiry = new Date(Date.now() + (response.expires_in * 1000));

            // Set the token for gapi client
            window.gapi.client.setToken({
              access_token: response.access_token
            });

            resolve({
              access_token: response.access_token,
              expires_in: response.expires_in,
              token_type: response.token_type || 'Bearer',
            });
          },
          error_callback: (error: any) => {
            console.error('❌ OAuth error callback:', error);
            reject(new Error(`Authentication failed: ${error.message || 'Unknown error'}`));
          }
        });

        console.log('🚪 Requesting access token...');
        tokenClient.requestAccessToken();
      });
    } catch (error) {
      console.error('❌ Google authentication failed:', error);
      
      // Provide more helpful error messages
      const errorObj = error as any;
      if (errorObj.message?.includes('popup_blocked')) {
        throw new Error('Pop-up blocked by browser. Please allow pop-ups for this site and try again.');
      } else if (errorObj.message?.includes('access_denied')) {
        throw new Error('Access denied. Please grant permission to access Google Drive.');
      } else {
        throw new Error(`Authentication failed: ${errorObj.message || 'Unknown error'}`);
      }
    }
  }

  // Check if token is valid
  isAuthenticated(): boolean {
    if (!this.accessToken || !this.tokenExpiry) {
      return false;
    }
    return new Date() < this.tokenExpiry;
  }

  // List files from Google Drive
  async listFiles(query?: string): Promise<GoogleDriveFile[]> {
    if (!this.isAuthenticated()) {
      console.log('🔐 Not authenticated, authenticating first...');
      await this.authenticate();
    }

    try {
      console.log('📋 Listing files with query:', query);
      
      const requestParams = {
        q: query || "mimeType='application/mbox' or name contains '.mbox' or name contains '.pst' or name contains '.olm'",
        fields: 'files(id, name, mimeType, size, modifiedTime, webViewLink, parents)',
        pageSize: 100,
        orderBy: 'modifiedTime desc',
        includeItemsFromAllDrives: true,
        supportsAllDrives: true,
      };
      
      console.log('📤 Request params:', requestParams);
      
      const response = await window.gapi.client.drive.files.list(requestParams);
      
      console.log('📥 API Response:', response);
      console.log('📁 Files in response:', response.result?.files?.length || 0);
      
      const files = response.result?.files || [];
      
      if (files.length === 0) {
        console.log('⚠️ No files returned from API');
      } else {
        console.log('✅ Files retrieved:', files);
      }
      
      return files;
    } catch (error) {
      console.error('❌ Failed to list Google Drive files:', error);
      console.error('❌ Error details:', JSON.stringify(error, null, 2));
      throw error;
    }
  }

  // Get file metadata
  async getFile(fileId: string): Promise<GoogleDriveFile> {
    if (!this.isAuthenticated()) {
      await this.authenticate();
    }

    try {
      const response = await window.gapi.client.drive.files.get({
        fileId: fileId,
        fields: 'id, name, mimeType, size, modifiedTime, webViewLink, parents',
      });

      return response.result;
    } catch (error) {
      console.error('Failed to get file metadata:', error);
      throw error;
    }
  }

  // Get folder path for a file
  async getFolderPath(parentIds?: string[]): Promise<string> {
    if (!parentIds || parentIds.length === 0) {
      return 'My Drive';
    }

    try {
      // Get the first parent folder
      const parentId = parentIds[0];
      if (parentId === 'root') {
        return 'My Drive';
      }

      const response = await window.gapi.client.drive.files.get({
        fileId: parentId,
        fields: 'name, parents',
      });

      const parentFolder = response.result;
      if (parentFolder.parents && parentFolder.parents.length > 0) {
        const grandParentPath = await this.getFolderPath(parentFolder.parents);
        return `${grandParentPath}/${parentFolder.name}`;
      } else {
        return parentFolder.name || 'Unknown Folder';
      }
    } catch (error) {
      console.error('Failed to get folder path:', error);
      return 'Unknown Folder';
    }
  }

  // Download file content (returns download URL for backend processing)
  async getDownloadUrl(fileId: string): Promise<string> {
    if (!this.isAuthenticated()) {
      await this.authenticate();
    }

    // Return the download URL with access token
    return `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media&access_token=${this.accessToken}`;
  }

  // Send file info to backend for processing
  async processGoogleDriveFile(fileId: string, mailboxId: string): Promise<any> {
    const downloadUrl = await this.getDownloadUrl(fileId);
    const fileMetadata = await this.getFile(fileId);

    const response = await fetch(`${config.apiBaseUrl}/mailboxes/${mailboxId}/process-google-drive`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        file_id: fileId,
        file_name: fileMetadata.name,
        download_url: downloadUrl,
        access_token: this.accessToken,
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to process Google Drive file');
    }

    return response.json();
  }

  // Check if user has connected their Google Drive (backend stored tokens)
  async isConnectedToBackend(userId: string): Promise<boolean> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/auth/google/status/${userId}`);
      if (!response.ok) {
        return false;
      }
      const result = await response.json();
      return result.connected === true;
    } catch (error) {
      console.error('Failed to check Google Drive connection status:', error);
      return false;
    }
  }

  // Disconnect from backend (revoke stored tokens)
  async disconnectFromBackend(userId: string): Promise<{success: boolean, message: string}> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/auth/google/disconnect/${userId}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error(`Failed to disconnect: ${response.status}`);
      }

      const result = await response.json();
      return {
        success: true,
        message: result.message || 'Google Drive disconnected successfully'
      };
    } catch (error) {
      console.error('Failed to disconnect Google Drive:', error);
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to disconnect'
      };
    }
  }

  // Sign out from Google
  async signOut(): Promise<void> {
    if (this.accessToken && window.google) {
      window.google.accounts.oauth2.revoke(this.accessToken, () => {
        console.log('🚪 Access token revoked');
      });
    }
    
    // Clear stored tokens
    this.accessToken = null;
    this.tokenExpiry = null;
    
    // Clear gapi token
    if (window.gapi && window.gapi.client) {
      window.gapi.client.setToken(null);
    }
  }
}

// Extend window interface for Google APIs
declare global {
  interface Window {
    gapi: any;
    google: {
      accounts: {
        oauth2: {
          initTokenClient: (config: any) => any;
          initCodeClient: (config: any) => any;
          revoke: (token: string, callback: () => void) => void;
        };
      };
    };
  }
}

export default new GoogleDriveService();