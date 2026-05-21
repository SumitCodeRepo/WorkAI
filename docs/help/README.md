# Enterprise AI Chatbot — Help & Operations Guide

This folder contains step-by-step guides for every operational task.
All guides are specific to this project's stack:

> **FastAPI** + **SQLite** + **FAISS** + **Ollama** ← backend
> **React Native (Expo 54)** ← mobile app

---

## Guides

| Guide | What it covers |
|---|---|
| [01-dev-setup.md](01-dev-setup.md) | Get the full stack running on a local development machine (Windows, Mac, Linux) |
| [02-hosting-linux-vps.md](02-hosting-linux-vps.md) | Deploy the backend to a Linux VPS (Ubuntu 22.04) with Nginx + systemd |
| [03-hosting-windows-vps.md](03-hosting-windows-vps.md) | Deploy the backend to a Windows Server / VPS with IIS or NSSM |
| [04-publish-app.md](04-publish-app.md) | Build and publish the React Native app to App Store + Google Play using EAS |
| [05-testing.md](05-testing.md) | Run all tests — backend scripts, TypeScript check, manual QA checklist |

---

## Quick Reference

### Start backend (dev)
```bash
cd backend/
..\RAG_VENV\Scripts\python -m uvicorn main:app --reload --port 8000
```

### Start mobile (dev)
```bash
cd mobile/
npx expo start
```

### Run all backend tests
```bash
cd backend/
..\RAG_VENV\Scripts\python test_ingestion.py
..\RAG_VENV\Scripts\python test_query_engine.py
..\RAG_VENV\Scripts\python test_router_agent.py
..\RAG_VENV\Scripts\python test_admin.py
```

### TypeScript check
```bash
cd mobile/
npx tsc --noEmit
```

### Health check
```bash
curl http://localhost:8000/health
```

---

## Architecture Recap

```
React Native App (Expo 54)
        │  JWT + REST + SSE
        ▼
FastAPI Backend (Python 3.11)
        │  SQLite (chatbot.db)
        │  FAISS indexes (vector_store/)
        │  Ollama LLM (gpt-oss:120b-cloud)
        │
   RouterAgent ──→ HR / IT / Finance / Legal / Admin Agent
                         ↓
                   FAISS vector search
                         ↓
                   Ollama RAG stream
```
