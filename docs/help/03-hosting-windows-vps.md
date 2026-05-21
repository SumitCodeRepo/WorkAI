# 03 — Hosting on a Windows VPS / Server

This guide deploys the FastAPI backend on a Windows Server or Windows VPS using:
- **NSSM** (Non-Sucking Service Manager) to run uvicorn as a Windows Service
- **IIS** with **Application Request Routing (ARR)** as the reverse proxy, OR
- **Caddy** as a simpler alternative reverse proxy with auto-HTTPS

---

## Server Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores | 8+ cores |
| RAM | 16 GB | 32 GB |
| Disk | 150 GB SSD | 300 GB SSD |
| OS | Windows Server 2019 | Windows Server 2022 |
| GPU | None (slow) | NVIDIA 24+ GB VRAM |

---

## Step 1 — Install Prerequisites

Open **PowerShell as Administrator** for all steps.

### Python 3.11
Download from https://www.python.org/downloads/ — choose the 64-bit installer.
During install, check **"Add Python to PATH"**.

```powershell
python --version    # verify: Python 3.11.x
```

### Git
```powershell
winget install --id Git.Git -e --source winget
# Restart PowerShell after install
git --version
```

### Ollama
Download from https://ollama.com/download/windows.

```powershell
# After install, pull the model (in a new PowerShell window)
ollama pull gpt-oss:120b-cloud
# Or a smaller model for CPU-only:
ollama pull mistral:7b
```

Ollama installs itself as a Windows service and starts automatically.

### NSSM (to run uvicorn as a service)
```powershell
# Download NSSM
Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile nssm.zip
Expand-Archive nssm.zip -DestinationPath C:\tools\nssm
# Add to PATH:
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\tools\nssm\nssm-2.24\win64", "Machine")
```

---

## Step 2 — Deploy the Backend

### 2a. Clone or copy the project

```powershell
# From Git:
git clone https://github.com/yourname/enterprise-chatbot.git C:\chatbot

# Or copy from your dev machine using robocopy:
robocopy D:\enterprise-chatbot C:\chatbot /MIR /XD RAG_VENV backend\temp mobile\node_modules __pycache__
```

### 2b. Create the virtual environment

```powershell
cd C:\chatbot
python -m venv RAG_VENV
```

### 2c. Install Python dependencies

```powershell
C:\chatbot\RAG_VENV\Scripts\pip install -r C:\chatbot\backend\requirements.txt
```

### 2d. Create the production .env

```powershell
@"
SECRET_KEY=<your-64-char-random-hex>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
DATABASE_URL=sqlite:///C:/chatbot/backend/chatbot.db
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gpt-oss:120b-cloud
RATE_LIMIT_CHAT=20/minute
"@ | Out-File -FilePath C:\chatbot\backend\.env -Encoding utf8
```

Generate a secret key:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2e. Create required directories

```powershell
New-Item -ItemType Directory -Force -Path C:\chatbot\backend\temp\uploads
New-Item -ItemType Directory -Force -Path C:\chatbot\backend\vector_store\hr
New-Item -ItemType Directory -Force -Path C:\chatbot\backend\vector_store\it
New-Item -ItemType Directory -Force -Path C:\chatbot\backend\vector_store\finance
New-Item -ItemType Directory -Force -Path C:\chatbot\backend\vector_store\legal
New-Item -ItemType Directory -Force -Path C:\chatbot\backend\vector_store\admin
```

### 2f. Test manually first

```powershell
cd C:\chatbot\backend
..\RAG_VENV\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
# Open http://localhost:8000/docs in browser
# Ctrl+C to stop
```

---

## Step 3 — Install as a Windows Service (NSSM)

```powershell
# Create the service
nssm install ChatbotAPI

# A GUI will appear. Set:
#   Path:           C:\chatbot\RAG_VENV\Scripts\python.exe
#   Startup dir:    C:\chatbot\backend
#   Arguments:      -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

Or set it all from the command line (no GUI):

```powershell
nssm install ChatbotAPI "C:\chatbot\RAG_VENV\Scripts\python.exe"
nssm set ChatbotAPI AppDirectory "C:\chatbot\backend"
nssm set ChatbotAPI AppParameters "-m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1"
nssm set ChatbotAPI AppStdout "C:\chatbot\backend\temp\service.log"
nssm set ChatbotAPI AppStderr "C:\chatbot\backend\temp\service-err.log"
nssm set ChatbotAPI Start SERVICE_AUTO_START
nssm set ChatbotAPI ObjectName LocalSystem
# Restart on failure:
nssm set ChatbotAPI AppExit Default Restart
nssm set ChatbotAPI AppRestartDelay 5000

# Start the service
nssm start ChatbotAPI

# Verify
nssm status ChatbotAPI   # should show RUNNING
```

### Service management commands

```powershell
nssm start   ChatbotAPI
nssm stop    ChatbotAPI
nssm restart ChatbotAPI
nssm status  ChatbotAPI
nssm remove  ChatbotAPI confirm   # uninstall
```

---

## Step 4 — Reverse Proxy

Choose **Option A (Caddy)** for simplicity or **Option B (IIS + ARR)** if you
already have IIS on the server.

---

### Option A — Caddy (Recommended: simpler, auto-HTTPS)

**Download Caddy:**
```powershell
# Download the Windows binary from https://caddyserver.com/download
# Save to C:\caddy\caddy.exe
Invoke-WebRequest -Uri "https://github.com/caddyserver/caddy/releases/latest/download/caddy_windows_amd64.zip" `
    -OutFile C:\caddy\caddy.zip
Expand-Archive C:\caddy\caddy.zip -DestinationPath C:\caddy
```

**Create Caddyfile** at `C:\caddy\Caddyfile`:
```
api.yourdomain.com {
    reverse_proxy 127.0.0.1:8000 {
        # SSE / streaming — flush immediately
        flush_interval -1
    }
    tls your-email@example.com
    request_body {
        max_size 50MB
    }
}
```

**Install Caddy as a service:**
```powershell
cd C:\caddy
.\caddy.exe service install
.\caddy.exe service start

# View logs
Get-EventLog -LogName Application -Source Caddy -Newest 50
```

Caddy obtains and renews TLS certificates from Let's Encrypt automatically.
Make sure port 80 and 443 are open in Windows Firewall and your VPS firewall.

```powershell
# Open firewall ports
New-NetFirewallRule -DisplayName "HTTP"  -Direction Inbound -Protocol TCP -LocalPort 80  -Action Allow
New-NetFirewallRule -DisplayName "HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

---

### Option B — IIS + Application Request Routing (ARR)

**Install IIS:**
```powershell
Enable-WindowsOptionalFeature -Online -FeatureName IIS-WebServerRole,IIS-WebServer,IIS-CommonHttpFeatures,IIS-HttpRedirect -All
```

**Install ARR + URL Rewrite** from https://www.iis.net/downloads/microsoft/application-request-routing.

**Create a web.config** in `C:\inetpub\wwwroot\`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="Proxy to Chatbot API" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8000/{R:1}" />
        </rule>
      </rules>
    </rewrite>
    <security>
      <requestFiltering>
        <!-- Allow large file uploads -->
        <requestLimits maxAllowedContentLength="52428800" />
      </requestFiltering>
    </security>
  </system.webServer>
</configuration>
```

**Enable ARR proxy mode** in IIS Manager:
1. Select the server node → Application Request Routing Cache → Server Proxy Settings
2. Enable proxy, disable SSL offloading for HTTP connections

**SSL:** Use IIS Manager → Server Certificates → Let's Encrypt (via win-acme):
```powershell
# Download win-acme from https://github.com/win-acme/win-acme
.\wacs.exe --target manual --host api.yourdomain.com --installation iis --siteid 1
```

---

## Step 5 — Firewall Rules

```powershell
# Allow HTTPS (and HTTP for Let's Encrypt challenge)
New-NetFirewallRule -DisplayName "HTTPS Inbound" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
New-NetFirewallRule -DisplayName "HTTP Inbound"  -Direction Inbound -Protocol TCP -LocalPort 80  -Action Allow

# Block direct access to uvicorn (only Nginx/Caddy/IIS should talk to it)
New-NetFirewallRule -DisplayName "Block uvicorn direct" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Block
```

---

## Step 6 — Update the Mobile App

In `mobile/services/api.ts`:
```typescript
export const BASE_URL = 'https://api.yourdomain.com';
```

Rebuild and republish (see `04-publish-app.md`).

---

## Ongoing Operations

### Update the backend

```powershell
cd C:\chatbot
git pull origin main
nssm restart ChatbotAPI
Get-Content C:\chatbot\backend\temp\app.log -Tail 50
```

### View logs

```powershell
# Live log tail
Get-Content C:\chatbot\backend\temp\app.log -Wait -Tail 20

# NSSM stdout log
Get-Content C:\chatbot\backend\temp\service.log -Tail 50

# Windows Event Log (Ollama)
Get-EventLog -LogName Application -Source ollama -Newest 20
```

### Backup

```powershell
$date = Get-Date -Format "yyyyMMdd"

# SQLite
Copy-Item C:\chatbot\backend\chatbot.db "C:\backups\chatbot-$date.db"

# FAISS indexes
Compress-Archive C:\chatbot\backend\vector_store "C:\backups\vector_store-$date.zip"
```

Schedule daily backups with Task Scheduler:
```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument '-NonInteractive -Command "Copy-Item C:\chatbot\backend\chatbot.db C:\backups\chatbot-$(Get-Date -Format yyyyMMdd).db"'
$trigger = New-ScheduledTaskTrigger -Daily -At "02:00AM"
Register-ScheduledTask -TaskName "ChatbotDBBackup" -Action $action -Trigger $trigger -RunLevel Highest
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Service won't start | Check `C:\chatbot\backend\temp\service-err.log`; verify the venv path in NSSM |
| 502 from proxy | Backend not listening — `nssm status ChatbotAPI` |
| Ollama not responding | `sc query Ollama` → should be RUNNING. Restart: `Restart-Service Ollama` |
| SSE tokens not streaming | Set `flush_interval -1` in Caddy / `proxy_buffering off` in Nginx |
| Large PDF upload fails | Increase `requestLimits maxAllowedContentLength` in web.config + `client_max_body_size` in Caddy |
| Path errors in .env | Use forward slashes or escaped backslashes: `C:/chatbot/...` or `C:\\chatbot\\...` |
