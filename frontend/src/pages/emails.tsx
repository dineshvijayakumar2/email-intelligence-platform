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
  Descriptions,
  Divider,
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
        width="90%"
        style={{ top: 20 }}
        styles={{ body: { maxHeight: 'calc(100vh - 120px)', overflowY: 'auto' } }}
      >
        {selectedEmail && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            {/* Email Header Info */}
            <Card size="small" title="Email Information">
              <Row gutter={[16, 16]}>
                <Col span={24}>
                  <Text type="secondary">Subject:</Text>
                  <br />
                  <Text strong style={{ fontSize: '16px' }}>{selectedEmail.subject}</Text>
                </Col>

                <Col span={12}>
                  <Text type="secondary">From:</Text>
                  <br />
                  {selectedEmail.sender_name && (
                    <Text>{selectedEmail.sender_name} </Text>
                  )}
                  <Text type="secondary">&lt;{selectedEmail.sender_email}&gt;</Text>
                </Col>

                <Col span={12}>
                  <Text type="secondary">Mailbox:</Text>
                  <br />
                  <Text>{selectedEmail.mailbox_name || 'Unknown'}</Text>
                </Col>

                {selectedEmail.recipients && selectedEmail.recipients.length > 0 && (
                  <Col span={24}>
                    <Text type="secondary">To:</Text>
                    <br />
                    {selectedEmail.recipients.map((recipient, idx) => (
                      <div key={idx} style={{ display: 'inline-block', marginRight: '12px' }}>
                        {recipient.name && <Text>{recipient.name} </Text>}
                        <Text type="secondary">&lt;{recipient.email}&gt;</Text>
                      </div>
                    ))}
                  </Col>
                )}

                {selectedEmail.cc_list && selectedEmail.cc_list.length > 0 && (
                  <Col span={24}>
                    <Text type="secondary">CC:</Text>
                    <br />
                    {selectedEmail.cc_list.map((cc, idx) => (
                      <div key={idx} style={{ display: 'inline-block', marginRight: '12px' }}>
                        {cc.name && <Text>{cc.name} </Text>}
                        <Text type="secondary">&lt;{cc.email}&gt;</Text>
                      </div>
                    ))}
                  </Col>
                )}

                {selectedEmail.bcc_list && selectedEmail.bcc_list.length > 0 && (
                  <Col span={24}>
                    <Text type="secondary">BCC:</Text>
                    <br />
                    {selectedEmail.bcc_list.map((bcc, idx) => (
                      <div key={idx} style={{ display: 'inline-block', marginRight: '12px' }}>
                        {bcc.name && <Text>{bcc.name} </Text>}
                        <Text type="secondary">&lt;{bcc.email}&gt;</Text>
                      </div>
                    ))}
                  </Col>
                )}

                <Col span={6}>
                  <Text type="secondary">Direction:</Text>
                  <br />
                  <Tag color={selectedEmail.is_outbound ? 'green' : 'blue'}>
                    {selectedEmail.is_outbound ? 'Outbound' : 'Inbound'}
                  </Tag>
                </Col>

                <Col span={6}>
                  <Text type="secondary">Reply:</Text>
                  <br />
                  <Text>{selectedEmail.is_reply ? 'Yes' : 'No'}</Text>
                </Col>

                <Col span={6}>
                  <Text type="secondary">Size:</Text>
                  <br />
                  <Text>{(selectedEmail.message_size / 1024).toFixed(1)} KB</Text>
                </Col>

                <Col span={6}>
                  <Text type="secondary">Folder:</Text>
                  <br />
                  <Tag color="blue">{selectedEmail.folder_path}</Tag>
                </Col>

                <Col span={12}>
                  <Text type="secondary">Sent Date:</Text>
                  <br />
                  <Space>
                    <CalendarOutlined />
                    <Text>{new Date(selectedEmail.sent_date).toLocaleString()}</Text>
                  </Space>
                </Col>

                {selectedEmail.received_date && (
                  <Col span={12}>
                    <Text type="secondary">Received Date:</Text>
                    <br />
                    <Space>
                      <CalendarOutlined />
                      <Text>{new Date(selectedEmail.received_date).toLocaleString()}</Text>
                    </Space>
                  </Col>
                )}

                <Col span={24}>
                  <Text type="secondary">Tags:</Text>
                  <br />
                  <Space wrap size={[4, 4]}>
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
                </Col>
              </Row>
            </Card>

            <Divider>Email Content</Divider>
            <Card
              size="small"
              title={
                <Space>
                  <MailOutlined />
                  <span>Message Body</span>
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
              style={{ marginBottom: 0 }}
            >
              {selectedEmail.body_html && emailBodyView === 'html' ? (
                <div
                  style={{
                    border: '1px solid #d9d9d9',
                    borderRadius: '4px',
                    backgroundColor: '#ffffff',
                    height: '500px',
                    overflow: 'auto',
                    position: 'relative'
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
                            padding: 20px;
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
                      display: 'block'
                    }}
                    sandbox="allow-same-origin allow-scripts allow-popups"
                    title="Email Content"
                  />
                </div>
              ) : selectedEmail.body_text ? (
                <div
                  style={{
                    border: '1px solid #d9d9d9',
                    borderRadius: '4px',
                    backgroundColor: '#ffffff',
                    minHeight: '400px',
                    maxHeight: '70vh',
                    overflow: 'auto',
                    padding: '20px',
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
                <div style={{ padding: '40px', textAlign: 'center' }}>
                  <Text type="secondary">No email content available</Text>
                </div>
              )}
            </Card>
          </Space>
        )}
      </Modal>
    </Space>
  );
};