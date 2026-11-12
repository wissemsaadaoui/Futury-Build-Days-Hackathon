"""GET /stocks/{isin}/report  (IR snapshot)"""
from __future__ import annotations

from typing import Literal, Optional

from app.schemas.common import DataStatusMixin, ExportLinks, ISODate, ISODateTime, OptNumber, Period, Schema, StockRef
from app.schemas.decisions import DecisionRef

Trend = Literal["up", "down", "flat", "better", "worse"]


# v0.3 (modifié par Alfred avec l'accord de l'équipe, à valider par Wissem) : unité "count" (section Alerts),
# trend null si la variation est inconnue, change_basis, alert_type ; ReportSection.alert_days
class ReportKpi(Schema):
    label: str
    value: OptNumber
    unit: Literal["shares", "EUR", "bps", "ratio", "pct", "count"]
    trend: Optional[Trend] = None
    change_pct: OptNumber = None
    change_basis: Optional[Literal["previous_period", "first_half"]] = None
    alert_type: Optional[str] = None  # section Alerts : type d'anomalie compté


class ReportAlertDay(Schema):
    date: ISODate
    n_alerts: int
    n_high: int
    types: list[str]
    top_description: str
    linked_event_id: Optional[str] = None
    detail_url: Optional[str] = None


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
    alert_days: Optional[list[ReportAlertDay]] = None  # v0.3 : section Alerts, top 5 jours
    text: Optional[str] = None


class ReportResponse(DataStatusMixin, Schema):
    stock: StockRef
    period: Period
    headline: str
    ai_points: list[str] = []  # v0.6
    ai_summary_id: Optional[str] = None  # v0.8 : pour POST /decisions (item_type ai_summary)
    ai_summary_decision: Optional[DecisionRef] = None
    sections: list[ReportSection]
    disclaimer: str
    generated_at: ISODateTime
    export: ExportLinks
