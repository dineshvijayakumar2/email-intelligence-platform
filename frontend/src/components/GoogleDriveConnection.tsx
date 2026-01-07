import React, { useState, useEffect } from 'react';
import { Button, Card, Space, Tag, Typography, message, Spin } from 'antd';
import { GoogleOutlined, DisconnectOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import googleDriveService from '../services/googleDriveService';

const { Text } = Typography;

interface GoogleDriveConnectionProps {
  userId: string; // Current user ID
  onConnectionChange?: (connected: boolean) => void;
}

const GoogleDriveConnection: React.FC<GoogleDriveConnectionProps> = ({ 
  userId, 
  onConnectionChange 
}) => {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    checkConnectionStatus();
  }, [userId]);

  const checkConnectionStatus = async () => {
    if (!userId) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const isConnected = await googleDriveService.isConnectedToBackend(userId);
      setConnected(isConnected);
      onConnectionChange?.(isConnected);
    } catch (error) {
      console.error('Failed to check Google Drive connection:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async () => {
    if (!userId) {
      message.error('User ID is required for Google Drive connection');
      return;
    }

    try {
      setConnecting(true);
      
      const result = await googleDriveService.authenticateForBackend(userId);
      
      if (result.success) {
        message.success(result.message);
        setConnected(true);
        onConnectionChange?.(true);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to connect Google Drive';
      message.error(errorMessage);
      console.error('Google Drive connection failed:', error);
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!userId) return;

    try {
      setConnecting(true);
      
      const result = await googleDriveService.disconnectFromBackend(userId);
      
      if (result.success) {
        message.success(result.message);
        setConnected(false);
        onConnectionChange?.(false);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to disconnect Google Drive';
      message.error(errorMessage);
      console.error('Google Drive disconnect failed:', error);
    } finally {
      setConnecting(false);
    }
  };

  if (loading) {
    return (
      <Card size="small">
        <Space>
          <Spin size="small" />
          <Text>Checking Google Drive connection...</Text>
        </Space>
      </Card>
    );
  }

  return (
    <Card size="small">
      <Space direction="vertical" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <GoogleOutlined style={{ fontSize: 16, color: '#4285f4' }} />
            <Text strong>Google Drive</Text>
            {connected ? (
              <Tag color="green" icon={<CheckCircleOutlined />}>Connected</Tag>
            ) : (
              <Tag color="orange" icon={<ExclamationCircleOutlined />}>Not Connected</Tag>
            )}
          </Space>
          
          {connected ? (
            <Button 
              size="small" 
              danger 
              icon={<DisconnectOutlined />}
              onClick={handleDisconnect}
              loading={connecting}
            >
              Disconnect
            </Button>
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
        
        {connected ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            ✅ You can now select any file from your Google Drive
          </Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            Connect your Google Drive to access email archive files directly
          </Text>
        )}
      </Space>
    </Card>
  );
};

export default GoogleDriveConnection;