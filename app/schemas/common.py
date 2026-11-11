"""Types communs – miroir de la section « Communs » de shared/types.ts."""
from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

# int | float : garde 1290000 en entier dans le JSON (un simple float le sérialiserait en 1290000.0)
Number = Union[int, float]
# Valeurs numériques pouvant être null tant que OHLC/Flows manquent ou que l'historique est trop court
# (mocks/API.md, section « null »)
OptNumber = Optional[Number]

ISODate = str  # "YYYY-MM-DD"
ISODateTime = str  # ISO 8601 avec fuseau
Index = Literal["DAX", "MDAX", "SDAX"]

EventType = Literal[
    "quarterly_results",
    "annual_results",
    "ad_hoc",
    "dividend",
    "press_release",
    "m_and_a",
    "agm",
    "index_change",
    "voting_rights",
    "directors_dealings",
]
ParticipantType = Literal["AGENT", "PROP", "MARKET_MAKER"]
MarketMode = Literal["AGGRESSIVE", "PASSIVE", "AUCTION"]


class Schema(BaseModel):
    """Base de tous les modèles : ignore les champs techniques des mocks (_endpoint, _note…)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class DataStatusMixin(BaseModel):
    """`_data_status` ({spreads|ohlc|flows: "real"|"mock"|"missing"}) : badge « données de démo » côté front."""

    data_status: Optional[dict[str, str]] = Field(default=None, alias="_data_status")


class StockRef(Schema):
    isin: str
    name: str
    index: str  # Index | string (peut être vide si l'ISIN n'a pas de spread ce jour-là)
    sector: Optional[str] = None


class ExportLinks(Schema):
    pdf_url: str


class Period(Schema):
    from_: ISODate = Field(alias="from")
    to: ISODate
