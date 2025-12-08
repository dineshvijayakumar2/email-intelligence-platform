# Email Intelligence Backend API

Simple FastAPI backend for the Email Intelligence POC platform.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Active Supabase project with the email intelligence schema

### Setup & Run

1. **Navigate to backend directory:**
   ```bash
   cd backend
   ```

2. **Run the setup script:**
   ```bash
   ./run.sh
   ```

That's it! The API will be running at `http://localhost:8000`

## 📖 API Documentation

Once running, visit:
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

## 🔧 Manual Setup (Alternative)

If you prefer manual setup:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase credentials

# Run server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 🔐 Environment Variables

Update `.env` file with your Supabase credentials:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_ANON_KEY=your_anon_key
```

## 📡 API Endpoints

### Processing
- `POST /api/mailboxes/{id}/process` - Start email processing
- `GET /api/processing-jobs` - List all processing jobs  
- `POST /api/processing-jobs/{id}/control` - Control job (pause/resume/stop)
- `DELETE /api/processing-jobs/{id}` - Delete completed job

### Connection Testing
- `POST /api/mailboxes/{id}/test-connection` - Test mailbox connection

### Dashboard
- `GET /api/dashboard/stats` - Get dashboard statistics

## 🎯 Features

### ✅ Implemented
- **Connection Testing:** Validates MBOX, IMAP, POP3, Outlook configurations
- **Processing Jobs:** Simulated email processing with real-time progress
- **Job Management:** Start, pause, resume, stop, and delete jobs
- **Sample Data Generation:** Creates sample emails and categories for testing
- **Error Simulation:** Realistic failure scenarios for testing
- **Database Integration:** Full Supabase integration with fallback mock data

### 📊 Processing Simulation
The backend simulates realistic email processing:
- Batch processing with configurable sizes
- Progressive status updates
- Random failures (~5% rate) for testing error handling
- Sample email and category generation
- Real-time job progress tracking

## 🔍 Testing the POC

1. **Start both frontend and backend:**
   ```bash
   # Terminal 1 - Frontend
   cd frontend && npm start

   # Terminal 2 - Backend  
   cd backend && ./run.sh
   ```

2. **Test workflow:**
   - Create mailboxes with different configurations
   - Test connection functionality
   - Start processing jobs and monitor progress
   - View generated sample data in the emails page

## 🛠️ Troubleshooting

### Common Issues

**Port 8000 already in use:**
```bash
# Find and kill process using port 8000
lsof -ti:8000 | xargs kill -9
```

**Python/pip issues:**
```bash
# Ensure you're using the right Python version
python3 --version
which python3
```

**Supabase connection errors:**
- Verify your `.env` file has correct credentials
- Check your Supabase project is active
- Ensure the database schema is properly set up

**Virtual environment issues:**
```bash
# Remove and recreate virtual environment
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 📝 Notes

- This is a POC implementation focused on demonstrating functionality
- Processing jobs are simulated - no actual email extraction occurs
- Sample data generation is limited to 50 emails per job for performance
- Redis integration is optional and not required for basic functionality
- All job state is maintained in Supabase for persistence across restarts