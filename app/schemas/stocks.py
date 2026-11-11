"""GET /stocks"""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from app.schemas.common import Index, ISODate, Number, OptNumber, Schema


class IndexPeriod(Schema):
    index: Index
    from_: Optional[ISODate] = Field(default=None, alias="from")
    until: Optional[ISODate] = None


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
    peers: list[str]  # ISINs


class StocksResponse(Schema):
    stocks: list[Stock]
