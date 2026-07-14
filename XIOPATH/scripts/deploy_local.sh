#!/bin/bash
# ==================================================
# XIOPATH — Local Mac Deployment (with Cloudflare Prep)
# ==================================================
# Usage: ./scripts/deploy_local.sh
# ==================================================

set -e

echo "================================================"
echo "🚀 Initiating Local Genesis Deployment on Mac"
echo "================================================"

# 1. Setup environment and secrets
echo "🔐 [1/2] Initializing secure environment variables..."
if [ ! -f .env ]; then
    echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" > .env
    echo "ENVIRONMENT=production" >> .env
    echo "FRONTEND_PORT=8080" >> .env  # Using 8080 locally to avoid sudo
    echo "API_PORT=8000" >> .env
fi

# 2. Build and Launch
echo "🐳 [2/2] Building containers and launching Swarm Control Plane..."
docker compose build
docker compose up -d

echo "================================================"
echo "✅ XIOPATH IS LIVE LOCALLY!"
echo "Frontend Dashboard: http://localhost:8080"
echo "WebSocket Mesh:     ws://localhost:8000/api/ws/worker"
echo "================================================"
echo ""
echo "To expose this to the world using Cloudflare, run:"
echo "cloudflared tunnel --url http://localhost:8080"
echo "================================================"
