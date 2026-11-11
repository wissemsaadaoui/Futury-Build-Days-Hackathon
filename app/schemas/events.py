"""GET /stocks/{isin}/events"""
from __future__ import annotations

from typing import Optional

from app.schemas.common import EventType, ISODate, OptNumber, Schema


class HeadlineMetric(Schema):
    volume_ratio: OptNumber  # null tant que l'OHLC n'est pas chargé
    price_change_pct: OptNumber  # idem
    spread_change_pct: OptNumber  # spread du jour vs baseline 20j, en %


class CorporateEvent(Schema):
    event_id: str
    date: ISODate
    time: str  # "HH:MM", vide si l'heure n'est pas connue
    trading_day: ISODate  # jour où l'effet est mesuré
    type: EventType
    title: str
    source_url: Optional[str]
    has_impact_card: bool
    headline_metric: HeadlineMetric


class EventsResponse(Schema):
    isin: str
    events: list[CorporateEvent]
    event_types: list[EventType]
