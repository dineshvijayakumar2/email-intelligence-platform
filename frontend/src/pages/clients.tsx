/**
 * Clients Page - Stage 2 Business Hierarchy
 *
 * List and manage consulting clients with their customer companies.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Table,
  Tag,
  Button,
  Space,
  Typography,
  Input,
  Row,
  Col,
  Statistic,
  Modal,
  Form,
  Select,
  message,
  Tooltip,
  Breadcrumb,
  Popconfirm,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  TeamOutlined,
  HomeOutlined,
  ReloadOutlined,
  BankOutlined,
  GlobalOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import {
  clientService,
  ClientSummary,
  ClientCreate,
  ClientUpdate,
  ClientStatus,
  InternalDomain,
} from '../services/clientService';

const { Text } = Typography;
const { Option } = Select;

const ClientsPage: React.FC = () => {
  // State
  const [loading, setLoading] = useState(false);
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingClient, setEditingClient] = useState<ClientSummary | null>(null);
  const [form] = Form.useForm();

  // Internal domains
  const [internalDomains, setInternalDomains] = useState<InternalDomain[]>([]);
  const [newDomain, setNewDomain] = useState('');
  const [domainsLoading, setDomainsLoading] = useState(false);

  // Filters
  const [statusFilter, setStatusFilter] = useState<ClientStatus | undefined>();

  // Load clients
  const loadClients = useCallback(async () => {
    setLoading(true);
    try {
      const response = await clientService.list(undefined, statusFilter);
      setClients(response.clients);
      setTotal(response.total);
    } catch (error) {
      console.error('Failed to load clients:', error);
      message.error('Failed to load clients');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  // Initial load
  useEffect(() => {
    loadClients();
  }, [loadClients]);

  // Handle create/edit
  const handleSubmit = async (values: any) => {
    try {
      if (editingClient) {
        await clientService.update(editingClient.id, values as ClientUpdate);
        message.success('Client updated successfully');
      } else {
        await clientService.create(values as ClientCreate);
        message.success('Client created successfully');
      }
      setModalVisible(false);
      form.resetFields();
      setEditingClient(null);
      loadClients();
    } catch (error: any) {
      message.error(error.message || 'Failed to save client');
    }
  };

  // Handle delete
  const handleDelete = async (id: string) => {
    try {
      await clientService.delete(id);
      message.success('Client deleted successfully');
      loadClients();
    } catch (error: any) {
      message.error(error.message || 'Failed to delete client');
    }
  };

  // Load internal domains for a client
  const loadInternalDomains = async (clientId: string) => {
    setDomainsLoading(true);
    try {
      const resp = await clientService.listInternalDomains(clientId);
      setInternalDomains(resp.domains);
    } catch { setInternalDomains([]); }
    finally { setDomainsLoading(false); }
  };

  const handleAddDomain = async () => {
    if (!editingClient || !newDomain.trim()) return;
    try {
      await clientService.addInternalDomain(editingClient.id, newDomain.trim());
      setNewDomain('');
      loadInternalDomains(editingClient.id);
      message.success(`Domain "${newDomain.trim()}" added`);
    } catch (err: any) {
      message.error(err.message || 'Failed to add domain');
    }
  };

  const handleRemoveDomain = async (domainId: string) => {
    if (!editingClient) return;
    try {
      await clientService.removeInternalDomain(editingClient.id, domainId);
      loadInternalDomains(editingClient.id);
    } catch { message.error('Failed to remove domain'); }
  };

  // Open edit modal
  const openEditModal = (client: ClientSummary) => {
    setEditingClient(client);
    form.setFieldsValue({
      client_name: client.client_name,
      client_label: client.client_label,
      status: client.status,
    });
    setModalVisible(true);
    loadInternalDomains(client.id);
  };

  // Table columns
  const columns = [
    {
      title: 'Client Name',
      dataIndex: 'client_name',
      key: 'client_name',
      render: (name: string, record: ClientSummary) => (
        <Space>
          <BankOutlined />
          <Text strong>{name}</Text>
          {record.client_label && (
            <Tag color="blue">{record.client_label}</Tag>
          )}
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: ClientStatus) => (
        <Tag color={clientService.getStatusColor(status)}>
          {clientService.getStatusLabel(status)}
        </Tag>
      ),
    },
    {
      title: 'Account Managers',
      key: 'account_managers',
      width: 220,
      render: (_: any, record: ClientSummary) => {
        if (!record.account_managers || record.account_managers.length === 0) {
          return (
            <Tooltip title="Assign mailboxes to account managers from the Mailboxes page">
              <Text type="secondary" style={{ fontSize: 12 }}>None assigned</Text>
            </Tooltip>
          );
        }
        return (
          <Space size={[0, 4]} wrap>
            {record.account_managers.map((am) => (
              <Tooltip key={am.id} title={am.email}>
                <Tag icon={<TeamOutlined />} color="blue">
                  {am.name}
                </Tag>
              </Tooltip>
            ))}
          </Space>
        );
      },
    },
    {
      title: 'Companies',
      dataIndex: 'customer_company_count',
      key: 'customer_company_count',
      width: 100,
      align: 'center' as const,
      render: (count: number) => (
        <Tooltip title="Customer Companies">
          <Tag color="geekblue">{count}</Tag>
        </Tooltip>
      ),
    },
    {
      title: 'Contacts',
      dataIndex: 'contact_count',
      key: 'contact_count',
      width: 100,
      align: 'center' as const,
      render: (count: number) => (
        <Tooltip title="Customer Contacts">
          <Tag color="cyan">{count}</Tag>
        </Tooltip>
      ),
    },
    {
      title: 'Mailboxes',
      dataIndex: 'mailbox_count',
      key: 'mailbox_count',
      width: 100,
      align: 'center' as const,
      render: (count: number) => (
        <Tooltip title="Connected Mailboxes">
          <Tag>{count}</Tag>
        </Tooltip>
      ),
    },
    {
      title: 'Emails',
      dataIndex: 'total_emails',
      key: 'total_emails',
      width: 100,
      align: 'right' as const,
      render: (count: number) => count.toLocaleString(),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 100,
      render: (_: any, record: ClientSummary) => (
        <Space size="small">
          <Tooltip title="Edit">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openEditModal(record)}
            />
          </Tooltip>
          <Popconfirm
            title="Delete this client?"
            description="This will also delete all customer companies, contacts, and rules."
            onConfirm={() => handleDelete(record.id)}
            okText="Delete"
            okButtonProps={{ danger: true }}
          >
            <Tooltip title="Delete">
              <Button
                type="text"
                size="small"
                icon={<DeleteOutlined />}
                danger
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // Calculate stats
  const activeClients = clients.filter(c => c.status === 'active').length;
  const totalCompanies = clients.reduce((sum, c) => sum + c.customer_company_count, 0);
  const totalContacts = clients.reduce((sum, c) => sum + c.contact_count, 0);

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      {/* Breadcrumb */}
      <Breadcrumb className="fade-in-up" style={{ marginBottom: 16 }}>
        <Breadcrumb.Item>
          <Link to="/"><HomeOutlined /> Home</Link>
        </Breadcrumb.Item>
        <Breadcrumb.Item>
          <TeamOutlined /> Clients
        </Breadcrumb.Item>
      </Breadcrumb>

      {/* Header */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }} className="fade-in-up">
        <Col>
          <Text type="secondary">
            Manage consulting clients and customer companies
          </Text>
        </Col>
        <Col>
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={loadClients}
              loading={loading}
            >
              Refresh
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingClient(null);
                form.resetFields();
                setModalVisible(true);
              }}
              className="glass-button-primary"
            >
              Add Client
            </Button>
          </Space>
        </Col>
      </Row>

      {/* Stats */}
      <Row gutter={16} style={{ marginBottom: 24 }} className="fade-in-up stagger-1">
        <Col span={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic title="Total Clients" value={total} valueStyle={{ color: '#667eea' }} />
          </div>
        </Col>
        <Col span={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic
              title="Active Clients"
              value={activeClients}
              valueStyle={{ color: '#3f8600' }}
            />
          </div>
        </Col>
        <Col span={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic title="Customer Companies" value={totalCompanies} valueStyle={{ color: '#764ba2' }} />
          </div>
        </Col>
        <Col span={6}>
          <div className="glass-card" style={{ padding: 24 }}>
            <Statistic title="Customer Contacts" value={totalContacts} valueStyle={{ color: '#fa8c16' }} />
          </div>
        </Col>
      </Row>

      {/* Filters */}
      <div className="glass-filters fade-in-up stagger-2" style={{ marginBottom: 24 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Text strong>Filter by Status:</Text>
            <Select
              style={{ width: '100%', marginTop: 8 }}
              placeholder="All Statuses"
              allowClear
              value={statusFilter}
              onChange={setStatusFilter}
            >
              <Option value="active">Active</Option>
              <Option value="inactive">Inactive</Option>
              <Option value="prospect">Prospect</Option>
            </Select>
          </Col>
        </Row>
      </div>

      {/* Clients Table */}
      <div className="glass-table-container fade-in-up stagger-3">
        <Table
          dataSource={clients}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            total,
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} clients`,
          }}
        />
      </div>

      {/* Create/Edit Modal */}
      <Modal
        title={editingClient ? 'Edit Client' : 'Add Client'}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          form.resetFields();
          setEditingClient(null);
        }}
        footer={null}
        width={600}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{ status: 'active' }}
        >
          <Form.Item
            name="client_name"
            label="Client Name"
            rules={[{ required: true, message: 'Please enter client name' }]}
          >
            <Input placeholder="e.g., ABC Corporation" />
          </Form.Item>

          <Form.Item
            name="client_label"
            label="Short Label"
            extra="A short identifier for quick reference (e.g., ABC)"
          >
            <Input placeholder="e.g., ABC" maxLength={20} />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="status"
                label="Status"
                rules={[{ required: true }]}
              >
                <Select>
                  <Option value="active">Active</Option>
                  <Option value="inactive">Inactive</Option>
                  <Option value="prospect">Prospect</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Account Managers">
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Managed at mailbox level. Assign mailboxes to account managers from the Mailboxes page.
                </Text>
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="industry"
            label="Industry"
          >
            <Input placeholder="e.g., Manufacturing, Technology" />
          </Form.Item>

          <Form.Item
            name="notes"
            label="Notes"
          >
            <Input.TextArea rows={3} placeholder="Additional notes..." />
          </Form.Item>

          {/* Internal Domains — only show when editing */}
          {editingClient && (
            <div style={{ marginBottom: 24 }}>
              <Text strong><GlobalOutlined /> Internal Domains</Text>
              <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 8 }}>
                Email domains owned by this client (excluded from customer extraction)
              </Text>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
                {internalDomains.map(d => (
                  <Tag key={d.id} closable onClose={() => handleRemoveDomain(d.id)} color="orange">
                    {d.domain}
                  </Tag>
                ))}
                {!domainsLoading && internalDomains.length === 0 && (
                  <Text type="secondary" style={{ fontSize: 12 }}>No internal domains configured</Text>
                )}
              </div>
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  placeholder="e.g., carbon8.com.au"
                  value={newDomain}
                  onChange={e => setNewDomain(e.target.value)}
                  onPressEnter={handleAddDomain}
                  style={{ flex: 1 }}
                />
                <Button type="primary" onClick={handleAddDomain} disabled={!newDomain.trim()}>
                  Add
                </Button>
              </Space.Compact>
            </div>
          )}

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setModalVisible(false)}>
                Cancel
              </Button>
              <Button type="primary" htmlType="submit">
                {editingClient ? 'Update' : 'Create'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ClientsPage;
