"""Bloc `intraday` de l'impact card : réaction minute par minute autour de l'annonce (mocks/API.md v0.2 §5.1).

- Annonce pendant la séance continue (09:00–17:30, le jour même) : référence = heure de publication.
- Annonce hors séance (avant l'ouverture, après la clôture, week-end) ou « notable day » sans annonce :
  référence = ouverture du `trading_day` (heure de l'opening auction).
- Trades utilisés : on-book Xetra pendant la séance, enchères comprises (volume, VWAP) ;
  `buy_aggressor_share` ne compte que les exécutions avec un côté agresseur connu.
- `None` si aucun trade n'est disponible pour ce jour.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import config
from app.analytics import data
from app.analytics._util import pct, r0, r1, r2, ratio

MINUTES_BEFORE = 30
MINUTES_AFTER = 120
FIRST_WINDOW_MIN = 15
PRICE_HORIZONS = {"after_5min": 5, "after_30min": 30, "after_60min": 60}


def _day_trades(isin: str, day: pd.Timestamp) -> pd.DataFrame:
    t = data.trades(isin)
    if t.empty:
        return t
    return t[t["date"] == day]


def _reference(day_trades: pd.DataFrame, day: pd.Timestamp, published_at: str | None) -> tuple[pd.Timestamp, bool]:
    """(heure de référence, during_session)."""
    if published_at:
        pub = pd.Timestamp(published_at).tz_convert(config.TZ)
        hm = pub.strftime("%H:%M")
        if pub.normalize().tz_localize(None) == day and data.SESSION_OPEN <= hm < data.SESSION_CLOSE:
            return pub, True
    opening = day_trades[day_trades["auction_type"] == "opening"]
    first = opening["ts_local"].iloc[0] if not opening.empty else day_trades["ts_local"].iloc[0]
    return first.floor("min"), False


def _window_volume(day_trades: pd.DataFrame, start: pd.Timestamp, minutes: int) -> float:
    m = (day_trades["ts_local"] >= start) & (day_trades["ts_local"] < start + pd.Timedelta(minutes=minutes))
    return float(day_trades.loc[m, "qty"].sum())


def _first_window(isin: str, day: pd.Timestamp, ref: pd.Timestamp, day_trades: pd.DataFrame) -> dict:
    """Volume des 15 premières minutes vs même créneau horaire sur les 20 séances précédentes."""
    vol = _window_volume(day_trades, ref, FIRST_WINDOW_MIN)
    clock = ref - ref.normalize()  # heure de la journée (Timedelta)
    t = data.trades(isin)
    prev_days = [d for d in pd.DatetimeIndex(sorted(t["date"].unique())) if d < day][-config.BASELINE_DAYS :]
    base_vals = []
    for d in prev_days:
        start = pd.Timestamp(d).tz_localize(config.TZ) + clock
        base_vals.append(_window_volume(t[t["date"] == d], start, FIRST_WINDOW_MIN))
    base = float(np.mean(base_vals)) if len(base_vals) >= max(3, config.BASELINE_DAYS // 4) else np.nan
    return {"volume": r0(vol), "baseline": r0(base), "ratio": r2(ratio(vol, base))}


def _price_changes(day_trades: pd.DataFrame, ref: pd.Timestamp, during_session: bool) -> dict:
    ts, px = day_trades["ts_local"], day_trades["price"]
    if during_session:
        before = px[ts < ref]
        p0 = before.iloc[-1] if not before.empty else np.nan
    else:
        # hors séance : on mesure à partir de l'ouverture (premier prix à/après la référence)
        after = px[ts >= ref]
        p0 = after.iloc[0] if not after.empty else np.nan
    out = {}
    for key, k in PRICE_HORIZONS.items():
        upto = px[ts <= ref + pd.Timedelta(minutes=k)]
        out[key] = r1(pct(upto.iloc[-1], p0)) if not upto.empty else None
    return out


def _minutes(day_trades: pd.DataFrame, ref: pd.Timestamp) -> list[dict]:
    t0 = ref.floor("min")
    offs = ((day_trades["ts_local"] - t0) // pd.Timedelta(minutes=1)).astype(int)
    tr = day_trades.assign(offset=offs)
    tr = tr[(tr["offset"] >= -MINUTES_BEFORE) & (tr["offset"] <= MINUTES_AFTER)]
    g = tr.groupby("offset")
    qty = g["qty"].sum()
    notional = g["notional_eur"].sum()
    buy = tr[tr["side"] == "BUY"].groupby("offset")["qty"].sum()
    sell = tr[tr["side"] == "SELL"].groupby("offset")["qty"].sum()
    rows, cum = [], 0.0
    for k in range(-MINUTES_BEFORE, MINUTES_AFTER + 1):
        v = float(qty.get(k, 0.0))
        cum += v
        b, s = float(buy.get(k, 0.0)), float(sell.get(k, 0.0))
        rows.append(
            {
                "offset_min": k,
                "time": (t0 + pd.Timedelta(minutes=k)).strftime("%H:%M"),
                "vwap": r2(notional.get(k) / v) if v else None,  # prix à 2 décimales (convention API)
                "volume": r0(v),
                "cum_volume": r0(cum),
                "buy_aggressor_share": r2(b / (b + s)) if (b + s) else None,
            }
        )
    return rows


def intraday_block(isin: str, day: pd.Timestamp, published_at: str | None) -> dict | None:
    """Bloc `intraday` (None si pas de trades ce jour-là)."""
    dt = _day_trades(isin, day)
    if dt.empty:
        return None
    ref, during = _reference(dt, day, published_at)
    return {
        "reference_time": ref.isoformat(timespec="seconds"),
        "during_session": during,
        "minutes": _minutes(dt, ref),
        "first_15min": _first_window(isin, day, ref, dt),
        "price_change_pct": _price_changes(dt, ref, during),
    }
