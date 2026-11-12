"""Phrase clé du dashboard (point 8) : générée par RÈGLES à partir des données, jamais par le LLM.

Compare le premier et le dernier mois des données (2026 : janvier et octobre) :
- spread médian du titre à 25 000 € (bps, Impact_bps du XLM), médiane des valeurs journalières du mois ;
- médiane des peers (médiane journalière des peers disponibles, puis médiane du mois) ;
- médiane du SDAX (membres de l'indice à la date, même méthode), pour le contexte ;
- position du titre vs les peers (au-dessus / en dessous) au début et à la fin ;
- décomposition prix / liquidité (pricing.decompose).

Texte validé par l'équipe :
  "pbb's cost to trade €25k rose from 54.3 to 97.4 bps (Jan–Oct), moving from below to above its peers' median."
Chaque mot variable (verbe, chiffres, mois, position) vient du calcul.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from app import config, etl
from app.analytics import data, pricing
from app.analytics._util import r1



@lru_cache(maxsize=1)
def _index_daily_median() -> dict[str, pd.Series]:
    """Spread médian journalier des membres de chaque indice À LA DATE (DAX / MDAX / SDAX)."""
    x = etl.load_xlm()
    x = x[x["notional"] == config.REF_NOTIONAL]
    if x.empty:
        return {}
    wide = x.pivot_table(index="date", columns="isin", values="impact_bps")
    idx = x.pivot_table(index="date", columns="isin", values="index", aggfunc="first").reindex_like(wide)
    return {name: wide.where(idx == name).median(axis=1, skipna=True) for name in ("DAX", "MDAX", "SDAX")}


def _month_median(s: pd.Series, month: pd.Period) -> float:
    if s is None or s.empty:
        return np.nan
    v = s[s.index.to_period("M") == month]
    return float(v.median()) if v.notna().any() else np.nan


def _position(own: float, peers: float) -> str | None:
    if np.isnan(own) or np.isnan(peers):
        return None
    return "above" if own > peers else "below"


def build_key_finding(isin: str) -> dict | None:
    """{text, numbers} ; None si les données ne permettent pas une phrase vraie."""
    from app.analytics.dashboard import _peer_spread_median

    days = data.trading_days()
    if len(days) == 0:
        return None
    first, last = days[0].to_period("M"), days[-1].to_period("M")
    if first == last:
        return None
    own = data.spread_series(isin)
    peers = _peer_spread_median(isin)
    index_name = data.index_on(isin, days[-1])
    index_series = _index_daily_median().get(index_name) if index_name else None

    a, b = _month_median(own, first), _month_median(own, last)
    pa, pb = _month_median(peers, first), _month_median(peers, last)
    if any(np.isnan(v) for v in (a, b)):
        return None
    pos_a, pos_b = _position(a, pa), _position(b, pb)
    who = data.short_name(isin)
    peers_word = "its peers' median" if data.peer_basis(isin) == "manual" else "its index peers' median"
    verb = "rose" if b > a else "fell"
    months = f"{days[0]:%b}–{days[-1]:%b}"
    text = f"{who}'s cost to trade €25k {verb} from {r1(a):.1f} to {r1(b):.1f} bps ({months})"
    if pos_a and pos_b:
        if pos_a != pos_b:
            text += f", moving from {pos_a} to {pos_b} {peers_word}."
        else:
            text += f", staying {pos_b} {peers_word}."
    else:
        text += "."

    first_range = (str(days[days.to_period("M") == first][0].date()), str(days[days.to_period("M") == first][-1].date()))
    last_range = (str(days[days.to_period("M") == last][0].date()), str(days[days.to_period("M") == last][-1].date()))
    dec = pricing.decompose(isin, first_range, last_range)
    share = dec.get("price_share")
    # Répartition prix / liquidité lisible seulement si les deux effets vont dans le sens de la variation (0–100 %) ;
    # sinon (petite variation, effets opposés) elle donnerait par ex. 315 % / −215 % : on ne l'affiche pas.
    if share is not None and not np.isnan(share) and not 0 <= share <= 1:
        share = None
    numbers = {
        "metric": "median spread for a EUR 25,000 round trip (bps, Xetra XLM)",
        "first_month": str(first),
        "last_month": str(last),
        "own_first_bps": r1(a),
        "own_last_bps": r1(b),
        "peers_median_first_bps": r1(pa),
        "peers_median_last_bps": r1(pb),
        "position_first": pos_a,
        "position_last": pos_b,
        "index": index_name,
        "index_median_first_bps": r1(_month_median(index_series, first)) if index_series is not None else None,
        "index_median_last_bps": r1(_month_median(index_series, last)) if index_series is not None else None,
        "change_bps": r1(b - a),
        "price_effect_pct": r1(share * 100) if share is not None and not np.isnan(share) else None,
        "liquidity_effect_pct": r1((1 - share) * 100) if share is not None and not np.isnan(share) else None,
        "n_peers": data.n_peers(isin),
    }
    return {"text": text, "numbers": numbers}
