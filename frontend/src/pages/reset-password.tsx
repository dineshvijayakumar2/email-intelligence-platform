/**
 * Reset Password Page
 *
 * Page where users can set a new password after clicking the reset link from their email.
 * Uses Supabase Auth's password update functionality.
 */

import React, { useState, useEffect } from 'react';
import { Form, Input, Button, Typography, Alert, Card, Space, message } from 'antd';
import { LockOutlined, CheckCircleOutlined, MailOutlined } from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import '../styles/login.css';

const { Title, Text, Paragraph } = Typography;

export const ResetPasswordPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isValidSession, setIsValidSession] = useState<boolean | null>(null);
  const { resetPassword, signOut } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    // Check if user has a valid recovery session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setIsValidSession(true);
      } else {
        setIsValidSession(false);
      }
    });
  }, []);

  const handleResetPassword = async (values: { password: string }) => {
    setLoading(true);
    setError(null);
    try {
      await resetPassword(values.password);
      setSuccess(true);

      // Redirect to dashboard after 3 seconds
      setTimeout(() => {
        navigate('/', { replace: true });
      }, 3000);
    } catch (err: any) {
      setError(err.message || 'Failed to reset password. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleCancelAndSignOut = async () => {
    try {
      await signOut();
      message.success('Signed out successfully');
      navigate('/login', { replace: true });
    } catch (err: any) {
      message.error('Failed to sign out');
    }
  };

  // Show loading while checking session
  if (isValidSession === null) {
    return (
      <div className="login-page">
        <div className="login-container">
          <Card className="login-card glass-card-static">
            <div style={{ textAlign: 'center', padding: '40px 0' }}>
              <Text type="secondary">Loading...</Text>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  // Show error if no valid session
  if (!isValidSession) {
    return (
      <div className="login-page">
        <div className="login-container">
          <Card className="login-card glass-card-static">
            <div className="login-header">
              <div className="login-logo">
                <MailOutlined />
              </div>
              <Title level={3}>Invalid or Expired Link</Title>
            </div>
            <Alert
              type="error"
              message="This password reset link is invalid or has expired."
              description="Please request a new password reset link from the login page."
              showIcon
              style={{ marginBottom: 20 }}
            />
            <Button type="primary" block onClick={() => navigate('/login')} size="large">
              Back to Login
            </Button>
          </Card>
        </div>
      </div>
    );
  }

  // Show success message
  if (success) {
    return (
      <div className="login-page">
        <div className="login-container">
          <Card className="login-card glass-card-static">
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <CheckCircleOutlined style={{ fontSize: 64, color: '#52c41a', marginBottom: 16 }} />
              <Title level={3}>Password Reset Successful!</Title>
              <Paragraph type="secondary">
                Your password has been updated successfully. You're already logged in and will be redirected to the dashboard.
              </Paragraph>
              <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 16 }}>
                Redirecting to dashboard...
              </Paragraph>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  // Show reset password form
  return (
    <div className="login-page">
      <div className="login-container">
        <Card className="login-card glass-card-static">
          <div className="login-header">
            <div className="login-logo">
              <MailOutlined />
            </div>
            <Title level={3} className="gradient-text">
              Set New Password
            </Title>
            <Text type="secondary">Please set a new password for your account</Text>
          </div>

          {error && (
            <Alert
              type="error"
              message={error}
              showIcon
              closable
              onClose={() => setError(null)}
              style={{ marginBottom: 20 }}
            />
          )}

          <Form onFinish={handleResetPassword} layout="vertical" size="large">
            <Form.Item
              name="password"
              label="New Password"
              rules={[
                { required: true, message: 'Please enter your new password' },
                { min: 6, message: 'Password must be at least 6 characters' },
              ]}
              hasFeedback
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="Enter new password"
                autoFocus
              />
            </Form.Item>

            <Form.Item
              name="confirmPassword"
              label="Confirm New Password"
              dependencies={['password']}
              hasFeedback
              rules={[
                { required: true, message: 'Please confirm your new password' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('Passwords do not match'));
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="Confirm new password" />
            </Form.Item>

            <Form.Item style={{ marginBottom: 0 }}>
              <Space style={{ width: '100%' }} direction="vertical">
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={loading}
                  block
                  className="glass-button-primary"
                >
                  Reset Password
                </Button>
                <Button block onClick={handleCancelAndSignOut}>
                  Cancel & Sign Out
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Card>

        <div className="login-footer">
          <Text type="secondary">Powered by Newbound Intelligence</Text>
        </div>
      </div>
    </div>
  );
};

export default ResetPasswordPage;