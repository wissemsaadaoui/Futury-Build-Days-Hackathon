"""Comparaison d'événements du même type + liste des événements d'une action."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics import data, events, metrics
from app.analytics._util import clean, iso, r1, r2
from app.analytics.impact import NotFound, headline_metrics


def list_events(isin: str) -> dict:
    if not data.known_isin(isin):
        raise NotFound(f"Unknown ISIN {isin}")
    ev = events.events_df(isin)
    out = []
    for _, r in ev.iterrows():
        td = pd.Timestamp(r["trading_day"])
        hm = headline_metrics(isin, td)
        out.append(
            {
                "event_id": r["event_id"],
                "date": r["date"],
                "time": r["time"],
                "trading_day": iso(td),
                "type": r["type"],
                "title": r["title"],
                "source_url": r["source_url"] or None,
                "has_impact_card": True,
                "headline_metric": hm,
            }
        )
    types = ["quarterly_results", "annual_results", "ad_hoc", "dividend", "press_release", "m_and_a", "agm", "index_change"]
    return clean({"isin": isin, "events": out, "event_types": types})


def _auction_change(isin: str, td: pd.Timestamp) -> float | None:
    share = data.auction_share_series(isin)
    if share.empty or td not in share.index:
        return None
    base, _ = metrics.baseline_at(share, data.trading_days(), td)
    return r2(share.at[td] - base)


def compare_events(event_type: str, index: str, start, end) -> dict:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    ev = events.events_df()
    ev = ev[(ev["type"] == event_type) & (ev["trading_day"] >= start) & (ev["trading_day"] <= end)]
    rows = []
    for _, r in ev.iterrows():
        td = pd.Timestamp(r["trading_day"])
        idx = data.index_on(r["isin"], td)
        if index and index.upper() != "ALL" and idx != index.upper():
            continue
        hm = headline_metrics(r["isin"], td)
        rows.append(
            {
                "event_id": r["event_id"],
                "isin": r["isin"],
                "name": data.name_of(r["isin"]),
                "date": iso(td),
                "volume_ratio": hm["volume_ratio"],
                "price_change_pct": hm["price_change_pct"],
                "spread_change_pct": hm["spread_change_pct"],
                "auction_share_change_pts": _auction_change(r["isin"], td),
            }
        )

    def med(key: str, absval: bool = False) -> float | None:
        vals = [abs(x[key]) if absval else x[key] for x in rows if x[key] is not None]
        return float(np.median(vals)) if vals else None

    return clean(
        {
            "filter": {"type": event_type, "index": index.upper(), "from": iso(start), "to": iso(end)},
            "summary": {
                "n_events": len(rows),
                "median_volume_ratio": r2(med("volume_ratio")),
                "median_abs_price_change_pct": r1(med("price_change_pct", absval=True)),
                "median_spread_change_pct": r1(med("spread_change_pct")),
            },
            "events": rows,
        }
    )
