"""GET /stocks/{isin}/dashboard"""
from __future__ import annotations

from typing import Literal, Optional

from app.schemas.common import DataStatusMixin, ISODate, OptNumber, Period, Schema, StockRef

# v0.3 : alertes sur les exécutions (§5.2) + level_break, voir mocks/API.md
AnomalyType = Literal[
    "volume_spike",
    "spread_widening",
    "price_move",
    "auction_spike",
    "large_trade",
    "aggressor_sweep",
    "net_flow",
    "level_break",
]
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
    spread_eur: OptNumber = None  # v0.2 : coût aller-retour en € pour 25 000 €
    spread_ticks: OptNumber = None  # v0.2 : coût par action en ticks Xetra (null sans trades)
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
    detail_url: str  # /events/{id}/impact-card si linked_event_id, sinon /days/{isin}/{date}/impact-card
    # Champs optionnels selon le type : large_trade, aggressor_sweep (time) ; + net_flow (side, notional_eur)
    time: Optional[str] = None  # "HH:MM:SS"
    side: Optional[Literal["BUY", "SELL"]] = None
    notional_eur: OptNumber = None
    level_type: Optional[Literal["support", "resistance"]] = None  # level_break uniquement
    level_price: OptNumber = None  # level_break uniquement (€)


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
