"""GET /stocks/{isin}/dashboard"""
from __future__ import annotations

from typing import Literal, Optional

from app.schemas.common import DataStatusMixin, ISODate, OptNumber, Period, Schema, StockRef

AnomalyType = Literal["volume_spike", "spread_widening", "price_move", "auction_spike"]
Severity = Literal["low", "medium", "high"]


class VsPeers(Schema):
    volume_ratio: OptNumber
    spread_diff_bps: OptNumber  # négatif = mieux que les peers
    auction_share_diff: OptNumber


class DashboardKpis(Schema):
    avg_daily_volume: OptNumber
    avg_daily_turnover_eur: OptNumber
    avg_spread_bps: OptNumber
    avg_auction_share: OptNumber  # 0–1
    price_change_pct: OptNumber
    anomaly_days: int
    vs_peers: VsPeers


class DailyPoint(Schema):
    date: ISODate
    open: OptNumber
    high: OptNumber
    low: OptNumber
    close: OptNumber
    volume: OptNumber
    turnover_eur: OptNumber
    volume_ratio: OptNumber  # volume / baseline 20j
    spread_bps: OptNumber
    auction_share: OptNumber  # 0–1, null si pas de Flows
    ema_20: OptNumber
    ema_50: OptNumber
    macd: OptNumber
    macd_signal: OptNumber
    macd_hist: OptNumber
    anomaly: bool


class PeerPoint(Schema):
    date: ISODate
    volume_ratio: OptNumber
    spread_bps: OptNumber
    auction_share: OptNumber


class Anomaly(Schema):
    date: ISODate
    type: AnomalyType
    severity: Severity
    value: OptNumber
    description: str
    linked_event_id: Optional[str]


class PriceLevel(Schema):
    price: float
    touches: int


class SupportResistance(Schema):
    support: list[PriceLevel]
    resistance: list[PriceLevel]


class DashboardResponse(DataStatusMixin, Schema):
    stock: StockRef
    period: Period
    kpis: DashboardKpis
    series: list[DailyPoint]
    peers_series: list[PeerPoint]
    anomalies: list[Anomaly]
    support_resistance: SupportResistance
