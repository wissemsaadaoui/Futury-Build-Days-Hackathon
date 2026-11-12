"""POST /assistant/chat – chat libre de l'AI Assistant (logique : app/assistant/chat.py)."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ISODate, Schema


class ChatMessage(Schema):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(Schema):
    isin: str
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class ChatLink(Schema):
    label: str
    type: Literal["day", "event", "preview", "compare"]
    ref: str


class ChatResponse(Schema):
    answer: str
    links: list[ChatLink]
    as_of: ISODate
