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
  role: 'admin' | 'client_manager' | 'account_manager';
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
    return users.filter(u => u.role === 'account_manager' && u.is_active);
  },
};

export default userService;
