# Thin HTTP client for Mistral: chat, embeddings, list models.

import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx

from .config import MISTRAL_API_KEY, MISTRAL_BASE

RETRYABLE_STATUSES = {429}
HTTP_MAX_RETRIES = int(os.getenv("MISTRAL_HTTP_MAX_RETRIES", "3"))
HTTP_BASE_SLEEP = float(os.getenv("MISTRAL_HTTP_BASE_SLEEP", "1.5"))
HTTP_MAX_SLEEP = float(os.getenv("MISTRAL_HTTP_MAX_SLEEP", "10.0"))


def _auth_headers(content_type: Optional[str] = None) -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        return None


async def _request_with_retry(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 120.0,
) -> httpx.Response:
    url = f"{MISTRAL_BASE}{path}"
    headers = _auth_headers("application/json" if payload is not None else None)
    attempt = 0
    sleep = HTTP_BASE_SLEEP
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            resp = await client.request(method, url, headers=headers, json=payload)
            try:
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in RETRYABLE_STATUSES and attempt < HTTP_MAX_RETRIES:
                    retry_after = _parse_retry_after(exc.response.headers.get("retry-after"))
                    wait = retry_after if retry_after is not None else sleep
                    await asyncio.sleep(max(wait, 0.0))
                    attempt += 1
                    if retry_after is None:
                        sleep = min(sleep * 2.0, HTTP_MAX_SLEEP)
                    continue
                raise


async def list_models() -> Dict[str, Any]:
    resp = await _request_with_retry("GET", "/models", payload=None, timeout=30.0)
    return resp.json()


async def chat(messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    resp = await _request_with_retry("POST", "/chat/completions", payload=payload)
    return resp.json()


async def embed(texts: List[str], embed_model: str) -> List[List[float]]:
    payload = {"model": embed_model, "input": texts}
    resp = await _request_with_retry("POST", "/embeddings", payload=payload)
    data = resp.json()
    return [item["embedding"] for item in data["data"]]
