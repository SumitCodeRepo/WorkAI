# 02 — Hosting on a Linux VPS (Ubuntu 22.04)

This guide deploys the FastAPI backend and Ollama to a Linux VPS with:
- **Nginx** as a reverse proxy (HTTPS termination, WebSocket/SSE support)
- **systemd** to keep the backend and Ollama alive after crashes/reboots
- **Let's Encrypt (Certbot)** for a free TLS certificate

The mobile app is not hosted — Expo distributes it as an app binary (see `04-publish-app.md`).

---

## Server Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16–32 GB |
| Disk | 100 GB SSD | 200 GB SSD |
| GPU | None (slow) | NVIDIA 24+ GB VRAM for 120b |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |

> **The 120b model is very large.** On CPU-only VPS it runs at ~0.5–2 tokens/s.
> For a responsive app, consider a smaller model (`llama3.2:3b`, `mistral:7b`)
> or a GPU VPS (Lambda Labs, RunPod, vast.ai). See model swap instructions below.

---

## Step 1 — Initial Server Setup

```bash
# Log in as root (or use your cloud provider's console)
ssh root@your-server-ip

# Create a non-root user
adduser chatbot
usermod -aG sudo chatbot

# Switch to the new user for all remaining steps
su - chatbot
```

### Firewall
```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'   # opens ports 80 + 443
sudo ufw enable
sudo ufw status
```

---

## Step 2 — Install System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    git curl wget build-essential
```

Verify Python:
```bash
python3.11 --version   # Python 3.11.x
```

---

## Step 3 — Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama (systemd service is created automatically)
sudo systemctl enable ollama
sudo systemctl start ollama

# Wait 10 seconds, then pull the model
# For GPU VPS:
ollama pull gpt-oss:120b-cloud

# For CPU-only VPS (much faster inference):
ollama pull mistral:7b
# Then set OLLAMA_MODEL=mistral:7b in .env
```

> Ollama listens on `127.0.0.1:11434` by default — this is safe because Nginx
> proxies the backend API, and the backend talks to Ollama internally.

---

## Step 4 — Deploy the Backend

### 4a. Upload the project

```bash
# On your local machine — copy the project (excluding venv, node_modules)
rsync -avz --exclude='RAG_VENV' --exclude='mobile/node_modules' \
    --exclude='backend/temp' --exclude='backend/__pycache__' \
    ./enterprise-chatbot/ chatbot@your-server-ip:/home/chatbot/app/
```

Or clone from Git:
```bash
git clone https://github.com/yourname/enterprise-chatbot.git /home/chatbot/app
```

### 4b. Create the virtual environment

```bash
cd /home/chatbot/app
python3.11 -m venv RAG_VENV
RAG_VENV/bin/pip install --upgrade pip
RAG_VENV/bin/pip install -r backend/requirements.txt
```

### 4c. Create production .env

```bash
cat > /home/chatbot/app/backend/.env << 'EOF'
SECRET_KEY=<paste your 64-char random hex here>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
DATABASE_URL=sqlite:////home/chatbot/app/backend/chatbot.db
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gpt-oss:120b-cloud
RATE_LIMIT_CHAT=20/minute
EOF
```

Generate the key:
```bash
python3.11 -c "import secrets; print(secrets.token_hex(32))"
```

### 4d. Create required directories

```bash
mkdir -p /home/chatbot/app/backend/temp/uploads
mkdir -p /home/chatbot/app/backend/vector_store/{hr,it,finance,legal,admin}
```

### 4e. Test the backend manually

```bash
cd /home/chatbot/app/backend
../RAG_VENV/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
# Ctrl+C to stop after verifying it starts
```

---

## Step 5 — systemd Service for the Backend

Create `/etc/systemd/system/chatbot.service`:

```bash
sudo nano /etc/systemd/system/chatbot.service
```

Paste:
```ini
[Unit]
Description=Enterprise AI Chatbot FastAPI Backend
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=exec
User=chatbot
WorkingDirectory=/home/chatbot/app/backend
ExecStart=/home/chatbot/app/RAG_VENV/bin/python -m uvicorn main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 1 \
    --log-level info
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable chatbot
sudo systemctl start chatbot
sudo systemctl status chatbot   # should show "active (running)"

# View live logs
sudo journalctl -u chatbot -f
```

---

## Step 6 — Nginx Reverse Proxy

### 6a. Create the site config

```bash
sudo nano /etc/nginx/sites-available/chatbot
```

Paste (replace `api.yourdomain.com`):
```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    # Redirect HTTP → HTTPS (Certbot will add this)
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    # SSL certificates (Certbot fills these in)
    ssl_certificate     /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # File upload size (match backend limit)
    client_max_body_size 50M;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # SSE / streaming — disable buffering so tokens reach the client instantly
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 120s;   # LLM can be slow — increase if needed
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/
sudo nginx -t        # test config
sudo systemctl reload nginx
```

### 6b. Get a TLS certificate (Let's Encrypt)

```bash
# Make sure your domain's A record points to this server's IP first
sudo certbot --nginx -d api.yourdomain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

---

## Step 7 — Update the Mobile App's BASE_URL

In `mobile/services/api.ts`:
```typescript
export const BASE_URL = 'https://api.yourdomain.com';
```

Then rebuild and republish the app (see `04-publish-app.md`).

---

## Step 8 — Ongoing Operations

### Updating the backend
```bash
cd /home/chatbot/app
git pull origin main
sudo systemctl restart chatbot
sudo journalctl -u chatbot -f   # watch for errors
```

### Viewing logs
```bash
# systemd logs (last 100 lines)
sudo journalctl -u chatbot -n 100 --no-pager

# Application log file
tail -f /home/chatbot/app/backend/temp/app.log

# Nginx access log
sudo tail -f /var/log/nginx/access.log
```

### Backup SQLite database
```bash
# Simple backup (safe while running — SQLite uses WAL mode)
cp /home/chatbot/app/backend/chatbot.db /home/chatbot/backups/chatbot-$(date +%Y%m%d).db

# Schedule daily backups with cron:
crontab -e
# Add: 0 2 * * * cp /home/chatbot/app/backend/chatbot.db /home/chatbot/backups/chatbot-$(date +\%Y\%m\%d).db
```

### Backup FAISS indexes
```bash
tar -czf /home/chatbot/backups/vector_store-$(date +%Y%m%d).tar.gz \
    /home/chatbot/app/backend/vector_store/
```

---

## Switching to a Smaller LLM (CPU-Only VPS)

```bash
# Pull a fast, small model
ollama pull mistral:7b          # ~4 GB, works on 8 GB RAM
# or
ollama pull llama3.2:3b        # ~2 GB, works on 4 GB RAM

# Update .env
nano /home/chatbot/app/backend/.env
# Change: OLLAMA_MODEL=mistral:7b

# Restart the backend
sudo systemctl restart chatbot
```

---

## Security Checklist

- [ ] `SECRET_KEY` is a 64-char random hex string, not the default
- [ ] `.env` file is not committed to git (`echo ".env" >> .gitignore`)
- [ ] Firewall only allows ports 22, 80, 443
- [ ] Nginx has SSL configured (no plain HTTP for API calls)
- [ ] `CORS allow_origins` in `main.py` is restricted to your domain in production
- [ ] SQLite file permissions: `chmod 600 /home/chatbot/app/backend/chatbot.db`
- [ ] Ollama is bound to `127.0.0.1` (not `0.0.0.0`) — not directly exposed
- [ ] Auto-renewal for TLS certificate is confirmed working

---

## Troubleshooting

```bash
# Backend not starting?
sudo journalctl -u chatbot -n 50

# Nginx 502 Bad Gateway?
# → Backend not running. Check: sudo systemctl status chatbot

# SSE streaming not working through Nginx?
# → Check proxy_buffering off is set in the location block

# Ollama out of memory?
# → Use a smaller model or add swap:
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
