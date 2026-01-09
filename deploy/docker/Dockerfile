# Multi-stage Dockerfile for Railway deployment
# Supports both backend and frontend in single deployment

# Backend stage
FROM python:3.9-slim as backend

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ backend/
COPY src/ src/

# Set working directory to backend
WORKDIR /app/backend

# Expose port
EXPOSE 8000

# Start command
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]