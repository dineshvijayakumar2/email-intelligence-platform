import React, { useState, useEffect } from 'react';
import { Search, FolderOpen, File, Home, ChevronRight } from 'lucide-react';
import { StatusBadge } from '@/components/ui/status-badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Spinner } from '@/lib/icons';
import { toast } from '@/lib/toast';
import googleDriveService from '../services/googleDriveService';
import { formatDate as formatDateUtil } from '../utils/dateUtils';
// @ts-ignore
import config from '../config.js';

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
  const [searchValue, setSearchValue] = useState('');

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
      toast.success('Successfully connected to Google Drive');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      toast.error(`Authentication failed: ${errorMessage}`);
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
          toast.info('No email archive files (.mbox, .pst, .olm) found in your Google Drive');
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
      toast.error('Failed to load files from Google Drive');
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
      toast.success(`Selected: ${selectedFile.name}`);
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
    return formatDateUtil(dateString);
  };

  const getFileIcon = (mimeType: string) => {
    if (mimeType === 'application/vnd.google-apps.folder') {
      return <FolderOpen className="h-4 w-4 text-blue-500" />;
    }
    return <File className="h-4 w-4 text-slate-400" />;
  };

  const getFileTypeBadge = (name: string) => {
    const lower = name.toLowerCase();
    if (lower.endsWith('.mbox')) return <StatusBadge variant="info">MBOX</StatusBadge>;
    if (lower.endsWith('.pst')) return <StatusBadge variant="success">PST</StatusBadge>;
    if (lower.endsWith('.olm')) return <StatusBadge variant="purple">OLM</StatusBadge>;
    return <StatusBadge variant="neutral">File</StatusBadge>;
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setIsModalVisible(true)}
        className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
        </svg>
        Select from Google Drive
      </button>

      <Dialog open={isModalVisible} onOpenChange={setIsModalVisible}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Select Email Archive from Google Drive</DialogTitle>
          </DialogHeader>

          {!isAuthenticated ? (
            <div className="flex flex-col items-center py-10 gap-5">
              <svg className="h-12 w-12 text-[#4285f4]" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
              </svg>
              <h3 className="text-lg font-semibold text-slate-900">Connect to Google Drive</h3>
              <p className="text-sm text-slate-500">Sign in to access your email archive files from Google Drive</p>
              <button
                type="button"
                onClick={handleAuthenticate}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-md bg-[#4285f4] px-5 py-2.5 text-sm font-medium text-white hover:bg-[#3367d6] transition-colors disabled:opacity-50"
              >
                {loading && <Spinner className="h-4 w-4 animate-spin" />}
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>
                </svg>
                Connect Google Drive
              </button>
            </div>
          ) : (
            <div className="relative">
              {loading && (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70 rounded-lg">
                  <Spinner className="h-6 w-6 animate-spin text-primary" />
                </div>
              )}
              <div className="flex flex-col gap-3">
                {/* Breadcrumb Navigation */}
                <nav className="flex items-center gap-1 text-sm">
                  {folderPath.map((folder, index) => (
                    <React.Fragment key={folder.id}>
                      {index > 0 && <ChevronRight className="h-3.5 w-3.5 text-slate-400" />}
                      <button
                        type="button"
                        onClick={() => handleNavigateToBreadcrumb(folder.id, index)}
                        className="inline-flex items-center gap-1 text-slate-600 hover:text-primary transition-colors"
                      >
                        {index === 0 && <Home className="h-3.5 w-3.5" />}
                        {folder.name}
                      </button>
                    </React.Fragment>
                  ))}
                </nav>

                {/* Search */}
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <input
                      type="text"
                      placeholder="Search in current folder..."
                      value={searchValue}
                      onChange={(e) => setSearchValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSearch(searchValue);
                      }}
                      className="w-full rounded-md border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => handleSearch(searchValue)}
                    className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                  >
                    Search
                  </button>
                </div>

                {/* File List */}
                {files.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                    <File className="h-10 w-10 mb-3" />
                    <p className="text-sm">No email archive files found</p>
                  </div>
                ) : (
                  <div className="max-h-[400px] overflow-y-auto border border-slate-200 rounded-lg divide-y divide-slate-100">
                    {files.map((file) => (
                      <div
                        key={file.id}
                        onClick={() => handleSelectFile(file)}
                        className={`flex items-start gap-3 px-3 py-3 cursor-pointer transition-colors ${
                          selectedFile?.id === file.id
                            ? 'bg-blue-50'
                            : 'hover:bg-slate-50'
                        } ${
                          file.mimeType === 'application/vnd.google-apps.folder'
                            ? 'border-l-[3px] border-l-blue-500'
                            : ''
                        }`}
                      >
                        <div className="mt-0.5">
                          {getFileIcon(file.mimeType)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-slate-900 truncate">{file.name}</span>
                            {file.mimeType !== 'application/vnd.google-apps.folder' && getFileTypeBadge(file.name)}
                            {file.mimeType === 'application/vnd.google-apps.folder' && (
                              <StatusBadge variant="info">
                                <FolderOpen className="h-3 w-3 mr-1" />
                                Folder
                              </StatusBadge>
                            )}
                          </div>
                          {file.mimeType === 'application/vnd.google-apps.folder' ? (
                            <p className="text-xs text-slate-400 mt-0.5">Click to open folder</p>
                          ) : (
                            <div className="mt-0.5">
                              <div className="flex items-center gap-4 text-xs text-slate-500">
                                <span>{formatFileSize(file.size)}</span>
                                <span>Modified: {formatDate(file.modifiedTime)}</span>
                              </div>
                              {file.folderPath && (
                                <p className="text-xs text-slate-400 mt-0.5">
                                  {file.folderPath}
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          <DialogFooter>
            <button
              type="button"
              onClick={() => setIsModalVisible(false)}
              className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleConfirmSelection}
              disabled={!selectedFile || selectedFile?.mimeType === 'application/vnd.google-apps.folder'}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Select File
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default GoogleDrivePicker;
