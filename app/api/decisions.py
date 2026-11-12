"""Human-in-the-loop (point 9) : « AI suggests, the IR team decides – every decision is logged. »
Routes minimales ; stockage dans data/decisions.db (app/store.py)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app import store
from app.analytics import NotFound, data
from app.schemas.decisions import Decision, DecisionIn, DecisionLog

router = APIRouter(prefix="/decisions", tags=["decisions"])
DECIDED_BY = "ir-team"  # un seul mot de passe d'équipe : pas d'identité individuelle


@router.post("", response_model=Decision)
def post_decision(body: DecisionIn) -> dict:
    if not data.known_isin(body.isin):
        raise NotFound(f"Unknown ISIN {body.isin}")
    return store.add_decision(body.item_type, body.item_id, body.isin, body.decision, DECIDED_BY,
                              note=(body.note or "").strip() or None)


@router.get("", response_model=DecisionLog)
def get_decisions(isin: Optional[str] = Query(None), limit: int = Query(500, ge=1, le=2000)) -> dict:
    return {"isin": isin, "decisions": store.list_decisions(isin, limit)}
