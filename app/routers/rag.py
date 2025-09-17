# /ingest, /ingest_files, /ingest_path, /query_rag

from typing import Dict, Any, List, Optional
from pathlib import Path
import tempfile
import uuid

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from app.schemas.rag import IngestBody, QueryRAGBody
from app.services.config import EMBED_MODEL, pick_model_and_params
from app.services.mistral import embed as mistral_embed, chat as mistral_chat
from app.services.qdrant import ensure_collection, upsert_points, search_topk
from app.services.chunk import chunk_by_tokens
from app.services.files import load_file_to_text, normalize_text

router = APIRouter()

def payloads_for_chunks(chunks: List[str], base_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for idx, c in enumerate(chunks):
        meta = dict(base_meta)
        meta.update({"chunk_index": idx, "text": c})
        out.append(meta)
    return out

async def embed_in_batches(chunks: List[str], batch_size: int = 96) -> List[List[float]]:
    all_vecs = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        vecs = await mistral_embed(batch, EMBED_MODEL)
        all_vecs.extend(vecs)
    return all_vecs

@router.post("/ingest")
async def ingest(body: IngestBody):
    metadatas = body.metadatas or [{} for _ in body.texts]
    all_chunks, metas = [], []
    for text, meta in zip(body.texts, metadatas):
        t = normalize_text(text)
        cs = chunk_by_tokens(t, max_tokens=800, overlap_tokens=120)
        all_chunks.extend(cs)
        metas.extend(payloads_for_chunks(cs, base_meta=meta))
    if not all_chunks:
        return {"ingested": 0}
    vecs = await embed_in_batches(all_chunks)
    ensure_collection(len(vecs[0]))
    upsert_points(vecs, metas)
    return {"ingested": len(all_chunks), "dim": len(vecs[0])}

@router.post("/ingest_files")
async def ingest_files(
    files: List[UploadFile] = File(...),
    source: Optional[str] = Form(None),
    max_tokens: int = Form(800),
    overlap_tokens: int = Form(120),
    namespace: Optional[str] = Form(None),
):
    texts, metas = [], []
    for uf in files:
        suffix = Path(uf.filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await uf.read())
            tmp_path = Path(tmp.name)

        raw = load_file_to_text(tmp_path)
        raw = normalize_text(raw)
        chunks = chunk_by_tokens(raw, max_tokens=max_tokens, overlap_tokens=overlap_tokens)

        base_meta = {
            "filename": uf.filename,
            "source": source or "upload",
            "namespace": namespace,
        }
        texts.extend(chunks)
        metas.extend(payloads_for_chunks(chunks, base_meta))
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    if not texts:
        return {"ingested": 0}
    vecs = await embed_in_batches(texts)
    ensure_collection(len(vecs[0]))
    upsert_points(vecs, metas)
    return {"files": len(files), "chunks": len(texts)}

@router.post("/ingest_path")
async def ingest_path(
    path: str = Form(...),
    glob: str = Form("**/*"),
    max_tokens: int = Form(800),
    overlap_tokens: int = Form(120),
    source: Optional[str] = Form(None),
    namespace: Optional[str] = Form(None),
):
    root = Path(path)
    if not root.exists():
        raise HTTPException(400, f"Path not found: {path}")
    exts = {".txt", ".md", ".markdown", ".html", ".htm", ".pdf", ".docx", ".csv", ".tsv"}
    files = [p for p in root.glob(glob) if p.is_file() and p.suffix.lower() in exts]
    if not files:
        return {"ingested": 0, "files": 0}

    all_chunks, all_meta = [], []
    for p in files:
        try:
            raw = load_file_to_text(p)
            raw = normalize_text(raw)
            chunks = chunk_by_tokens(raw, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
            base_meta = {
                "filename": str(p),
                "source": source or "dir",
                "namespace": namespace,
            }
            all_chunks.extend(chunks)
            all_meta.extend(payloads_for_chunks(chunks, base_meta))
        except Exception as e:
            print(f"[ingest_path] skip {p}: {e}")

    if not all_chunks:
        return {"ingested": 0, "files": len(files)}
    vecs = await embed_in_batches(all_chunks)
    ensure_collection(len(vecs[0]))
    upsert_points(vecs, all_meta)
    return {"files": len(files), "chunks": len(all_chunks)}

@router.post("/query_rag")
async def query_rag(body: QueryRAGBody, profile: Optional[str] = Query(None)):
    sel = pick_model_and_params(
        profile_name=(body.profile if body.profile is not None else profile),
        explicit_model=None,
        explicit_temp=body.temperature,
        explicit_max_tokens=body.max_tokens,
    )
    qvec = (await mistral_embed([body.question], EMBED_MODEL))[0]
    hits = search_topk(qvec, limit=body.top_k)

    parts, sources = [], []
    for i, h in enumerate(hits, start=1):
        pl = h.payload or {}
        t = pl.get("text", "")
        parts.append(f"[{i}] {t}")
        meta = {k: v for k, v in pl.items() if k != "text"}
        sources.append({"ref": i, "score": h.score, "metadata": meta})

    context = "\n\n".join(parts)
    system = {"role": "system", "content": "Answer strictly from CONTEXT. If missing, say you don't know. Cite [1], [2], ..."}
    user = {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {body.question}\nAnswer in the question language."}
    resp = await mistral_chat([system, user], sel["model"], sel["temperature"], sel["max_tokens"])
    answer = resp["choices"][0]["message"]["content"]
    return {"answer": answer, "sources": sources, "_meta": {"profile": sel["profile"], "model": sel["model"]}}
