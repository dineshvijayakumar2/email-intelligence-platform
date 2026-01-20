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
const { Title } = Typography;

export const Layout: React.FC<PropsWithChildren> = ({ children }) => {
  const location = useLocation();

  return (
    <AntdLayout style={{ minHeight: "100vh" }}>
      <Sider width={200} style={{ backgroundColor: "#001529" }}>
        <div style={{ padding: "16px", textAlign: "center" }}>
          <Title level={4} style={{ color: "white", margin: 0 }}>
            📧 Email Intelligence
          </Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          style={{ height: "100%", borderRight: 0 }}
        >
          <Menu.Item key="/" icon={<DashboardOutlined />}>
            <Link to="/">Dashboard</Link>
          </Menu.Item>
          <Menu.Item key="/mailboxes" icon={<InboxOutlined />}>
            <Link to="/mailboxes">Mailboxes</Link>
          </Menu.Item>
          <Menu.Item key="/emails" icon={<MailOutlined />}>
            <Link to="/emails">Emails</Link>
          </Menu.Item>
          <Menu.Item key="/processing" icon={<SettingOutlined />}>
            <Link to="/processing">Processing</Link>
          </Menu.Item>
          <Menu.Item key="/errors" icon={<ExclamationCircleOutlined />}>
            <Link to="/errors">Errors</Link>
          </Menu.Item>
          <Menu.Item key="/clients" icon={<TeamOutlined />}>
            <Link to="/clients">Clients</Link>
          </Menu.Item>
        </Menu>
      </Sider>
      <AntdLayout>
        <Header style={{ 
          backgroundColor: "#fff", 
          padding: "0 24px",
          display: "flex",
          alignItems: "center",
          boxShadow: "0 2px 8px rgba(0,0,0,0.1)"
        }}>
          <Title level={3} style={{ margin: 0 }}>
            Email Intelligence Platform
          </Title>
        </Header>
        <Content style={{ padding: "24px", backgroundColor: "#f0f2f5" }}>
          {children}
        </Content>
      </AntdLayout>
    </AntdLayout>
  );
};