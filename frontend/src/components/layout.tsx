import React, { PropsWithChildren, useState, useEffect } from "react";
import { Layout as AntdLayout, Menu, Typography, Drawer, Button } from "antd";
import { Link, useLocation } from "react-router-dom";
import {
  DashboardOutlined,
  MailOutlined,
  InboxOutlined,
  SettingOutlined,
  ExclamationCircleOutlined,
  TeamOutlined,
  MenuOutlined,
  CloseOutlined
} from "@ant-design/icons";

const { Header, Content } = AntdLayout;
const { Title, Text } = Typography;

// Page titles mapped to routes
const pageTitles: Record<string, string> = {
  '/': 'Dashboard',
  '/mailboxes': 'Mailboxes',
  '/emails': 'Emails',
  '/processing': 'Processing Jobs',
  '/errors': 'Error Logs',
  '/clients': 'Clients',
};

export const Layout: React.FC<PropsWithChildren> = ({ children }) => {
  const location = useLocation();
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

  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: <Link to="/">Dashboard</Link>,
    },
    {
      key: '/mailboxes',
      icon: <InboxOutlined />,
      label: <Link to="/mailboxes">Mailboxes</Link>,
    },
    {
      key: '/emails',
      icon: <MailOutlined />,
      label: <Link to="/emails">Emails</Link>,
    },
    {
      key: '/processing',
      icon: <SettingOutlined />,
      label: <Link to="/processing">Processing</Link>,
    },
    {
      key: '/errors',
      icon: <ExclamationCircleOutlined />,
      label: <Link to="/errors">Errors</Link>,
    },
    {
      key: '/clients',
      icon: <TeamOutlined />,
      label: <Link to="/clients">Clients</Link>,
    },
  ];

  // Get selected key from current path
  const getSelectedKey = () => {
    // Check for exact match first
    if (pageTitles[location.pathname]) {
      return location.pathname;
    }
    // Check for partial match (for nested routes)
    for (const path of Object.keys(pageTitles)) {
      if (path !== '/' && location.pathname.startsWith(path)) {
        return path;
      }
    }
    return '/';
  };

  return (
    <AntdLayout style={{ minHeight: "100vh" }}>
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
                <Title level={5} style={{ margin: 0 }}>Email Intelligence</Title>
                <Text type="secondary" style={{ fontSize: 12 }}>Analytics Platform</Text>
              </div>
            </div>
            <Button
              type="text"
              icon={<CloseOutlined />}
              onClick={() => setDrawerVisible(false)}
            />
          </div>
          <Menu
            mode="inline"
            selectedKeys={[getSelectedKey()]}
            items={menuItems}
            className="mobile-nav-menu"
          />
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

          {/* Right: Date/Status */}
          <div className="header-right">
            {isMobile ? (
              <Link to="/" className="mobile-brand">
                <span className="brand-icon">📧</span>
              </Link>
            ) : (
              <Text type="secondary" className="header-date">
                {new Date().toLocaleDateString('en-US', {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric'
                })}
              </Text>
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
