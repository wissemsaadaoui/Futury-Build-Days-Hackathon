"""ETL – chargement des données (propriétaire : partenaire back-end).

Les signatures et colonnes sont fixées dans CLAUDE.md (section « Interfaces ») : app/analytics s'appuie dessus.
Chaque fonction lit data/raw une seule fois (lru_cache) ; app.main les précharge au démarrage.
Sans fichiers, elles renvoient un DataFrame vide avec les bonnes colonnes (l'analytics retombe alors sur les mocks).
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app import config
from app.etl.flows import FLOWS_COLS, load_flows
from app.etl.ohlc import OHLC_COLS, load_ohlc
from app.etl.trades import TRADES_COLS, load_trades
from app.etl.universe import get_universe, index_on_date, load_constituents
from app.etl.xlm import XLM_COLS, load_xlm

EVENTS_COLS = ["event_id", "isin", "date", "time", "trading_day", "type", "title", "source_url"]

__all__ = [
    "load_xlm",
    "load_ohlc",
    "load_flows",
    "load_events",
    "load_trades",
    "load_constituents",
    "get_universe",
    "index_on_date",
    "warm_up",
    "XLM_COLS",
    "OHLC_COLS",
    "FLOWS_COLS",
    "EVENTS_COLS",
    "TRADES_COLS",
]


@lru_cache(maxsize=1)
def load_events() -> pd.DataFrame:
    """event_id, isin, date, time, trading_day, type, title, source_url
    trading_day peut être vide : app.analytics.events le calcule."""
    if not config.EVENTS_CSV.exists():
        return pd.DataFrame(columns=EVENTS_COLS)
    df = pd.read_csv(config.EVENTS_CSV, dtype=str).fillna("")
    for col in EVENTS_COLS:
        if col not in df.columns:
            df[col] = ""
    return df[EVENTS_COLS]


def warm_up() -> None:
    """Charge toutes les données en mémoire (appelé au démarrage de l'API)."""
    load_xlm()
    load_ohlc()
    load_flows()
    load_events()
    get_universe()
    for isin in config.DEMO_ISINS:
        for i in (isin, *config.PEERS.get(isin, [])):
            load_trades(i)
