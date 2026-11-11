"""IR snapshot : rapport court et exportable sur une période."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics import data, events
from app.analytics._util import clean, iso, now_iso, pct, r0, r1, r2
from app.analytics.dashboard import _peer_spread_median
from app.analytics.impact import NotFound, headline_metrics

DISCLAIMER = "Descriptive analysis of historical Xetra trading data. Not investment advice."


def _trend(change: float | None, lower_is_better: bool = False, flat: float = 2.0) -> str:
    if change is None or abs(change) < flat:
        return "flat"
    up = change > 0
    return "up" if up else "down"


def _kpi(label: str, value, unit: str, change: float | None) -> dict:
    return {"label": label, "value": value, "unit": unit, "trend": _trend(change), "change_pct": r1(change)}


def build_report(isin: str, start, end) -> dict:
    if not data.known_isin(isin):
        raise NotFound(f"Unknown ISIN {isin}")
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    days = data.trading_days()
    rng = days[(days >= start) & (days <= end)]
    if len(rng) < 2:
        raise NotFound("Not enough trading days in the requested period")
    # Période précédente de même longueur, pour les tendances
    i0 = days.get_loc(rng[0])
    prev = days[max(0, i0 - len(rng)) : i0]

    status = {"spreads": "real", "ohlc": "missing", "flows": "missing"}
    sp = data.spread_series(isin)
    sp_now, sp_prev = sp.reindex(rng).mean(), sp.reindex(prev).mean() if len(prev) else np.nan

    profile, peers_kpis = [], []
    if data.has_ohlc():
        status["ohlc"] = "real"
        px = data.ohlc(isin)
        v_now, v_prev = px["volume"].reindex(rng).mean(), px["volume"].reindex(prev).mean()
        t_now, t_prev = px["turnover_eur"].reindex(rng).mean(), px["turnover_eur"].reindex(prev).mean()
        profile += [
            _kpi("Avg daily volume", r0(v_now), "shares", pct(v_now, v_prev)),
            _kpi("Avg daily turnover", r0(t_now), "EUR", pct(t_now, t_prev)),
        ]
    profile.append(_kpi("Avg spread (25k EUR)", r1(sp_now), "bps", pct(sp_now, sp_prev)))
    share = data.auction_share_series(isin)
    if not share.empty:
        status["flows"] = "real"
        a_now, a_prev = share.reindex(rng).mean(), share.reindex(prev).mean()
        profile.append(_kpi("Auction share", r2(a_now), "ratio", pct(a_now, a_prev)))

    peer_sp = _peer_spread_median(isin).reindex(rng).mean()
    diff = sp_now - peer_sp
    peers_kpis.append({"label": "Spread vs peers", "value": r1(diff), "unit": "bps", "trend": "better" if diff < 0 else "worse"})

    notable = []
    ev = events.events_df(isin)
    ev = ev[(ev["trading_day"] >= rng[0]) & (ev["trading_day"] <= rng[-1])]
    for _, r in ev.iterrows():
        hm = headline_metrics(isin, pd.Timestamp(r["trading_day"]))
        notable.append(
            {
                "event_id": r["event_id"],
                "date": iso(r["trading_day"]),
                "title": r["title"],
                "volume_ratio": hm["volume_ratio"],
                "price_change_pct": hm["price_change_pct"],
                "spread_change_pct": hm["spread_change_pct"],
            }
        )

    from app.assistant import templates

    report = {
        "stock": data.stock_ref(isin, rng[-1]),
        "period": {"from": iso(rng[0]), "to": iso(rng[-1])},
        "headline": "",
        "sections": [
            {"title": "Trading profile", "kpis": profile, "text": templates.profile_text(profile)},
            {"title": "Peer comparison", "kpis": peers_kpis, "text": templates.peers_text(r1(sp_now), r1(peer_sp), len(data.peers_of(isin)))},
            {"title": "Notable events", "items": notable},
        ],
        "disclaimer": DISCLAIMER,
        "generated_at": now_iso(),
        "export": {"pdf_url": f"/stocks/{isin}/report.pdf"},
        "_data_status": status,
    }
    report = clean(report)

    from app.assistant import summarize_report

    report["headline"] = summarize_report(report)
    return report
