# 01 — Getting the Dev Environment Running

This guide gets the full stack running locally on a fresh machine.
Estimated time: 20–40 minutes depending on download speeds.

---

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Node.js | 18+ LTS | `node --version` |
| npm | 9+ | `npm --version` |
| Git | any | `git --version` |
| Ollama | latest | `ollama --version` |
| Expo Go | latest | install on your phone / emulator |

### Installing Ollama
Download from https://ollama.com. After install:

```bash
# Start the Ollama server (runs in background)
ollama serve

# Pull the model used in this project
ollama pull gpt-oss:120b-cloud

# Verify it works
ollama list
```

> **Heavy model alert:** `gpt-oss:120b-cloud` requires ~70 GB disk and a GPU or
> very fast CPU. For local dev on modest hardware, swap it for a smaller model:
> ```bash
> ollama pull llama3.2:3b
> # Then set in backend/.env:
> OLLAMA_MODEL=llama3.2:3b
> ```

---

## Step 1 — Clone / Open the Project

```bash
# If you cloned from git:
git clone <your-repo-url> enterprise-chatbot
cd enterprise-chatbot

# Or open the existing folder:
cd e:/Claude_Work/PythonCode    # Windows
```

The project layout:
```
enterprise-chatbot/
├── backend/          ← FastAPI Python server
├── mobile/           ← React Native Expo app
├── docs/             ← Documentation (you are here)
├── RAG_VENV/         ← Python virtual environment
└── temp/             ← Logs + temp uploads (auto-created)
```

---

## Step 2 — Backend Setup

### 2a. Create the virtual environment (first time only)

```bash
# Windows
python -m venv RAG_VENV

# Mac / Linux
python3 -m venv RAG_VENV
```

### 2b. Install Python dependencies

```bash
# Windows
RAG_VENV\Scripts\pip install -r backend\requirements.txt

# Mac / Linux
RAG_VENV/bin/pip install -r backend/requirements.txt
```

> **Windows note:** `bcrypt` is pinned to `4.0.1` in `requirements.txt`. bcrypt 5.x
> has an API change that breaks `passlib`. The pin is intentional.

### 2c. Configure the .env file

Copy the example or create `backend/.env`:

```ini
SECRET_KEY=change-this-to-a-long-random-secret-key-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
DATABASE_URL=sqlite:///./chatbot.db
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:120b-cloud
RATE_LIMIT_CHAT=20/minute
```

Generate a real `SECRET_KEY`:
```bash
# Python one-liner
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2d. Start the backend

Always `cd` into `backend/` before running uvicorn — the server expects to
find `chatbot.db`, `vector_store/`, and `temp/` relative to its working directory.

```bash
# Windows
cd backend
..\RAG_VENV\Scripts\python -m uvicorn main:app --reload --port 8000

# Mac / Linux
cd backend
../RAG_VENV/bin/python -m uvicorn main:app --reload --port 8000
```

**Expected output:**
```
INFO     Starting Enterprise AI Chatbot API...
INFO     Initialising database tables...
INFO     Database tables ready
INFO     Pre-loading FAISS indexes for all departments...
INFO     All FAISS indexes loaded
INFO     Enterprise AI Chatbot API ready — http://localhost:8000/docs
INFO     Uvicorn running on http://0.0.0.0:8000
```

Open http://localhost:8000/docs to see Swagger UI.

### 2e. Verify with health check

```bash
curl http://localhost:8000/health
# {"status":"ok","db":"ok","ollama":"ok","phase":9}
# If Ollama isn't running: "status":"degraded","ollama":"error"
```

---

## Step 3 — Mobile Setup

### 3a. Install Node dependencies

```bash
cd mobile
npm install
```

> If you see peer dependency conflicts: `npm install --legacy-peer-deps`

### 3b. Configure the backend URL

Open `mobile/services/api.ts` and set `BASE_URL` to match where your backend is:

| Scenario | BASE_URL |
|---|---|
| Android emulator (AVD) | `http://10.0.2.2:8000` ← default |
| iOS simulator | `http://localhost:8000` |
| Physical device (same WiFi) | `http://192.168.x.x:8000` (your machine's LAN IP) |
| Remote VPS | `https://api.yourdomain.com` |

Find your LAN IP:
```bash
# Windows
ipconfig | findstr "IPv4"
# Mac
ifconfig | grep "inet "
# Linux
ip addr show
```

### 3c. Start Expo dev server

```bash
cd mobile
npx expo start
```

You'll see a QR code in the terminal. Options:
- **Expo Go app** (iOS/Android): Scan the QR code — fastest for physical devices
- **Android emulator**: Press `a` (requires Android Studio + AVD)
- **iOS simulator**: Press `i` (Mac only, requires Xcode)
- **Web**: Press `w` (limited — for layout inspection only)

---

## Step 4 — First Run Walkthrough

1. **Register an admin account:**
   Use Swagger UI → `POST /auth/register`:
   ```json
   { "email": "admin@company.com", "password": "Admin1234!", "full_name": "Admin User", "role": "admin" }
   ```

2. **Register a regular user:**
   ```json
   { "email": "user@company.com", "password": "User1234!", "full_name": "Test User" }
   ```

3. **Upload a test document (via Swagger):**
   - `POST /admin/documents/upload`
   - Authorize with the admin JWT first (click "Authorize" in Swagger)
   - Upload any PDF to the `hr` department

4. **Chat with the HR agent:**
   - Log in as the regular user in the mobile app
   - Tap the HR card
   - Ask: "What is the leave policy?"

---

## Common Issues

### Backend

| Problem | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | venv not activated or wrong pip | Make sure you run `..\RAG_VENV\Scripts\python`, not the system `python` |
| `sqlite3.OperationalError` | wrong working directory | Always `cd backend/` before running uvicorn |
| `Connection refused` (Ollama) | Ollama not running | Run `ollama serve` in a separate terminal |
| `UnicodeEncodeError` on Windows | Windows cp1252 console | Cosmetic — logs use `errors="replace"`, output still works |
| Port 8000 already in use | Another process | Kill it: `netstat -ano | findstr :8000` then `taskkill /PID <pid> /F` |

### Mobile

| Problem | Cause | Fix |
|---|---|---|
| `Network request failed` | Wrong `BASE_URL` | Use `10.0.2.2` for Android emulator, not `localhost` |
| Metro bundler crash | Node modules corrupt | Delete `node_modules/` + `npm install --legacy-peer-deps` |
| QR code not working | Device not on same WiFi | Connect device to same network as dev machine |
| White screen / silent crash | JS error | Press `j` in Expo terminal to open debugger |

---

## Development Tips

- **Auto-reload:** `--reload` flag restarts the backend on every `.py` file save
- **Swagger UI:** http://localhost:8000/docs — test every endpoint without the mobile app
- **Server logs:** `temp/app.log` — rolling log with INFO+ messages
- **SQLite inspection:** use [DB Browser for SQLite](https://sqlitebrowser.org/) to inspect `backend/chatbot.db`
- **FAISS indexes:** stored in `backend/vector_store/<dept>/index.faiss` — don't delete these unless you want to re-ingest all documents
- **HuggingFace cache warning on Windows:** cosmetic only — the embedder still works without symlinks
