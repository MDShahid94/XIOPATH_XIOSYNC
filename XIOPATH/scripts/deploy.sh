#!/bin/bash
# ==================================================
# XIOPATH — Oracle Cloud Zero-Touch Deployment Script
# ==================================================
# Usage: ./scripts/deploy.sh <SERVER_IP> <SSH_KEY_PATH>
# ==================================================

set -e

if [ "$#" -ne 2 ]; then
    echo "Usage: ./scripts/deploy.sh <SERVER_IP> <SSH_KEY_PATH>"
    echo "Example: ./scripts/deploy.sh 150.230.x.x ~/.ssh/oracle_key"
    exit 1
fi

SERVER_IP=$1
SSH_KEY=$2
REMOTE_USER="ubuntu" # Default for Oracle Ubuntu images
REMOTE_DIR="~/xiopath"

echo "================================================"
echo "🚀 Initiating Genesis Deployment to $SERVER_IP"
echo "================================================"

# 1. Connect and install Docker on the remote server
echo "📦 [1/4] Installing Docker and Docker Compose on remote Oracle VM..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no $REMOTE_USER@$SERVER_IP << 'EOF'
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker $USER
    mkdir -p ~/xiopath
EOF

# 2. Transfer project files
echo "📂 [2/4] Transferring XIOPATH source code to Oracle VM..."
rsync -avz --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude 'data' -e "ssh -i $SSH_KEY" ./ $REMOTE_USER@$SERVER_IP:$REMOTE_DIR

# 3. Setup environment and secrets on remote
echo "🔐 [3/4] Initializing secure environment variables..."
ssh -i "$SSH_KEY" $REMOTE_USER@$SERVER_IP << 'EOF'
    cd ~/xiopath
    if [ ! -f .env ]; then
        echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" > .env
        echo "ENVIRONMENT=production" >> .env
        echo "FRONTEND_PORT=80" >> .env
        echo "API_PORT=8000" >> .env
    fi
EOF

# 4. Build and Launch
echo "🐳 [4/4] Building ARM64 containers and launching Swarm Control Plane..."
ssh -i "$SSH_KEY" $REMOTE_USER@$SERVER_IP << 'EOF'
    cd ~/xiopath
    
    # Oracle VMs sometimes have strict iptables. Open port 80 and 8000.
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT || true
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT || true
    sudo netfilter-persistent save || true
    
    # Execute docker compose
    sudo docker compose build
    sudo docker compose up -d
    
    echo "================================================"
    echo "✅ XIOPATH IS LIVE!"
    echo "Frontend Dashboard: http://$(curl -s ifconfig.me)"
    echo "WebSocket Mesh:     ws://$(curl -s ifconfig.me):8000/api/ws/worker"
    echo "================================================"
EOF
