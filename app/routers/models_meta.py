from fastapi import APIRouter
from app.services.config import MODELS_CFG
from app.services.mistral import list_models

router = APIRouter()

@router.get("/profiles")
def profiles():
    cfg = MODELS_CFG.get("models", {})
    out = {k: v for k, v in cfg.items() if k != "default"}
    return {"default": cfg.get("default"), "profiles": out}

@router.get("/models")
async def models():
    return await list_models()
