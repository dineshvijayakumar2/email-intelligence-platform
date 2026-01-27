/**
 * Gmail LIVE Connection Component
 *
 * Displays Gmail connection status, sync information, and controls
 * for Stage 2 Epic 1.3 (S1-07, S1-10)
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Button, Card, Space, Tag, Typography, message, Spin, Statistic, Tooltip, Progress, InputNumber, Divider } from 'antd';
import {
  GoogleOutlined,
  DisconnectOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
  MailOutlined,
  ClockCircleOutlined,
  SettingOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import gmailService, { GmailConnectionStatus } from '../services/gmailService';

const { Text } = Typography;

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
      message.error('User ID is required for Gmail connection');
      return;
    }

    try {
      setConnecting(true);
      const result = await gmailService.connect(userId);

      if (result.success) {
        message.success(result.message);
        await checkStatus();
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to connect Gmail';
      message.error(errorMessage);
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
        message.success(result.message);
        await checkStatus();
      } else {
        message.error(result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to disconnect Gmail';
      message.error(errorMessage);
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
        message.success('Sync started in background');
        // Update status to show syncing
        setStatus(prev => prev ? { ...prev, sync_status: 'syncing' } : null);
        // Poll for completion
        setTimeout(checkStatus, 5000);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to trigger sync';
      message.error(errorMessage);
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
        message.success(`Sync interval updated to ${syncInterval} minutes`);
        setShowSettings(false);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to save config';
      message.error(errorMessage);
    } finally {
      setSavingConfig(false);
    }
  };

  const getSyncStatusTag = () => {
    if (!status) return null;

    switch (status.sync_status) {
      case 'syncing':
        return (
          <Tag color="processing" icon={<SyncOutlined spin />}>
            Syncing
          </Tag>
        );
      case 'error':
        return (
          <Tooltip title={status.error}>
            <Tag color="error" icon={<ExclamationCircleOutlined />}>
              Error
            </Tag>
          </Tooltip>
        );
      case 'idle':
        return (
          <Tag color="success" icon={<CheckCircleOutlined />}>
            Ready
          </Tag>
        );
      default:
        return (
          <Tag color="default" icon={<ClockCircleOutlined />}>
            {status.sync_status}
          </Tag>
        );
    }
  };

  if (loading) {
    return (
      <Card size="small" className={compact ? '' : 'glass-card'}>
        <Space>
          <Spin size="small" />
          <Text>Checking Gmail connection...</Text>
        </Space>
      </Card>
    );
  }

  // Compact view for dashboard
  if (compact) {
    return (
      <div
        style={{
          background: status?.connected
            ? 'linear-gradient(135deg, rgba(66, 133, 244, 0.12) 0%, rgba(52, 168, 83, 0.12) 100%)'
            : 'linear-gradient(135deg, rgba(66, 133, 244, 0.08) 0%, rgba(52, 168, 83, 0.08) 100%)',
          border: status?.connected
            ? '1px solid rgba(66, 133, 244, 0.3)'
            : '1px dashed rgba(66, 133, 244, 0.3)',
          borderRadius: 12,
          padding: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <GoogleOutlined style={{ fontSize: 24, color: '#4285f4' }} />
          <div style={{ flex: 1 }}>
            <Text strong style={{ color: '#4285f4' }}>Gmail LIVE Sync</Text>
            {status?.connected && (
              <div style={{ marginTop: 4 }}>
                {getSyncStatusTag()}
              </div>
            )}
          </div>
          {status?.connected ? (
            <Space size={4}>
              <Button
                size="small"
                icon={<SyncOutlined spin={syncing || status.sync_status === 'syncing'} />}
                onClick={handleSyncNow}
                loading={syncing}
                disabled={status.sync_status === 'syncing'}
              >
                Sync Now
              </Button>
              <Button
                size="small"
                type="text"
                danger
                icon={<DisconnectOutlined />}
                onClick={handleDisconnect}
                loading={connecting}
                title="Disconnect Gmail"
              />
            </Space>
          ) : (
            <Button
              type="primary"
              size="small"
              icon={<GoogleOutlined />}
              onClick={handleConnect}
              loading={connecting}
            >
              Connect
            </Button>
          )}
        </div>

        {status?.connected ? (
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                <MailOutlined style={{ marginRight: 4 }} />
                {status.email_count.toLocaleString()} emails synced
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                <ClockCircleOutlined style={{ marginRight: 4 }} />
                {gmailService.formatRelativeTime(status.last_sync_at)}
              </Text>
            </div>
            {status.sync_status === 'syncing' && (
              <Progress percent={99} status="active" showInfo={false} size="small" />
            )}
          </Space>
        ) : (
          <Text type="secondary" style={{ fontSize: 13 }}>
            Connect Gmail for real-time email sync. Auto-sync every {syncInterval} minutes.
          </Text>
        )}
      </div>
    );
  }

  // Full view for dedicated Gmail settings page
  return (
    <Card
      className="glass-card"
      title={
        <Space>
          <GoogleOutlined style={{ fontSize: 20, color: '#4285f4' }} />
          <Text strong>Gmail LIVE Sync</Text>
          {status?.connected ? (
            <Tag color="green" icon={<CheckCircleOutlined />}>Connected</Tag>
          ) : (
            <Tag color="orange" icon={<ExclamationCircleOutlined />}>Not Connected</Tag>
          )}
        </Space>
      }
      extra={
        status?.connected ? (
          <Space>
            <Button
              icon={<SyncOutlined spin={syncing || status.sync_status === 'syncing'} />}
              onClick={handleSyncNow}
              loading={syncing}
              disabled={status.sync_status === 'syncing'}
            >
              Sync Now
            </Button>
            <Button
              danger
              icon={<DisconnectOutlined />}
              onClick={handleDisconnect}
              loading={connecting}
            >
              Disconnect
            </Button>
          </Space>
        ) : (
          <Button
            type="primary"
            icon={<GoogleOutlined />}
            onClick={handleConnect}
            loading={connecting}
          >
            Connect Gmail
          </Button>
        )
      }
    >
      {status?.connected ? (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {/* Stats Row */}
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <Statistic
              title="Emails Synced"
              value={status.email_count}
              prefix={<MailOutlined />}
              valueStyle={{ color: '#667eea' }}
            />
            <Statistic
              title="Last Sync"
              value={gmailService.formatRelativeTime(status.last_sync_at)}
              prefix={<ClockCircleOutlined />}
            />
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>Sync Status</Text>
              <div style={{ marginTop: 8 }}>
                {getSyncStatusTag()}
              </div>
            </div>
          </div>

          {/* Sync Progress */}
          {status.sync_status === 'syncing' && (
            <div>
              <Text type="secondary">Syncing new emails...</Text>
              <Progress percent={99} status="active" />
            </div>
          )}

          {/* Error Display */}
          {status.sync_status === 'error' && status.error && (
            <div style={{
              background: 'rgba(255, 77, 79, 0.1)',
              border: '1px solid rgba(255, 77, 79, 0.3)',
              borderRadius: 8,
              padding: 12
            }}>
              <Text type="danger">
                <ExclamationCircleOutlined style={{ marginRight: 8 }} />
                {status.error}
              </Text>
            </div>
          )}

          {/* Settings Section */}
          <Divider style={{ margin: '16px 0' }} />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: showSettings ? 16 : 0 }}>
              <Space>
                <SettingOutlined />
                <Text strong>Sync Settings</Text>
              </Space>
              <Button
                type="text"
                size="small"
                onClick={() => setShowSettings(!showSettings)}
              >
                {showSettings ? 'Hide' : 'Configure'}
              </Button>
            </div>

            {showSettings && (
              <div style={{
                background: 'rgba(102, 126, 234, 0.05)',
                border: '1px solid rgba(102, 126, 234, 0.2)',
                borderRadius: 8,
                padding: 16
              }}>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                      Sync Interval (minutes)
                    </Text>
                    <Space>
                      <InputNumber
                        min={1}
                        max={1440}
                        value={syncInterval}
                        onChange={(value) => setSyncInterval(value || 15)}
                        style={{ width: 100 }}
                      />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        (1 min - 24 hours)
                      </Text>
                    </Space>
                  </div>
                  <Button
                    type="primary"
                    icon={<SaveOutlined />}
                    onClick={handleSaveConfig}
                    loading={savingConfig}
                    size="small"
                  >
                    Save Settings
                  </Button>
                </Space>
              </div>
            )}
          </div>

          {/* Info */}
          {!showSettings && (
            <Text type="secondary" style={{ fontSize: 13 }}>
              Gmail syncs automatically every {syncInterval} minutes. Only new emails are fetched using incremental sync.
            </Text>
          )}
        </Space>
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Text>
            Connect your Gmail account to enable real-time email synchronization.
          </Text>
          <ul style={{ margin: 0, paddingLeft: 20, color: 'rgba(0,0,0,0.65)' }}>
            <li>Automatic sync every {syncInterval} minutes (configurable)</li>
            <li>Incremental sync - only fetches new emails</li>
            <li>Read-only access - we never modify your emails</li>
            <li>Secure OAuth 2.0 authentication</li>
          </ul>
        </Space>
      )}
    </Card>
  );
};

export default GmailConnection;
