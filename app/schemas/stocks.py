"""GET /stocks"""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from app.schemas.common import Index, ISODate, Number, OptNumber, PeerBasis, Schema


class IndexPeriod(Schema):
    index: Index
    from_: Optional[ISODate] = Field(default=None, alias="from")
    until: Optional[ISODate] = None


class Coverage(Schema):
    dashboard: bool  # False : moins de 21 séances avec un spread mesuré (dashboard -> 404 avec message)
    events: bool  # annonces chargées (data/events.csv)
    intraday: bool  # trades horodatés disponibles
    sessions: int  # séances avec un spread XLM mesuré


class Stock(Schema):
    isin: str
    name: str
    ticker: str
    index: Index
    index_history: Optional[list[IndexPeriod]] = None
    sector: str
    shares_outstanding: Optional[Number] = None
    market_cap_eur: OptNumber  # null : pas de source de market cap dans les données Deutsche Börse
    is_selected: bool
    peers: list[str]  # ISINs (liste manuelle ; vide en base index)
    peer_basis: Optional[PeerBasis] = None  # v0.11
    coverage: Optional[Coverage] = None  # v0.11 : ce que les données couvrent pour cet émetteur


class StocksResponse(Schema):
    stocks: list[Stock]
    default_isin: Optional[str] = None  # v0.11 : émetteur affiché par défaut (pbb)
