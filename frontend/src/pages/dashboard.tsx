import React, { useState, useEffect } from "react";
import { Row, Col, Card, Statistic, Typography, Space, Progress, Table } from "antd";
import { MailOutlined, InboxOutlined, SendOutlined, SettingOutlined } from "@ant-design/icons";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import { dashboardService, DashboardStats, VolumeData, CategoryData, RecentEmail } from '../services/dashboardService';

const { Title, Text } = Typography;

export const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats>({
    totalEmails: 0,
    totalMailboxes: 0,
    todayEmails: 0,
    processingJobs: 0,
  });
  const [volumeData, setVolumeData] = useState<VolumeData[]>([]);
  const [categoryData, setCategoryData] = useState<CategoryData[]>([]);
  const [recentEmails, setRecentEmails] = useState<RecentEmail[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      const [statsData, volumeDataResult, categoryDataResult, recentEmailsResult] = await Promise.all([
        dashboardService.getDashboardStats(),
        dashboardService.getVolumeData(),
        dashboardService.getCategoryData(),
        dashboardService.getRecentEmails(),
      ]);

      setStats(statsData);
      setVolumeData(volumeDataResult);
      setCategoryData(categoryDataResult);
      setRecentEmails(recentEmailsResult);
    } catch (error) {
      console.error('Error loading dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    {
      title: 'Subject',
      dataIndex: 'subject',
      key: 'subject',
      ellipsis: true,
    },
    {
      title: 'Sender',
      dataIndex: 'sender',
      key: 'sender',
    },
    {
      title: 'Category',
      dataIndex: 'category',
      key: 'category',
      render: (category: string) => (
        <span style={{ 
          padding: '4px 8px', 
          borderRadius: '4px', 
          backgroundColor: category === 'Promotional' ? '#fff1f0' : '#f6ffed',
          color: category === 'Promotional' ? '#cf1322' : '#389e0d'
        }}>
          {category}
        </span>
      ),
    },
    {
      title: 'Received',
      dataIndex: 'received',
      key: 'received',
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      {/* Header */}
      <div>
        <Title level={2} style={{ margin: 0 }}>
          📊 Dashboard
        </Title>
        <Text type="secondary">
          Overview of your email intelligence platform
        </Text>
      </div>

      {/* Statistics Cards */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title="Total Emails"
              value={stats.totalEmails}
              prefix={<MailOutlined />}
              valueStyle={{ color: "#1890ff" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title="Mailboxes"
              value={stats.totalMailboxes}
              prefix={<InboxOutlined />}
              valueStyle={{ color: "#52c41a" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title="Today's Emails"
              value={stats.todayEmails}
              prefix={<SendOutlined />}
              valueStyle={{ color: "#fa8c16" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card loading={loading}>
            <Statistic
              title="Processing Jobs"
              value={stats.processingJobs}
              prefix={<SettingOutlined />}
              valueStyle={{ color: "#722ed1" }}
            />
            <Progress percent={65} size="small" showInfo={false} style={{ marginTop: 8 }} />
          </Card>
        </Col>
      </Row>

      {/* Charts Row */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title="📈 Email Volume (Last 7 Days)" style={{ height: 400 }} loading={loading}>
            {!loading && volumeData.length > 0 && (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={volumeData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickFormatter={(value) => new Date(value).toLocaleDateString()} />
                  <YAxis />
                  <Tooltip labelFormatter={(value) => new Date(value).toLocaleDateString()} />
                  <Bar dataKey="inbound" fill="#1890ff" name="Inbound" />
                  <Bar dataKey="outbound" fill="#52c41a" name="Outbound" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="🎯 Email Categories" style={{ height: 400 }} loading={loading}>
            {!loading && categoryData.length > 0 && (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={categoryData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name} ${(percent ? percent * 100 : 0).toFixed(0)}%`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
      </Row>

      {/* Recent Activity */}
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card title="📧 Recent Emails" extra={<a href="/emails">View All</a>} loading={loading}>
            {!loading && (
              <Table
                dataSource={recentEmails}
                columns={columns}
                pagination={false}
                size="small"
                rowKey="id"
              />
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  );
};