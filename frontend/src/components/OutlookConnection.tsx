/**
 * Outlook LIVE Connection Component
 *
 * Displays Outlook connection status, sync information, and controls
 * Supports both O365 (work/school) and personal Microsoft accounts
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Alert, Button, Card, Space, Tag, Typography, message, Spin, Statistic, Tooltip, Progress, InputNumber, Divider } from 'antd';
import {
  WindowsOutlined,
  DisconnectOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
  MailOutlined,
  ClockCircleOutlined,
  SettingOutlined,
  SaveOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import outlookService, { OutlookConnectionStatus } from '../services/outlookService';

const { Text } = Typography;

interface OutlookConnectionProps {
  userId: string;
  onConnectionChange?: (connected: boolean) => void;
  compact?: boolean; // For dashboard view
}

const OutlookConnection: React.FC<OutlookConnectionProps> = ({
  userId,
  onConnectionChange,
  compact = false
}) => {
  const [status, setStatus] = useState<OutlookConnectionStatus | null>(null);
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
      const connectionStatus = await outlookService.getConnectionStatus(userId);
      setStatus(connectionStatus);
      onConnectionChange?.(connectionStatus.connected);
    } catch (error) {
      console.error('[OutlookConnection] Failed to check status:', error);
    } finally {
      setLoading(false);
    }
  }, [userId, onConnectionChange]);

  // Load config on mount
  const loadConfig = useCallback(async () => {
    try {
      const config = await outlookService.getConfig();
      setSyncInterval(config.sync_interval_minutes);
    } catch (error) {
      console.error('[OutlookConnection] Failed to load config:', error);
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
      message.error('User ID is required for Outlook connection');
      return;
    }

    try {
      setConnecting(true);
      const result = await outlookService.connect(userId);

      if (result.success) {
        message.success(result.message);
        await checkStatus();
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to connect Outlook';
      message.error(errorMessage);
      console.error('[OutlookConnection] Connection failed:', error);
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!userId) return;

    try {
      setConnecting(true);
      const result = await outlookService.disconnect(userId);

      if (result.success) {
        message.success(result.message);
        await checkStatus();
      } else {
        message.error(result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to disconnect Outlook';
      message.error(errorMessage);
      console.error('[OutlookConnection] Disconnect failed:', error);
    } finally {
      setConnecting(false);
    }
  };

  const handleSyncNow = async () => {
    if (!userId || !status?.connected) return;

    try {
      setSyncing(true);
      const result = await outlookService.triggerSync(userId);

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
      const result = await outlookService.updateConfig({
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

  const isAuthExpired = status?.sync_status === 'auth_expired' || status?.requires_reauth === true;

  const getSyncStatusTag = () => {
    if (!status) return null;

    switch (status.sync_status) {
      case 'syncing':
        return (
          <Tag color="processing" icon={<SyncOutlined spin />}>
            Syncing
          </Tag>
        );
      case 'auth_expired':
        return (
          <Tag color="warning" icon={<ExclamationCircleOutlined />}>
            Reconnect Required
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
          <Text>Checking Outlook connection...</Text>
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
            ? 'linear-gradient(135deg, rgba(0, 120, 212, 0.12) 0%, rgba(0, 183, 195, 0.12) 100%)'
            : 'linear-gradient(135deg, rgba(0, 120, 212, 0.08) 0%, rgba(0, 183, 195, 0.08) 100%)',
          border: status?.connected
            ? '1px solid rgba(0, 120, 212, 0.3)'
            : '1px dashed rgba(0, 120, 212, 0.3)',
          borderRadius: 12,
          padding: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <WindowsOutlined style={{ fontSize: 24, color: '#0078d4' }} />
          <div style={{ flex: 1 }}>
            <Text strong style={{ color: '#0078d4' }}>Outlook LIVE Sync</Text>
            {status?.connected && (
              <div style={{ marginTop: 4 }}>
                {getSyncStatusTag()}
              </div>
            )}
          </div>
          {status?.connected ? (
            isAuthExpired ? (
              <Button
                type="primary"
                size="small"
                danger
                icon={<ReloadOutlined />}
                onClick={handleConnect}
                loading={connecting}
              >
                Reconnect
              </Button>
            ) : (
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
                  title="Disconnect Outlook"
                />
              </Space>
            )
          ) : (
            <Button
              type="primary"
              size="small"
              icon={<WindowsOutlined />}
              onClick={handleConnect}
              loading={connecting}
              style={{ background: '#0078d4', borderColor: '#0078d4' }}
            >
              Connect
            </Button>
          )}
        </div>

        {status?.connected ? (
          isAuthExpired ? (
            <Alert
              type="warning"
              showIcon
              message="Authentication expired"
              description="Your Outlook token has been revoked. Reconnect to restore automatic sync."
              style={{ borderRadius: 8 }}
            />
          ) : (
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <MailOutlined style={{ marginRight: 4 }} />
                  {status.email_count.toLocaleString()} emails synced
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <ClockCircleOutlined style={{ marginRight: 4 }} />
                  {outlookService.formatRelativeTime(status.last_sync_at)}
                </Text>
              </div>
              {status.sync_status === 'syncing' && (
                <Progress percent={99} status="active" showInfo={false} size="small" strokeColor="#0078d4" />
              )}
            </Space>
          )
        ) : (
          <Text type="secondary" style={{ fontSize: 13 }}>
            Connect Outlook for real-time email sync. Supports O365 and personal accounts.
          </Text>
        )}
      </div>
    );
  }

  // Full view for dedicated Outlook settings page
  return (
    <Card
      className="glass-card"
      title={
        <Space>
          <WindowsOutlined style={{ fontSize: 20, color: '#0078d4' }} />
          <Text strong>Outlook LIVE Sync</Text>
          {status?.connected ? (
            <Tag color="blue" icon={<CheckCircleOutlined />}>Connected</Tag>
          ) : (
            <Tag color="orange" icon={<ExclamationCircleOutlined />}>Not Connected</Tag>
          )}
        </Space>
      }
      extra={
        status?.connected ? (
          isAuthExpired ? (
            <Button
              type="primary"
              danger
              icon={<ReloadOutlined />}
              onClick={handleConnect}
              loading={connecting}
            >
              Reconnect Outlook
            </Button>
          ) : (
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
          )
        ) : (
          <Button
            type="primary"
            icon={<WindowsOutlined />}
            onClick={handleConnect}
            loading={connecting}
            style={{ background: '#0078d4', borderColor: '#0078d4' }}
          >
            Connect Outlook
          </Button>
        )
      }
    >
      {status?.connected ? (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {/* Auth Expired Banner */}
          {isAuthExpired && (
            <Alert
              type="warning"
              showIcon
              message="Outlook authentication has expired"
              description="Your refresh token has been revoked or expired. Automatic sync has stopped. Click 'Reconnect Outlook' to restore sync."
              action={
                <Button
                  type="primary"
                  danger
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={handleConnect}
                  loading={connecting}
                >
                  Reconnect Outlook
                </Button>
              }
            />
          )}

          {/* Stats Row */}
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <Statistic
              title="Emails Synced"
              value={status.email_count}
              prefix={<MailOutlined />}
              valueStyle={{ color: '#0078d4' }}
            />
            <Statistic
              title="Last Sync"
              value={outlookService.formatRelativeTime(status.last_sync_at)}
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
              <Progress percent={99} status="active" strokeColor="#0078d4" />
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
                background: 'rgba(0, 120, 212, 0.05)',
                border: '1px solid rgba(0, 120, 212, 0.2)',
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
                    style={{ background: '#0078d4', borderColor: '#0078d4' }}
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
              Outlook syncs automatically every {syncInterval} minutes. Only new emails are fetched using delta queries.
            </Text>
          )}
        </Space>
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Text>
            Connect your Microsoft account to enable real-time email synchronization.
          </Text>
          <ul style={{ margin: 0, paddingLeft: 20, color: 'rgba(0,0,0,0.65)' }}>
            <li>Supports both O365 (work/school) and personal Microsoft accounts</li>
            <li>Automatic sync every {syncInterval} minutes (configurable)</li>
            <li>Incremental sync using delta queries - only fetches new emails</li>
            <li>Read-only access - we never modify your emails</li>
            <li>Secure OAuth 2.0 authentication via Microsoft Identity Platform</li>
          </ul>
        </Space>
      )}
    </Card>
  );
};

export default OutlookConnection;
