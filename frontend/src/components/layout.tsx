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

const { Header, Sider, Content } = AntdLayout;
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

  // Get current page title based on route
  const getCurrentPageTitle = () => {
    // Handle dynamic routes like /mailboxes/edit/:id
    for (const [path, title] of Object.entries(pageTitles)) {
      if (location.pathname === path || location.pathname.startsWith(path + '/')) {
        return title;
      }
    }
    return 'Dashboard';
  };

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

  // Sidebar content component (reused in both Sider and Drawer)
  const SidebarContent = () => (
    <>
      {/* Logo Section */}
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">
          📧
        </div>
        <Title level={5} className="sidebar-title">
          Email Intelligence
        </Title>
        <Text className="sidebar-subtitle">
          Analytics Platform
        </Text>
      </div>

      {/* Navigation Menu */}
      <Menu
        mode="inline"
        selectedKeys={[getSelectedKey()]}
        className="glass-menu"
        items={menuItems}
      />
    </>
  );

  return (
    <AntdLayout style={{ minHeight: "100vh" }}>
      {/* Desktop Sidebar - Hidden on mobile */}
      {!isMobile && (
        <Sider
          width={240}
          className="glass-sidebar"
          style={{
            position: 'fixed',
            left: 0,
            top: 0,
            bottom: 0,
            zIndex: 1000,
          }}
        >
          <SidebarContent />
        </Sider>
      )}

      {/* Mobile Drawer */}
      {isMobile && (
        <Drawer
          placement="left"
          onClose={() => setDrawerVisible(false)}
          open={drawerVisible}
          closable={false}
          width={240}
          styles={{
            body: { padding: 0 },
          }}
          style={{
            zIndex: 1001,
          }}
        >
          <div className="glass-sidebar" style={{ height: '100%' }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '16px',
              borderBottom: '1px solid rgba(255, 255, 255, 0.1)'
            }}>
              <Title level={5} style={{ margin: 0, color: 'white' }}>Menu</Title>
              <Button
                type="text"
                icon={<CloseOutlined style={{ color: 'white' }} />}
                onClick={() => setDrawerVisible(false)}
              />
            </div>
            <SidebarContent />
          </div>
        </Drawer>
      )}

      {/* Main Content Area */}
      <AntdLayout style={{ marginLeft: isMobile ? 0 : 240 }}>
        {/* Glass Header */}
        <Header
          className="glass-header"
          style={{
            padding: isMobile ? "0 16px" : "0 32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            height: 64,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {/* Mobile Menu Button */}
            {isMobile && (
              <Button
                type="text"
                icon={<MenuOutlined style={{ fontSize: 20, color: '#667eea' }} />}
                onClick={() => setDrawerVisible(true)}
                style={{ marginRight: 8 }}
              />
            )}
            <Title level={4} className="header-title" style={{ margin: 0 }}>
              {getCurrentPageTitle()}
            </Title>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {!isMobile && (
              <Text type="secondary" style={{ fontSize: 13 }}>
                {new Date().toLocaleDateString('en-US', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}
              </Text>
            )}
          </div>
        </Header>

        {/* Glass Content */}
        <Content className="glass-content" style={{ padding: 0, overflow: 'auto' }}>
          {children}
        </Content>
      </AntdLayout>
    </AntdLayout>
  );
};
