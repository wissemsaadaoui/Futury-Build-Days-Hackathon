"""Effet du niveau de prix sur le spread.

Le XLM (`impact_bps`) est un coût RELATIF au prix. Avec un tick size fixe en euros, une baisse du cours
augmente mécaniquement le spread en bps. Ce module exprime le spread en euros et en ticks, et décompose
une variation de spread en « effet prix » (coût constant en € par action) et « effet liquidité » (le reste).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from app import config
from app.analytics import data

# Grilles candidates (€), de la plus fine à la plus grosse. Le tick d'un mois = la plus grosse grille
# sur laquelle tombent >= 99,5 % des prix exécutés en continu.
_TICK_GRID = (0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5)
_TICK_COVERAGE = 0.995


def infer_tick(prices: pd.Series) -> float | None:
    """Tick size déduit des prix exécutés (None si pas assez de prix)."""
    p = pd.Series(prices).dropna()
    if len(p) < 50:
        return None
    units = np.round(p.to_numpy() * 1e4).astype(np.int64)  # en 1/10 000 €
    best = None
    for t in _TICK_GRID:
        step = int(round(t * 1e4))
        if (units % step == 0).mean() >= _TICK_COVERAGE:
            best = t
    return best


@lru_cache(maxsize=64)
def tick_series(isin: str) -> pd.Series:
    """Tick size (€) par jour de trading, déduit mois par mois des trades continus (vide sans trades).
    Limite : déduit empiriquement (le tick Xetra dépend de la bande de liquidité MiFID II et du prix),
    pas lu dans un référentiel officiel."""
    t = data.continuous_trades(isin)
    if t.empty:
        return pd.Series(dtype=float)
    month = t["date"].dt.to_period("M")
    ticks = {m: infer_tick(g["price"]) for m, g in t.groupby(month)}
    days = pd.DatetimeIndex(sorted(t["date"].unique()))
    return pd.Series([ticks.get(d.to_period("M")) for d in days], index=days, dtype=float)


def spread_eur_25k(bps: float | pd.Series) -> float | pd.Series:
    """Coût aller-retour en € pour 25 000 € échangés."""
    return bps / 1e4 * config.REF_NOTIONAL


@lru_cache(maxsize=256)
def spread_frame(isin: str) -> pd.DataFrame:
    """Par jour : spread_bps, close, spread_eur (pour 25 k€), spread_eur_per_share, tick, spread_ticks."""
    sp = data.spread_series(isin)
    px = data.ohlc(isin)
    df = pd.DataFrame({"spread_bps": sp})
    df["close"] = px["close"].astype(float).reindex(df.index) if not px.empty else np.nan
    df["spread_eur"] = spread_eur_25k(df["spread_bps"])
    df["spread_eur_per_share"] = df["spread_bps"] / 1e4 * df["close"]
    tk = tick_series(isin)
    df["tick"] = tk.reindex(df.index) if not tk.empty else np.nan
    df["spread_ticks"] = df["spread_eur_per_share"] / df["tick"]
    return df


def monthly(isin: str) -> pd.DataFrame:
    """Médiane mensuelle du spread (bps, € par action, ticks) et cours moyen."""
    df = spread_frame(isin)
    g = df.groupby(df.index.to_period("M"))
    return pd.DataFrame(
        {
            "spread_bps": g["spread_bps"].median(),
            "close": g["close"].mean(),
            "spread_eur_per_share": g["spread_eur_per_share"].median(),
            "tick": g["tick"].median(),
            "spread_ticks": g["spread_ticks"].median(),
        }
    )


def decompose(isin: str, a: tuple[str, str], b: tuple[str, str]) -> dict:
    """Décompose la variation du spread médian (bps) entre les périodes a et b.

    effet prix     = spread qu'on aurait en b si le coût en € par action était resté celui de a,
                     moins le spread de a :  bps_a × (P_a / P_b) − bps_a
    effet liquidité = le reste : bps_b − bps_a × (P_a / P_b)
    P = cours de clôture moyen de la période. Somme des deux effets = variation totale.
    """
    df = spread_frame(isin)
    pa = df.loc[a[0] : a[1]]
    pb = df.loc[b[0] : b[1]]
    bps_a, bps_b = pa["spread_bps"].median(), pb["spread_bps"].median()
    p_a, p_b = pa["close"].mean(), pb["close"].mean()
    if any(pd.isna(x) for x in (bps_a, bps_b, p_a, p_b)) or p_b == 0:
        return {"isin": isin, "bps_a": bps_a, "bps_b": bps_b, "price_a": p_a, "price_b": p_b,
                "price_effect_bps": np.nan, "liquidity_effect_bps": np.nan, "price_share": np.nan}
    counterfactual = bps_a * p_a / p_b
    total = bps_b - bps_a
    price_eff = counterfactual - bps_a
    return {
        "isin": isin,
        "bps_a": bps_a,
        "bps_b": bps_b,
        "price_a": p_a,
        "price_b": p_b,
        "eur_per_share_a": pa["spread_eur_per_share"].median(),
        "eur_per_share_b": pb["spread_eur_per_share"].median(),
        "ticks_a": pa["spread_ticks"].median(),
        "ticks_b": pb["spread_ticks"].median(),
        "total_change_bps": total,
        "price_effect_bps": price_eff,
        "liquidity_effect_bps": bps_b - counterfactual,
        "price_share": price_eff / total if total else np.nan,
    }


def clear_caches() -> None:
    for fn in (tick_series, spread_frame):
        fn.cache_clear()
