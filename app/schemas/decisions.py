"""/decisions – journal human-in-the-loop (logique : app/store.py, app/analytics/decisions.py)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.schemas.common import Schema


class DecisionIn(Schema):
    item_type: Literal["alert", "ai_summary", "anomaly"]
    item_id: str = Field(min_length=1, max_length=200)
    isin: str
    decision: Literal["approved", "dismissed"]
    note: Optional[str] = Field(default=None, max_length=500)


class Decision(Schema):
    id: int
    item_type: str  # alert | ai_summary | anomaly | threshold
    item_id: str
    isin: str
    decision: str  # approved | dismissed | threshold_changed
    note: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    decided_at: str  # ISO 8601, Europe/Berlin
    decided_by: str


class DecisionRef(Schema):
    """Dernière décision d'un élément, renvoyée avec les anomalies / alertes / résumés IA."""
    id: int
    decision: Literal["approved", "dismissed"]
    note: Optional[str] = None
    decided_at: str
    decided_by: str


class DecisionLog(Schema):
    isin: Optional[str] = None
    decisions: list[Decision]
