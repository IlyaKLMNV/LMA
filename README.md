# Mistral 7B Chat (FastAPI Proxy) 🎯

**Overview**  
Tiny backend that proxies the official **Mistral AI** API and (optionally) adds RAG on top of Qdrant.

- `GET /health` — quick readiness check  
- `GET /models` — list available models  
- `POST /chat` — chat completion endpoint  
- (RAG) `POST /ingest`, `POST /ingest_files`, `POST /ingest_path` — data ingestion  
- (RAG) `POST /query_rag` — ask with retrieval context  
- `GET /profiles` — model profiles (switching via `configs/models.yaml`)

A minimal `index.html` is included — a simple browser chat that talks to the backend.

---

## 🧠 Stack

- **Language model:** `open-mistral-7b`  
- **Backend:** Python 3.10+, FastAPI + Uvicorn  
- **API client:** `httpx` (you can swap for `mistralai` SDK)  
- **RAG (optional):** `mistral-embed` + **Qdrant**

---

## 🚀 Quick commands (Docker Compose)
- `docker compose down` - Stops and removes containers and networks Stops and removes containers and networks of the current Compose project
- `docker compose up -d` - Reads compose.yaml in the current key, builds images if necessary, creates/updates the network and containers, and starts services in the background (detached) without logging to the console
- `docker compose up -d --build` - Builds images (if needed) and runs containers in the background.
- `docker compose ps` - Shows the current status of services: whether they are running, which ports are forwarded, and container names.

# Swagger: http://127.0.0.1:8000/docs
