/**
 * Login Page
 *
 * Authentication page with email/password, Google, and Microsoft OAuth options.
 * Uses Supabase Auth for all authentication methods.
 */

import React, { useState, useEffect } from 'react';
import { Form, Input, Button, Divider, Typography, Alert, Space, Card, Tabs } from 'antd';
import {
  UserOutlined,
  LockOutlined,
  GoogleOutlined,
  WindowsOutlined,
  MailOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useLocation } from 'react-router-dom';
import { isSupabaseConfigured } from '../lib/supabase';
import '../styles/login.css';

const { Title, Text, Paragraph } = Typography;

export const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>('login');
  const { signInWithEmail, signInWithGoogle, signInWithMicrosoft, signUp, isAuthenticated } =
    useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const isConfigured = isSupabaseConfigured();

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      const from = (location.state as any)?.from?.pathname || '/';
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, location]);

  const handleEmailLogin = async (values: { email: string; password: string }) => {
    setLoading(true);
    setError(null);
    try {
      await signInWithEmail(values.email, values.password);
      const from = (location.state as any)?.from?.pathname || '/';
      navigate(from, { replace: true });
    } catch (err: any) {
      setError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleSignUp = async (values: { email: string; password: string; name: string }) => {
    setLoading(true);
    setError(null);
    try {
      await signUp(values.email, values.password, values.name);
      setError(null);
      setActiveTab('login');
      // Show success message
      alert('Account created! Please check your email to verify your account.');
    } catch (err: any) {
      setError(err.message || 'Sign up failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError(null);
    try {
      await signInWithGoogle();
    } catch (err: any) {
      setError(err.message || 'Google login failed');
    }
  };

  const handleMicrosoftLogin = async () => {
    setError(null);
    try {
      await signInWithMicrosoft();
    } catch (err: any) {
      setError(err.message || 'Microsoft login failed');
    }
  };

  if (!isConfigured) {
    return (
      <div className="login-page">
        <div className="login-container">
          <Card className="login-card glass-card-static">
            <div className="login-header">
              <div className="login-logo">
                <MailOutlined />
              </div>
              <Title level={3}>Configuration Required</Title>
              <Text type="secondary">
                Supabase authentication is not configured. Please set the following environment
                variables:
              </Text>
            </div>
            <Alert
              type="warning"
              message="Missing Configuration"
              description={
                <div>
                  <code>VITE_SUPABASE_URL</code>
                  <br />
                  <code>VITE_SUPABASE_ANON_KEY</code>
                </div>
              }
              showIcon
              style={{ marginTop: 16 }}
            />
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-container">
        <Card className="login-card glass-card-static">
          <div className="login-header">
            <div className="login-logo">
              <MailOutlined />
            </div>
            <Title level={3} className="gradient-text">
              Email Intelligence Platform
            </Title>
            <Text type="secondary">Sign in to access your mailbox analytics</Text>
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

          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            centered
            items={[
              {
                key: 'login',
                label: 'Sign In',
                children: (
                  <>
                    {/* OAuth Buttons */}
                    <Space direction="vertical" style={{ width: '100%', marginBottom: 20 }}>
                      <Button
                        block
                        size="large"
                        icon={<GoogleOutlined />}
                        onClick={handleGoogleLogin}
                        className="oauth-btn google-btn"
                      >
                        Continue with Google
                      </Button>
                      <Button
                        block
                        size="large"
                        icon={<WindowsOutlined />}
                        onClick={handleMicrosoftLogin}
                        className="oauth-btn microsoft-btn"
                      >
                        Continue with Microsoft
                      </Button>
                    </Space>

                    <Divider plain>
                      <Text type="secondary">or sign in with email</Text>
                    </Divider>

                    {/* Email/Password Form */}
                    <Form onFinish={handleEmailLogin} layout="vertical" size="large">
                      <Form.Item
                        name="email"
                        rules={[
                          { required: true, message: 'Please enter your email' },
                          { type: 'email', message: 'Please enter a valid email' },
                        ]}
                      >
                        <Input prefix={<UserOutlined />} placeholder="Email address" />
                      </Form.Item>
                      <Form.Item
                        name="password"
                        rules={[{ required: true, message: 'Please enter your password' }]}
                      >
                        <Input.Password prefix={<LockOutlined />} placeholder="Password" />
                      </Form.Item>
                      <Form.Item style={{ marginBottom: 0 }}>
                        <Button
                          type="primary"
                          htmlType="submit"
                          loading={loading}
                          block
                          className="glass-button-primary"
                        >
                          Sign In
                        </Button>
                      </Form.Item>
                    </Form>
                  </>
                ),
              },
              {
                key: 'signup',
                label: 'Create Account',
                children: (
                  <>
                    {/* OAuth Buttons */}
                    <Space direction="vertical" style={{ width: '100%', marginBottom: 20 }}>
                      <Button
                        block
                        size="large"
                        icon={<GoogleOutlined />}
                        onClick={handleGoogleLogin}
                        className="oauth-btn google-btn"
                      >
                        Continue with Google
                      </Button>
                      <Button
                        block
                        size="large"
                        icon={<WindowsOutlined />}
                        onClick={handleMicrosoftLogin}
                        className="oauth-btn microsoft-btn"
                      >
                        Continue with Microsoft
                      </Button>
                    </Space>

                    <Divider plain>
                      <Text type="secondary">or create account with email</Text>
                    </Divider>

                    <Form onFinish={handleSignUp} layout="vertical" size="large">
                      <Form.Item
                        name="name"
                        rules={[{ required: true, message: 'Please enter your name' }]}
                      >
                        <Input prefix={<UserOutlined />} placeholder="Full name" />
                      </Form.Item>
                      <Form.Item
                        name="email"
                        rules={[
                          { required: true, message: 'Please enter your email' },
                          { type: 'email', message: 'Please enter a valid email' },
                        ]}
                      >
                        <Input prefix={<MailOutlined />} placeholder="Email address" />
                      </Form.Item>
                      <Form.Item
                        name="password"
                        rules={[
                          { required: true, message: 'Please enter a password' },
                          { min: 6, message: 'Password must be at least 6 characters' },
                        ]}
                      >
                        <Input.Password prefix={<LockOutlined />} placeholder="Password" />
                      </Form.Item>
                      <Form.Item
                        name="confirmPassword"
                        dependencies={['password']}
                        rules={[
                          { required: true, message: 'Please confirm your password' },
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
                        <Input.Password prefix={<LockOutlined />} placeholder="Confirm password" />
                      </Form.Item>
                      <Form.Item style={{ marginBottom: 0 }}>
                        <Button
                          type="primary"
                          htmlType="submit"
                          loading={loading}
                          block
                          className="glass-button-primary"
                        >
                          Create Account
                        </Button>
                      </Form.Item>
                    </Form>
                  </>
                ),
              },
            ]}
          />
        </Card>

        <div className="login-footer">
          <Text type="secondary">Powered by Newbound Intelligence</Text>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
