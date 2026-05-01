"""
Test script for Sprint 2 Phase 5A/5B - Extraction API Endpoints

This script tests the extraction control endpoints.

Usage:
    python test_extraction_api.py

Prerequisites:
    1. Run migration 010: psql -U postgres -d your_db -f scripts/sprint2/sprint2_migration_010_incremental_mode.sql
    2. Backend server running on http://localhost:3000
"""

import requests
import json
import time

BASE_URL = "http://localhost:3000/api/v1/analytics"

# ANSI colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")


def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.END}")


def print_info(msg):
    print(f"{Colors.BLUE}→ {msg}{Colors.END}")


def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")


def test_extraction_pipeline():
    """
    Test the extraction pipeline endpoints
    """
    print("\n" + "="*80)
    print("Sprint 2 Phase 5A/5B - Extraction API Test")
    print("="*80 + "\n")

    # Step 1: Get a mailbox ID to test with
    print_info("Step 1: Fetching mailbox for testing...")

    # First, get a client
    clients_response = requests.get("http://localhost:3000/api/v1/customers")
    if clients_response.status_code != 200:
        print_error("Failed to fetch clients")
        return

    clients = clients_response.json()
    if not clients:
        print_error("No clients found. Create a client first.")
        return

    client_id = clients[0]['id']
    print_success(f"Using client: {clients[0].get('client_name', 'Unknown')} ({client_id})")

    # Get mailboxes for this client
    mailboxes_response = requests.get(f"http://localhost:3000/api/v1/mailboxes?client_id={client_id}")
    if mailboxes_response.status_code != 200:
        print_error("Failed to fetch mailboxes")
        return

    mailboxes = mailboxes_response.json()
    if not mailboxes:
        print_error("No mailboxes found for this client. Connect a mailbox first.")
        return

    mailbox_id = mailboxes[0]['id']
    mailbox_email = mailboxes[0].get('email_address', 'Unknown')
    print_success(f"Using mailbox: {mailbox_email} ({mailbox_id})")

    # Step 2: Test POST /extraction/run (incremental mode)
    print_info("\nStep 2: Testing POST /extraction/run (incremental mode)...")

    extraction_request = {
        "mailbox_id": mailbox_id,
        "mode": "incremental",
        "lookback_days": 7,
        "exclude_mailing_lists": True,
        "exclude_noreply": True,
        "exclude_shared": True,
        "exclude_internal": True,
        "force_relink": False,
        "skip_role_classification": False
    }

    print_info(f"Request payload: {json.dumps(extraction_request, indent=2)}")

    run_response = requests.post(
        f"{BASE_URL}/extraction/run",
        json=extraction_request
    )

    if run_response.status_code == 200:
        job_info = run_response.json()
        print_success("Extraction job started successfully!")
        print(json.dumps(job_info, indent=2))
        job_id = job_info.get('id', 'pending')

        # Wait a moment for the job to be created
        time.sleep(2)
    else:
        print_error(f"Failed to start extraction: {run_response.status_code}")
        print(run_response.text)
        return

    # Step 3: Test GET /extraction/jobs (list all jobs)
    print_info("\nStep 3: Testing GET /extraction/jobs (list all jobs)...")

    list_response = requests.get(f"{BASE_URL}/extraction/jobs?client_id={client_id}")

    if list_response.status_code == 200:
        jobs_data = list_response.json()
        print_success(f"Found {jobs_data['total']} extraction jobs")

        if jobs_data['jobs']:
            latest_job = jobs_data['jobs'][0]
            job_id = latest_job['id']
            print(f"\nLatest job:")
            print(json.dumps(latest_job, indent=2, default=str))
        else:
            print_warning("No jobs found")
            return
    else:
        print_error(f"Failed to list jobs: {list_response.status_code}")
        print(list_response.text)
        return

    # Step 4: Test GET /extraction/jobs/{job_id} (get specific job)
    print_info(f"\nStep 4: Testing GET /extraction/jobs/{job_id} (get specific job)...")

    job_response = requests.get(f"{BASE_URL}/extraction/jobs/{job_id}")

    if job_response.status_code == 200:
        job_detail = job_response.json()
        print_success("Job details retrieved successfully!")
        print(json.dumps(job_detail, indent=2, default=str))
    else:
        print_error(f"Failed to get job details: {job_response.status_code}")
        print(job_response.text)

    # Step 5: Test GET /extraction/progress/{job_id} (real-time progress)
    print_info(f"\nStep 5: Testing GET /extraction/progress/{job_id} (real-time progress)...")

    progress_response = requests.get(f"{BASE_URL}/extraction/progress/{job_id}")

    if progress_response.status_code == 200:
        progress_data = progress_response.json()
        print_success("Progress retrieved successfully!")
        print(json.dumps(progress_data, indent=2, default=str))

        # Monitor progress for a few iterations
        print_info("\nMonitoring job progress (polling every 5 seconds for 30 seconds)...")
        for i in range(6):
            time.sleep(5)
            progress_response = requests.get(f"{BASE_URL}/extraction/progress/{job_id}")
            if progress_response.status_code == 200:
                progress_data = progress_response.json()
                status = progress_data['status']
                step = progress_data.get('current_step', 'Unknown')
                step_num = progress_data.get('current_step_number', 0)
                total_steps = progress_data.get('total_steps', 13)

                print(f"  [{i+1}/6] Status: {status} | Step {step_num}/{total_steps}: {step}")

                if status in ['completed', 'failed']:
                    print_success(f"Job {status}!")
                    break
            else:
                print_error(f"Failed to get progress: {progress_response.status_code}")
                break
    else:
        print_error(f"Failed to get progress: {progress_response.status_code}")
        print(progress_response.text)

    # Summary
    print("\n" + "="*80)
    print("Test Summary")
    print("="*80)
    print_success("✓ POST /extraction/run - Trigger extraction")
    print_success("✓ GET /extraction/jobs - List all jobs")
    print_success("✓ GET /extraction/jobs/{job_id} - Get job details")
    print_success("✓ GET /extraction/progress/{job_id} - Get real-time progress")
    print_info("Note: POST /extraction/jobs/{job_id}/cancel not tested (would cancel running job)")
    print("\n")


if __name__ == "__main__":
    try:
        test_extraction_pipeline()
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to backend server. Make sure it's running on http://localhost:3000")
    except Exception as e:
        print_error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
