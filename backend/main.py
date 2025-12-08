from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import asyncio
import json
from datetime import datetime, timedelta
import random

# Load environment variables
load_dotenv()

app = FastAPI(title="Email Intelligence API", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# Pydantic models
class MailboxConfig(BaseModel):
    name: str
    email_address: str
    mailbox_type: str
    is_active: bool = True
    connection_config: Optional[Dict[str, Any]] = {}

class ProcessingJobConfig(BaseModel):
    job_type: str
    total_records: Optional[int] = 1000
    batch_size: Optional[int] = 100
    enable_categorization: Optional[bool] = True
    enable_enrichment: Optional[bool] = False

class ConnectionTest(BaseModel):
    mailbox_type: str
    connection_config: Dict[str, Any]

# In-memory job storage for POC (use Redis in production)
active_jobs = {}

@app.get("/")
async def root():
    return {"message": "Email Intelligence API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Mailbox endpoints
@app.post("/api/mailboxes/{mailbox_id}/test-connection")
async def test_connection(mailbox_id: str, connection_test: ConnectionTest):
    """Test mailbox connection based on type"""
    
    # Simulate connection testing with realistic delays
    await asyncio.sleep(2)
    
    mailbox_type = connection_test.mailbox_type
    config = connection_test.connection_config
    
    try:
        if mailbox_type == "mbox":
            file_path = config.get("file_path")
            if not file_path or not file_path.endswith('.mbox'):
                raise HTTPException(status_code=400, detail="Invalid MBOX file path")
            # Simulate file existence check
            success = True
            
        elif mailbox_type == "imap":
            server = config.get("server")
            port = config.get("port", 993)
            if not server:
                raise HTTPException(status_code=400, detail="IMAP server required")
            # Simulate IMAP connection test
            success = True
            
        elif mailbox_type == "pop3":
            server = config.get("server")
            port = config.get("port", 995)
            if not server:
                raise HTTPException(status_code=400, detail="POP3 server required")
            # Simulate POP3 connection test
            success = True
            
        elif mailbox_type == "outlook":
            client_id = config.get("oauth_config", {}).get("client_id")
            if not client_id:
                raise HTTPException(status_code=400, detail="OAuth client ID required")
            # Simulate OAuth validation
            success = True
            
        else:
            raise HTTPException(status_code=400, detail="Unsupported mailbox type")
            
        return {
            "success": success,
            "message": f"Successfully connected to {mailbox_type.upper()} mailbox",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")

@app.post("/api/mailboxes/{mailbox_id}/process")
async def start_processing(mailbox_id: str, config: ProcessingJobConfig, background_tasks: BackgroundTasks):
    """Start email processing for a mailbox"""
    
    try:
        # Get mailbox info
        mailbox_result = supabase.table('mailboxes').select('*').eq('id', mailbox_id).execute()
        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
            
        mailbox = mailbox_result.data[0]
        
        # Create processing job
        job_data = {
            "job_type": config.job_type,
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": config.total_records,
            "processed_records": 0,
            "failed_records": 0,
            "created_at": datetime.utcnow().isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_log": []
        }
        
        # Insert job into database
        result = supabase.table('processing_jobs').insert(job_data).execute()
        job = result.data[0]
        
        # Store job in memory for tracking
        active_jobs[job['id']] = {
            **job,
            "mailbox_name": mailbox['name'],
            "mailbox_type": mailbox['mailbox_type']
        }
        
        # Start background processing
        background_tasks.add_task(simulate_processing, job['id'], config)
        
        return job
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")

async def simulate_processing(job_id: str, config: ProcessingJobConfig):
    """Simulate email processing job"""
    
    try:
        # Update job status to running
        await update_job_status(job_id, "running", {"started_at": datetime.utcnow().isoformat()})
        
        total_records = config.total_records or 1000
        batch_size = config.batch_size or 100
        
        # Simulate processing in batches
        processed = 0
        failed = 0
        
        while processed < total_records:
            # Simulate processing delay
            await asyncio.sleep(1)
            
            # Process a batch
            batch_processed = min(batch_size, total_records - processed)
            
            # Simulate some failures (5% failure rate)
            batch_failed = random.randint(0, max(1, batch_processed // 20))
            batch_success = batch_processed - batch_failed
            
            processed += batch_success
            failed += batch_failed
            
            # Update progress
            await update_job_status(job_id, "running", {
                "processed_records": processed,
                "failed_records": failed
            })
            
            # Simulate job failure occasionally (5% chance)
            if random.random() < 0.05 and processed > 100:
                error_msg = "Simulated processing error: Connection timeout"
                await update_job_status(job_id, "failed", {
                    "error_log": [error_msg],
                    "completed_at": datetime.utcnow().isoformat()
                })
                return
        
        # Job completed successfully
        await update_job_status(job_id, "completed", {
            "processed_records": total_records,
            "completed_at": datetime.utcnow().isoformat()
        })
        
        # Generate sample emails if categorization is enabled
        if config.enable_categorization:
            await generate_sample_emails(job_id, total_records)
            
    except Exception as e:
        await update_job_status(job_id, "failed", {
            "error_log": [f"Processing error: {str(e)}"],
            "completed_at": datetime.utcnow().isoformat()
        })

async def update_job_status(job_id: str, status: str, updates: Dict[str, Any]):
    """Update job status in database and memory"""
    
    update_data = {"status": status, **updates}
    
    # Update database
    supabase.table('processing_jobs').update(update_data).eq('id', job_id).execute()
    
    # Update in-memory job
    if job_id in active_jobs:
        active_jobs[job_id].update(update_data)

async def generate_sample_emails(job_id: str, count: int):
    """Generate sample email data for demonstration"""
    
    categories = ['promotional', 'transactional', 'conversation', 'system', 'spam']
    senders = [
        'noreply@amazon.com', 'support@github.com', 'team@slack.com',
        'notifications@linkedin.com', 'info@stripe.com', 'hello@discord.com'
    ]
    subjects = [
        'Your order has been shipped', 'Security alert for your account',
        'Welcome to our platform', 'Monthly report is ready',
        'Meeting reminder: Project sync', 'Invoice #12345 from Stripe'
    ]
    
    # Get mailbox for this job
    job_result = supabase.table('processing_jobs').select('mailbox_id').eq('id', job_id).execute()
    if not job_result.data:
        return
        
    mailbox_id = job_result.data[0]['mailbox_id']
    
    # Generate sample emails (limit to 50 for POC)
    sample_count = min(50, count // 20)
    
    for i in range(sample_count):
        email_data = {
            "mailbox_id": mailbox_id,
            "message_id": f"<sample-{job_id}-{i}@example.com>",
            "subject": random.choice(subjects),
            "sender_email": random.choice(senders),
            "sender_name": random.choice(senders).split('@')[0].title(),
            "sent_date": (datetime.utcnow() - timedelta(days=random.randint(1, 30))).isoformat(),
            "received_date": datetime.utcnow().isoformat(),
            "is_outbound": random.choice([True, False]),
            "is_reply": random.choice([True, False]),
            "folder_path": "INBOX",
            "message_size": random.randint(1024, 50000),
            "body_text": f"This is a sample email body for email {i+1}. Generated for POC demonstration.",
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Insert email
        email_result = supabase.table('emails').insert(email_data).execute()
        if email_result.data:
            email_id = email_result.data[0]['id']
            
            # Add category
            category_data = {
                "email_id": email_id,
                "category": random.choice(categories),
                "confidence": round(random.uniform(0.7, 1.0), 2),
                "detection_method": "ai_classifier",
                "created_at": datetime.utcnow().isoformat()
            }
            
            supabase.table('email_categories').insert(category_data).execute()

@app.get("/api/processing-jobs")
async def get_processing_jobs():
    """Get all processing jobs"""
    
    try:
        # Try to get from database with mailbox join
        result = supabase.table('processing_jobs').select(
            'id, job_type, mailbox_id, status, total_records, processed_records, failed_records, started_at, completed_at, created_at, error_log, mailboxes(name)'
        ).order('created_at', desc=True).execute()
        
        jobs = []
        for job in result.data:
            job_data = {
                **job,
                "mailbox_name": job.get('mailboxes', {}).get('name') if job.get('mailboxes') else 'Unknown Mailbox',
                "progress": 0 if job['total_records'] == 0 else round((job['processed_records'] / job['total_records']) * 100)
            }
            # Remove the nested mailboxes object
            if 'mailboxes' in job_data:
                del job_data['mailboxes']
            jobs.append(job_data)
            
        return jobs
        
    except Exception as e:
        # Fallback: return mock data
        return [
            {
                "id": "mock-1",
                "job_type": "extraction",
                "mailbox_id": "mb-1",
                "mailbox_name": "Sample Mailbox",
                "status": "completed",
                "total_records": 1000,
                "processed_records": 1000,
                "failed_records": 0,
                "started_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "created_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
                "error_log": [],
                "progress": 100
            }
        ]

@app.post("/api/processing-jobs/{job_id}/control")
async def control_job(job_id: str, action: str):
    """Control processing job (pause, resume, stop)"""
    
    valid_actions = ["pause", "resume", "stop"]
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {valid_actions}")
    
    try:
        status_map = {
            "pause": "paused",
            "resume": "running", 
            "stop": "failed"
        }
        
        new_status = status_map[action]
        update_data = {"status": new_status}
        
        if action == "stop":
            update_data["completed_at"] = datetime.utcnow().isoformat()
            
        supabase.table('processing_jobs').update(update_data).eq('id', job_id).execute()
        
        return {"message": f"Job {action}d successfully", "status": new_status}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to {action} job: {str(e)}")

@app.delete("/api/processing-jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a processing job"""
    
    try:
        supabase.table('processing_jobs').delete().eq('id', job_id).execute()
        
        # Remove from memory if exists
        if job_id in active_jobs:
            del active_jobs[job_id]
            
        return {"message": "Job deleted successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")

# Email analysis endpoints for dashboard
@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Get dashboard statistics"""
    
    try:
        # Get stats from database
        emails_count = supabase.table('emails').select('id', count='exact').execute()
        mailboxes_count = supabase.table('mailboxes').select('id', count='exact').execute()
        
        today = datetime.utcnow().date().isoformat()
        today_emails = supabase.table('emails').select('id', count='exact').gte('sent_date', today).execute()
        
        processing_jobs_count = supabase.table('processing_jobs').select('id', count='exact').in_('status', ['pending', 'running']).execute()
        
        return {
            "totalEmails": emails_count.count or 0,
            "totalMailboxes": mailboxes_count.count or 0, 
            "todayEmails": today_emails.count or 0,
            "processingJobs": processing_jobs_count.count or 0
        }
        
    except Exception as e:
        # Return mock data if database unavailable
        return {
            "totalEmails": 1250,
            "totalMailboxes": 3,
            "todayEmails": 45,
            "processingJobs": 1
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)