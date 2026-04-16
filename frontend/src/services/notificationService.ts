import api from './apiClient';

export interface Notification {
  id: string;
  event_id: string;
  recipient_user_id: string;
  channel: string;
  status: string;
  title: string | null;
  body: string | null;
  delivered_at: string | null;
  read_at: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

interface NotificationListResponse {
  notifications: Notification[];
  count: number;
}

interface UnreadCountResponse {
  count: number;
}

export async function getNotifications(unread = false, limit = 50): Promise<Notification[]> {
  const data = await api.get<NotificationListResponse>(
    `/notifications?unread=${unread}&limit=${limit}`,
  );
  return data.notifications;
}

export async function getUnreadCount(): Promise<number> {
  const data = await api.get<UnreadCountResponse>('/notifications/unread-count');
  return data.count;
}

export async function markRead(notificationId: string): Promise<void> {
  await api.post(`/notifications/${notificationId}/read`);
}

export async function markAllRead(): Promise<void> {
  await api.post('/notifications/read-all');
}
