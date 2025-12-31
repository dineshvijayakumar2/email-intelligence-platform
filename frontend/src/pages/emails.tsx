import React, { useState, useEffect } from "react";
import {
  Card,
  Table,
  Space,
  Typography,
  Tag,
  Input,
  Select,
  DatePicker,
  Button,
  Tooltip,
  Drawer,
  Descriptions,
  Divider,
  message,
} from "antd";
import {
  SearchOutlined,
  FilterOutlined,
  EyeOutlined,
  MailOutlined,
  CalendarOutlined,
} from "@ant-design/icons";
import { emailService, Email, EmailFilters } from '../services/emailService';

const { Title, Text, Paragraph } = Typography;
const { RangePicker } = DatePicker;
const { Option } = Select;
const { Search } = Input;

const getCategoryColor = (category: string) => {
  const colors = {
    promotional: '#f50',
    transactional: '#2db7f5',
    conversation: '#87d068',
    internal: '#722ed1',
    system: '#fa8c16',
  };
  return colors[category as keyof typeof colors] || '#d9d9d9';
};

const getCategoryLabel = (category: string) => {
  const labels = {
    promotional: 'Promotional',
    transactional: 'Transactional',
    conversation: 'Conversation',
    internal: 'Internal',
    system: 'System',
  };
  return labels[category as keyof typeof labels] || category;
};

export const EmailList: React.FC = () => {
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [mailboxes, setMailboxes] = useState<string[]>([]);
  const [filters, setFilters] = useState<EmailFilters>({
    search: '',
    category: '',
    mailbox: '',
    dateRange: null,
    isOutbound: '',
  });

  useEffect(() => {
    loadEmails();
    loadFilterOptions();
  }, []);

  useEffect(() => {
    loadEmails();
  }, [filters, currentPage, pageSize]);

  const loadEmails = async () => {
    try {
      setLoading(true);
      const { emails: emailData, totalCount: total } = await emailService.getEmails(
        filters,
        currentPage,
        pageSize
      );
      setEmails(emailData);
      setTotalCount(total);
    } catch (error) {
      console.error('Error loading emails:', error);
      message.error('Failed to load emails');
    } finally {
      setLoading(false);
    }
  };

  const loadFilterOptions = async () => {
    try {
      const [categoriesData, mailboxesData] = await Promise.all([
        emailService.getEmailCategories(),
        emailService.getMailboxNames(),
      ]);
      setCategories(categoriesData);
      setMailboxes(mailboxesData);
    } catch (error) {
      console.error('Error loading filter options:', error);
    }
  };

  const showEmailDetails = async (email: Email) => {
    try {
      // Load full email details including body
      const fullEmail = await emailService.getEmail(email.id);
      setSelectedEmail(fullEmail);
      setDrawerVisible(true);
    } catch (error) {
      console.error('Error loading email details:', error);
      message.error('Failed to load email details');
    }
  };

  const handleFilterChange = (key: keyof EmailFilters, value: any) => {
    setFilters(prev => ({
      ...prev,
      [key]: value
    }));
    setCurrentPage(1); // Reset to first page when filters change
  };

  const clearFilters = () => {
    setFilters({
      search: '',
      category: '',
      mailbox: '',
      dateRange: null,
      isOutbound: '',
    });
    setCurrentPage(1);
  };

  const columns = [
    {
      title: 'Subject',
      dataIndex: 'subject',
      key: 'subject',
      width: '40%',
      ellipsis: true,
      render: (text: string, record: Email) => (
        <Space direction="vertical" size="small">
          <Text strong>{text}</Text>
          <Space size="small">
            <Text type="secondary" style={{ fontSize: 12 }}>
              From: {record.sender_name || record.sender_email}
            </Text>
            {record.is_reply && (
              <Tag color="blue">Reply</Tag>
            )}
            {record.is_outbound && (
              <Tag color="green">Sent</Tag>
            )}
          </Space>
        </Space>
      ),
    },
    {
      title: 'Tags',
      dataIndex: 'tags',
      key: 'tags',
      width: '20%',
      render: (tags: string[]) => (
        <Space wrap size={[4, 4]}>
          {tags && tags.length > 0 ? (
            tags.slice(0, 4).map(tag => (
              <Tag key={tag} color={getCategoryColor(tag)} style={{ margin: 0 }}>
                {getCategoryLabel(tag)}
              </Tag>
            ))
          ) : (
            <Tag color="default">No tags</Tag>
          )}
          {tags && tags.length > 4 && (
            <Tooltip title={tags.slice(4).map(t => getCategoryLabel(t)).join(', ')}>
              <Tag color="default" style={{ margin: 0 }}>+{tags.length - 4}</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: 'Mailbox',
      dataIndex: 'mailbox_name',
      key: 'mailbox_name',
      width: '15%',
      render: (name: string) => (
        <Space>
          <MailOutlined />
          <Text>{name}</Text>
        </Space>
      ),
    },
    {
      title: 'Date',
      dataIndex: 'sent_date',
      key: 'sent_date',
      width: '15%',
      render: (date: string) => (
        <Space direction="vertical" size="small">
          <Text>{new Date(date).toLocaleDateString()}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {new Date(date).toLocaleTimeString()}
          </Text>
        </Space>
      ),
      sorter: true,
    },
    {
      title: 'Size',
      dataIndex: 'message_size',
      key: 'message_size',
      width: '10%',
      render: (size: number) => {
        const kb = (size / 1024).toFixed(1);
        return <Text type="secondary">{kb} KB</Text>;
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      width: '10%',
      render: (_: any, record: Email) => (
        <Tooltip title="View Details">
          <Button
            type="text"
            icon={<EyeOutlined />}
            onClick={() => showEmailDetails(record)}
          />
        </Tooltip>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Title level={2} style={{ margin: 0 }}>
          📧 Emails
        </Title>
        <Text type="secondary">
          Showing {totalCount} email{totalCount !== 1 ? 's' : ''}
          {filters.category && ` in ${getCategoryLabel(filters.category)}`}
          {filters.mailbox && ` from ${filters.mailbox}`}
          {filters.isOutbound && ` (${filters.isOutbound})`}
          {filters.search && ` matching "${filters.search}"`}
        </Text>
      </div>

      {/* Filters */}
      <Card title={<Space><FilterOutlined />Filters</Space>} size="small">
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Search
            placeholder="Search emails..."
            allowClear
            style={{ width: 250 }}
            value={filters.search}
            onChange={(e) => handleFilterChange('search', e.target.value)}
            prefix={<SearchOutlined />}
          />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <Text type="secondary" style={{ fontSize: '12px' }}>Category:</Text>
            <Select
              placeholder="All"
              allowClear
              style={{ width: 150 }}
              value={filters.category}
              onChange={(value) => handleFilterChange('category', value)}
            >
              {categories.map(category => (
                <Option key={category} value={category}>
                  {getCategoryLabel(category)}
                </Option>
              ))}
            </Select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <Text type="secondary" style={{ fontSize: '12px' }}>Mailbox:</Text>
            <Select
              placeholder="All"
              allowClear
              style={{ width: 150 }}
              value={filters.mailbox}
              onChange={(value) => handleFilterChange('mailbox', value)}
            >
              {mailboxes.map(mailbox => (
                <Option key={mailbox} value={mailbox}>
                  {mailbox}
                </Option>
              ))}
            </Select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <Text type="secondary" style={{ fontSize: '12px' }}>Direction:</Text>
            <Select
              placeholder="All"
              allowClear
              style={{ width: 120 }}
              value={filters.isOutbound}
              onChange={(value) => handleFilterChange('isOutbound', value)}
            >
              <Option value="inbound">Inbound</Option>
              <Option value="outbound">Outbound</Option>
            </Select>
          </div>

          <RangePicker
            placeholder={['Start Date', 'End Date']}
            style={{ width: 250 }}
            onChange={(dates, dateStrings) =>
              handleFilterChange('dateRange', dates ? dateStrings as [string, string] : null)
            }
          />

          <Button onClick={clearFilters}>Clear Filters</Button>
        </div>
      </Card>

      {/* Email Table */}
      <Card>
        <Table
          dataSource={emails}
          columns={columns}
          loading={loading}
          rowKey="id"
          size="small"
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            total: totalCount,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total, range) =>
              `${range[0]}-${range[1]} of ${total} emails`,
            onChange: (page, size) => {
              setCurrentPage(page);
              if (size !== pageSize) {
                setPageSize(size);
                setCurrentPage(1);
              }
            },
          }}
          scroll={{ x: 1200 }}
        />
      </Card>

      {/* Email Details Drawer */}
      <Drawer
        title={<Space><MailOutlined />Email Details</Space>}
        placement="right"
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
        width={600}
      >
        {selectedEmail && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Descriptions title="Email Information" bordered size="small">
              <Descriptions.Item label="Subject" span={3}>
                <Text strong>{selectedEmail.subject}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="From" span={2}>
                {selectedEmail.sender_name && (
                  <div>{selectedEmail.sender_name}</div>
                )}
                <Text type="secondary">{selectedEmail.sender_email}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Direction">
                <Tag color={selectedEmail.is_outbound ? 'green' : 'blue'}>
                  {selectedEmail.is_outbound ? 'Outbound' : 'Inbound'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Category" span={2}>
                <Tag color={getCategoryColor(selectedEmail.category || 'unassigned')}>
                  {getCategoryLabel(selectedEmail.category || 'unassigned')}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Reply">
                {selectedEmail.is_reply ? 'Yes' : 'No'}
              </Descriptions.Item>
              <Descriptions.Item label="Date" span={2}>
                <Space>
                  <CalendarOutlined />
                  {new Date(selectedEmail.sent_date).toLocaleString()}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Size">
                {(selectedEmail.message_size / 1024).toFixed(1)} KB
              </Descriptions.Item>
              <Descriptions.Item label="Folder" span={2}>
                {selectedEmail.folder_path}
              </Descriptions.Item>
              <Descriptions.Item label="Mailbox">
                {selectedEmail.mailbox_name}
              </Descriptions.Item>
            </Descriptions>

            <Divider>Email Content Preview</Divider>
            <Card size="small" title="Message Body">
              <Paragraph>
                {selectedEmail.body_text ? (
                  <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
                    {selectedEmail.body_text.substring(0, 1000)}
                    {selectedEmail.body_text.length > 1000 && '...'}
                  </pre>
                ) : (
                  <Text type="secondary">
                    Email content preview would be displayed here. In a real implementation, 
                    this would show the actual email body content retrieved from the database.
                  </Text>
                )}
              </Paragraph>
            </Card>
          </Space>
        )}
      </Drawer>
    </Space>
  );
};