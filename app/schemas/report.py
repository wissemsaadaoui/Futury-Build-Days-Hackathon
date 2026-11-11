"""GET /stocks/{isin}/report  (IR snapshot)"""
from __future__ import annotations

from typing import Literal, Optional

from app.schemas.common import DataStatusMixin, ExportLinks, ISODate, ISODateTime, OptNumber, Period, Schema, StockRef

Trend = Literal["up", "down", "flat", "better", "worse"]


class ReportKpi(Schema):
    label: str
    value: OptNumber
    unit: Literal["shares", "EUR", "bps", "ratio", "pct"]
    trend: Trend
    change_pct: OptNumber = None


class ReportItem(Schema):
    event_id: str
    date: ISODate
    title: str
    volume_ratio: OptNumber
    price_change_pct: OptNumber
    spread_change_pct: OptNumber


class ReportSection(Schema):
    title: str
    kpis: Optional[list[ReportKpi]] = None
    items: Optional[list[ReportItem]] = None
    text: Optional[str] = None


class ReportResponse(DataStatusMixin, Schema):
    stock: StockRef
    period: Period
    headline: str
    sections: list[ReportSection]
    disclaimer: str
    generated_at: ISODateTime
    export: ExportLinks
