"""Événements : calcul du jour de trading et liste des annonces."""
from __future__ import annotations

import pandas as pd

from app import config, etl
from app.analytics import data


def resolve_trading_day(day: str, time: str, days: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Annonce avant 17:30 -> même jour (s'il est ouvré) ; après -> jour de trading suivant."""
    d = pd.Timestamp(day).normalize()
    after_close = bool(time) and time >= config.MARKET_CLOSE
    i = days.searchsorted(d, side="right" if after_close else "left")
    return days[i] if i < len(days) else None


def events_df(isin: str | None = None) -> pd.DataFrame:
    ev = etl.load_events().copy()
    if isin:
        ev = ev[ev["isin"] == isin]
    days = data.trading_days()
    tds = []
    for _, row in ev.iterrows():
        td = pd.Timestamp(row["trading_day"]) if row.get("trading_day") else resolve_trading_day(row["date"], row["time"], days)
        tds.append(td)
    ev["trading_day"] = tds
    return ev.dropna(subset=["trading_day"]).sort_values("trading_day").reset_index(drop=True)


def get_event(event_id: str) -> dict | None:
    ev = events_df()
    row = ev[ev["event_id"] == event_id]
    return None if row.empty else row.iloc[0].to_dict()


def event_payload(row: dict) -> dict:
    """Bloc "event" de l'impact card."""
    time = row.get("time") or "00:00"
    return {
        "event_id": row["event_id"],
        "type": row["type"],
        "title": row["title"],
        # heure inconnue (non vérifiée) -> null plutôt qu'un faux minuit
        "published_at": pd.Timestamp(f"{row['date']} {time}").tz_localize(config.TZ).isoformat() if row.get("time") else None,
        "trading_day": pd.Timestamp(row["trading_day"]).strftime("%Y-%m-%d"),
        "source_url": row.get("source_url") or None,
    }
