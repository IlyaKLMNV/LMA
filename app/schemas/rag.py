from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class IngestBody(BaseModel):
    texts: List[str]
    metadatas: Optional[List[Dict[str, Any]]] = None

class QueryRAGBody(BaseModel):
    question: str
    profile: Optional[str] = None
    top_k: int = 5
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
