"""GET /stocks/{isin}/event-preview – réactions passées du trading à un type d'annonce (mocks/API.md v0.4 §5.3)."""
from __future__ import annotations

from typing import Literal, Optional

from app.schemas.common import DataStatusMixin, EventType, ISODate, OptNumber, Schema, StockRef


class PreviewStat(Schema):
    n: int  # nombre de valeurs disponibles
    median: OptNumber  # null si n = 0
    min: OptNumber
    max: OptNumber


class PreviewEvent(Schema):
    event_id: str
    date: ISODate  # trading_day
    spread_change_pct: OptNumber
    volume_ratio: OptNumber
    price_abs_change_pct: OptNumber  # amplitude absolue, jamais signée
    sessions_to_normal: OptNumber  # null = pas revenu à la normale en 5 séances
    auction_share_change_pts: OptNumber
    first_15min_ratio: OptNumber  # null si pas d'intraday


class PreviewHistory(Schema):
    n: int
    events: list[PreviewEvent]
    spread_change_pct: PreviewStat
    volume_ratio: PreviewStat
    price_abs_change_pct: PreviewStat
    sessions_to_normal: PreviewStat
    auction_share_change_pts: PreviewStat
    first_15min_ratio: PreviewStat


class PeerHistory(PreviewHistory):
    peers_note: Optional[str] = None  # si aucun événement de peer


class Upcoming(Schema):
    date: ISODate
    title: Optional[str] = None
    event_id: Optional[str] = None
    source_url: Optional[str] = None


class EventPreviewResponse(DataStatusMixin, Schema):
    stock: StockRef
    event_type: EventType
    as_of: Optional[ISODate] = None  # `date` demandé : seuls les événements AVANT cette date ; null = tous
    upcoming: Optional[Upcoming] = None
    own_history: PreviewHistory
    peers: PeerHistory
    attention_points: list[str]
    confidence: Literal["low", "medium", "high"]  # low : n < 3, medium : 3–5, high : > 5
    note: str
    ai_summary: str
