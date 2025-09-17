from typing import List, Literal, Optional
from pydantic import BaseModel

class Msg(BaseModel):
    role: Literal["system","user","assistant"]
    content: str

class ChatBody(BaseModel):
    profile: Optional[str] = None
    model: Optional[str] = None
    messages: List[Msg]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
