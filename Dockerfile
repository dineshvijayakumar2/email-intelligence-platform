FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/

WORKDIR /app/backend

EXPOSE 8000

CMD python3 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
