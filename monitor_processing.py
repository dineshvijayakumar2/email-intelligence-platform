#!/usr/bin/env python3
"""
Real-time monitoring script for email processing
Run this in a separate terminal while test_real_mbox.py is running
"""
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from src.database.supabase_client import SupabaseClient


def clear_screen():
    """Clear terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')


def get_latest_job():
    """Get the most recent processing job"""
    try:
        supabase = SupabaseClient.get_client(use_service_key=True)
        result = supabase.table('processing_jobs')\
            .select('*')\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()

        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        print(f"Error fetching job: {e}")
        return None


def get_mailbox_stats(mailbox_id):
    """Get email count for a mailbox"""
    try:
        supabase = SupabaseClient.get_client(use_service_key=True)
        result = supabase.table('emails')\
            .select('id', count='exact')\
            .eq('mailbox_id', mailbox_id)\
            .execute()

        return result.count or 0
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return 0


def format_duration(seconds):
    """Format seconds into human-readable duration"""
    if not seconds:
        return "N/A"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def monitor_processing(refresh_interval=2):
    """Monitor processing in real-time"""
    print("Email Processing Monitor")
    print("Press Ctrl+C to exit\n")

    try:
        while True:
            clear_screen()

            print("=" * 80)
            print(f" EMAIL PROCESSING MONITOR - {datetime.now().strftime('%H:%M:%S')}")
            print("=" * 80)
            print()

            job = get_latest_job()

            if not job:
                print("❌ No processing jobs found")
                print("\nWaiting for processing to start...")
            else:
                # Job details
                print(f"📋 Job ID: {job['id']}")
                print(f"📁 Job Type: {job.get('job_type', 'N/A')}")
                print(f"📊 Status: {job['status'].upper()}")
                print()

                # Timing
                started = job.get('started_at')
                completed = job.get('completed_at')
                created = job.get('created_at')

                if started:
                    start_time = datetime.fromisoformat(started.replace('Z', '+00:00'))
                    if completed:
                        end_time = datetime.fromisoformat(completed.replace('Z', '+00:00'))
                        duration = (end_time - start_time).total_seconds()
                        print(f"⏱️  Duration: {format_duration(duration)}")
                    else:
                        duration = (datetime.now() - start_time.replace(tzinfo=None)).total_seconds()
                        print(f"⏱️  Running for: {format_duration(duration)}")
                else:
                    print(f"⏱️  Pending (not started yet)")

                print()

                # Progress
                processed = job.get('processed_records', 0)
                failed = job.get('failed_records', 0)
                total = job.get('total_records', 0)

                print(f"✅ Processed: {processed:,} emails")
                print(f"❌ Failed: {failed:,} emails")

                if total and total > 0:
                    percent = (processed / total) * 100
                    print(f"📈 Progress: {percent:.1f}% ({processed:,} / {total:,})")

                    # Progress bar
                    bar_width = 50
                    filled = int(bar_width * processed // total)
                    bar = "█" * filled + "░" * (bar_width - filled)
                    print(f"   [{bar}]")

                    # Estimate time remaining
                    if processed > 0 and started:
                        start_time = datetime.fromisoformat(started.replace('Z', '+00:00'))
                        elapsed = (datetime.now() - start_time.replace(tzinfo=None)).total_seconds()
                        rate = processed / elapsed if elapsed > 0 else 0
                        remaining = total - processed
                        eta_seconds = remaining / rate if rate > 0 else 0
                        print(f"⚡ Speed: {rate:.1f} emails/sec")
                        print(f"⏳ ETA: {format_duration(eta_seconds)}")

                print()

                # Database stats (if mailbox_id available)
                if job.get('mailbox_id'):
                    db_count = get_mailbox_stats(job['mailbox_id'])
                    print(f"💾 Total emails in database: {db_count:,}")
                    print()

                # Errors
                errors = job.get('error_log', [])
                if errors:
                    print("⚠️  ERRORS:")
                    for i, error in enumerate(errors[:3], 1):
                        print(f"   {i}. {error}")
                    if len(errors) > 3:
                        print(f"   ... and {len(errors) - 3} more")
                    print()

                # Status indicator
                if job['status'] == 'running':
                    print("🟢 Status: PROCESSING...")
                elif job['status'] == 'completed':
                    print("✅ Status: COMPLETED!")
                elif job['status'] == 'failed':
                    print("🔴 Status: FAILED")
                elif job['status'] == 'pending':
                    print("🟡 Status: PENDING")

            print()
            print("=" * 80)
            print(f"Auto-refresh every {refresh_interval}s | Press Ctrl+C to exit")

            time.sleep(refresh_interval)

    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped")
        sys.exit(0)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Monitor email processing in real-time')
    parser.add_argument(
        '--interval',
        type=int,
        default=2,
        help='Refresh interval in seconds (default: 2)'
    )

    args = parser.parse_args()

    monitor_processing(refresh_interval=args.interval)
