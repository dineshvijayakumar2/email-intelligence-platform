# 📧 Email Intelligence POC

**Advanced Email Analysis Platform with Cloud Storage Integration**

A comprehensive proof-of-concept for email intelligence gathering, processing, and analysis with support for multiple archive formats and cloud storage providers including **Google Drive OAuth2 integration**.

---

## 🔥 **New!** Google Drive OAuth2 Integration
**Industry-standard authentication for seamless Google Drive access**

- ✅ **One-click connection** - Users connect Google Drive with OAuth2 popup
- ✅ **Secure token management** - Backend stores and refreshes tokens automatically  
- ✅ **Access entire Drive** - Browse and select any file without manual sharing
- ✅ **Real-time status** - Connection indicators and management UI
- ✅ **Production ready** - Same OAuth2 flow used by Slack, Notion, Zapier

**Quick Setup**: See [Google Drive Setup](#4-google-drive-setup-optional-but-recommended) below.

---

## 🌟 Features

### **Core Email Processing**
- ✅ **Multi-format Support**: MBOX, PST, OLM archives
- ✅ **Real-time Processing**: Live progress tracking with Redis
- ✅ **Email Categorization**: Industry-specific tagging and analysis
- ✅ **Data Enrichment**: Contact extraction and normalization
- ✅ **Scalable Architecture**: Concurrent processing with thread pools

### **Cloud Storage Integration** 🆕
- ✅ **Google Drive OAuth2**: Industry-standard authentication (like Slack, Notion)
- ✅ **Seamless File Access**: Browse and select files from entire Google Drive
- ✅ **Secure Token Management**: Backend-managed refresh tokens
- ✅ **Auto Token Refresh**: No manual intervention required
- ✅ **AWS S3 Support**: S3 bucket integration for enterprise
- ✅ **Local File Support**: Traditional file path processing

### **Modern Web Interface**
- ✅ **React TypeScript Frontend**: Modern, responsive UI
- ✅ **Real-time Dashboard**: Live processing monitoring
- ✅ **Google Drive Integration UI**: One-click connection management
- ✅ **Mailbox Management**: Create, edit, and manage email sources
- ✅ **Processing Jobs**: Start, monitor, and track email analysis

---

## 🚀 Quick Start

### **Prerequisites**
- **Python 3.8+** with pip
- **Node.js 16+** with npm
- **Redis Server** (for job processing)
- **Supabase Account** (for database)

### **1. Clone Repository**
```bash
git clone <repository-url>
cd email-intelligence-poc
```

### **2. Environment Setup**
Create environment configuration files:

**`.env.development`** (for local development):
```bash
# Database Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Google Drive OAuth2 Integration
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000

# API Configuration
API_BASE_URL=http://localhost:8000/api
```

### **3. Google Drive Setup (Optional but Recommended)**
For Google Drive integration, configure OAuth2 credentials:

1. **Go to [Google Cloud Console](https://console.cloud.google.com/)**
2. **Create or select a project**
3. **Enable Google Drive API**
4. **Create OAuth2 credentials:**
   - Application type: **Web application**
   - Authorized JavaScript origins: `http://localhost:3000`
   - Authorized redirect URIs: `http://localhost:3000`
5. **Copy Client ID and Client Secret to your `.env.development` file**

### **4. Database Setup**
```bash
# Run database migrations
cd backend
python -c "
from src.database.supabase_client import get_client
import subprocess
subprocess.run(['psql', f'{supabase_url}/sql', '-f', 'scripts/create_tables.sql'])
"
```

Or manually run SQL files in Supabase SQL Editor:
- `scripts/create_tables.sql`
- `migrations/add_user_integrations.sql`

### **5. Start Services**

#### **Option A: Automated Startup (Recommended)**
```bash
# Full startup with environment checks
./start-poc.sh

# Or specify environment
./start-poc.sh development
./start-poc.sh production
```

#### **Option B: Quick Development Commands**
```bash
# Quick commands for development
./quick-start.sh setup          # First-time setup
./quick-start.sh start          # Start both services  
./quick-start.sh status         # Check if services are running
./quick-start.sh stop           # Stop all services
./quick-start.sh logs           # View logs
```

**Manual startup:**
```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py

# Terminal 3: Start Frontend
cd frontend
npm install
npm run dev
```

### **6. Access Application**
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

---

## 📚 Usage Guide

### **Creating Mailboxes**

#### **Local File Mailbox**
1. Navigate to **Mailboxes** → **Add Mailbox**
2. Enter mailbox name and email (optional)
3. Select mailbox type: `MBOX`, `PST`, or `OLM`
4. Choose **Local File** as source
5. Provide file path: `/path/to/archive.mbox`
6. Test connection and create

#### **Google Drive Mailbox** 🆕
1. Navigate to **Mailboxes** → **Add Mailbox**
2. Enter mailbox name and email (optional)
3. Select mailbox type: `MBOX`, `PST`, or `OLM`
4. Choose **Google Drive** as source
5. **Connect Google Drive** (OAuth2 popup)
6. **Select file** from your Google Drive
7. Test connection and create

### **Processing Emails**
1. Go to **Mailboxes** and find your mailbox
2. Click **Process** button
3. Configure processing options:
   - **Job Type**: `extraction`, `categorization`, `enrichment`
   - **Batch Size**: Number of emails per batch
   - **Total Records**: Limit processing (leave empty for all)
4. Monitor progress in real-time
5. View results in **Dashboard** and **Emails**

### **Google Drive Integration**

#### **Connection Management**
- **Connect**: One-click OAuth2 authentication
- **Status**: Real-time connection indicator
- **Disconnect**: Revoke access anytime
- **Reconnect**: Seamless re-authentication

#### **File Selection**
- **Browse entire Google Drive**: No manual sharing required
- **Search functionality**: Find files quickly
- **Format filtering**: Only show compatible files
- **Real-time preview**: File details and metadata

---

## 🏗️ Architecture

### **Backend (Python/FastAPI)**
```
backend/
├── main.py                 # FastAPI application
├── src/
│   ├── database/           # Supabase & Redis clients
│   ├── extractors/         # Email format processors
│   ├── processors/         # Email analysis & categorization
│   ├── storage/            # Cloud storage adapters
│   └── utils/              # Progress tracking & utilities
└── requirements.txt        # Python dependencies
```

### **Frontend (React/TypeScript)**
```
frontend/
├── src/
│   ├── components/         # Reusable UI components
│   │   ├── GoogleDriveConnection.tsx    # OAuth2 integration
│   │   ├── GoogleDrivePicker.tsx        # File browser
│   │   ├── MailboxCreateForm.tsx        # Mailbox creation
│   │   └── MailboxEditForm.tsx          # Mailbox editing
│   ├── pages/              # Application pages
│   ├── services/           # API clients & integrations
│   └── config.js           # Configuration
└── package.json            # Node.js dependencies
```

### **Cloud Storage Architecture**
```
┌─────────────────────────────────────────────┐
│                Frontend                     │
│  ┌─────────────────┐ ┌──────────────────┐   │
│  │ Google Drive    │ │ Local File       │   │
│  │ OAuth2 UI       │ │ Browser          │   │
│  └─────────────────┘ └──────────────────┘   │
└─────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────┐
│                Backend                      │
│  ┌─────────────────┐ ┌──────────────────┐   │
│  │ OAuth2 Token    │ │ File Stream      │   │
│  │ Management      │ │ Processing       │   │
│  └─────────────────┘ └──────────────────┘   │
└─────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────┐
│            Storage Providers                │
│  ┌─────────────────┐ ┌──────────────────┐   │
│  │ Google Drive    │ │ AWS S3 / Local   │   │
│  │ Files           │ │ Files            │   │
│  └─────────────────┘ └──────────────────┘   │
└─────────────────────────────────────────────┘
```

---

## 🔧 Configuration

### **Environment Variables**
| Variable | Description | Example |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase project URL | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | Supabase public key | `eyJ...` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `GOOGLE_CLIENT_ID` | Google OAuth2 client ID | `xxx.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth2 client secret | `GOCSPX-xxx` |
| `GOOGLE_REDIRECT_URI` | OAuth2 redirect URI | `http://localhost:3000` |
| `API_BASE_URL` | Backend API base URL | `http://localhost:8000/api` |

### **Google Drive OAuth2 Scopes**
```javascript
'https://www.googleapis.com/auth/drive.readonly'
'https://www.googleapis.com/auth/userinfo.email'
```

### **Supported File Formats**
- **MBOX**: Universal email format (Gmail exports, Thunderbird, Apple Mail)
- **PST**: Windows Outlook archive files with folder structure
- **OLM**: Mac Outlook archive files with folder hierarchy

---

## 🧪 Development

### **Running Tests**
```bash
# Backend tests
cd backend
python -m pytest tests/

# Frontend tests
cd frontend
npm test
```

### **Code Quality**
```bash
# Python linting
cd backend
flake8 src/
black src/

# TypeScript linting
cd frontend
npm run lint
npm run type-check
```

### **Database Migrations**
```bash
# Add new migration
cd backend/migrations/
# Create new .sql file
psql $SUPABASE_URL -f new_migration.sql
```

### **API Documentation**
Visit http://localhost:8000/docs for interactive API documentation with all OAuth2 endpoints.

---

## 🔐 Security

### **OAuth2 Security Features**
- ✅ **Industry-standard flow**: Authorization code + PKCE
- ✅ **Secure token storage**: Backend-managed refresh tokens
- ✅ **User data isolation**: Each user only accesses their own files
- ✅ **Token encryption**: Secure database storage
- ✅ **Automatic refresh**: No manual token management
- ✅ **Easy revocation**: One-click disconnect

### **Best Practices**
- Never commit credentials to Git
- Use environment variables for all secrets
- Rotate Google OAuth2 credentials regularly
- Monitor API usage quotas
- Enable logging and auditing
- Use HTTPS in production

---

## 🚀 Production Deployment

### **Environment Setup**
1. **Create production environment file** (`.env.production`)
2. **Configure production database** (Supabase production instance)
3. **Set up production Redis** (Redis Cloud or AWS ElastiCache)
4. **Configure production Google OAuth2** credentials
5. **Update CORS settings** for production domains

### **Docker Deployment** (Optional)
```dockerfile
# Example Dockerfile structure
FROM python:3.9-slim

# Backend setup
COPY backend/ /app/backend/
WORKDIR /app/backend
RUN pip install -r requirements.txt

# Frontend build
FROM node:16 AS frontend-build
COPY frontend/ /app/frontend/
WORKDIR /app/frontend
RUN npm install && npm run build

# Combine and serve
COPY --from=frontend-build /app/frontend/dist /app/static
CMD ["python", "main.py"]
```

### **Scaling Considerations**
- **Redis Cluster**: For high-availability job processing
- **Load Balancing**: Multiple backend instances
- **Database Connection Pooling**: Optimize Supabase connections
- **File Processing Queue**: Separate workers for large files
- **CDN**: Static file delivery optimization

---

## 🛠️ API Reference

### **OAuth2 Endpoints**
```http
# Exchange authorization code for tokens
POST /api/auth/google/exchange
{
  "code": "authorization_code",
  "user_id": "user_identifier"
}

# Check user connection status
GET /api/auth/google/status/{user_id}

# Disconnect user Google Drive
DELETE /api/auth/google/disconnect/{user_id}
```

### **Mailbox Endpoints**
```http
# Create Google Drive mailbox
POST /api/mailboxes
{
  "name": "My Google Drive Archive",
  "mailbox_type": "mbox",
  "connection_config": {
    "file_source": "google_drive",
    "google_drive_file_id": "1abc...",
    "google_drive_file_name": "archive.mbox",
    "user_id": "user_123"
  }
}

# Test connection
POST /api/mailboxes/test/test-connection
```

---

## 📖 Documentation

- **[Google Drive Integration Guide](docs/GOOGLE_DRIVE_INTEGRATION.md)** - Complete OAuth2 setup
- **[Cloud Storage Integration](docs/CLOUD_STORAGE.md)** - AWS S3 and other providers
- **[Architecture Overview](docs/ARCHITECTURE.md)** - System design and components
- **[Quick Start Guide](docs/QUICKSTART.md)** - Step-by-step setup instructions

---

## 🐛 Troubleshooting

### **Common Issues**

#### **OAuth2 Redirect URI Mismatch**
```
Error: (redirect_uri_mismatch) Bad Request
```
**Solution**: Update Google Cloud Console OAuth2 settings:
- JavaScript origins: `http://localhost:3000`
- Redirect URIs: `http://localhost:3000`

#### **Backend Connection Failed**
```
Error: Backend API failed to start
```
**Solutions**:
1. Check Redis is running: `redis-server`
2. Verify environment variables in `.env.development`
3. Check logs: `tail -f backend.log`
4. Ensure port 8000 is available

#### **Google Drive Connection Issues**
```
Error: Authentication failed
```
**Solutions**:
1. Verify Google Client ID/Secret in environment
2. Check Google Drive API is enabled
3. Ensure correct redirect URI configuration
4. Clear browser cache and cookies

#### **File Processing Errors**
```
Error: Failed to download from Google Drive
```
**Solutions**:
1. Check user has access to the file
2. Verify OAuth tokens are valid
3. Ensure file hasn't been moved/deleted
4. Re-authenticate Google Drive connection

---

## 🤝 Contributing

1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/amazing-feature`
3. **Commit changes**: `git commit -m 'Add amazing feature'`
4. **Push to branch**: `git push origin feature/amazing-feature`
5. **Open Pull Request**

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🙋 Support

- **Documentation**: Check the `/docs` folder for detailed guides
- **Issues**: Report bugs and feature requests in GitHub Issues
- **API Documentation**: Visit http://localhost:8000/docs when running locally

---

**Built with ❤️ using Python, TypeScript, React, and Google Cloud APIs**