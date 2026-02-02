/**
 * Mailbox Assignment Service
 *
 * API service for assigning mailboxes to clients and account managers.
 * Admin-only functionality.
 */

import config from '../config';
import { getAccessToken } from '../lib/supabase';

export interface MailboxAssignment {
  mailbox_id: string;
  client_id?: string | null;
  user_id?: string | null;
}

export const mailboxAssignmentService = {
  /**
   * Assign a mailbox to a client
   */
  async assignToClient(mailboxId: string, clientId: string | null): Promise<void> {
    const token = await getAccessToken();
    const response = await fetch(`${config.apiBaseUrl}/mailboxes/${mailboxId}/assign-client`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ client_id: clientId }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to assign mailbox to client');
    }

    return response.json();
  },

  /**
   * Assign a mailbox to an account manager (user)
   */
  async assignToUser(mailboxId: string, userId: string | null): Promise<void> {
    const token = await getAccessToken();
    const response = await fetch(`${config.apiBaseUrl}/mailboxes/${mailboxId}/assign-user`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ user_id: userId }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to assign mailbox to user');
    }

    return response.json();
  },
};

export default mailboxAssignmentService;
