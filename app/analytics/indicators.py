"""Indicateurs techniques – usage DESCRIPTIF uniquement (jamais de prédiction de prix)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_indicators(close: pd.Series) -> pd.DataFrame:
    """EMA20, EMA50, MACD(12, 26, 9) sur une série de clôtures."""
    c = close.astype(float)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return pd.DataFrame(
        {
            "ema_20": c.ewm(span=20, adjust=False).mean(),
            "ema_50": c.ewm(span=50, adjust=False).mean(),
            "macd": macd,
            "macd_signal": signal,
            "macd_hist": macd - signal,
        },
        index=close.index,
    )


def support_resistance(
    high: pd.Series,
    low: pd.Series,
    last_close: float,
    window: int = 5,
    tol: float = 0.015,
    min_touches: int = 2,
    top: int = 3,
) -> dict:
    """Niveaux où le prix a rebondi plusieurs fois (pivots locaux regroupés à `tol` près)."""
    h, l = high.to_numpy(float), low.to_numpy(float)
    pivots: list[float] = []
    for i in range(window, len(h) - window):
        if h[i] == np.nanmax(h[i - window : i + window + 1]):
            pivots.append(h[i])
        if l[i] == np.nanmin(l[i - window : i + window + 1]):
            pivots.append(l[i])

    levels: list[dict] = []
    for p in sorted(pivots):
        if levels and abs(p - levels[-1]["price"]) / levels[-1]["price"] < tol:
            lv = levels[-1]
            lv["touches"] += 1
            lv["price"] = lv["price"] + (p - lv["price"]) / lv["touches"]
        else:
            levels.append({"price": float(p), "touches": 1})

    strong = [lv for lv in levels if lv["touches"] >= min_touches]
    support = sorted((lv for lv in strong if lv["price"] < last_close), key=lambda lv: -lv["price"])[:top]
    resistance = sorted((lv for lv in strong if lv["price"] > last_close), key=lambda lv: lv["price"])[:top]
    fmt = lambda lst: [{"price": round(lv["price"], 2), "touches": lv["touches"]} for lv in lst]
    return {"support": fmt(support), "resistance": fmt(resistance)}


def technical_context(px: pd.DataFrame, day: pd.Timestamp, after_days: int = 5) -> dict | None:
    """Contexte technique autour d'un jour : tendance, momentum avant/après, niveau cassé."""
    if px.empty or day not in px.index:
        return None
    ind = add_indicators(px["close"])
    i = px.index.get_loc(day)
    if i < 1:
        return None
    prev = px.index[i - 1]
    after = px.index[min(i + after_days, len(px) - 1)]
    sr = support_resistance(px["high"].iloc[:i], px["low"].iloc[:i], float(px["close"].iloc[i - 1]))
    c_prev, c_day = float(px.at[prev, "close"]), float(px.at[day, "close"])
    broke = None
    for lv in sr["resistance"]:
        if c_prev <= lv["price"] < c_day:
            broke = {"type": "resistance", "price": lv["price"]}
            break
    if broke is None:
        for lv in sr["support"]:
            if c_day < lv["price"] <= c_prev:
                broke = {"type": "support", "price": lv["price"]}
                break
    return {
        "trend_before": "above_ema50" if c_prev >= ind.at[prev, "ema_50"] else "below_ema50",
        "macd_before": "bullish" if ind.at[prev, "macd_hist"] >= 0 else "bearish",
        "macd_after": "bullish" if ind.at[after, "macd_hist"] >= 0 else "bearish",
        "broke_level": broke,
    }
