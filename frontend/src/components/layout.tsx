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
  TeamOutlined,
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
  '/emails': 'All Emails',
  // Customers
  '/customers': 'Companies',
  '/customers/contacts': 'Contacts',
  '/customers/threads': 'Threads',
  // Insights
  '/insights/inbox': 'Smart Inbox',
  '/insights/digest': 'Daily Digest',
  '/insights/opportunities': 'Opportunities',
  '/insights/strategic': 'Strategic Digest',
  '/insights/search': 'Semantic Search',
  '/insights/agent': 'AI Assistant',
  // Manage
  '/manage/response-times': 'Response Times',
  '/manage/patterns': 'Communication Patterns',
  '/manage/email-rules': 'Email Rules',
  '/manage/data-health': 'Data Health',
  '/manage/extraction': 'Extraction Management',
  '/manage/processing': 'Processing Jobs',
  '/manage/errors': 'Error Logs',
  '/manage/ai-usage': 'AI Usage',
  '/manage/ai-playground': 'AI Playground',
  '/manage/quickbase': 'QB Config',
  '/manage/quickbase-data': 'QB Data',
  '/manage/quickbase-matches': 'QB Match Review',
  '/manage/logs': 'Log Monitor',
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
      key: 'customers-menu',
      icon: <TeamOutlined />,
      label: 'Customers',
      children: [
        { key: '/customers', label: <Link to="/customers">Companies</Link> },
        { key: '/customers/contacts', label: <Link to="/customers/contacts">Contacts</Link> },
        { key: '/customers/threads', label: <Link to="/customers/threads">Threads</Link> },
      ],
    },
    {
      key: '/insights',
      icon: <BulbOutlined />,
      label: 'Insights',
      children: [
        { key: '/insights/inbox', label: <Link to="/insights/inbox">Smart Inbox</Link> },
        { key: '/insights/digest', label: <Link to="/insights/digest">Daily Digest</Link> },
        { key: '/insights/opportunities', label: <Link to="/insights/opportunities">Opportunities</Link> },
        { key: '/insights/strategic', label: <Link to="/insights/strategic">Strategic Digest</Link> },
        { key: '/insights/search', label: <Link to="/insights/search">Semantic Search</Link> },
        { key: '/insights/agent', label: <Link to="/insights/agent">AI Assistant</Link> },
      ],
    },
    {
      key: '/manage',
      icon: <SettingOutlined />,
      label: 'Manage',
      children: [
        { key: '/mailboxes', label: <Link to="/mailboxes">Mailboxes</Link> },
        { key: '/clients', label: <Link to="/clients">Clients</Link> },
        { key: '/manage/email-rules', label: <Link to="/manage/email-rules">Email Rules</Link> },
        { key: '/manage/extraction', label: <Link to="/manage/extraction">Extraction</Link> },
        { type: 'divider' as const },
        { key: '/manage/processing', label: <Link to="/manage/processing">Processing Jobs</Link> },
        { key: '/manage/errors', label: <Link to="/manage/errors">Error Logs</Link> },
        { key: '/manage/response-times', label: <Link to="/manage/response-times">Response Times</Link> },
        { key: '/manage/patterns', label: <Link to="/manage/patterns">Comm Patterns</Link> },
        { key: '/manage/data-health', label: <Link to="/manage/data-health">Data Health</Link> },
        { type: 'divider' as const },
        { key: '/settings', label: <Link to="/settings">Settings</Link> },
        ...(isAdmin ? [
          { key: '/manage/ai-usage', label: <Link to="/manage/ai-usage">AI Usage</Link> },
          { key: '/manage/ai-playground', label: <Link to="/manage/ai-playground">AI Playground</Link> },
          { key: '/manage/quickbase', label: <Link to="/manage/quickbase">QB Config</Link> },
          { key: '/manage/quickbase-data', label: <Link to="/manage/quickbase-data">QB Data</Link> },
          { key: '/manage/quickbase-matches', label: <Link to="/manage/quickbase-matches">QB Match Review</Link> },
          { key: '/manage/intelligence-config', label: <Link to="/manage/intelligence-config">Intelligence Config</Link> },
          { key: '/manage/logs', label: <Link to="/manage/logs">Log Monitor</Link> },
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
