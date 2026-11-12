"""GET /events/{event_id}/impact-card  |  GET /days/{isin}/{date}/impact-card"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.schemas.common import (
    DataStatusMixin,
    EventType,
    ExportLinks,
    ISODate,
    ISODateTime,
    MarketMode,
    OptNumber,
    ParticipantType,
    Period,
    Schema,
    StockRef,
)
from app.schemas.dashboard import AnomalyType


class ImpactEvent(Schema):
    event_id: str
    type: EventType
    title: str
    published_at: Optional[ISODateTime]  # null si l'heure de publication n'est pas vérifiée
    trading_day: ISODate
    source_url: Optional[str]


class Baseline(Schema):
    method: str
    from_: ISODate = Field(alias="from")
    to: ISODate


class RatioMetric(Schema):
    event: OptNumber
    baseline: OptNumber
    ratio: OptNumber
    z_score: OptNumber = None


class PriceMetric(Schema):
    prev_close: OptNumber
    open: OptNumber
    close: OptNumber
    change_pct: OptNumber
    intraday_range_pct: OptNumber


class SpreadMetric(Schema):
    event: OptNumber
    baseline: OptNumber
    change_pct: OptNumber


class AuctionShareMetric(Schema):
    event: OptNumber
    baseline: OptNumber
    change_pts: OptNumber


class AuctionMetric(Schema):
    volume: OptNumber
    baseline: OptNumber
    ratio: OptNumber


class Metrics(Schema):
    volume: RatioMetric
    turnover_eur: RatioMetric
    price: PriceMetric
    spread_bps: SpreadMetric
    auction_share: AuctionShareMetric
    opening_auction: AuctionMetric
    closing_auction: AuctionMetric


class ParticipantFlow(Schema):
    type: ParticipantType
    buy: OptNumber
    sell: OptNumber
    net: OptNumber


class ModeShare(Schema):
    mode: MarketMode
    share: OptNumber


class Flows(Schema):
    by_participant: list[ParticipantFlow]
    by_mode: list[ModeShare]


class WindowPoint(Schema):
    offset: int  # 0 = jour de l'événement
    date: ISODate
    close: OptNumber
    volume_ratio: OptNumber
    spread_bps: OptNumber


class ImpactVsPeers(Schema):
    peer_avg_volume_ratio: OptNumber
    peer_avg_price_change_pct: OptNumber
    excess_return_pct: OptNumber


class BrokeLevel(Schema):
    type: Literal["support", "resistance"]
    price: float


class TechnicalContext(Schema):
    trend_before: Literal["above_ema50", "below_ema50"]
    macd_before: Literal["bullish", "bearish"]
    macd_after: Literal["bullish", "bearish"]
    broke_level: Optional[BrokeLevel]


# v0.2 (modifié par Alfred, à valider par le backend) : bloc intraday, voir mocks/API.md §5.1
class IntradayMinute(Schema):
    offset_min: int
    time: str  # "HH:MM"
    vwap: OptNumber
    volume: OptNumber
    cum_volume: OptNumber
    buy_aggressor_share: OptNumber


class IntradayFirstWindow(Schema):
    volume: OptNumber
    baseline: OptNumber
    ratio: OptNumber


class IntradayPriceChange(Schema):
    after_5min: OptNumber
    after_30min: OptNumber
    after_60min: OptNumber


class IntradayBlock(Schema):
    reference_time: ISODateTime
    during_session: bool
    minutes: list[IntradayMinute]
    first_15min: IntradayFirstWindow
    price_change_pct: IntradayPriceChange


# v0.3 : activité des séances AVANT une notification de droits de vote (WpHG art. 40), mocks/API.md §5.4
class PreDisclosureWindow(Period):  # Period gère déjà l'alias "from"
    sessions: int


class PreDisclosureDay(Schema):
    date: ISODate
    anomaly_types: list[AnomalyType]
    volume_ratio: OptNumber
    agent_net_flow_eur: OptNumber  # flux net AGENT en € ; null sans Flows


class PreDisclosureActivity(Schema):
    window: PreDisclosureWindow
    days: list[PreDisclosureDay]
    summary: str  # phrase neutre, ne désigne jamais l'investisseur notifié


class ImpactCardResponse(DataStatusMixin, Schema):
    card_id: str
    stock: StockRef
    event: Optional[ImpactEvent]  # null pour un « notable day » sans annonce
    baseline: Baseline
    metrics: Metrics
    flows: Flows
    window: list[WindowPoint]
    vs_peers: ImpactVsPeers
    technical_context: TechnicalContext
    intraday: Optional[IntradayBlock] = None  # v0.2 : null si pas de trades ce jour-là
    pre_disclosure_activity: Optional[PreDisclosureActivity] = None  # v0.3 : voting_rights uniquement
    ai_summary: str
    ai_points: list[str] = []  # v0.6 : 3–4 phrases courtes, chacune vérifiée par le garde-fou
    generated_at: ISODateTime
    export: ExportLinks
