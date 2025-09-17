# Thin HTTP client for Mistral: chat, embeddings, list models.

from typing import Any, Dict, List
import httpx
from .config import MISTRAL_API_KEY, MISTRAL_BASE

async def list_models() -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{MISTRAL_BASE}/models", headers=headers)
        r.raise_for_status()
        return r.json()

async def chat(messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": False}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{MISTRAL_BASE}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()

async def embed(texts: List[str], embed_model: str) -> List[List[float]]:
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": embed_model, "input": texts}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{MISTRAL_BASE}/embeddings", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return [item["embedding"] for item in data["data"]]
