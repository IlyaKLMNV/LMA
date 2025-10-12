import os, json, hashlib, time, sys
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
import httpx
import tiktoken
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, Filter, FieldCondition, MatchValue, PointStruct

load_dotenv()
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kb")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY") or os.getenv("LMA_MISTRAL_API_KEY")
MISTRAL_EMBED_MODEL = os.getenv("MISTRAL_EMBED_MODEL", "mistral-embed")

EMBED_BATCH = int(os.getenv("MISTRAL_EMBED_BATCH", "64"))
EMBED_MAX_RETRIES = int(os.getenv("MISTRAL_EMBED_MAX_RETRIES", "6"))
EMBED_BASE_SLEEP = float(os.getenv("MISTRAL_EMBED_BASE_SLEEP", "1.0"))

def _embed_http(batch: List[str]) -> List[List[float]]:
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
    payload = {"model": MISTRAL_EMBED_MODEL, "input": batch}
    last_exc = None
    last_status = None
    for attempt in range(EMBED_MAX_RETRIES):
        try:
            r = httpx.post(
                "https://api.mistral.ai/v1/embeddings",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if r.status_code in (429, 500, 502, 503, 504):
                last_status = r.status_code
                retry_after = r.headers.get("retry-after", "")
                if retry_after and retry_after.replace(".", "", 1).isdigit():
                    delay = float(retry_after)
                else:
                    delay = min(30.0, EMBED_BASE_SLEEP * (2 ** attempt))
                print(f"[embed] {r.status_code}. retry in {delay:.1f}s (attempt {attempt+1}/{EMBED_MAX_RETRIES})")
                time.sleep(delay)
                continue
            r.raise_for_status()
            data = r.json()["data"]
            return [d["embedding"] for d in data]
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response is not None:
                print("[embed] status", exc.response.status_code, "headers", dict(exc.response.headers))
            raise
        except httpx.HTTPError as exc:
            last_exc = exc
            delay = min(30.0, EMBED_BASE_SLEEP * (2 ** attempt))
            print(f"[embed] transport error {exc!r}. retry in {delay:.1f}s (attempt {attempt+1}/{EMBED_MAX_RETRIES})")
            time.sleep(delay)
    if last_exc:
        raise RuntimeError(f"Embedding failed after {EMBED_MAX_RETRIES} retries: {last_exc!r}")
    raise RuntimeError(f"Embedding failed after {EMBED_MAX_RETRIES} retries (last status {last_status})")

def embed_texts_mistral_batched(texts: List[str]) -> List[List[float]]:
    out: List[List[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i+EMBED_BATCH]
        vecs = _embed_http(batch)
        out.extend(vecs)
        if i + EMBED_BATCH < len(texts):
            time.sleep(0.2)
    return out

def probe_dim() -> int:
    return len(_embed_http(["probe"])[0])

def count_tokens(text: str, enc) -> int:
    return len(enc.encode(text))

def chunk_text(text: str, enc, max_tokens=700, overlap=100) -> List[str]:
    toks = enc.encode(text)
    out = []
    i = 0
    n = len(toks)
    while i < n:
        j = min(i + max_tokens, n)
        out.append(enc.decode(toks[i:j]))
        if j == n: break
        i = max(0, j - overlap)
    return out

def ensure_collection(client: QdrantClient, dim: int):
    cols = client.get_collections().collections
    if not any(c.name == QDRANT_COLLECTION for c in cols):
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

def upsert_document(client: QdrantClient, doc: Dict, enc, dim: int):
    path = Path(doc["path"])
    text = path.read_text(encoding="utf-8")
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    doc_id = doc["doc_id"]

    # если уже есть и хэш совпал — пропускаем
    existing, _next = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
        with_payload=True,
        limit=1
    )
    if existing:
        if existing[0].payload.get("content_hash") == content_hash:
            print(f"= {doc_id}: без изменений")
            return
        # иначе чистим старые чанки
        client.delete(
            collection_name=QDRANT_COLLECTION,
            points_selector=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
        )
        print(f"* {doc_id}: контент изменился → перезалив")

    chunks = chunk_text(text, enc)
    print(f"[{doc_id}] chunks: {len(chunks)}; batch={EMBED_BATCH}")
    vectors = embed_texts_mistral_batched(chunks)
    ts = int(time.time())
    points: List[PointStruct] = []
    for i, (ch, vec) in enumerate(zip(chunks, vectors)):
        pid = int(hashlib.md5(f"{doc_id}-{i}-{content_hash}".encode()).hexdigest()[:12], 16)
        payload = {
            "doc_id": doc_id,
            "chunk_index": i,
            "content_hash": content_hash,
            "title": doc.get("title",""),
            "url": doc.get("url",""),
            "lang": doc.get("lang","ru"),
            "doc_type": doc.get("doc_type","doc"),
            "region": doc.get("region",""),
            "text": ch,
            "ts_ingested": ts,
        }
        points.append(PointStruct(id=pid, vector=vec, payload=payload))
    client.upsert(collection_name=QDRANT_COLLECTION, points=points)
    print(f"+ {doc_id}: {len(points)} чанков")

def ingest(manifest_path: str):
    if not MISTRAL_API_KEY:
        raise RuntimeError("Нет MISTRAL_API_KEY / LMA_MISTRAL_API_KEY в .env")
    enc = tiktoken.get_encoding("cl100k_base")
    dim = probe_dim()
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, dim)
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            doc = json.loads(line)
            upsert_document(client, doc, enc, dim)

def search(query: str, top_k=5, lang=None):
    enc = tiktoken.get_encoding("cl100k_base")
    qvec = _embed_http([query])[0]
    client = QdrantClient(url=QDRANT_URL)
    flt = None
    if lang:
        flt = Filter(must=[FieldCondition(key="lang", match=MatchValue(value=lang))])
    hits = client.search(collection_name=QDRANT_COLLECTION, query_vector=qvec, limit=top_k, with_payload=True, query_filter=flt)
    print(f"\nTOP {top_k} for: {query}\n")
    for i,h in enumerate(hits,1):
        p = h.payload
        snippet = p["text"].replace("\n"," ")[:220]
        print(f"{i}. {p.get('title')} [{p.get('doc_type')}] — {p.get('url')}\n   {snippet}...\n")

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "ingest":
        ingest(sys.argv[2])
    elif cmd == "search":
        query = " ".join(sys.argv[2:])
        search(query, top_k=5, lang="ru")
    else:
        print("Usage: python scripts/ingest_qdrant.py ingest docs/manifest.jsonl")
        print("       python scripts/ingest_qdrant.py search \"Как завершить поездку?\"")
