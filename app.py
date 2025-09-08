# app.py
# Minimal FastAPI proxy to Mistral's /v1/chat/completions with non-streaming calls.
# Comments are in English per your request.

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal, Optional

# Hardcoded API key (you asked to keep it in code explicitly).
MISTRAL_API_KEY = "0IAClm1qBDX927s7mGD61pegnbiFQEJe"

# Base URL for Mistral API
MISTRAL_URL = "https://api.mistral.ai/v1"

# Default 7B model (adjust if your account lists a different name in /v1/models)
DEFAULT_MODEL = "open-mistral-7b"

app = FastAPI(title="Mistral Chat Proxy")

# CORS: allow calling the API from a simple local HTML page
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Msg(BaseModel):
    role: Literal["system","user","assistant"]
    content: str

class ChatBody(BaseModel):
    model: Optional[str] = None
    messages: List[Msg]
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.3
    max_tokens: Optional[int] = 512

@app.get("/health")
def health():
    # Simple health endpoint
    return {"ok": True}

@app.get("/models")
async def models():
    # Helpful endpoint to list available models in your account
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{MISTRAL_URL}/models", headers=headers)
        r.raise_for_status()
        return r.json()

@app.post("/chat")
async def chat(body: ChatBody):
    # Proxy a non-streaming chat completion call to Mistral
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": body.model or DEFAULT_MODEL,
        "messages": [m.model_dump() for m in body.messages],
        "temperature": body.temperature,
        "max_tokens": body.max_tokens,
        "stream": False,  # keep it simple; streaming can be added later
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{MISTRAL_URL}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()
