from typing import Optional
from fastapi import APIRouter, Query
from app.schemas.chat import ChatBody
from app.services.config import pick_model_and_params
from app.services.mistral import chat as mistral_chat

router = APIRouter()

@router.post("/chat")
async def chat(body: ChatBody, profile: Optional[str] = Query(None)):
    # Resolve final model/params
    sel = pick_model_and_params(
        profile_name=(body.profile if body.profile is not None else profile),
        explicit_model=body.model,
        explicit_temp=body.temperature,
        explicit_max_tokens=body.max_tokens,
    )
    msgs = [m.model_dump() for m in body.messages]
    resp = await mistral_chat(msgs, sel["model"], sel["temperature"], sel["max_tokens"])
    resp["_meta"] = {"profile": sel["profile"], "model": sel["model"]}
    return resp
