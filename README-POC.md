# 📧 Email Intelligence Platform POC

A comprehensive email intelligence platform built with React frontend and FastAPI backend, featuring real-time email processing, categorization, and analysis.

## 🚀 Quick Start

### One-Command Setup
```bash
./start-poc.sh
```

This script will:
- Start the backend API server on port 8000
- Start the frontend development server on port 3000
- Install all dependencies automatically
- Display logs and monitoring information

### Manual Setup

If you prefer to start services individually:

#### Backend API
```bash
cd backend
./run.sh
```

#### Frontend
```bash
cd frontend  
npm start
```

## 🎯 POC Features

### ✅ Implemented
- **Multi-type Mailbox Configuration:** MBOX, IMAP, POP3, Outlook/Office 365
- **Connection Testing:** Real-time validation for all mailbox types
- **Processing Job Management:** Start, monitor, pause, resume, stop jobs
- **Real-time Progress Tracking:** Live updates with WebSocket-like polling
- **Sample Data Generation:** Automatic creation of emails and categories
- **Error Simulation:** Realistic failure scenarios for testing
- **Dashboard Analytics:** Email statistics and volume charts
- **Full CRUD Operations:** Complete mailbox and job management

### 🎨 User Interface
- **Responsive Design:** Built with Ant Design components
- **Real-time Updates:** Auto-refreshing job progress
- **Intuitive Navigation:** Clean, professional interface
- **Error Handling:** Comprehensive user feedback
- **Progress Visualization:** Step indicators and progress bars

## 🏗️ Architecture

```
📁 Email Intelligence/
├── 📁 frontend/          # React + TypeScript
│   ├── 📁 src/
│   │   ├── 📁 components/    # Reusable UI components
│   │   ├── 📁 pages/         # Main application pages
│   │   ├── 📁 services/      # API integration layer
│   │   └── 📁 supabase/      # Database configuration
│   └── 📄 package.json
├── 📁 backend/           # FastAPI + Python
│   ├── 📄 main.py           # API server
│   ├── 📄 requirements.txt   # Python dependencies
│   └── 📄 .env             # Environment configuration
└── 📄 start-poc.sh      # One-command startup
```

### Technology Stack
- **Frontend:** React 18, TypeScript, Ant Design, Supabase Client
- **Backend:** FastAPI, Python 3.8+, Supabase, Asyncio
- **Database:** Supabase (PostgreSQL)
- **Real-time:** HTTP polling (simulated WebSocket behavior)

## 🌐 API Endpoints

### Processing
- `POST /api/mailboxes/{id}/process` - Start email processing job
- `GET /api/processing-jobs` - List all processing jobs
- `POST /api/processing-jobs/{id}/control` - Control job (pause/resume/stop)
- `DELETE /api/processing-jobs/{id}` - Delete completed job

### Connection Testing  
- `POST /api/mailboxes/{id}/test-connection` - Test mailbox configuration

### Dashboard
- `GET /api/dashboard/stats` - Get email and mailbox statistics
- `GET /health` - API health check

## 🧪 Testing the POC

### 1. **Mailbox Configuration**
1. Navigate to **Mailboxes** → **Add Mailbox**
2. Try different mailbox types:
   - **MBOX:** Enter any file path (e.g., `/path/to/emails.mbox`)
   - **IMAP:** Use `imap.gmail.com:993` with SSL
   - **POP3:** Use `pop.gmail.com:995` with SSL  
   - **Outlook:** Enter sample OAuth client/tenant IDs
3. Click **Test Connection** to validate configuration
4. Save the mailbox when connection succeeds

### 2. **Processing Jobs**
1. Click **Process** button on any active mailbox
2. Configure processing options:
   - **Job Type:** extraction, categorization, enrichment, full
   - **Batch Size:** 100-10000 emails per batch
   - **Enable features:** categorization, AI enrichment
3. Click **Start Processing** and monitor real-time progress
4. Watch the progress indicators and job status updates

### 3. **Real-time Monitoring**
- Jobs automatically update every 2 seconds
- Progress bars show completion percentage
- Step indicators display current processing phase
- Error logs appear for failed jobs
- Sample emails are generated for successful jobs

### 4. **Dashboard Analytics**
- View email volume charts
- Monitor processing job status
- Check mailbox statistics
- Analyze email categories

## 🔧 Configuration

### Environment Variables

**Frontend (`.env.local`)**
```env
REACT_APP_SUPABASE_URL=your_supabase_url
REACT_APP_SUPABASE_ANON_KEY=your_anon_key  
REACT_APP_API_BASE_URL=http://localhost:8000/api
```

**Backend (`.env`)**
```env
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_ANON_KEY=your_anon_key
```

### Database Schema
The platform uses Supabase with these main tables:
- `mailboxes` - Email source configurations
- `emails` - Processed email data
- `email_categories` - AI-generated email classifications  
- `processing_jobs` - Job queue and status tracking
- `email_enrichment` - Advanced AI analysis results

## 🚦 Stopping Services

### Using the startup script:
```bash
# Find process IDs from startup script output
kill <BACKEND_PID> <FRONTEND_PID>
```

### Manual shutdown:
```bash
# Kill by port
lsof -ti:8000 | xargs kill -9  # Backend
lsof -ti:3000 | xargs kill -9  # Frontend
```

## 📊 Monitoring & Logs

- **Frontend logs:** `frontend.log`
- **Backend logs:** `backend.log`
- **API documentation:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

## 🎯 POC Demonstration Flow

1. **Setup:** Run `./start-poc.sh` and open http://localhost:3000
2. **Create Mailbox:** Add a new mailbox with any configuration
3. **Test Connection:** Verify the connection works 
4. **Start Processing:** Launch a processing job and watch progress
5. **Monitor Dashboard:** Check statistics and email data
6. **Explore Features:** Try different job types and configurations

## 🔍 Troubleshooting

### Common Issues

**Port conflicts:**
```bash
./start-poc.sh  # Script handles port conflicts automatically
```

**Dependencies:**
```bash
# Backend dependencies
cd backend && pip install -r requirements.txt

# Frontend dependencies  
cd frontend && npm install
```

**Database connection:**
- Verify Supabase credentials in `.env` files
- Check database schema is properly set up
- Ensure Supabase project is active

**API connection:**
- Backend must be running on port 8000
- Check `REACT_APP_API_BASE_URL` in frontend `.env.local`
- Verify CORS is enabled for localhost:3000

## 🎊 POC Success Criteria

✅ **Functional mailbox configuration for all types**  
✅ **Working connection testing with realistic validation**  
✅ **Real-time processing job monitoring**  
✅ **Sample data generation for demonstration**  
✅ **Professional UI with comprehensive error handling**  
✅ **Complete API integration between frontend and backend**  
✅ **Database persistence with Supabase integration**  

---

**🎉 The POC demonstrates a fully functional email intelligence platform ready for production development!**