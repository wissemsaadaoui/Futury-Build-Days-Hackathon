"""POST /assistant/chat (protégée par le Bearer token, voir auth.py) : route minimale, logique dans app/assistant."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request

from app.assistant.chat import chat
from app.schemas.assistant import ChatRequest, ChatResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])

RATE_LIMIT = 20  # requêtes
RATE_WINDOW_S = 60.0  # par minute et par token
_calls: dict[str, deque[float]] = defaultdict(deque)


def _check_rate(token: str, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    q = _calls[token]
    while q and now - q[0] >= RATE_WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests: 20 per minute. Please wait a moment.")
    q.append(now)


@router.post("/chat", response_model=ChatResponse)
def post_chat(body: ChatRequest, request: Request) -> dict:
    _check_rate(request.headers.get("authorization", ""))
    return chat(body.isin, [m.model_dump() for m in body.messages])
