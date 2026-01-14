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
  Modal,
  message,
  Row,
  Col,
} from "antd";
import {
  SearchOutlined,
  FilterOutlined,
  EyeOutlined,
  MailOutlined,
  CalendarOutlined,
  CloseOutlined,
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
  const [modalVisible, setModalVisible] = useState(false);
  const [emailBodyView, setEmailBodyView] = useState<'html' | 'text'>('html');
  const [categories, setCategories] = useState<string[]>([]);
  const [mailboxes, setMailboxes] = useState<string[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [filters, setFilters] = useState<EmailFilters>({
    search: '',
    category: '',
    mailbox: '',
    folder: '',
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
      const [categoriesData, mailboxesData, foldersData] = await Promise.all([
        emailService.getEmailCategories(),
        emailService.getMailboxNames(),
        emailService.getFolderNames(),
      ]);
      setCategories(categoriesData);
      setMailboxes(mailboxesData);
      setFolders(foldersData);
    } catch (error) {
      console.error('Error loading filter options:', error);
    }
  };

  const showEmailDetails = async (email: Email) => {
    try {
      // Load full email details including body
      const fullEmail = await emailService.getEmail(email.id);
      setSelectedEmail(fullEmail);
      setModalVisible(true);
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
      folder: '',
      dateRange: null,
      isOutbound: '',
    });
    setCurrentPage(1);
  };

  // Filter out folder-based tags (folders should be in folder_path column)
  const filterContentTags = (tags: string[]) => {
    if (!tags) return [];
    const folderTags = ['inbox', 'sent', 'spam', 'trash', 'archive', 'drafts', 'other'];
    return tags.filter(tag => !folderTags.includes(tag.toLowerCase()));
  };

  const columns = [
    {
      title: 'Subject',
      dataIndex: 'subject',
      key: 'subject',
      width: '30%',
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
      width: '18%',
      render: (tags: string[]) => {
        const contentTags = filterContentTags(tags);
        return (
          <Space wrap size={[4, 4]}>
            {contentTags && contentTags.length > 0 ? (
              contentTags.slice(0, 3).map(tag => (
                <Tag key={tag} color={getCategoryColor(tag)} style={{ margin: 0 }}>
                  {getCategoryLabel(tag)}
                </Tag>
              ))
            ) : (
              <Tag color="default">No tags</Tag>
            )}
            {contentTags && contentTags.length > 3 && (
              <Tooltip title={contentTags.slice(3).map(t => getCategoryLabel(t)).join(', ')}>
                <Tag color="default" style={{ margin: 0 }}>+{contentTags.length - 3}</Tag>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: 'Folder',
      dataIndex: 'folder_path',
      key: 'folder_path',
      width: '12%',
      render: (folder: string) => {
        // Determine folder icon/color based on common folder names
        const folderLower = (folder || '').toLowerCase();
        let color = 'default';
        if (folderLower.includes('inbox')) color = 'blue';
        else if (folderLower.includes('sent')) color = 'green';
        else if (folderLower.includes('spam') || folderLower.includes('junk')) color = 'red';
        else if (folderLower.includes('trash') || folderLower.includes('deleted')) color = 'volcano';
        else if (folderLower.includes('archive')) color = 'geekblue';
        else if (folderLower.includes('draft')) color = 'orange';

        return (
          <Tag color={color} style={{ maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {folder || 'INBOX'}
          </Tag>
        );
      },
    },
    {
      title: 'Mailbox',
      dataIndex: 'mailbox_name',
      key: 'mailbox_name',
      width: '12%',
      ellipsis: true,
      render: (name: string) => (
        <Tooltip title={name}>
          <Space>
            <MailOutlined />
            <Text ellipsis>{name}</Text>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: 'Date',
      dataIndex: 'sent_date',
      key: 'sent_date',
      width: '13%',
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
      width: '8%',
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
          {filters.folder && ` in folder "${filters.folder}"`}
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
            <Text type="secondary" style={{ fontSize: '12px' }}>Folder:</Text>
            <Select
              placeholder="All"
              allowClear
              style={{ width: 150 }}
              value={filters.folder}
              onChange={(value) => handleFilterChange('folder', value)}
            >
              {folders.map(folder => (
                <Option key={folder} value={folder}>
                  {folder}
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

      {/* Email Details Modal */}
      <Modal
        title={
          <Space>
            <MailOutlined />
            <Text strong>Email Details</Text>
          </Space>
        }
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width="95%"
        style={{ top: 20, maxWidth: '1800px' }}
        styles={{ body: { maxHeight: 'calc(100vh - 120px)', overflowY: 'auto', padding: '24px' } }}
      >
        {selectedEmail && (
          <Row gutter={24} style={{ width: '100%' }}>
            {/* Left Column - Email Metadata */}
            <Col span={8}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                {/* Subject Card */}
                <Card size="small" title={<Text strong>Subject</Text>} style={{ marginBottom: 0 }}>
                  <Text style={{ fontSize: '15px' }}>{selectedEmail.subject}</Text>
                </Card>

                {/* From/To Card */}
                <Card size="small" title={<Text strong>Participants</Text>} style={{ marginBottom: 0 }}>
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    <div>
                      <Text type="secondary" strong>From:</Text><br />
                      {selectedEmail.sender_name && <Text>{selectedEmail.sender_name}<br /></Text>}
                      <Text type="secondary" style={{ fontSize: '13px' }}>{selectedEmail.sender_email}</Text>
                    </div>

                    {selectedEmail.recipients && selectedEmail.recipients.length > 0 && (
                      <div>
                        <Text type="secondary" strong>To:</Text><br />
                        {selectedEmail.recipients.map((recipient, idx) => (
                          <div key={idx} style={{ marginBottom: '4px' }}>
                            {recipient.name && <Text>{recipient.name}<br /></Text>}
                            <Text type="secondary" style={{ fontSize: '13px' }}>{recipient.email}</Text>
                          </div>
                        ))}
                      </div>
                    )}

                    {selectedEmail.cc_list && selectedEmail.cc_list.length > 0 && (
                      <div>
                        <Text type="secondary" strong>CC:</Text><br />
                        {selectedEmail.cc_list.map((cc, idx) => (
                          <div key={idx} style={{ marginBottom: '4px' }}>
                            {cc.name && <Text>{cc.name}<br /></Text>}
                            <Text type="secondary" style={{ fontSize: '13px' }}>{cc.email}</Text>
                          </div>
                        ))}
                      </div>
                    )}

                    {selectedEmail.bcc_list && selectedEmail.bcc_list.length > 0 && (
                      <div>
                        <Text type="secondary" strong>BCC:</Text><br />
                        {selectedEmail.bcc_list.map((bcc, idx) => (
                          <div key={idx} style={{ marginBottom: '4px' }}>
                            {bcc.name && <Text>{bcc.name}<br /></Text>}
                            <Text type="secondary" style={{ fontSize: '13px' }}>{bcc.email}</Text>
                          </div>
                        ))}
                      </div>
                    )}
                  </Space>
                </Card>

                {/* Metadata Card */}
                <Card size="small" title={<Text strong>Details</Text>} style={{ marginBottom: 0 }}>
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    <div>
                      <Text type="secondary">Mailbox:</Text><br />
                      <Text>{selectedEmail.mailbox_name || 'Unknown'}</Text>
                    </div>
                    <div>
                      <Text type="secondary">Folder:</Text><br />
                      <Tag color="blue">{selectedEmail.folder_path}</Tag>
                    </div>
                    <div>
                      <Text type="secondary">Direction:</Text><br />
                      <Tag color={selectedEmail.is_outbound ? 'green' : 'blue'}>
                        {selectedEmail.is_outbound ? 'Outbound' : 'Inbound'}
                      </Tag>
                    </div>
                    <div>
                      <Text type="secondary">Reply:</Text><br />
                      <Text>{selectedEmail.is_reply ? 'Yes' : 'No'}</Text>
                    </div>
                    <div>
                      <Text type="secondary">Size:</Text><br />
                      <Text>{(selectedEmail.message_size / 1024).toFixed(1)} KB</Text>
                    </div>
                    <div>
                      <Text type="secondary">Sent Date:</Text><br />
                      <Space size="small">
                        <CalendarOutlined />
                        <Text style={{ fontSize: '13px' }}>{new Date(selectedEmail.sent_date).toLocaleString()}</Text>
                      </Space>
                    </div>
                    {selectedEmail.received_date && (
                      <div>
                        <Text type="secondary">Received Date:</Text><br />
                        <Space size="small">
                          <CalendarOutlined />
                          <Text style={{ fontSize: '13px' }}>{new Date(selectedEmail.received_date).toLocaleString()}</Text>
                        </Space>
                      </div>
                    )}
                  </Space>
                </Card>

                {/* Tags Card */}
                <Card size="small" title={<Text strong>Tags</Text>} style={{ marginBottom: 0 }}>
                  <Space wrap size={[4, 8]}>
                    {selectedEmail.tags && filterContentTags(selectedEmail.tags).length > 0 ? (
                      filterContentTags(selectedEmail.tags).map(tag => (
                        <Tag key={tag} color={getCategoryColor(tag)}>
                          {getCategoryLabel(tag)}
                        </Tag>
                      ))
                    ) : (
                      <Tag color="default">No content tags</Tag>
                    )}
                  </Space>
                </Card>
              </Space>
            </Col>

            {/* Right Column - Email Body */}
            <Col span={16}>
              <Card
                size="small"
                title={
                  <Space>
                    <MailOutlined />
                    <span>Email Content</span>
                  </Space>
                }
                extra={
                  (selectedEmail.body_html && selectedEmail.body_text) && (
                    <Space>
                      <Button
                        size="small"
                        type={emailBodyView === 'html' ? 'primary' : 'default'}
                        onClick={() => setEmailBodyView('html')}
                      >
                        HTML View
                      </Button>
                      <Button
                        size="small"
                        type={emailBodyView === 'text' ? 'primary' : 'default'}
                        onClick={() => setEmailBodyView('text')}
                      >
                        Plain Text
                      </Button>
                    </Space>
                  )
                }
                styles={{ body: { padding: 0 } }}
                style={{ height: 'calc(100vh - 200px)' }}
              >
                {selectedEmail.body_html && emailBodyView === 'html' ? (
                  <div
                    style={{
                      height: '100%',
                      overflow: 'auto',
                      backgroundColor: '#ffffff'
                    }}
                  >
                    <iframe
                      srcDoc={`
                        <!DOCTYPE html>
                        <html>
                        <head>
                          <meta charset="UTF-8">
                          <base target="_blank">
                          <style>
                            html, body {
                              margin: 0;
                              padding: 0;
                              min-width: fit-content;
                            }
                            body {
                              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                              font-size: 14px;
                              line-height: 1.6;
                              color: #333;
                              padding: 24px;
                            }
                            img {
                              max-width: 100%;
                              height: auto;
                            }
                            a {
                              color: #1890ff;
                              text-decoration: none;
                            }
                            a:hover {
                              text-decoration: underline;
                            }
                            table {
                              border-collapse: collapse;
                            }
                            blockquote {
                              border-left: 3px solid #d9d9d9;
                              padding-left: 16px;
                              margin-left: 0;
                              color: #666;
                            }
                            pre {
                              background: #f5f5f5;
                              padding: 12px;
                              border-radius: 4px;
                              overflow-x: auto;
                            }
                          </style>
                        </head>
                        <body>${selectedEmail.body_html}</body>
                        </html>
                      `}
                      style={{
                        width: '100%',
                        height: '100%',
                        border: 'none',
                        display: 'block',
                        minHeight: 'calc(100vh - 240px)'
                      }}
                      sandbox="allow-same-origin allow-scripts allow-popups"
                      title="Email Content"
                    />
                  </div>
                ) : selectedEmail.body_text ? (
                  <div
                    style={{
                      backgroundColor: '#ffffff',
                      height: '100%',
                      overflow: 'auto',
                      padding: '24px',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                      fontSize: '14px',
                      lineHeight: '1.6',
                      color: '#333',
                      whiteSpace: 'pre-wrap',
                      wordWrap: 'break-word',
                      overflowWrap: 'break-word'
                    }}
                  >
                    {selectedEmail.body_text}
                  </div>
                ) : (
                  <div style={{ padding: '60px', textAlign: 'center', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Text type="secondary">No email content available</Text>
                  </div>
                )}
              </Card>
            </Col>
          </Row>
        )}
      </Modal>
    </Space>
  );
};