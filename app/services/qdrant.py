# Qdrant client helpers: ensure collection, upsert, search.

import uuid
from typing import Dict, List, Any
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from .config import QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION

client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def ensure_collection(dim: int) -> None:
    names = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION not in names:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

def upsert_points(vectors: List[List[float]], payloads: List[Dict[str, Any]]) -> int:
    points = [PointStruct(id=str(uuid.uuid4()), vector=vec, payload=pl) for vec, pl in zip(vectors, payloads)]
    client.upsert(collection_name=QDRANT_COLLECTION, points=points)
    return len(points)

def search_topk(query_vector: List[float], limit: int = 5):
    return client.search(collection_name=QDRANT_COLLECTION, query_vector=query_vector, limit=limit)
