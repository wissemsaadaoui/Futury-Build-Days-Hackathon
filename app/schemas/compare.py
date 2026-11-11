"""GET /compare"""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import EventType, Index, ISODate, OptNumber, Schema


class CompareFilter(Schema):
    type: EventType
    index: Index
    from_: ISODate = Field(alias="from")
    to: ISODate


class CompareSummary(Schema):
    n_events: int
    median_volume_ratio: OptNumber
    median_abs_price_change_pct: OptNumber
    median_spread_change_pct: OptNumber


class CompareEvent(Schema):
    event_id: str
    isin: str
    name: str
    date: ISODate
    volume_ratio: OptNumber
    price_change_pct: OptNumber
    spread_change_pct: OptNumber
    auction_share_change_pts: OptNumber


class CompareResponse(Schema):
    filter: CompareFilter
    summary: CompareSummary
    events: list[CompareEvent]
