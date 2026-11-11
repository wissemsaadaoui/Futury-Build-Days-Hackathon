"""Part A – Dashboard : l'état normal du trading dans le temps."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics import alerts, data, events, indicators, metrics, pricing
from app.analytics._util import clean, iso, load_mock, pct, r0, r1, r2, ratio


def _peer_spread_median(isin: str) -> pd.Series:
    cols = [data.spread_series(p) for p in data.peers_of(isin)]
    cols = [c for c in cols if not c.empty]
    if not cols:
        return pd.Series(dtype=float)
    return pd.concat(cols, axis=1).median(axis=1, skipna=True)


def _event_by_day(isin: str) -> dict[pd.Timestamp, str]:
    ev = events.events_df(isin)
    return {pd.Timestamp(r["trading_day"]): r["event_id"] for _, r in ev.iterrows()}


def _anomaly_rows(isin: str, spread: pd.Series, volume: pd.Series | None, start, end) -> list[dict]:
    ev_day = _event_by_day(isin)
    frames = [metrics.spread_anomalies(spread)]
    if volume is not None:
        frames.append(metrics.volume_anomalies(volume))
    rows = []
    for f in frames:
        f = f[(f.index >= start) & (f.index <= end)]
        for d, r in f.iterrows():
            if r["type"] == "volume_spike":
                desc = f"Volume {r['ratio']:.1f}x above 20-day baseline"
                value = r2(r["ratio"])
            else:
                desc = f"Spread {r['ratio']:.1f}x its 20-day baseline"
                value = r2(r["ratio"])
            rows.append(
                {"date": iso(d), "type": r["type"], "severity": r["severity"], "value": value, "description": desc,
                 "linked_event_id": ev_day.get(pd.Timestamp(d)), "detail_url": alerts.detail_url(isin, d, ev_day.get(pd.Timestamp(d)))}
            )
    if volume is not None:  # alertes sur les exécutions (trades, Flows, enchères) : seulement avec l'OHLC (ADTV)
        for a in alerts.alert_rows(isin, pd.Timestamp(start), pd.Timestamp(end), ev_day):
            a["date"] = iso(a["date"])
            a["value"] = r2(a["value"])
            if "notional_eur" in a:
                a["notional_eur"] = r0(a["notional_eur"])
            if "level_price" in a:
                a["level_price"] = r2(a["level_price"])
            rows.append(a)
    return sorted(rows, key=lambda x: (x["date"], x["type"]))


def build_dashboard(isin: str, start, end) -> dict:
    from app.analytics.impact import NotFound

    if not data.known_isin(isin):
        raise NotFound(f"Unknown ISIN {isin}")
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    days = data.trading_days()
    rng = days[(days >= start) & (days <= end)]
    if len(rng) == 0:
        raise NotFound("No trading days in the requested period")

    dash = load_mock("dashboard")
    status = {"spreads": "real", "ohlc": "mock", "flows": "mock"}
    dash["stock"] = data.stock_ref(isin, rng[-1])
    dash["period"] = {"from": iso(rng[0]), "to": iso(rng[-1])}

    sp = data.spread_series(isin)
    peer_sp = _peer_spread_median(isin)
    sp_in = sp.reindex(rng)
    peer_in = peer_sp.reindex(rng)
    k = dash["kpis"]
    k["avg_spread_bps"] = r1(sp_in.mean())
    k["vs_peers"]["spread_diff_bps"] = r1(sp_in.mean() - peer_in.mean())

    if data.has_ohlc():
        status["ohlc"] = "real"
        px = data.ohlc(isin)
        vol = px["volume"].astype(float)
        vmean, _ = metrics.rolling_baseline(vol)
        ind = indicators.add_indicators(px["close"])
        share = data.auction_share_series(isin)
        if data.has_flows():
            status["flows"] = "real"
        spf = pricing.spread_frame(isin)
        series = []
        for d in rng:
            if d not in px.index:
                continue
            row = px.loc[d]
            series.append(
                {
                    "date": iso(d),
                    "open": r2(row["open"]), "high": r2(row["high"]), "low": r2(row["low"]), "close": r2(row["close"]),
                    "volume": r0(row["volume"]), "turnover_eur": r0(row["turnover_eur"]),
                    "volume_ratio": r2(ratio(row["volume"], vmean.get(d))),
                    "spread_bps": r1(sp.get(d, np.nan)),
                    "spread_eur": r1(spf["spread_eur"].get(d, np.nan)),        # coût aller-retour pour 25 000 € (€)
                    "spread_ticks": r1(spf["spread_ticks"].get(d, np.nan)),    # coût par action en ticks (null sans trades)
                    "auction_share": r2(share.get(d, np.nan)) if not share.empty else None,
                    "ema_20": r2(ind.at[d, "ema_20"]), "ema_50": r2(ind.at[d, "ema_50"]),
                    "macd": round(float(ind.at[d, "macd"]), 3), "macd_signal": round(float(ind.at[d, "macd_signal"]), 3),
                    "macd_hist": round(float(ind.at[d, "macd_hist"]), 3),
                    "anomaly": False,
                }
            )
        dash["series"] = series

        # Peers : médiane du volume_ratio et de l'auction_share
        p_ratio, p_share = [], []
        for p in data.peers_of(isin):
            ppx = data.ohlc(p)
            if ppx.empty:
                continue
            pv = ppx["volume"].astype(float)
            pm, _ = metrics.rolling_baseline(pv)
            p_ratio.append(pv / pm)
            ps = data.auction_share_series(p)
            if not ps.empty:
                p_share.append(ps)
        med = lambda lst: pd.concat(lst, axis=1).median(axis=1) if lst else pd.Series(dtype=float)
        pr, psh = med(p_ratio), med(p_share)
        dash["peers_series"] = [
            {"date": iso(d), "volume_ratio": r2(pr.get(d, np.nan)), "spread_bps": r1(peer_sp.get(d, np.nan)), "auction_share": r2(psh.get(d, np.nan)) if not psh.empty else None}
            for d in rng
        ]

        v_in = vol.reindex(rng)
        t_in = px["turnover_eur"].astype(float).reindex(rng)
        k["avg_daily_volume"] = r0(v_in.mean())
        k["avg_daily_turnover_eur"] = r0(t_in.mean())
        k["avg_auction_share"] = r2(share.reindex(rng).mean()) if not share.empty else None
        closes = px["close"].reindex(rng).dropna()
        k["price_change_pct"] = r1(pct(closes.iloc[-1], closes.iloc[0])) if len(closes) > 1 else None
        own_ratio = (vol / vmean).reindex(rng).mean()
        k["vs_peers"]["volume_ratio"] = r2(ratio(own_ratio, pr.reindex(rng).mean())) if not pr.empty else None
        k["vs_peers"]["auction_share_diff"] = r2(share.reindex(rng).mean() - psh.reindex(rng).mean()) if not share.empty and not psh.empty else None

        upto = px[px.index <= rng[-1]]
        dash["support_resistance"] = indicators.support_resistance(upto["high"], upto["low"], float(upto["close"].iloc[-1]))
        anomalies = _anomaly_rows(isin, sp, vol, rng[0], rng[-1])
    else:
        # Pas encore d'OHLC : on garde la structure mock, avec les vrais spreads aux dates présentes
        for row in dash["series"]:
            row["spread_bps"] = r1(sp.get(pd.Timestamp(row["date"]), np.nan)) if pd.Timestamp(row["date"]) in sp.index else row["spread_bps"]
        for row in dash["peers_series"]:
            d = pd.Timestamp(row["date"])
            if d in peer_sp.index:
                row["spread_bps"] = r1(peer_sp.get(d))
        anomalies = _anomaly_rows(isin, sp, None, rng[0], rng[-1])

    dash["anomalies"] = anomalies
    flagged = {a["date"] for a in anomalies}
    for row in dash["series"]:
        row["anomaly"] = row["date"] in flagged
    k["anomaly_days"] = len(flagged)
    dash["_data_status"] = status
    return clean(dash)
