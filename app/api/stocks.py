"""Routes /stocks : liste, dashboard, événements, IR snapshot."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app import analytics, config, etl
from app.api.params import DateRange, date_range
from app.schemas import DashboardResponse, EventsResponse, ReportResponse, StocksResponse

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("", response_model=StocksResponse)
def get_stocks() -> dict:
    """Action(s) de démo + leurs peers (sélecteur d'action)."""
    universe = etl.get_universe().set_index("isin")
    stocks = []
    for isin in config.DEMO_ISINS:
        for s in [isin, *config.PEERS.get(isin, [])]:
            if s not in universe.index or any(x["isin"] == s for x in stocks):
                continue
            row = universe.loc[s]
            stocks.append(
                {
                    "isin": s,
                    "name": row["name"],
                    "ticker": row["mnemonic"],
                    "index": row["index"],
                    "sector": row["sector"],
                    "market_cap_eur": None,
                    "is_selected": s == isin,
                    "peers": config.PEERS.get(s, []),
                }
            )
    return {"stocks": stocks}


@router.get("/{isin}/dashboard", response_model=DashboardResponse)
def get_dashboard(isin: str, period: DateRange = Depends(date_range)) -> dict:
    return analytics.build_dashboard(isin, period.start, period.end)


@router.get("/{isin}/events", response_model=EventsResponse)
def get_events(isin: str) -> dict:
    return analytics.list_events(isin)


@router.get("/{isin}/report", response_model=ReportResponse)
def get_report(isin: str, period: DateRange = Depends(date_range)) -> dict:
    return analytics.build_report(isin, period.start, period.end)
