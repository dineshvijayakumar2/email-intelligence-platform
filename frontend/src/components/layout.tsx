import React, { PropsWithChildren, useState, useEffect } from 'react';
import {
  Layout as AntdLayout,
  Menu,
  Typography,
  Drawer,
  Button,
  Avatar,
  Dropdown,
  Space,
  Tag,
} from 'antd';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  DashboardOutlined,
  SettingOutlined,
  MenuOutlined,
  CloseOutlined,
  LogoutOutlined,
  DownOutlined,
  BarChartOutlined,
  BulbOutlined,
  MailOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';

const { Header, Content } = AntdLayout;
const { Title, Text } = Typography;

// Page titles mapped to routes
const pageTitles: Record<string, string> = {
  '/': 'Dashboard',
  '/mailboxes': 'Mailboxes',
  '/intelligence/inbox': 'Smart Inbox',
  '/intelligence/digest': 'Daily Digest',
  '/intelligence/opportunities': 'Opportunities',
  '/intelligence/usage': 'AI Usage',
  '/intelligence/strategic-digest': 'Strategic Digest',
  '/emails': 'All Emails',
  '/processing': 'Processing Jobs',
  '/errors': 'Error Logs',
  '/analytics': 'Analytics',
  '/analytics/contacts': 'Contact Analytics',
  '/analytics/companies': 'Company Analytics',
  '/analytics/threads': 'Thread Analytics',
  '/analytics/response-times': 'Response Times',
  '/analytics/email-rules': 'Email Rules',
  '/analytics/data-health': 'Data Health',
  '/analytics/patterns': 'Communication Patterns',
  '/extraction': 'Extraction Management',
  '/clients': 'Clients',
  '/users': 'User Management',
  '/admin/data': 'Admin Data View',
  '/admin/audit-logs': 'Audit Logs',
  '/settings': 'Settings',
};

// Role labels and colors
const roleConfig: Record<string, { label: string; color: string }> = {
  admin: { label: 'Admin', color: 'gold' },
  client_manager: { label: 'Client Manager', color: 'blue' },
  account_manager: { label: 'Account Manager', color: 'green' },
};

export const Layout: React.FC<PropsWithChildren> = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { profile, signOut, isAdmin } = useAuth();
  const [isMobile, setIsMobile] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false);

  // Check if device is mobile
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);

    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Close drawer when route changes
  useEffect(() => {
    setDrawerVisible(false);
  }, [location.pathname]);

  const handleSignOut = async () => {
    await signOut();
    navigate('/login', { replace: true });
  };

  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: <Link to="/">Dashboard</Link>,
    },
    {
      key: '/emails',
      icon: <MailOutlined />,
      label: <Link to="/emails">Emails</Link>,
    },
    {
      key: '/intelligence',
      icon: <BulbOutlined />,
      label: 'Intelligence',
      children: [
        { key: '/intelligence/inbox', label: <Link to="/intelligence/inbox">Smart Inbox</Link> },
        { key: '/intelligence/digest', label: <Link to="/intelligence/digest">Daily Digest</Link> },
        { key: '/intelligence/opportunities', label: <Link to="/intelligence/opportunities">Opportunities</Link> },
        { key: '/intelligence/strategic-digest', label: <Link to="/intelligence/strategic-digest">Strategic Digest</Link> },
      ],
    },
    {
      key: '/analytics',
      icon: <BarChartOutlined />,
      label: 'Analytics',
      children: [
        { key: '/analytics/overview', label: <Link to="/analytics">Overview</Link> },
        { key: '/analytics/contacts', label: <Link to="/analytics/contacts">Contacts</Link> },
        { key: '/analytics/companies', label: <Link to="/analytics/companies">Companies</Link> },
        { key: '/analytics/threads', label: <Link to="/analytics/threads">Threads</Link> },
        { key: '/analytics/response-times', label: <Link to="/analytics/response-times">Response Times</Link> },
        { key: '/analytics/patterns', label: <Link to="/analytics/patterns">Patterns</Link> },
        { key: '/analytics/data-health', label: <Link to="/analytics/data-health">Data Health</Link> },
      ],
    },
    {
      key: '/manage',
      icon: <SettingOutlined />,
      label: 'Manage',
      children: [
        { key: '/mailboxes', label: <Link to="/mailboxes">Mailboxes</Link> },
        { key: '/clients', label: <Link to="/clients">Clients</Link> },
        { key: '/analytics/email-rules', label: <Link to="/analytics/email-rules">Email Rules</Link> },
        { key: '/extraction', label: <Link to="/extraction">Extraction</Link> },
        { type: 'divider' as const },
        { key: '/processing', label: <Link to="/processing">Processing Jobs</Link> },
        { key: '/errors', label: <Link to="/errors">Error Logs</Link> },
        { type: 'divider' as const },
        { key: '/settings', label: <Link to="/settings">Settings</Link> },
        ...(isAdmin ? [
          { key: '/intelligence/usage', label: <Link to="/intelligence/usage">AI Usage</Link> },
          { key: '/intelligence/quickbase', label: <Link to="/intelligence/quickbase">QB Config</Link> },
          { key: '/intelligence/quickbase-data', label: <Link to="/intelligence/quickbase-data">QB Data</Link> },
          { key: '/users', label: <Link to="/users">Users</Link> },
          { key: '/admin/data', label: <Link to="/admin/data">Data View</Link> },
          { key: '/admin/audit-logs', label: <Link to="/admin/audit-logs">Audit Logs</Link> },
        ] : []),
      ],
    },
  ];

  // Get selected key from current path
  const getSelectedKey = () => {
    // Check for exact match first
    if (pageTitles[location.pathname]) {
      return location.pathname;
    }
    // Check for partial match (for nested routes) — longest match wins
    let bestMatch = '/';
    let bestLen = 0;
    for (const path of Object.keys(pageTitles)) {
      if (path !== '/' && location.pathname.startsWith(path) && path.length > bestLen) {
        bestMatch = path;
        bestLen = path.length;
      }
    }
    return bestMatch;
  };

  // User dropdown menu items
  const userMenuItems = [
    {
      key: 'profile',
      label: (
        <div style={{ padding: '4px 0' }}>
          <div style={{ fontWeight: 500 }}>{profile?.name || 'User'}</div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {profile?.email}
          </Text>
          {profile?.roles && profile.roles.length > 0 && (
            <div style={{ marginTop: 4 }}>
              {profile.roles.map(role => (
                <Tag key={role} color={roleConfig[role]?.color || 'default'} style={{ marginBottom: 4 }}>
                  {roleConfig[role]?.label || role}
                </Tag>
              ))}
            </div>
          )}
        </div>
      ),
      disabled: true,
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: 'Sign Out',
      onClick: handleSignOut,
    },
  ];

  // Get user initials for avatar
  const getUserInitials = () => {
    if (profile?.name) {
      const names = profile.name.split(' ');
      if (names.length >= 2) {
        return `${names[0][0]}${names[1][0]}`.toUpperCase();
      }
      return profile.name.substring(0, 2).toUpperCase();
    }
    return 'U';
  };

  return (
    <AntdLayout style={{ minHeight: '100vh' }}>
      {/* Mobile Drawer for navigation */}
      <Drawer
        placement="left"
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
        closable={false}
        width={280}
        styles={{
          body: { padding: 0 },
        }}
        className="mobile-nav-drawer"
      >
        <div className="mobile-nav-content">
          <div className="mobile-nav-header">
            <div className="mobile-nav-logo">
              <span className="logo-icon">📧</span>
              <div className="logo-text">
                <Title level={5} style={{ margin: 0 }}>
                  Email Intelligence
                </Title>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Analytics Platform
                </Text>
              </div>
            </div>
            <Button type="text" icon={<CloseOutlined />} onClick={() => setDrawerVisible(false)} />
          </div>

          {/* User info in mobile drawer */}
          {profile && (
            <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(102, 126, 234, 0.1)' }}>
              <Space>
                <Avatar
                  size={40}
                  src={profile.avatarUrl}
                  style={{ backgroundColor: '#667eea' }}
                >
                  {!profile.avatarUrl && getUserInitials()}
                </Avatar>
                <div>
                  <div style={{ fontWeight: 500 }}>{profile.name}</div>
                  <div style={{ marginTop: 4 }}>
                    {profile.roles?.map(role => (
                      <Tag
                        key={role}
                        color={roleConfig[role]?.color || 'default'}
                        style={{ marginRight: 4, marginBottom: 4 }}
                      >
                        {roleConfig[role]?.label || role}
                      </Tag>
                    ))}
                  </div>
                </div>
              </Space>
            </div>
          )}

          <Menu
            mode="inline"
            selectedKeys={[getSelectedKey()]}
            items={menuItems}
            className="mobile-nav-menu"
          />

          {/* Logout button at bottom of mobile drawer */}
          <div style={{ padding: '16px 20px', borderTop: '1px solid rgba(102, 126, 234, 0.1)' }}>
            <Button
              block
              icon={<LogoutOutlined />}
              onClick={handleSignOut}
              style={{ borderColor: '#ff4d4f', color: '#ff4d4f' }}
            >
              Sign Out
            </Button>
          </div>
        </div>
      </Drawer>

      {/* Top Navigation Header */}
      <Header className="app-header">
        <div className="header-container">
          {/* Left: Logo & Brand */}
          <div className="header-left">
            {isMobile ? (
              <Button
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setDrawerVisible(true)}
                className="mobile-menu-btn"
              />
            ) : (
              <Link to="/" className="header-brand">
                <span className="brand-icon">📧</span>
                <span className="brand-text">Email Intelligence</span>
              </Link>
            )}
          </div>

          {/* Center: Navigation (Desktop only) */}
          {!isMobile && (
            <nav className="header-nav">
              <Menu
                mode="horizontal"
                selectedKeys={[getSelectedKey()]}
                items={menuItems}
                className="header-menu"
              />
            </nav>
          )}

          {/* Right: User Menu */}
          <div className="header-right">
            {isMobile ? (
              <Link to="/" className="mobile-brand">
                <span className="brand-icon">📧</span>
              </Link>
            ) : (
              <Dropdown menu={{ items: userMenuItems }} trigger={['click']} placement="bottomRight">
                <Button type="text" style={{ height: 'auto', padding: '4px 8px' }}>
                  <Space size={8}>
                    <Avatar
                      size={32}
                      src={profile?.avatarUrl}
                      style={{ backgroundColor: '#667eea' }}
                    >
                      {!profile?.avatarUrl && getUserInitials()}
                    </Avatar>
                    {!isMobile && (
                      <>
                        <span style={{ fontWeight: 500, color: '#374151' }}>
                          {profile?.name || 'User'}
                        </span>
                        <DownOutlined style={{ fontSize: 10, color: '#9ca3af' }} />
                      </>
                    )}
                  </Space>
                </Button>
              </Dropdown>
            )}
          </div>
        </div>
      </Header>

      {/* Main Content */}
      <Content className="glass-content" style={{ marginTop: 64 }}>
        {children}
      </Content>
    </AntdLayout>
  );
};
