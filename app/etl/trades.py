"""Trades on-book Xetra, extraits par scripts/extract_trades.py dans data/processed/trades_<ISIN>.csv.gz."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from app import config

TRADES_COLS = ["ts_utc", "ts_local", "date", "price", "qty", "notional_eur", "side", "is_auction", "auction_type"]


def trades_path(isin: str) -> Path:
    return config.PROCESSED_DIR / f"trades_{isin}.csv.gz"


@lru_cache(maxsize=None)
def load_trades(isin: str) -> pd.DataFrame:
    """ts_utc, ts_local (Europe/Berlin), date, price, qty, notional_eur, side (BUY|SELL|"" = pas d'agresseur),
    is_auction (side vide), auction_type (opening|midday|closing|"" ), triés par ts_utc.

    Fichier absent (script pas encore lancé) -> DataFrame vide avec les bonnes colonnes.
    """
    path = trades_path(isin)
    if not path.exists():
        return pd.DataFrame(columns=TRADES_COLS)
    df = pd.read_csv(path, dtype={"side": str, "auction_type": str}, keep_default_na=False)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, format="ISO8601")
    df["ts_local"] = df["ts_utc"].dt.tz_convert(config.TZ)
    df["date"] = pd.to_datetime(df["date"])
    df["is_auction"] = df["is_auction"].astype(str).str.lower() == "true"
    return df[TRADES_COLS].sort_values("ts_utc", kind="stable").reset_index(drop=True)
