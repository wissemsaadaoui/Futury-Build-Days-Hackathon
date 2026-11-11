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
    """Flows JOURNALIERS d'une action : uniquement les lignes n_days == 1.
    Une ligne multi-jours (n_days > 1, flux censuré publié plus tard) mélangerait plusieurs séances :
    elle est exclue de toutes les métriques journalières (auction_share, net flow, by_participant)."""
    df = etl.load_flows()
    if df.empty:
        return df
    d = df[df["isin"] == isin].copy()
    if "n_days" in d.columns:
        d = d[d["n_days"].fillna(1).astype(int) == 1]
    d["date"] = pd.to_datetime(d["date"])
    for col in ("participant", "mode", "side"):
        d[col] = d[col].astype(str)
    return d


# ---------- trades (on-book Xetra) ----------
SESSION_OPEN = "09:00"
SESSION_CLOSE = "17:30"   # fin du continu ; la closing auction suit (~17:30–17:35)
SESSION_END = "17:36"     # après : impressions hors séance (exclues)


@lru_cache(maxsize=64)
def trades(isin: str) -> pd.DataFrame:
    """Trades on-book d'une action pendant la séance Xetra (09:00–17:36, enchères comprises).
    Les impressions avant 09:00 ou après 17:36 (hors séance, sans agresseur) sont exclues, SAUF les enchères
    identifiées (opening/midday/closing) : une closing auction prolongée peut se terminer après 17:36."""
    t = etl.load_trades(isin)
    if t.empty:
        return t
    hm = t["ts_local"].dt.strftime("%H:%M")
    labelled = t["auction_type"].fillna("").astype(str) != ""
    t = t[((hm >= SESSION_OPEN) & (hm < SESSION_END)) | labelled].copy()
    t["side"] = t["side"].fillna("").astype(str)
    t["auction_type"] = t["auction_type"].fillna("").astype(str)
    return t.reset_index(drop=True)


def has_trades(isin: str) -> bool:
    return not trades(isin).empty


@lru_cache(maxsize=64)
def continuous_trades(isin: str) -> pd.DataFrame:
    """Exécutions du trading continu avec un côté agresseur connu (BUY|SELL), hors enchères."""
    t = trades(isin)
    if t.empty:
        return t
    hm = t["ts_local"].dt.strftime("%H:%M")
    keep = t["side"].isin(["BUY", "SELL"]) & (t["auction_type"] == "") & (hm < SESSION_CLOSE)
    return t[keep].reset_index(drop=True)


@lru_cache(maxsize=256)
def auction_volume_series(isin: str, kind: str) -> pd.Series:
    """Volume (actions) de l'enchère `kind` (opening|midday|closing) par jour de trading.
    0 si l'enchère n'a rien exécuté ce jour-là (jours présents dans les trades)."""
    t = trades(isin)
    if t.empty:
        return pd.Series(dtype=float)
    days = pd.DatetimeIndex(sorted(t["date"].unique()))
    v = t[t["auction_type"] == kind].groupby("date")["qty"].sum().astype(float)
    return v.reindex(days, fill_value=0.0)


@lru_cache(maxsize=256)
def closing_auction_share_series(isin: str) -> pd.Series:
    """Part du volume du jour exécutée dans la closing auction (0–1) : volume closing (trades) ÷ volume OHLC."""
    px = ohlc(isin)
    ca = auction_volume_series(isin, "closing")
    if px.empty or ca.empty:
        return pd.Series(dtype=float)
    vol = px["volume"].astype(float).reindex(ca.index)
    return (ca / vol.where(vol > 0)).dropna()


@lru_cache(maxsize=256)
def adtv_series(isin: str, n: int = config.ALERT_ADTV_DAYS) -> pd.Series:
    """ADTV en € : moyenne du turnover_eur (OHLC) des n jours de trading PRÉCÉDENTS (jour courant exclu)."""
    px = ohlc(isin)
    if px.empty:
        return pd.Series(dtype=float)
    t = px["turnover_eur"].astype(float)
    return t.rolling(n, min_periods=max(5, n // 3)).mean().shift(1)


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
    for fn in (trading_days, spread_series, index_series, ohlc, flows, auction_share_series, trades, continuous_trades,
               auction_volume_series, closing_auction_share_series, adtv_series):
        fn.cache_clear()
    from app.analytics import pricing  # import tardif (pricing dépend de data)

    pricing.clear_caches()
    from app.analytics import alerts

    alerts.clear_caches()
