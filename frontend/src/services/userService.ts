/**
 * User Service
 *
 * API service for user management operations.
 */

import config from '../config';
import { getAccessToken } from '../lib/supabase';

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  roles: Array<'admin' | 'client_manager' | 'account_manager'>;
  is_active: boolean;
}

export const userService = {
  /**
   * Get all users (admin only)
   */
  async getUsers(): Promise<UserProfile[]> {
    const token = await getAccessToken();
    const response = await fetch(`${config.apiBaseUrl}/auth/users`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to fetch users');
    }

    return response.json();
  },

  /**
   * Get account managers only
   */
  async getAccountManagers(): Promise<UserProfile[]> {
    const users = await this.getUsers();
    return users.filter(u => u.roles?.includes('account_manager') && u.is_active);
  },

  /**
   * Get account managers assigned to a specific client
   * @param clientId - The client ID to filter by
   */
  async getAccountManagersByClient(clientId: string): Promise<UserProfile[]> {
    const token = await getAccessToken();
    const response = await fetch(
      `${config.apiBaseUrl}/auth/users?role=account_manager&active_only=true`,
      {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      }
    );

    if (!response.ok) {
      throw new Error('Failed to fetch account managers');
    }

    const users: UserProfile[] = await response.json();

    // Filter to only those assigned to the specific client
    // Note: Backend returns assigned_clients array for each user
    return users.filter((u) => {
      const userWithClients = u as any; // Backend returns extended type with assigned_clients
      return userWithClients.assigned_clients?.some((c: any) => c.id === clientId);
    });
  },
};

export default userService;
