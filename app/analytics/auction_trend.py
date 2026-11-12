"""Auction share trend (dashboard, champ `auction_trend`).

- `auction_share` : volume AUCTION ÷ volume total des Flows (lignes d'un seul jour, date = REPORTED_FLOW_DATES).
  Les Flows comptent achat + vente au numérateur comme au dénominateur : le ratio n'est pas doublé.
  Jour censuré (< 7 exécutions) ou publié agrégé sur plusieurs jours : pas de ligne journalière -> null (jamais 0).
- `baseline_20d` : moyenne mobile des 20 dernières séances (jour inclus), calculée sur tout l'historique ;
  null tant qu'il n'y a pas 20 valeurs.
- `opening` / `intraday` / `closing` : volume de chaque enchère planifiée, lu dans les trades horodatés
  (une exécution par enchère) ÷ volume du jour (OHLC). Jamais déduit des Flows, qui regroupent toutes les enchères.
  Leur somme peut rester sous `auction_share` : les Flows comptent aussi les enchères non planifiées
  (interruptions de volatilité).
Parts entre 0 et 1, arrondies à 2 décimales (convention du contrat API).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics import data
from app.analytics._util import iso, r2

WINDOW = 20
PARTS = (("opening", "opening"), ("intraday", "midday"), ("closing", "closing"))


def rolling_share(share: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """Moyenne mobile 20 séances de la part d'enchères ; un jour sans valeur ne compte pas pour 0."""
    if share.empty:
        return pd.Series(dtype=float)
    return share.reindex(days).rolling(WINDOW, min_periods=WINDOW).mean()


def part_shares(isin: str) -> dict[str, pd.Series]:
    """{opening, intraday, closing} -> part du volume du jour (0–1), {} si les trades ne couvrent pas l'action."""
    px = data.ohlc(isin)
    if px.empty or not data.has_trades(isin):
        return {}
    vol = px["volume"].astype(float)
    out = {}
    for key, kind in PARTS:
        v = data.auction_volume_series(isin, kind)
        v.index = pd.DatetimeIndex(v.index)
        den = vol.reindex(v.index)
        out[key] = (v / den.where(den > 0)).dropna()
    return out


def build_auction_trend(isin: str, rng: pd.DatetimeIndex) -> dict | None:
    """Bloc `auction_trend` du dashboard sur les jours `rng` ; None sans Flows."""
    share = data.auction_share_series(isin)
    if share.empty or len(rng) == 0:
        return None
    base = rolling_share(share, data.trading_days())
    parts = part_shares(isin)
    series = []
    for d in rng:
        row = {"date": iso(d), "auction_share": r2(share.get(d, np.nan)), "baseline_20d": r2(base.get(d, np.nan))}
        for key, s in parts.items():
            row[key] = r2(s.get(d, np.nan))
        series.append(row)

    st = trend_stats(isin, rng)
    mark = lambda m: None if m is None else {k: (v if k == "date" else r2(v)) for k, v in m.items()}
    return {
        "window": WINDOW,
        "has_parts": bool(parts),
        "series": series,
        "start": mark(st["start"]),            # première moyenne 20 séances disponible dans la période
        "latest": mark(st["latest"]),          # dernière moyenne 20 séances de la période
        "change_vs_start": r2(st["change"]),   # latest − start, en part (0.05 = +5 points)
        "peak": mark(st["peak"]),              # jour le plus haut de la période (valeur journalière)
    }


def trend_stats(isin: str, rng: pd.DatetimeIndex) -> dict:
    """Valeurs NON arrondies (0–1) : start / latest (moyenne 20 séances), change, peak (+ parts du jour du pic)."""
    share = data.auction_share_series(isin)
    out = {"start": None, "latest": None, "change": None, "peak": None}
    if share.empty or len(rng) == 0:
        return out
    base_in = rolling_share(share, data.trading_days()).reindex(rng).dropna()
    if len(base_in):
        out["start"] = {"date": iso(base_in.index[0]), "value": float(base_in.iloc[0])}
        out["latest"] = {"date": iso(base_in.index[-1]), "value": float(base_in.iloc[-1])}
    if len(base_in) > 1:
        out["change"] = float(base_in.iloc[-1] - base_in.iloc[0])
    in_rng = share.reindex(rng).dropna()
    if len(in_rng):
        day = in_rng.idxmax()
        out["peak"] = {"date": iso(day), "value": float(in_rng.loc[day])}
        for key, s in part_shares(isin).items():
            v = s.get(day, np.nan)
            out["peak"][key] = None if pd.isna(v) else float(v)
    return out
