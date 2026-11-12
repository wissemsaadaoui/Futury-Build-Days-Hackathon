"""Alertes sur les exécutions (mocks/API.md v0.2 §3 et §5.2) : large_trade, aggressor_sweep, net_flow, auction_spike.

Les données décrivent des EXÉCUTIONS on-book, pas des investisseurs : aucun texte ne dit « an investor ».
On écrit « a single execution », « aggressive buy orders », « agency flow ».
Seuils : app/config.py (ALERT_*). ADTV = moyenne du turnover_eur (OHLC) des 30 séances précédentes.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from app import config
from app.analytics import data, indicators, metrics, thresholds

PARTICIPANT_LABEL = {"AGENT": "Agency flow (orders on behalf of clients)", "PROP": "Proprietary trading flow"}
ALERT_TYPES = ("large_trade", "aggressor_sweep", "net_flow", "auction_spike", "price_move", "level_break")


def _eur(x: float) -> str:
    """640000 -> 'EUR 640k', 2_300_000 -> 'EUR 2.3m'."""
    x = abs(float(x))
    return f"EUR {x / 1e6:.1f}m" if x >= 1e6 else f"EUR {x / 1e3:.0f}k"


def _threshold_eur(adtv: float, share: float | None = None) -> float:
    """Seuil d'une exécution (ou d'une rafale) : >= part de l'ADTV, OU >= ALERT_LARGE_TRADE_EUR s'il est défini
    -> le plus bas des deux. Sans ADTV ni seuil absolu : inf (pas d'alerte)."""
    share = config.ALERT_LARGE_TRADE_ADTV_SHARE if share is None else share
    cands = []
    if config.ALERT_LARGE_TRADE_EUR:
        cands.append(config.ALERT_LARGE_TRADE_EUR)
    if adtv is not None and not np.isnan(adtv) and adtv > 0:
        cands.append(share * adtv)
    return min(cands) if cands else np.inf


def _severity(value: float, threshold: float) -> str:
    return "high" if value >= config.ALERT_HIGH_FACTOR * threshold else "medium"


def _with_adtv(isin: str, df: pd.DataFrame, share: float | None = None) -> pd.DataFrame:
    adtv = data.adtv_series(isin)
    out = df.copy()
    out["adtv"] = out["date"].map(adtv) if not adtv.empty else np.nan
    out["threshold"] = [_threshold_eur(a, share) for a in out["adtv"]]
    return out


# ---------- large_trade ----------
def _th(isin: str) -> dict[str, float]:
    return thresholds.current(isin)


def large_trades(isin: str) -> pd.DataFrame:
    """Une ligne par jour : la plus grosse exécution continue au-dessus du seuil (+ nombre d'exécutions au-dessus)."""
    return _large_trades(isin, _th(isin)["large_trade_adtv_pct"] / 100)


@lru_cache(maxsize=64)
def _large_trades(isin: str, share: float) -> pd.DataFrame:
    t = data.continuous_trades(isin)
    cols = ["date", "time", "side", "notional_eur", "adtv", "n_above"]
    if t.empty:
        return pd.DataFrame(columns=cols)
    t = _with_adtv(isin, t[["date", "ts_local", "side", "notional_eur"]], share)
    hit = t[t["notional_eur"] >= t["threshold"]]
    if hit.empty:
        return pd.DataFrame(columns=cols)
    n_above = hit.groupby("date").size()
    top = hit.sort_values("notional_eur", ascending=False).drop_duplicates("date").sort_values("date")
    top = top.assign(time=top["ts_local"].dt.strftime("%H:%M:%S"), n_above=top["date"].map(n_above))
    return top[cols + ["threshold"]].reset_index(drop=True)


# ---------- aggressor_sweep ----------
def sweep_runs(trades: pd.DataFrame, window_s: float = config.ALERT_SWEEP_WINDOW_S) -> pd.DataFrame:
    """Regroupe les exécutions CONSÉCUTIVES du même côté agresseur dont l'écart au début de la rafale est <= window_s.
    Proxy d'un gros ordre unique qui balaie le carnet. Entrée : trades continus triés par ts_local."""
    cols = ["date", "start", "side", "n", "notional_eur", "qty", "duration_s"]
    if trades.empty:
        return pd.DataFrame(columns=cols)
    t = trades.sort_values("ts_local", kind="stable").reset_index(drop=True)
    ts = t["ts_local"].to_numpy()
    side = t["side"].to_numpy()
    day = t["date"].to_numpy()
    run_id = np.zeros(len(t), dtype=np.int64)
    start = ts[0]
    rid = 0
    win = np.timedelta64(int(window_s * 1e9), "ns")
    for i in range(1, len(t)):
        if side[i] != side[i - 1] or day[i] != day[i - 1] or ts[i] - start > win:
            rid += 1
            start = ts[i]
        run_id[i] = rid
    g = t.assign(run=run_id).groupby("run")
    runs = pd.DataFrame(
        {
            "date": g["date"].first(),
            "start": g["ts_local"].first(),
            "end": g["ts_local"].last(),
            "side": g["side"].first(),
            "n": g.size(),
            "notional_eur": g["notional_eur"].sum(),
            "qty": g["qty"].sum(),
        }
    )
    runs["duration_s"] = (runs["end"] - runs["start"]).dt.total_seconds()
    return runs[runs["n"] >= 2][cols].reset_index(drop=True)


def sweeps(isin: str) -> pd.DataFrame:
    """Une ligne par jour : la plus grosse rafale au-dessus du seuil."""
    th = _th(isin)
    return _sweeps(isin, int(th["sweep_min_trades"]), th["sweep_adtv_pct"] / 100)


@lru_cache(maxsize=64)
def _sweeps(isin: str, min_trades: int, share: float) -> pd.DataFrame:
    cols = ["date", "time", "side", "notional_eur", "n", "duration_s", "adtv"]
    runs = sweep_runs(data.continuous_trades(isin))
    runs = runs[runs["n"] >= min_trades]
    if runs.empty:
        return pd.DataFrame(columns=cols)
    runs = _with_adtv(isin, runs, share)
    hit = runs[runs["notional_eur"] >= runs["threshold"]]
    if hit.empty:
        return pd.DataFrame(columns=cols)
    top = hit.sort_values("notional_eur", ascending=False).drop_duplicates("date").sort_values("date")
    top = top.assign(time=top["start"].dt.strftime("%H:%M:%S"))
    return top[cols + ["threshold"]].reset_index(drop=True)


# ---------- net_flow ----------
@lru_cache(maxsize=64)
def net_flows(isin: str) -> pd.DataFrame:
    """Flux net en € par jour et par participant (AGENT, PROP), Flows n_days == 1 uniquement (data.flows).
    net = notional acheté − notional vendu, tous modes confondus. Sans notional_eur : volume × VWAP (OHLC)."""
    f = data.flows(isin)
    cols = ["date", "participant", "net_eur", "adtv", "share"]
    if f.empty:
        return pd.DataFrame(columns=cols)
    f = f[f["participant"].isin(list(PARTICIPANT_LABEL))].copy()
    if "notional_eur" not in f.columns or f["notional_eur"].fillna(0).eq(0).all():
        px = data.ohlc(isin)
        vwap = px["vwap"] if "vwap" in px.columns else px["close"]
        f["notional_eur"] = f["volume"] * f["date"].map(vwap.astype(float))
    signed = np.where(f["side"] == "BUY", 1.0, -1.0) * f["notional_eur"].astype(float)
    net = f.assign(signed=signed).groupby(["date", "participant"])["signed"].sum().rename("net_eur").reset_index()
    adtv = data.adtv_series(isin)
    net["adtv"] = net["date"].map(adtv) if not adtv.empty else np.nan
    net["share"] = net["net_eur"] / net["adtv"]
    return net[cols]


# ---------- auction_spike ----------
def auction_spikes(isin: str) -> pd.DataFrame:
    """Jours où la part de la closing auction dépasse N x (défaut 2) sa moyenne des 20 séances précédentes."""
    return _auction_spikes(isin, _th(isin)["auction_spike_ratio"])


@lru_cache(maxsize=64)
def _auction_spikes(isin: str, ratio_min: float) -> pd.DataFrame:
    share = data.closing_auction_share_series(isin)
    cols = ["date", "share", "baseline", "ratio"]
    if share.empty:
        return pd.DataFrame(columns=cols)
    mean, _ = metrics.rolling_baseline(share)
    df = pd.DataFrame({"share": share, "baseline": mean})
    df["ratio"] = df["share"] / df["baseline"]
    df = df[df["ratio"] > ratio_min].dropna()
    return df.rename_axis("date").reset_index()[cols]


# ---------- price_move (« notable day ») ----------
@lru_cache(maxsize=64)
def day_moves(isin: str) -> pd.DataFrame:
    """Par jour : rendement de l'action, médiane des rendements des peers, rendement excédentaire, volume_ratio."""
    px = data.ohlc(isin)
    cols = ["ret_pct", "peer_ret_pct", "excess_pct", "volume_ratio"]
    if px.empty:
        return pd.DataFrame(columns=cols)
    ret = px["close"].astype(float).pct_change() * 100
    peer_rets = [data.mask_peer(isin, p, data.ohlc(p)["close"].astype(float).pct_change() * 100)
                 for p in data.peers_of(isin) if not data.ohlc(p).empty]
    peer_rets = [r for r in peer_rets if not r.empty]
    peer = pd.concat(peer_rets, axis=1).median(axis=1, skipna=True).reindex(ret.index) if peer_rets else pd.Series(np.nan, index=ret.index)
    vol = px["volume"].astype(float)
    vmean, _ = metrics.rolling_baseline(vol)
    return pd.DataFrame({"ret_pct": ret, "peer_ret_pct": peer, "excess_pct": ret - peer, "volume_ratio": vol / vmean})


@lru_cache(maxsize=64)
def price_moves(isin: str) -> pd.DataFrame:
    """|rendement excédentaire vs médiane des peers| > ALERT_PRICE_MOVE_PCT ET volume_ratio > ALERT_PRICE_MOVE_VOLUME.
    Rendement EXCÉDENTAIRE : une journée où tout le secteur bouge ne déclenche rien."""
    m = day_moves(isin).dropna(subset=["excess_pct", "volume_ratio"])
    hit = m[(m["excess_pct"].abs() > config.ALERT_PRICE_MOVE_PCT) & (m["volume_ratio"] > config.ALERT_PRICE_MOVE_VOLUME)]
    return hit.rename_axis("date").reset_index()


# ---------- level_break ----------
def _lb_key(isin: str) -> tuple[float, int, float]:
    th = _th(isin)
    return th["large_trade_adtv_pct"], int(th["sweep_min_trades"]), th["sweep_adtv_pct"]


def level_breaks(isin: str) -> pd.DataFrame:
    """Clôture qui franchit un support/une résistance (calculés sur l'historique AVANT le jour), confirmée par
    volume_ratio > ALERT_LEVEL_BREAK_VOLUME ET au moins un large_trade ou aggressor_sweep le même jour."""
    return _level_breaks(isin, *_lb_key(isin))


@lru_cache(maxsize=64)
def _level_breaks(isin: str, _lt_pct: float, _sw_min: int, _sw_pct: float) -> pd.DataFrame:
    # les paramètres ne servent qu'à la clé de cache : large_trades / sweeps relisent les mêmes seuils
    cols = ["date", "level_type", "level_price", "touches", "close", "volume_ratio"]
    px = data.ohlc(isin)
    if px.empty:
        return pd.DataFrame(columns=cols)
    confirmed = set(large_trades(isin)["date"]) | set(sweeps(isin)["date"])
    vr = day_moves(isin)["volume_ratio"]
    rows = []
    for d in sorted(confirmed):
        d = pd.Timestamp(d)
        if not (vr.get(d, np.nan) > config.ALERT_LEVEL_BREAK_VOLUME):
            continue
        lv = indicators.broken_level(px, d)
        if lv:
            rows.append({"date": d, "level_type": lv["type"], "level_price": lv["price"], "touches": lv["touches"],
                         "close": float(px.at[d, "close"]), "volume_ratio": float(vr[d])})
    return pd.DataFrame(rows, columns=cols)


def detail_url(isin: str, day, linked_event_id: str | None) -> str:
    """Lien de l'alerte : l'impact card de l'événement du jour, sinon celle du « notable day »."""
    if linked_event_id:
        return f"/events/{linked_event_id}/impact-card"
    return f"/days/{isin}/{pd.Timestamp(day).strftime('%Y-%m-%d')}/impact-card"


# ---------- anomalies au format dashboard ----------
def alert_rows(isin: str, start: pd.Timestamp, end: pd.Timestamp, linked: dict[pd.Timestamp, str]) -> list[dict]:
    """Toutes les alertes de la période, au format `dashboard.anomalies[]` (v0.2 §5.2)."""
    rows: list[dict] = []
    inside = lambda d: start <= pd.Timestamp(d) <= end  # noqa: E731

    for _, r in large_trades(isin).iterrows():
        if not inside(r["date"]):
            continue
        share = r["notional_eur"] / r["adtv"] if r["adtv"] else np.nan
        side = "buy-initiated" if r["side"] == "BUY" else "sell-initiated"
        more = f"; {int(r['n_above']) - 1} other execution(s) above the threshold that day" if r["n_above"] > 1 else ""
        rows.append({
            "date": r["date"], "type": "large_trade", "severity": _severity(r["notional_eur"], r["threshold"]),
            "value": share,
            "description": f"A single {side} execution of {_eur(r['notional_eur'])} ({share:.0%} of 30-day average daily turnover) at {r['time'][:5]}{more}",
            "time": r["time"], "side": r["side"], "notional_eur": r["notional_eur"],
        })

    for _, r in sweeps(isin).iterrows():
        if not inside(r["date"]):
            continue
        share = r["notional_eur"] / r["adtv"] if r["adtv"] else np.nan
        side = "buy" if r["side"] == "BUY" else "sell"
        span = "at the same timestamp" if r["duration_s"] < 0.05 else f"within {r['duration_s']:.1f} s"
        rows.append({
            "date": r["date"], "type": "aggressor_sweep", "severity": _severity(r["notional_eur"], r["threshold"]),
            "value": share,
            "description": f"Aggressive {side} orders swept the order book: {int(r['n'])} executions worth {_eur(r['notional_eur'])} "
                           f"{span} at {r['time'][:5]} ({share:.0%} of 30-day average daily turnover)",
            "time": r["time"], "side": r["side"], "notional_eur": r["notional_eur"],
        })

    nf = net_flows(isin)
    th = _th(isin)
    limit = th["net_flow_adtv_pct"] / 100
    for _, r in nf[nf["share"].abs() > limit].iterrows():
        if not inside(r["date"]):
            continue
        verb = "net buying" if r["net_eur"] > 0 else "net selling"
        rows.append({
            "date": r["date"], "type": "net_flow", "severity": _severity(abs(r["share"]), limit),
            "value": r["share"],
            "description": f"{PARTICIPANT_LABEL[r['participant']]} was {verb} {_eur(r['net_eur'])} "
                           f"({abs(r['share']):.0%} of 30-day average daily turnover)",
            "side": "BUY" if r["net_eur"] > 0 else "SELL", "notional_eur": abs(r["net_eur"]),
        })

    for _, r in auction_spikes(isin).iterrows():
        if not inside(r["date"]):
            continue
        rows.append({
            "date": r["date"], "type": "auction_spike", "severity": _severity(r["ratio"], th["auction_spike_ratio"]),
            "value": r["ratio"],
            "description": f"Closing auction executed {r['share']:.0%} of the day's volume ({r['ratio']:.1f}x its 20-day average share)",
        })

    for _, r in price_moves(isin).iterrows():
        if not inside(r["date"]):
            continue
        rows.append({
            "date": r["date"], "type": "price_move", "severity": _severity(abs(r["excess_pct"]), config.ALERT_PRICE_MOVE_PCT),
            "value": r["excess_pct"],
            "description": f"Price moved {r['excess_pct']:+.1f}% vs peers on {r['volume_ratio']:.1f}x usual volume",
        })

    for _, r in level_breaks(isin).iterrows():
        if not inside(r["date"]):
            continue
        verb = "rose above the resistance" if r["level_type"] == "resistance" else "fell below the support"
        rows.append({
            "date": r["date"], "type": "level_break",
            "severity": _severity(r["volume_ratio"], config.ALERT_LEVEL_BREAK_VOLUME),
            "value": r["volume_ratio"],
            "description": f"Close of EUR {r['close']:.2f} {verb} at EUR {r['level_price']:.2f} "
                           f"({int(r['touches'])} previous touches) on {r['volume_ratio']:.1f}x usual volume, "
                           f"confirmed by unusually large executions",
            "level_type": r["level_type"], "level_price": r["level_price"],
        })

    for row in rows:
        row["linked_event_id"] = linked.get(pd.Timestamp(row["date"]))
        row["detail_url"] = detail_url(isin, row["date"], row["linked_event_id"])
    return rows


def day_alerts(isin: str, day: pd.Timestamp) -> list[dict]:
    """Alertes d'un seul jour (pour l'impact card et l'assistant)."""
    return alert_rows(isin, day, day, {})


def clear_caches() -> None:
    for fn in (_large_trades, _sweeps, net_flows, _auction_spikes, day_moves, price_moves, _level_breaks):
        getattr(fn, "cache_clear", lambda: None)()  # tolère une fonction remplacée par monkeypatch (tests)


# Compatibilité tests : level_breaks.__wrapped__(isin) = calcul sans cache avec les seuils courants
level_breaks.__wrapped__ = lambda isin: _level_breaks.__wrapped__(isin, *_lb_key(isin))  # type: ignore[attr-defined]
