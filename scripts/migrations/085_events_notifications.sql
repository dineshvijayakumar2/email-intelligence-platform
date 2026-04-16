-- Migration 085: Events + Notifications tables
-- Event-driven notification system for in-app delivery via WebSocket.

-- Events: any significant system event (job state changes, sync completions, etc.)
CREATE TABLE IF NOT EXISTS events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  client_id UUID REFERENCES clients(id),
  source_type TEXT,
  source_id TEXT,
  payload JSONB DEFAULT '{}',
  dispatched_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_undispatched
  ON events(created_at)
  WHERE dispatched_at IS NULL;

CREATE INDEX idx_events_type_created
  ON events(event_type, created_at);

-- Notifications: per-recipient delivery record linked to an event
CREATE TABLE IF NOT EXISTS notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID REFERENCES events(id) ON DELETE CASCADE,
  recipient_user_id UUID NOT NULL,
  channel TEXT NOT NULL DEFAULT 'in_app',
  status TEXT NOT NULL DEFAULT 'pending',
  title TEXT,
  body TEXT,
  delivered_at TIMESTAMPTZ,
  read_at TIMESTAMPTZ,
  payload JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_unread
  ON notifications(recipient_user_id, created_at)
  WHERE status != 'read';

CREATE INDEX idx_notifications_pending
  ON notifications(created_at)
  WHERE status = 'pending';
