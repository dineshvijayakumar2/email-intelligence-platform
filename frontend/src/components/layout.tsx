import React, { PropsWithChildren } from "react";
import { Layout as AntdLayout, Menu, Typography } from "antd";
import { Link, useLocation } from "react-router-dom";
import {
  DashboardOutlined,
  MailOutlined,
  InboxOutlined,
  SettingOutlined,
  ExclamationCircleOutlined,
  TeamOutlined
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

  return (
    <AntdLayout style={{ minHeight: "100vh" }}>
      {/* Glass Sidebar */}
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
      </Sider>

      {/* Main Content Area */}
      <AntdLayout style={{ marginLeft: 240 }}>
        {/* Glass Header */}
        <Header
          className="glass-header"
          style={{
            padding: "0 32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            height: 64,
          }}
        >
          <div>
            <Title level={4} className="header-title">
              {getCurrentPageTitle()}
            </Title>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              {new Date().toLocaleDateString('en-US', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
              })}
            </Text>
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
