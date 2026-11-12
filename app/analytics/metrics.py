"""Baseline, z-score et anomalies."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import config


def baseline_days(days: pd.DatetimeIndex, day: pd.Timestamp, n: int = config.BASELINE_DAYS) -> pd.DatetimeIndex:
    """Les n jours de trading strictement avant `day`."""
    i = days.searchsorted(day)
    return days[max(0, i - n) : i]


def baseline_at(s: pd.Series, days: pd.DatetimeIndex, day: pd.Timestamp, n: int = config.BASELINE_DAYS) -> tuple[float, float]:
    """(moyenne, écart-type) de s sur les n jours de trading avant `day` (jour exclu)."""
    vals = s.reindex(baseline_days(days, day, n)).dropna()
    if len(vals) < max(3, n // 4):
        return np.nan, np.nan
    return float(vals.mean()), float(vals.std(ddof=1)) if len(vals) > 1 else np.nan


def rolling_baseline(s: pd.Series, n: int = config.BASELINE_DAYS) -> tuple[pd.Series, pd.Series]:
    """Moyenne et écart-type glissants des n jours précédents (jour courant exclu)."""
    minp = max(3, n // 4)
    mean = s.rolling(n, min_periods=minp).mean().shift(1)
    std = s.rolling(n, min_periods=minp).std().shift(1)
    return mean, std


def zscore(value: float, mean: float, std: float) -> float:
    if std is None or np.isnan(std) or std == 0 or np.isnan(value) or np.isnan(mean):
        return np.nan
    return (value - mean) / std


def volume_anomalies(volume: pd.Series, z_min: float = 2.0) -> pd.DataFrame:
    """z-score > z_min (défaut 2) -> medium, > z_min + 1 (défaut 3) -> high."""
    mean, std = rolling_baseline(volume)
    z = (volume - mean) / std
    ratio_ = volume / mean
    out = pd.DataFrame({"z": z, "ratio": ratio_}).dropna()
    out = out[out["z"] > z_min]
    out["severity"] = np.where(out["z"] > z_min + 1, "high", "medium")
    out["type"] = "volume_spike"
    return out


def spread_anomalies(spread: pd.Series, z_min: float = 3.0, ratio_min: float = 1.2) -> pd.DataFrame:
    """z-score > z_min ET spread > ratio_min x baseline -> medium ; z > z_min + 1 ou ratio > 1,25 x ratio_min -> high
    (défauts 3 / 1,2 -> high si z > 4 ou ratio > 1,5). Calibré sur les 174 actions : ~3,7 alertes par action sur 10 mois."""
    mean, std = rolling_baseline(spread)
    ratio_ = spread / mean
    z = (spread - mean) / std
    out = pd.DataFrame({"ratio": ratio_, "z": z}).dropna()
    out = out[(out["z"] > z_min) & (out["ratio"] > ratio_min)]
    out["severity"] = np.where((out["z"] > z_min + 1) | (out["ratio"] > 1.25 * ratio_min), "high", "medium")
    out["type"] = "spread_widening"
    return out
