"""IR snapshot : rapport court et exportable sur une période."""
from __future__ import annotations

import pandas as pd

from app import config
from app.analytics import data, events
from app.analytics._util import clean, iso, now_iso, pct, r0, r1, r2
from app.analytics.dashboard import _peer_spread_median
from app.analytics.impact import NotFound, headline_metrics

DISCLAIMER = "Descriptive analysis of historical Xetra trading data. Not investment advice."


# Base de comparaison des KPIs (champ change_basis)
PREVIOUS_PERIOD = "previous_period"  # même nombre de séances juste avant la période
FIRST_HALF = "first_half"            # 2e moitié de la période vs 1re moitié (pas assez de données avant)
BASIS_TEXT = {PREVIOUS_PERIOD: "vs previous period", FIRST_HALF: "vs first half of the period"}


def _trend(change: float | None, flat: float = 2.0) -> str | None:
    """None si la variation est inconnue : on n'affiche jamais « flat » faute de données."""
    if change is None:
        return None
    if abs(change) < flat:
        return "flat"
    return "up" if change > 0 else "down"


def _change(s: pd.Series, rng: pd.DatetimeIndex, prev: pd.DatetimeIndex) -> tuple[float | None, str | None]:
    """Variation (%) de la moyenne de `s` et sa base : période précédente si elle a assez de données,
    sinon 2e moitié vs 1re moitié de la période. (None, None) si aucune des deux n'est calculable."""
    if s is None or s.empty:
        return None, None
    prev_vals = s.reindex(prev).dropna()
    if len(prev) and len(prev_vals) >= max(3, len(prev) // 4):
        c = pct(s.reindex(rng).mean(), prev_vals.mean())
        if c is not None:
            return c, PREVIOUS_PERIOD
    half = len(rng) // 2
    first, second = s.reindex(rng[:half]).dropna(), s.reindex(rng[half:]).dropna()
    if len(first) and len(second):
        c = pct(second.mean(), first.mean())
        if c is not None:
            return c, FIRST_HALF
    return None, None


def _kpi(label: str, value, unit: str, change: tuple[float | None, str | None]) -> dict:
    c, basis = change
    return {"label": label, "value": value, "unit": unit, "trend": _trend(c), "change_pct": r1(c), "change_basis": basis}


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
    sp_now = sp.reindex(rng).mean()

    profile, peers_kpis = [], []
    if data.has_ohlc():
        status["ohlc"] = "real"
        px = data.ohlc(isin)
        vol, turn = px["volume"].astype(float), px["turnover_eur"].astype(float)
        profile += [
            _kpi("Avg daily volume", r0(vol.reindex(rng).mean()), "shares", _change(vol, rng, prev)),
            _kpi("Avg daily turnover", r0(turn.reindex(rng).mean()), "EUR", _change(turn, rng, prev)),
        ]
    profile.append(_kpi("Avg spread (25k EUR)", r1(sp_now), "bps", _change(sp, rng, prev)))
    share = data.auction_share_series(isin)
    if not share.empty:
        status["flows"] = "real"
        profile.append(_kpi("Auction share", r2(share.reindex(rng).mean()), "ratio", _change(share, rng, prev)))

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
            {"title": "Peer comparison", "kpis": peers_kpis, "text": templates.peers_text(r1(sp_now), r1(peer_sp), len(data.peers_of(isin)), config.SECTORS.get(isin))},
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
