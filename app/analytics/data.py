"""Accès aux données préparées pour l'analyse (au-dessus de app.etl)."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app import config, etl


def has_ohlc() -> bool:
    return not etl.load_ohlc().empty


def has_flows() -> bool:
    return not etl.load_flows().empty


@lru_cache(maxsize=1)
def trading_days() -> pd.DatetimeIndex:
    """Calendrier de trading = toutes les dates présentes dans les données."""
    dates = [etl.load_xlm()["date"]]
    if has_ohlc():
        dates.append(pd.to_datetime(etl.load_ohlc()["date"]))
    s = pd.concat(dates)
    return pd.DatetimeIndex(sorted(pd.to_datetime(s).unique()))


def known_isin(isin: str) -> bool:
    return isin in set(etl.load_xlm()["isin"]) or (has_ohlc() and isin in set(etl.load_ohlc()["isin"]))


@lru_cache(maxsize=256)
def spread_series(isin: str, notional: float = config.REF_NOTIONAL) -> pd.Series:
    """Impact_bps au notional de référence, indexé par date."""
    x = etl.load_xlm()
    s = x[(x["isin"] == isin) & (x["notional"] == notional)].set_index("date")["impact_bps"]
    return s.sort_index()


@lru_cache(maxsize=256)
def index_series(isin: str) -> pd.Series:
    x = etl.load_xlm()
    return x[x["isin"] == isin].drop_duplicates("date").set_index("date")["index"].sort_index()


def index_on(isin: str, day: pd.Timestamp) -> str | None:
    s = index_series(isin)
    s = s[s.index <= day]
    return None if s.empty else str(s.iloc[-1])


def peers_of(isin: str) -> list[str]:
    return [p for p in config.PEERS.get(isin, []) if p != isin]


def name_of(isin: str) -> str:
    if isin in config.NAMES:
        return config.NAMES[isin]
    x = etl.load_xlm()
    m = x.loc[x["isin"] == isin, "mnemonic"]
    return str(m.iloc[0]) if not m.empty else isin


@lru_cache(maxsize=256)
def ohlc(isin: str) -> pd.DataFrame:
    """OHLC d'une action, indexé par date (vide si pas de données)."""
    df = etl.load_ohlc()
    if df.empty:
        return df
    d = df[df["isin"] == isin].copy()
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date").sort_index()


@lru_cache(maxsize=256)
def flows(isin: str) -> pd.DataFrame:
    df = etl.load_flows()
    if df.empty:
        return df
    d = df[df["isin"] == isin].copy()
    d["date"] = pd.to_datetime(d["date"])
    return d


@lru_cache(maxsize=256)
def auction_share_series(isin: str) -> pd.Series:
    """Part du volume exécutée en AUCTION, par jour (0–1)."""
    f = flows(isin)
    if f.empty:
        return pd.Series(dtype=float)
    tot = f.groupby("date")["volume"].sum()
    auc = f[f["mode"] == "AUCTION"].groupby("date")["volume"].sum()
    return (auc.reindex(tot.index).fillna(0) / tot).sort_index()


def stock_ref(isin: str, day: pd.Timestamp | None = None) -> dict:
    idx = index_on(isin, day) if day is not None else index_on(isin, trading_days()[-1])
    return {
        "isin": isin,
        "name": name_of(isin),
        "index": idx or "",
        "sector": config.SECTORS.get(isin, ""),
    }


def clear_caches() -> None:
    """À appeler si les données ETL changent (tests)."""
    for fn in (trading_days, spread_series, index_series, ohlc, flows, auction_share_series):
        fn.cache_clear()
