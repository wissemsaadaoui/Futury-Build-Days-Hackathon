"""Schémas Pydantic – propriétaire : partenaire back-end.

Miroir de `shared/types.ts` et des mocks JSON (snake_case). Écarts volontaires :
- les valeurs numériques sont nullables (mocks/API.md : null tant que OHLC/Flows manquent) ;
- `_data_status` est conservé (badge « données de démo » côté front).
"""
from __future__ import annotations

from app.schemas.assistant import ChatRequest, ChatResponse
from app.schemas.compare import CompareResponse
from app.schemas.dashboard import DashboardResponse
from app.schemas.event_preview import EventPreviewResponse
from app.schemas.events import EventsResponse
from app.schemas.impact_card import ImpactCardResponse
from app.schemas.report import ReportResponse
from app.schemas.stocks import StocksResponse

__all__ = [
    "StocksResponse",
    "DashboardResponse",
    "EventsResponse",
    "ImpactCardResponse",
    "CompareResponse",
    "ReportResponse",
    "EventPreviewResponse",
    "ChatRequest",
    "ChatResponse",
]
