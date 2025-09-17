# Token-based chunking with a safe fallback when tiktoken is missing.

from typing import List

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:
    _ENC = None

def chunk_by_tokens(text: str, max_tokens: int = 800, overlap_tokens: int = 120) -> List[str]:
    """Chunk long text by tokens; fall back to whitespace split."""
    if not text or text.isspace():
        return []
    if _ENC is None:
        words = text.split()
        chunks, i = [], 0
        while i < len(words):
            piece = words[i:i+max_tokens]
            chunks.append(" ".join(piece).strip())
            i += max_tokens - overlap_tokens
        return [c for c in chunks if c]
    toks = _ENC.encode(text)
    chunks, i = [], 0
    while i < len(toks):
        piece = toks[i:i+max_tokens]
        chunks.append(_ENC.decode(piece).strip())
        i += max_tokens - overlap_tokens
    return [c for c in chunks if c]
