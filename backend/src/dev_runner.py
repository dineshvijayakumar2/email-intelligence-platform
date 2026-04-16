"""
Local development runner — API + worker in a single process.

Usage: python -m src.dev_runner

Starts uvicorn for the API and the worker main loop concurrently.
Ctrl+C stops both gracefully.
"""
import asyncio
import logging
import os
import sys
import threading

# Ensure backend is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

env = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env)


def _run_api():
    """Run uvicorn in a thread."""
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("API_PORT", "8000")),
        reload=False,
        log_level="info",
    )


async def _run_worker():
    """Run the worker main loop."""
    from src.workers.job_runner import main
    await main()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [dev] %(name)s %(levelname)s: %(message)s",
    )
    logger = logging.getLogger("dev_runner")

    logger.info("Starting dev runner: API + worker in single process")

    api_thread = threading.Thread(target=_run_api, daemon=True)
    api_thread.start()
    logger.info("API server started on thread")

    try:
        asyncio.run(_run_worker())
    except KeyboardInterrupt:
        logger.info("Dev runner shutting down")


if __name__ == "__main__":
    main()
