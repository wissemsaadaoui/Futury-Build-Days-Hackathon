"""POST /assistant/chat (protégée par le Bearer token, voir auth.py) : route minimale, logique dans app/assistant."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request

from app.analytics import NotFound, data
from app.assistant.chat import chat, suggested_questions
from app.schemas.assistant import ChatRequest, ChatResponse, SuggestionsResponse

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


@router.get("/suggestions", response_model=SuggestionsResponse)
def get_suggestions(isin: str) -> dict:
    """4 questions suggérées pour l'émetteur (pbb : celles de la démo)."""
    if not data.known_isin(isin):
        raise NotFound(f"Unknown ISIN {isin}")
    return {"isin": isin, "questions": list(suggested_questions(isin))}
