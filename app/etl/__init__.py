"""ETL – chargement des données.

TEMPORAIRE (créé par Alfred pour démarrer l'analyse) – propriétaire : partenaire back-end.
`load_xlm()` est fonctionnel. `load_ohlc()` et `load_flows()` renvoient un DataFrame VIDE
(avec les bonnes colonnes) tant que les données ne sont pas là : l'analytics retombe alors sur les mocks.
Les signatures et colonnes sont fixées dans CLAUDE.md : les garder identiques.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app import config

XLM_COLS = ["date", "isin", "mnemonic", "index", "notional", "impact_bps"]
OHLC_COLS = ["date", "isin", "open", "high", "low", "close", "volume", "turnover_eur"]
FLOWS_COLS = ["date", "isin", "participant", "mode", "side", "volume"]
EVENTS_COLS = ["event_id", "isin", "date", "time", "trading_day", "type", "title", "source_url"]


@lru_cache(maxsize=1)
def load_xlm() -> pd.DataFrame:
    """date (datetime64), isin, mnemonic, index, notional (float), impact_bps (float, NaN possible)"""
    files = sorted((config.DATA_DIR / "spreads").glob("dax_mdax_sdax_xlm.*.csv"))
    if not files:
        return pd.DataFrame(columns=XLM_COLS)
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    df = df.rename(
        columns={
            "Date": "date",
            "ISIN": "isin",
            "Mnemonic": "mnemonic",
            "Index": "index",
            "Notional_CCY": "notional",
            "Impact_bps": "impact_bps",
        }
    )
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
    df["notional"] = df["notional"].astype(float)
    df["impact_bps"] = pd.to_numeric(df["impact_bps"], errors="coerce")
    return df[XLM_COLS].sort_values(["isin", "date", "notional"]).reset_index(drop=True)


@lru_cache(maxsize=1)
def load_ohlc() -> pd.DataFrame:
    """date, isin, open, high, low, close, volume, turnover_eur  – TODO partenaire (vide pour l'instant)"""
    return pd.DataFrame(columns=OHLC_COLS)


@lru_cache(maxsize=1)
def load_flows() -> pd.DataFrame:
    """date, isin, participant, mode, side, volume  – TODO partenaire (vide pour l'instant)"""
    return pd.DataFrame(columns=FLOWS_COLS)


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


@lru_cache(maxsize=1)
def get_universe() -> pd.DataFrame:
    """isin, name, mnemonic, index (actuel), sector (peut être vide)"""
    xlm = load_xlm()
    if xlm.empty:
        return pd.DataFrame(columns=["isin", "name", "mnemonic", "index", "sector"])
    last = xlm.sort_values("date").groupby("isin").tail(1)[["isin", "mnemonic", "index"]]
    last["name"] = last["isin"].map(config.NAMES).fillna(last["mnemonic"])
    last["sector"] = last["isin"].map(config.SECTORS).fillna("")
    return last[["isin", "name", "mnemonic", "index", "sector"]].reset_index(drop=True)
