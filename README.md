# Mistral 7B Chat (FastAPI Proxy) 🎯

**Overview**  
Tiny backend that proxies the official **Mistral AI** API:

- `GET /health` — quick readiness check  
- `GET /models` — list available models  
- `POST /chat` — chat completion endpoint  

A minimal `index.html` is included — a simple browser chat that talks to the local backend.

---

## 🧠 Stack

- **Language model:** `open-mistral-7b`  
- **Backend:** Python 3.10+, FastAPI + Uvicorn  
- **API client:** `httpx` (you can swap for `mistralai` SDK)  
- **(Optional) RAG:** `mistral-embed` + Qdrant via `/ingest` and `/query_rag` (if implemented in `app.py`)

---

## 🚀 Run locally
./.venv/Scripts/python -m uvicorn app:app --reload --port 8000
