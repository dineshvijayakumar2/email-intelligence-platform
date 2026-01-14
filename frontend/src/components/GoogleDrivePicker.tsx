import React, { useState, useEffect } from 'react';
import { Button, Modal, List, Space, Tag, message, Spin, Input, Empty, Breadcrumb, Typography } from 'antd';
import { GoogleOutlined, FileOutlined, FolderOutlined, SearchOutlined, HomeOutlined } from '@ant-design/icons';
import googleDriveService from '../services/googleDriveService';
// @ts-ignore
import config from '../config.js';

const { Text } = Typography;

interface GoogleDriveFile {
  id: string;
  name: string;
  mimeType: string;
  size?: string;
  modifiedTime?: string;
  parents?: string[];
  folderPath?: string; // Added to store resolved folder path
}

interface GoogleDrivePickerProps {
  onFileSelect: (file: GoogleDriveFile) => void;
  acceptedFormats?: string[];
}

const GoogleDrivePicker: React.FC<GoogleDrivePickerProps> = ({ 
  onFileSelect, 
  acceptedFormats = ['.mbox', '.pst', '.olm'] 
}) => {
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState<GoogleDriveFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<GoogleDriveFile | null>(null);
  const [currentFolder, setCurrentFolder] = useState<string>('all');
  const [folderPath, setFolderPath] = useState<Array<{id: string, name: string}>>([
    { id: 'all', name: 'All Files' }
  ]);

  useEffect(() => {
    // Check authentication status on mount
    setIsAuthenticated(googleDriveService.isAuthenticated());
  }, []);

  const handleAuthenticate = async () => {
    setLoading(true);
    try {
      await googleDriveService.authenticate();
      setIsAuthenticated(true);
      await loadFiles('all'); // Load all files
      message.success('Successfully connected to Google Drive');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      message.error(`Authentication failed: ${errorMessage}`);
      console.error('Authentication error:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadFiles = async (folderId: string = 'all', query?: string) => {
    setLoading(true);
    try {
      let searchQuery: string;

      if (folderId === 'all') {
        // Show ALL archive files from everywhere (owned, shared, any folder)
        const formatQueries = [
          "name contains '.mbox'",
          "name contains '.MBOX'",
          "name contains '.pst'",
          "name contains '.PST'",
          "name contains '.olm'",
          "name contains '.OLM'",
          "name contains 'mbox'",
          "mimeType = 'application/mbox'"
        ];

        searchQuery = `(${formatQueries.join(' or ')}) and trashed = false`;

        if (query) {
          searchQuery += ` and name contains '${query}'`;
        }
      } else if (folderId === 'root') {
        // For root, show items in My Drive root and shared with me
        searchQuery = `('root' in parents or sharedWithMe) and trashed = false`;
        if (query) {
          searchQuery += ` and name contains '${query}'`;
        }
      } else {
        // For specific folders, use standard parent query
        searchQuery = `'${folderId}' in parents and trashed = false`;
        if (query) {
          searchQuery += ` and name contains '${query}'`;
        }
      }

      // Get items based on the query
      const allItems = await googleDriveService.listFiles(searchQuery);

      if (folderId === 'all') {
        // In "all files" view, resolve folder paths for each file
        const filesWithPaths = await Promise.all(
          allItems.map(async (file) => {
            try {
              const folderPath = await googleDriveService.getFolderPath(file.parents);
              return { ...file, folderPath };
            } catch (error) {
              console.warn(`Failed to get folder path for ${file.name}:`, error);
              return { ...file, folderPath: 'Unknown Location' };
            }
          })
        );

        setFiles(filesWithPaths);

        if (allItems.length === 0) {
          message.info('No email archive files (.mbox, .pst, .olm) found in your Google Drive');
        }
      } else {
        // In folder view, separate folders and files
        const folders = allItems.filter(item =>
          item.mimeType === 'application/vnd.google-apps.folder'
        );

        const files = allItems.filter(item => {
          if (item.mimeType === 'application/vnd.google-apps.folder') return false;

          const fileName = item.name.toLowerCase();
          return acceptedFormats.some(format =>
            fileName.includes(format.toLowerCase()) ||
            fileName.endsWith(format.toLowerCase()) ||
            item.mimeType === 'application/mbox'
          );
        });

        // Combine: folders first, then files
        const combined = [...folders, ...files];
        setFiles(combined);
      }
    } catch (error) {
      message.error('Failed to load files from Google Drive');
      console.error('Error loading files:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (value: string) => {
    if (isAuthenticated) {
      loadFiles(currentFolder, value);
    }
  };

  const handleNavigateToFolder = (folder: GoogleDriveFile) => {
    // Add to path
    setFolderPath(prev => [...prev, { id: folder.id, name: folder.name }]);
    setCurrentFolder(folder.id);
    loadFiles(folder.id);
  };

  const handleNavigateToBreadcrumb = (folderId: string, index: number) => {
    // Remove items after this index from path
    setFolderPath(prev => prev.slice(0, index + 1));
    setCurrentFolder(folderId);
    loadFiles(folderId);
  };

  const handleSelectFile = (file: GoogleDriveFile) => {
    if (file.mimeType === 'application/vnd.google-apps.folder') {
      handleNavigateToFolder(file);
    } else {
      setSelectedFile(file);
    }
  };

  const handleConfirmSelection = () => {
    if (selectedFile) {
      onFileSelect(selectedFile);
      setIsModalVisible(false);
      message.success(`Selected: ${selectedFile.name}`);
    }
  };

  const formatFileSize = (bytes?: string) => {
    if (!bytes) return 'Unknown size';
    const size = parseInt(bytes);
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unknown date';
    return new Date(dateString).toLocaleDateString();
  };

  const getFileIcon = (mimeType: string) => {
    if (mimeType === 'application/vnd.google-apps.folder') {
      return <FolderOutlined />;
    }
    return <FileOutlined />;
  };

  const getFileTypeTag = (name: string) => {
    if (name.endsWith('.mbox')) return <Tag color="blue">MBOX</Tag>;
    if (name.endsWith('.pst')) return <Tag color="green">PST</Tag>;
    if (name.endsWith('.olm')) return <Tag color="purple">OLM</Tag>;
    return <Tag>File</Tag>;
  };

  return (
    <>
      <Button 
        icon={<GoogleOutlined />} 
        onClick={() => setIsModalVisible(true)}
        type="primary"
      >
        Select from Google Drive
      </Button>

      <Modal
        title="Select Email Archive from Google Drive"
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        onOk={handleConfirmSelection}
        width={800}
        okText="Select File"
        okButtonProps={{ 
          disabled: !selectedFile || selectedFile?.mimeType === 'application/vnd.google-apps.folder' 
        }}
      >
        {!isAuthenticated ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <GoogleOutlined style={{ fontSize: 48, color: '#4285f4', marginBottom: 20 }} />
            <h3>Connect to Google Drive</h3>
            <p>Sign in to access your email archive files from Google Drive</p>
            <Button 
              type="primary" 
              icon={<GoogleOutlined />} 
              onClick={handleAuthenticate}
              loading={loading}
              size="large"
            >
              Connect Google Drive
            </Button>
          </div>
        ) : (
          <Spin spinning={loading}>
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              {/* Breadcrumb Navigation */}
              <Breadcrumb 
                items={folderPath.map((folder, index) => ({
                  key: folder.id,
                  title: (
                    <a onClick={() => handleNavigateToBreadcrumb(folder.id, index)}>
                      {index === 0 ? <><HomeOutlined /> {folder.name}</> : folder.name}
                    </a>
                  )
                }))}
              />

              <Input.Search
                placeholder="Search in current folder..."
                prefix={<SearchOutlined />}
                onSearch={handleSearch}
                enterButton="Search"
              />

              {files.length === 0 ? (
                <Empty 
                  description="No email archive files found"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <List
                  dataSource={files}
                  style={{ maxHeight: 400, overflowY: 'auto' }}
                  renderItem={(file) => (
                    <List.Item
                      key={file.id}
                      onClick={() => handleSelectFile(file)}
                      style={{
                        cursor: 'pointer',
                        backgroundColor: selectedFile?.id === file.id ? '#f0f2f5' : 'transparent',
                        padding: '12px',
                        borderRadius: '4px',
                        borderLeft: file.mimeType === 'application/vnd.google-apps.folder' ? '3px solid #1890ff' : 'none',
                      }}
                    >
                      <List.Item.Meta
                        avatar={getFileIcon(file.mimeType)}
                        title={
                          <Space>
                            {file.name}
                            {file.mimeType !== 'application/vnd.google-apps.folder' && getFileTypeTag(file.name)}
                            {file.mimeType === 'application/vnd.google-apps.folder' && (
                              <Tag color="blue" icon={<FolderOutlined />}>Folder</Tag>
                            )}
                          </Space>
                        }
                        description={
                          file.mimeType === 'application/vnd.google-apps.folder' ? (
                            <Text type="secondary">Click to open folder</Text>
                          ) : (
                            <Space direction="vertical" size={2}>
                              <Space size="large">
                                <span>{formatFileSize(file.size)}</span>
                                <span>Modified: {formatDate(file.modifiedTime)}</span>
                              </Space>
                              {file.folderPath && (
                                <Text type="secondary" style={{ fontSize: '12px' }}>
                                  📁 {file.folderPath}
                                </Text>
                              )}
                            </Space>
                          )
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Space>
          </Spin>
        )}
      </Modal>
    </>
  );
};

export default GoogleDrivePicker;