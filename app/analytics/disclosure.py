"""Bloc `pre_disclosure_activity` des impact cards `voting_rights` (notifications WpHG art. 40).

Le franchissement de seuil PRÉCÈDE la notification : l'investisseur a jusqu'à 4 jours de bourse pour notifier
l'émetteur, qui publie ensuite. On regarde donc les anomalies et alertes des 7 séances AVANT le jour de publication
(jour de publication exclu, même si la notification tombe en cours de séance).

Ne jamais affirmer que ce trading EST celui de l'investisseur notifié : il « may coincide with ».
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics import alerts, data, metrics
from app.analytics._util import iso, r0, r2

PRE_DISCLOSURE_SESSIONS = 7
TYPE_LABEL = {
    "volume_spike": "volume spike",
    "spread_widening": "spread widening",
    "large_trade": "large single execution",
    "aggressor_sweep": "aggressor sweep",
    "net_flow": "unusual net flow",
    "auction_spike": "large closing auction",
    "price_move": "price move vs peers",
    "level_break": "support/resistance break",
}


def window_before(day: pd.Timestamp, n: int = PRE_DISCLOSURE_SESSIONS) -> pd.DatetimeIndex:
    """Les n séances strictement avant `day` (le jour de publication est exclu)."""
    return metrics.baseline_days(data.trading_days(), pd.Timestamp(day).normalize(), n)


def pre_disclosure_activity(isin: str, published_day: pd.Timestamp, n: int = PRE_DISCLOSURE_SESSIONS) -> dict | None:
    """Jours avec anomalies/alertes dans les n séances avant la publication ; None si rien d'inhabituel."""
    from app.analytics.dashboard import _anomaly_rows  # import tardif (dashboard importe impact)

    win = window_before(published_day, n)
    if len(win) == 0:
        return None
    px = data.ohlc(isin)
    vol = px["volume"].astype(float) if not px.empty else None
    rows = _anomaly_rows(isin, data.spread_series(isin), vol, win[0], win[-1])
    rows = [r for r in rows if pd.Timestamp(r["date"]) in win]  # garde-fou : uniquement AVANT la publication
    if not rows:
        return None

    vr = alerts.day_moves(isin)["volume_ratio"] if vol is not None else pd.Series(dtype=float)
    nf = alerts.net_flows(isin)
    agent = nf[nf["participant"] == "AGENT"].set_index("date")["net_eur"] if not nf.empty else pd.Series(dtype=float)
    by_day: dict[str, list[str]] = {}
    for r in rows:
        by_day.setdefault(r["date"], [])
        if r["type"] not in by_day[r["date"]]:
            by_day[r["date"]].append(r["type"])

    days = []
    for d in sorted(by_day):
        ts = pd.Timestamp(d)
        days.append({
            "date": d,
            "anomaly_types": by_day[d],
            "volume_ratio": r2(vr.get(ts, np.nan)),
            "agent_net_flow_eur": r0(agent.get(ts, np.nan)),
        })
    kinds = sorted({t for v in by_day.values() for t in v}, key=list(TYPE_LABEL).index)
    k = len(days)
    summary = (
        f"Unusual activity in the {len(win)} sessions before the disclosure: {k} flagged session{'s' if k > 1 else ''} "
        f"({', '.join(TYPE_LABEL.get(t, t) for t in kinds)}). This trading may coincide with the position change "
        f"reported in the notification; the data do not show who traded."
    )
    return {
        "window": {"from": iso(win[0]), "to": iso(win[-1]), "sessions": len(win)},
        "days": days,
        "summary": summary,
    }
