"""Impact card : réaction du marché à un événement (ou à un jour inhabituel).

Stratégie "progressive" : on part du mock, puis on remplace chaque bloc par de vraies valeurs
dès que la source de données existe. `_data_status` indique ce qui est réel ou encore mock.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import config
from app.analytics import data, events, indicators, intraday, metrics
from app.analytics._util import clean, iso, load_mock, nanmedian, now_iso, pct, r0, r1, r2, ratio


class NotFound(KeyError):
    """ISIN, événement ou jour inconnu -> l'API renvoie 404."""


def _spread_block(isin: str, days: pd.DatetimeIndex, td: pd.Timestamp) -> tuple[dict, float, float]:
    sp = data.spread_series(isin)
    ev = sp.get(td, np.nan)
    base, _ = metrics.baseline_at(sp, days, td)
    return {"event": r1(ev), "baseline": r1(base), "change_pct": r1(pct(ev, base))}, ev, base


def _ohlc_blocks(isin: str, days: pd.DatetimeIndex, td: pd.Timestamp, card: dict) -> None:
    px = data.ohlc(isin)
    if td not in px.index:
        raise NotFound(f"No OHLC data for {isin} on {iso(td)}")
    vol = px["volume"].astype(float)
    v_ev = float(vol.at[td])
    v_mean, v_std = metrics.baseline_at(vol, days, td)
    turn = px["turnover_eur"].astype(float)
    t_mean, _ = metrics.baseline_at(turn, days, td)
    i = px.index.get_loc(td)
    prev_close = float(px["close"].iloc[i - 1]) if i > 0 else np.nan
    o, h, l, c = (float(px.at[td, k]) for k in ("open", "high", "low", "close"))

    m = card["metrics"]
    m["volume"] = {"event": r0(v_ev), "baseline": r0(v_mean), "ratio": r2(ratio(v_ev, v_mean)), "z_score": r1(metrics.zscore(v_ev, v_mean, v_std))}
    m["turnover_eur"] = {"event": r0(turn.at[td]), "baseline": r0(t_mean), "ratio": r2(ratio(turn.at[td], t_mean))}
    m["price"] = {
        "prev_close": r2(prev_close),
        "open": r2(o),
        "close": r2(c),
        "change_pct": r1(pct(c, prev_close)),
        "intraday_range_pct": r1((h - l) / prev_close * 100 if prev_close else np.nan),
    }

    # Fenêtre : prix et volume relatif (vs la baseline de l'événement)
    for row in card["window"]:
        d = pd.Timestamp(row["date"])
        row["close"] = r2(px["close"].get(d, np.nan))
        row["volume_ratio"] = r2(ratio(vol.get(d, np.nan), v_mean))

    # Peers : même jour de trading
    peer_ratios, peer_moves = [], []
    for p in data.peers_of(isin):
        ppx = data.ohlc(p)
        if ppx.empty or td not in ppx.index:
            continue
        pm, _ = metrics.baseline_at(ppx["volume"].astype(float), days, td)
        j = ppx.index.get_loc(td)
        if j > 0:
            peer_moves.append(pct(ppx["close"].iloc[j], ppx["close"].iloc[j - 1]))
        peer_ratios.append(ratio(ppx.at[td, "volume"], pm))
    peer_ratio = nanmedian(peer_ratios)
    peer_move = nanmedian(peer_moves)
    own = pct(c, prev_close)
    card["vs_peers"] = {
        "peer_avg_volume_ratio": r2(peer_ratio),
        "peer_avg_price_change_pct": r1(peer_move),
        "excess_return_pct": r1(own - peer_move if own is not None and not np.isnan(peer_move) else np.nan),
    }
    card["technical_context"] = indicators.technical_context(px, td) or card["technical_context"]


def _flows_blocks(isin: str, days: pd.DatetimeIndex, td: pd.Timestamp, card: dict) -> bool:
    f = data.flows(isin)
    day = f[f["date"] == td]
    if day.empty:
        return False
    share = data.auction_share_series(isin)
    s_mean, _ = metrics.baseline_at(share, days, td)
    s_ev = share.get(td, np.nan)
    card["metrics"]["auction_share"] = {"event": r2(s_ev), "baseline": r2(s_mean), "change_pts": r2(s_ev - s_mean)}

    by_p = []
    for p in ("AGENT", "PROP", "MARKET_MAKER"):
        dp = day[day["participant"] == p]
        buy = dp.loc[dp["side"] == "BUY", "volume"].sum()
        sell = dp.loc[dp["side"] == "SELL", "volume"].sum()
        by_p.append({"type": p, "buy": r0(buy), "sell": r0(sell), "net": r0(buy - sell)})
    tot = day["volume"].sum()
    by_m = [{"mode": mo, "share": r2(day.loc[day["mode"] == mo, "volume"].sum() / tot if tot else np.nan)} for mo in ("AGGRESSIVE", "PASSIVE", "AUCTION")]
    card["flows"] = {"by_participant": by_p, "by_mode": by_m}
    return True


def _auction_blocks(isin: str, days: pd.DatetimeIndex, td: pd.Timestamp, card: dict) -> bool:
    """Opening / closing auction depuis les trades (les Flows regroupent toutes les enchères dans AUCTION).
    volume = actions exécutées dans l'enchère ce jour-là, baseline = moyenne des 20 séances précédentes."""
    if not data.has_trades(isin):
        return False
    for kind, key in (("opening", "opening_auction"), ("closing", "closing_auction")):
        s = data.auction_volume_series(isin, kind)
        if td not in s.index:
            return False
        mean, _ = metrics.baseline_at(s, days, td)
        card["metrics"][key] = {"volume": r0(s.at[td]), "baseline": r0(mean), "ratio": r2(ratio(s.at[td], mean))}
    return True


def _build(isin: str, td: pd.Timestamp, event_row: dict | None) -> dict:
    if not data.known_isin(isin):
        raise NotFound(f"Unknown ISIN {isin}")
    days = data.trading_days()
    if td not in days:
        raise NotFound(f"{iso(td)} is not a trading day in the data")

    card = load_mock("impact-card")
    status = {"spreads": "real", "ohlc": "mock", "flows": "mock", "opening_closing_auction": "mock"}

    i = days.get_loc(td)
    base = metrics.baseline_days(days, td)
    card["card_id"] = f"card_{event_row['event_id']}" if event_row else f"card_{isin}_{iso(td)}"
    card["stock"] = {k: v for k, v in data.stock_ref(isin, td).items() if k != "sector"}
    card["event"] = events.event_payload(event_row) if event_row else None
    card["baseline"] = {
        "method": f"{config.BASELINE_DAYS}-day mean before event",
        "from": iso(base[0]) if len(base) else None,
        "to": iso(base[-1]) if len(base) else None,
    }

    # Spreads (réel)
    card["metrics"]["spread_bps"], _, _ = _spread_block(isin, days, td)
    sp = data.spread_series(isin)
    mock_win = {w["offset"]: w for w in card["window"]}
    win = []
    for d in days[max(0, i - config.WINDOW_DAYS) : i + config.WINDOW_DAYS + 1]:
        off = int(days.get_loc(d) - i)
        mw = mock_win.get(off, {})
        win.append({"offset": off, "date": iso(d), "close": mw.get("close"), "volume_ratio": mw.get("volume_ratio"), "spread_bps": r1(sp.get(d, np.nan))})
    card["window"] = win

    if data.has_ohlc():
        _ohlc_blocks(isin, days, td, card)
        status["ohlc"] = "real"
    if data.has_flows() and _flows_blocks(isin, days, td, card):
        status["flows"] = "real"
    if _auction_blocks(isin, days, td, card):
        status["opening_closing_auction"] = "real"
    card["intraday"] = intraday.intraday_block(isin, td, card["event"]["published_at"] if card["event"] else None)
    status["intraday"] = "real" if card["intraday"] else "missing"

    card["_data_status"] = status
    card["generated_at"] = now_iso()
    card["export"] = {
        "pdf_url": f"/events/{event_row['event_id']}/impact-card.pdf" if event_row else f"/days/{isin}/{iso(td)}/impact-card.pdf"
    }

    from app.assistant import summarize_impact_card  # import tardif (évite les imports circulaires)

    card = clean(card)
    card["ai_summary"] = summarize_impact_card(card)
    return card


def build_impact_card(event_id: str) -> dict:
    row = events.get_event(event_id)
    if row is None:
        raise NotFound(f"Unknown event {event_id}")
    return _build(row["isin"], pd.Timestamp(row["trading_day"]), row)


def build_day_card(isin: str, day) -> dict:
    return _build(isin, pd.Timestamp(day).normalize(), None)


def headline_metrics(isin: str, td: pd.Timestamp) -> dict:
    """Petits chiffres pour la liste d'événements (volume_ratio, price_change_pct, spread_change_pct)."""
    days = data.trading_days()
    out: dict = {"volume_ratio": None, "price_change_pct": None, "spread_change_pct": None}
    block, _, _ = _spread_block(isin, days, td)
    out["spread_change_pct"] = block["change_pct"]
    px = data.ohlc(isin) if data.has_ohlc() else pd.DataFrame()
    if not px.empty and td in px.index:
        vol = px["volume"].astype(float)
        vm, _ = metrics.baseline_at(vol, days, td)
        i = px.index.get_loc(td)
        out["volume_ratio"] = r2(ratio(vol.at[td], vm))
        if i > 0:
            out["price_change_pct"] = r1(pct(px["close"].iloc[i], px["close"].iloc[i - 1]))
    return out
