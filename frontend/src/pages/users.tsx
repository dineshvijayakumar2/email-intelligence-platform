/**
 * User Management Page
 *
 * Admin-only page for managing users, roles, and client assignments.
 */

import React, { useState, useEffect } from 'react';
import {
  Table,
  Card,
  Button,
  Space,
  Typography,
  Tag,
  Modal,
  Form,
  Select,
  message,
  Avatar,
  Tooltip,
  Popconfirm,
  Badge,
  Empty,
  Spin,
  Input,
} from 'antd';
import {
  UserOutlined,
  CrownOutlined,
  TeamOutlined,
  SolutionOutlined,
  EditOutlined,
  PlusOutlined,
  LinkOutlined,
  DisconnectOutlined,
  SearchOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import api from '../services/apiClient';
import { clientService, ClientSummary } from '../services/clientService';

const { Title, Text } = Typography;

interface User {
  id: string;
  email: string;
  name: string;
  roles: Array<'admin' | 'client_manager' | 'account_manager'>;
  is_active: boolean;
  avatar_url?: string;
  created_at: string;
  updated_at: string;
  assigned_clients?: ClientSummary[];
}

// Role configuration
const roleConfig = {
  admin: {
    label: 'Admin',
    color: 'gold',
    icon: <CrownOutlined />,
    description: 'Full access to all mailboxes and settings',
  },
  client_manager: {
    label: 'Client Manager',
    color: 'blue',
    icon: <TeamOutlined />,
    description: 'Access to assigned client mailboxes',
  },
  account_manager: {
    label: 'Account Manager',
    color: 'green',
    icon: <SolutionOutlined />,
    description: 'Access to own mailboxes only',
  },
};

const UsersPage: React.FC = () => {
  const { isAdmin } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [assignModalVisible, setAssignModalVisible] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [searchText, setSearchText] = useState('');
  const [form] = Form.useForm();
  const [assignForm] = Form.useForm();

  useEffect(() => {
    loadUsers();
    loadClients();
  }, []);

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await api.get<User[]>('/auth/users');
      console.log('API Response:', data);
      console.log('First user:', data?.[0]);
      setUsers(data || []);
    } catch (error) {
      console.error('Failed to load users:', error);
      message.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const loadClients = async () => {
    try {
      const response = await clientService.list();
      setClients(response.clients);
    } catch (error) {
      console.error('Failed to load clients:', error);
    }
  };

  const handleEditRole = (user: User) => {
    setSelectedUser(user);
    form.setFieldsValue({ roles: user.roles || [] });
    setEditModalVisible(true);
  };

  const handleManageAssignments = (user: User) => {
    setSelectedUser(user);
    assignForm.setFieldsValue({
      client_ids: user.assigned_clients?.map((c) => c.id) || [],
    });
    setAssignModalVisible(true);
  };

  const handleUpdateRole = async (values: { roles: string[] }) => {
    if (!selectedUser) return;

    try {
      await api.patch(`/auth/users/${selectedUser.id}/roles`, { roles: values.roles });
      message.success('User roles updated successfully');
      setEditModalVisible(false);
      loadUsers();
    } catch (error: any) {
      message.error(error.message || 'Failed to update user roles');
    }
  };

  const handleUpdateAssignments = async (values: { client_ids: string[] }) => {
    if (!selectedUser) return;

    try {
      // Use different endpoint based on role
      // account_manager: /client-assignments (operational)
      // client_manager: /client-assignments (will be updated to use managed-clients in backend)
      await api.put(`/auth/users/${selectedUser.id}/client-assignments`, {
        client_ids: values.client_ids,
      });

      const roleType = selectedUser.roles?.includes('client_manager') ? 'oversight' : 'operational';
      message.success(`Client ${roleType} assignments updated successfully`);
      setAssignModalVisible(false);
      loadUsers();
    } catch (error: any) {
      message.error(error.message || 'Failed to update client assignments');
    }
  };

  const handleToggleActive = async (user: User) => {
    try {
      await api.patch(`/auth/users/${user.id}/status`, { is_active: !user.is_active });
      message.success(`User ${user.is_active ? 'deactivated' : 'activated'} successfully`);
      loadUsers();
    } catch (error: any) {
      message.error(error.message || 'Failed to update user status');
    }
  };

  // Filter users by search text
  const filteredUsers = users.filter(
    (user) =>
      user.name.toLowerCase().includes(searchText.toLowerCase()) ||
      user.email.toLowerCase().includes(searchText.toLowerCase())
  );

  const columns = [
    {
      title: 'User',
      key: 'user',
      render: (_: any, record: User) => (
        <Space>
          <Avatar
            size={40}
            src={record.avatar_url}
            style={{ backgroundColor: record.is_active ? '#667eea' : '#d9d9d9' }}
          >
            {record.name?.charAt(0).toUpperCase() || 'U'}
          </Avatar>
          <div>
            <div style={{ fontWeight: 500 }}>
              {record.name}
              {!record.is_active && (
                <Tag color="default" style={{ marginLeft: 8 }}>
                  Inactive
                </Tag>
              )}
            </div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {record.email}
            </Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Roles',
      dataIndex: 'roles',
      key: 'roles',
      render: (roles: string[]) => (
        <>
          {roles?.map(role => {
            const config = roleConfig[role as keyof typeof roleConfig];
            return (
              <Tooltip key={role} title={config?.description}>
                <Tag color={config?.color} icon={config?.icon} style={{ marginBottom: 4 }}>
                  {config?.label || role}
                </Tag>
              </Tooltip>
            );
          })}
        </>
      ),
      filters: Object.entries(roleConfig).map(([value, config]) => ({
        text: config.label,
        value,
      })),
      onFilter: (value: any, record: User) => record.roles?.includes(value),
    },
    {
      title: 'Assigned Clients',
      key: 'clients',
      render: (_: any, record: User) => {
        // Show client assignments for both account_manager and client_manager roles
        const hasClientRole = record.roles?.includes('account_manager') || record.roles?.includes('client_manager');
        if (!hasClientRole) {
          return <Text type="secondary">-</Text>;
        }
        const clientCount = record.assigned_clients?.length || 0;
        const roleLabel = record.roles?.includes('client_manager') ? 'Manages' : 'Assigned to';
        if (clientCount === 0) {
          return <Text type="secondary">No clients {roleLabel.toLowerCase()}</Text>;
        }
        return (
          <Space wrap>
            {record.assigned_clients?.slice(0, 3).map((client) => (
              <Tag
                key={client.id}
                color={record.roles?.includes('client_manager') ? 'blue' : 'green'}
              >
                {client.client_name}
              </Tag>
            ))}
            {clientCount > 3 && <Tag>+{clientCount - 3} more</Tag>}
          </Space>
        );
      },
    },
    {
      title: 'Status',
      key: 'status',
      render: (_: any, record: User) => (
        <Badge
          status={record.is_active ? 'success' : 'default'}
          text={record.is_active ? 'Active' : 'Inactive'}
        />
      ),
      filters: [
        { text: 'Active', value: true },
        { text: 'Inactive', value: false },
      ],
      onFilter: (value: any, record: User) => record.is_active === value,
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, record: User) => (
        <Space size="small">
          <Tooltip title="Edit role">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => handleEditRole(record)}
              size="small"
            />
          </Tooltip>
          {(record.roles?.includes('client_manager') || record.roles?.includes('account_manager')) && (
            <Tooltip title={record.roles?.includes('client_manager') ? 'Manage client oversight' : 'Assign to clients'}>
              <Button
                type="text"
                icon={<LinkOutlined />}
                onClick={() => handleManageAssignments(record)}
                size="small"
              />
            </Tooltip>
          )}
          <Tooltip title={record.is_active ? 'Deactivate' : 'Activate'}>
            <Popconfirm
              title={`${record.is_active ? 'Deactivate' : 'Activate'} user?`}
              description={`Are you sure you want to ${record.is_active ? 'deactivate' : 'activate'} ${record.name}?`}
              onConfirm={() => handleToggleActive(record)}
              okText="Yes"
              cancelText="No"
            >
              <Button
                type="text"
                icon={record.is_active ? <StopOutlined /> : <CheckCircleOutlined />}
                danger={record.is_active}
                size="small"
              />
            </Popconfirm>
          </Tooltip>
        </Space>
      ),
    },
  ];

  if (!isAdmin) {
    return (
      <div className="glass-page-bg" style={{ padding: 24 }}>
        <Card className="glass-card-static">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="You don't have permission to view this page"
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} className="gradient-text" style={{ margin: 0 }}>
          User Management
        </Title>
        <Text type="secondary">Manage user roles and client assignments</Text>
      </div>

      <Card className="glass-card-static" style={{ marginBottom: 24 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <Space>
            <Input
              placeholder="Search users..."
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{ width: 250 }}
              allowClear
            />
          </Space>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadUsers} loading={loading}>
              Refresh
            </Button>
          </Space>
        </div>
      </Card>

      <div className="glass-table-container">
        <Table
          columns={columns}
          dataSource={filteredUsers}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} users`,
          }}
        />
      </div>

      {/* Edit Roles Modal */}
      <Modal
        title={`Edit Roles - ${selectedUser?.name}`}
        open={editModalVisible}
        onCancel={() => setEditModalVisible(false)}
        footer={null}
        className="glass-modal"
      >
        <Form form={form} onFinish={handleUpdateRole} layout="vertical">
          <Form.Item
            name="roles"
            label="User Roles"
            rules={[{ required: true, message: 'Please select at least one role' }]}
            extra="Users can have multiple roles. Example: Admin can also be Account Manager to monitor mailboxes."
          >
            <Select mode="multiple" size="large" placeholder="Select roles">
              {Object.entries(roleConfig).map(([value, config]) => (
                <Select.Option key={value} value={value}>
                  <Space>
                    {config.icon}
                    <span>{config.label}</span>
                  </Space>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setEditModalVisible(false)}>Cancel</Button>
              <Button type="primary" htmlType="submit" className="glass-button-primary">
                Update Roles
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Assign Clients Modal */}
      <Modal
        title={`Manage Client Assignments - ${selectedUser?.name}`}
        open={assignModalVisible}
        onCancel={() => setAssignModalVisible(false)}
        footer={null}
        className="glass-modal"
        width={500}
      >
        <Form form={assignForm} onFinish={handleUpdateAssignments} layout="vertical">
          <Form.Item
            name="client_ids"
            label="Assigned Clients"
            extra="This user will have access to mailboxes belonging to these clients"
          >
            <Select
              mode="multiple"
              size="large"
              placeholder="Select clients to assign"
              optionFilterProp="label"
              showSearch
            >
              {clients.map((client) => (
                <Select.Option key={client.id} value={client.id} label={client.client_name}>
                  <Space>
                    <TeamOutlined />
                    <span>{client.client_name}</span>
                    {client.client_label && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        ({client.client_label})
                      </Text>
                    )}
                  </Space>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setAssignModalVisible(false)}>Cancel</Button>
              <Button type="primary" htmlType="submit" className="glass-button-primary">
                Update Assignments
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default UsersPage;
