#!/bin/bash
set -e

echo "================================================"
echo "Starting XIOPATH Control Plane..."
echo "================================================"

# Ensure database directory exists
mkdir -p /app/data

# Run Alembic migrations to ensure the DB schema is up to date
echo "[Initialization] Running database migrations..."
alembic upgrade head

# Start the FastAPI application
echo "[Initialization] Starting FastAPI server on port 8000..."
exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"
