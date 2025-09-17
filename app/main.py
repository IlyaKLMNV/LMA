# FastAPI app assembly: middleware + routers.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.health import router as health_router
from app.routers.models_meta import router as models_router
from app.routers.chat import router as chat_router
from app.routers.rag import router as rag_router

app = FastAPI(title="LMA RAG API (Mistral + Qdrant)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# Register routers
app.include_router(health_router)
app.include_router(models_router)
app.include_router(chat_router)
app.include_router(rag_router)
