from __future__ import annotations

import json
import math
import re

import numpy as np
import pandas as pd
import pytest

from app import analytics as A
from app import etl
from app.analytics import _util, data, events, indicators, metrics
from app.assistant import guard, templates

PBB = "DE0008019001"


# ---------- helpers ----------
def _keys(d, prefix=""):
    """Ensemble des chemins de clés d'un JSON (listes : on regarde le 1er élément)."""
    out = set()
    if isinstance(d, dict):
        for k, v in d.items():
            if k.startswith("_"):
                continue
            out.add(prefix + k)
            out |= _keys(v, prefix + k + ".")
    elif isinstance(d, list) and d and isinstance(d[0], dict):
        out |= _keys(d[0], prefix + "[].")
    return out


def _missing_keys(mock, out, prefix=""):
    """Clés du mock absentes de `out`. Une valeur null ou [] dans `out` accepte toute la sous-structure
    (broke_level: null, support: [] sont valides avec les données réelles)."""
    if out is None or out == []:
        return set()
    if isinstance(mock, dict):
        if not isinstance(out, dict):
            return {prefix.rstrip(".")}
        missing = set()
        for k, v in mock.items():
            if k.startswith("_"):
                continue
            if k not in out:
                missing.add(prefix + k)
            else:
                missing |= _missing_keys(v, out[k], prefix + k + ".")
        return missing
    if isinstance(mock, list) and mock and isinstance(mock[0], dict):
        return _missing_keys(mock[0], out[0], prefix + "[].") if isinstance(out, list) else {prefix.rstrip(".")}
    return set()


# Champs optionnels du contrat v0.2 (présents seulement sur certains types d'anomalies)
OPTIONAL_KEYS = {"anomalies.[].time", "anomalies.[].side", "anomalies.[].notional_eur"}


def _no_nan(obj):
    s = json.dumps(obj)  # échoue si objet non sérialisable
    assert "NaN" not in s and "Infinity" not in s


@pytest.fixture
def synthetic_ohlc_flows(monkeypatch):
    """OHLC + Flows synthétiques pour pbb et ses peers, sur le calendrier réel."""
    xlm = etl.load_xlm()
    days = sorted(xlm["date"].unique())
    rng = np.random.default_rng(0)
    rows, frows = [], []
    for isin in [PBB] + data.peers_of(PBB):
        price = 9.0
        for d in days:
            vol = rng.integers(300_000, 500_000)
            if isin == PBB and d == pd.Timestamp("2026-03-05"):
                vol = 2_000_000
            o = price
            price = max(1, price * (1 + rng.normal(0, 0.015)))
            rows.append({"date": d, "isin": isin, "open": o, "high": max(o, price) * 1.01, "low": min(o, price) * 0.99, "close": price, "volume": vol, "turnover_eur": vol * price})
            for p in ("AGENT", "PROP", "MARKET_MAKER"):
                for m in ("AGGRESSIVE", "PASSIVE", "AUCTION"):
                    for s in ("BUY", "SELL"):
                        frows.append({"date": d, "isin": isin, "participant": p, "mode": m, "side": s, "volume": int(vol / 18 * rng.uniform(0.7, 1.3))})
    ohlc_df, flows_df = pd.DataFrame(rows), pd.DataFrame(frows)
    monkeypatch.setattr(etl, "load_ohlc", lambda: ohlc_df)
    monkeypatch.setattr(etl, "load_flows", lambda: flows_df)
    data.clear_caches()
    yield
    data.clear_caches()


# ---------- calculs de base ----------
def test_baseline_excludes_current_day():
    days = pd.DatetimeIndex(pd.bdate_range("2026-01-01", periods=30))
    s = pd.Series(1.0, index=days)
    s.iloc[-1] = 100.0
    mean, _ = metrics.baseline_at(s, days, days[-1])
    assert mean == 1.0


def test_trading_day_rule():
    days = pd.DatetimeIndex(pd.to_datetime(["2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09"]))
    assert events.resolve_trading_day("2026-03-04", "07:00", days) == pd.Timestamp("2026-03-04")
    assert events.resolve_trading_day("2026-03-04", "22:00", days) == pd.Timestamp("2026-03-05")
    assert events.resolve_trading_day("2026-03-06", "18:00", days) == pd.Timestamp("2026-03-09")  # vendredi soir -> lundi
    assert events.resolve_trading_day("2026-03-07", "10:00", days) == pd.Timestamp("2026-03-09")  # samedi -> lundi


def test_indicators_and_support_resistance():
    close = pd.Series(np.r_[np.linspace(10, 12, 30), np.linspace(12, 10, 30), np.linspace(10, 12, 30)])
    ind = indicators.add_indicators(close)
    assert {"ema_20", "ema_50", "macd", "macd_signal", "macd_hist"} <= set(ind.columns)
    sr = indicators.support_resistance(close * 1.001, close * 0.999, float(close.iloc[-1]) - 0.5)
    assert sr["resistance"] and all(lv["touches"] >= 2 for lv in sr["resistance"])


def test_clean_removes_nan():
    out = _util.clean({"a": float("nan"), "b": [np.float64(1.5), np.inf], "c": pd.Timestamp("2026-03-05")})
    assert out == {"a": None, "b": [1.5, None], "c": "2026-03-05"}


# ---------- données réelles (spreads) ----------
def test_spread_data_loaded():
    assert data.trading_days()[0] == pd.Timestamp("2026-01-02")
    assert len(data.trading_days()) == 213
    # pbb reste en SDAX toute l'année
    assert data.index_on(PBB, pd.Timestamp("2026-01-02")) == "SDAX"
    assert data.index_on(PBB, pd.Timestamp("2026-10-30")) == "SDAX"


def _xlm_spread(isin: str, day: str) -> float:
    x = etl.load_xlm()
    row = x[(x["isin"] == isin) & (x["date"] == pd.Timestamp(day)) & (x["notional"] == 25_000)]
    return float(row["impact_bps"].iloc[0])


def test_impact_card_shape_matches_mock():
    card = A.build_impact_card("evt_003")  # FY 2025 results
    assert not _missing_keys(_util.load_mock("impact-card"), card)
    assert card["event"]["trading_day"] == "2026-03-05"
    assert card["metrics"]["spread_bps"]["event"] == pytest.approx(_xlm_spread(PBB, "2026-03-05"), abs=0.05)
    assert len(card["window"]) == 11 and card["window"][5]["offset"] == 0
    assert card["ai_summary"]
    _no_nan(card)


def test_after_close_event_maps_to_next_day():
    days = data.trading_days()
    # 16:48 (evt_005, directors' dealings) : avant 17:30 -> même jour
    assert A.build_impact_card("evt_005")["event"]["trading_day"] == "2026-03-17"
    # une annonce à 18:00 un jeudi -> vendredi ; un vendredi -> lundi
    assert events.resolve_trading_day("2026-03-05", "18:00", days) == pd.Timestamp("2026-03-06")
    assert events.resolve_trading_day("2026-03-06", "18:00", days) == pd.Timestamp("2026-03-09")


def test_unknown_time_gives_null_published_at():
    ev = A.build_impact_card("evt_003")["event"]  # heure non vérifiée dans events.csv
    assert ev["published_at"] is None and ev["trading_day"] == "2026-03-05"
    assert A.build_impact_card("evt_002")["event"]["published_at"] == "2026-02-13T12:26:00+01:00"


def test_unknown_ids_raise_notfound():
    with pytest.raises(A.NotFound):
        A.build_impact_card("nope")
    with pytest.raises(A.NotFound):
        A.build_dashboard("XX0000000000", "2026-01-01", "2026-02-01")
    with pytest.raises(A.NotFound):
        A.build_day_card(PBB, "2026-03-07")  # samedi


def test_dashboard_spread_only(monkeypatch):
    """Mode « spreads seulement » : OHLC et Flows vidés -> structure mock, spreads réels."""
    monkeypatch.setattr(etl, "load_ohlc", lambda: pd.DataFrame(columns=etl.OHLC_COLS))
    monkeypatch.setattr(etl, "load_flows", lambda: pd.DataFrame(columns=etl.FLOWS_COLS))
    data.clear_caches()
    try:
        d = A.build_dashboard(PBB, "2026-01-01", "2026-10-30")
        assert not _missing_keys(_util.load_mock("dashboard"), d) - OPTIONAL_KEYS
        assert d["_data_status"] == {"spreads": "real", "ohlc": "mock", "flows": "mock"}
        dates = [a["date"] for a in d["anomalies"]]
        assert dates == sorted(dates)
        event_ids = {e["event_id"] for e in A.list_events(PBB)["events"]}
        for a in d["anomalies"]:
            assert a["type"] in {"volume_spike", "spread_widening", "price_move", "auction_spike"}
            assert a["severity"] in {"low", "medium", "high"}
            assert a["linked_event_id"] is None or a["linked_event_id"] in event_ids
        _no_nan(d)
    finally:
        data.clear_caches()


def test_events_compare_report():
    ev = A.list_events(PBB)
    assert [e["event_id"] for e in ev["events"]][:2] == ["evt_001", "evt_002"]
    c = A.compare_events("voting_rights", "ALL", "2026-01-01", "2026-10-30")
    raw = etl.load_events()
    assert c["summary"]["n_events"] == int((raw["type"] == "voting_rights").sum())
    r = A.build_report(PBB, "2026-04-01", "2026-06-30")
    assert r["headline"] and r["disclaimer"].endswith("Not investment advice.")
    for x in (ev, c, r):
        _no_nan(x)


# ---------- chemin complet avec OHLC + Flows ----------
def test_full_path_with_ohlc_and_flows(synthetic_ohlc_flows):
    card = A.build_impact_card("evt_003")
    assert card["_data_status"]["ohlc"] == "real" and card["_data_status"]["flows"] == "real"
    assert card["metrics"]["volume"]["ratio"] > 3
    assert card["metrics"]["volume"]["z_score"] > 3
    assert {p["type"] for p in card["flows"]["by_participant"]} == {"AGENT", "PROP", "MARKET_MAKER"}
    assert math.isclose(sum(m["share"] for m in card["flows"]["by_mode"]), 1.0, abs_tol=0.02)
    assert card["vs_peers"]["peer_avg_volume_ratio"] is not None
    assert all(w["close"] is not None for w in card["window"])

    d = A.build_dashboard(PBB, "2026-03-01", "2026-04-30")
    assert d["series"][0]["date"] >= "2026-03-01" and len(d["series"]) == len(d["peers_series"])
    assert any(a["type"] == "volume_spike" and a["date"] == "2026-03-05" for a in d["anomalies"])
    _no_nan(d)

    r = A.build_report(PBB, "2026-04-01", "2026-06-30")
    labels = [k["label"] for k in r["sections"][0]["kpis"]]
    assert "Avg daily volume" in labels and "Auction share" in labels
    _no_nan(r)


# ---------- garde-fou LLM ----------
def test_guard_rejects_invented_numbers_and_advice():
    facts = {"spread": {"event": 44.2, "baseline": 30.3, "change_pct": 45.8}}
    assert guard.check("The spread widened to 44.2 bps from 30.3 bps (+45.8%).", facts)
    assert not guard.check("The spread widened to 51.0 bps.", facts)
    assert not guard.check("The spread widened to 44.2 bps; investors should buy.", facts)
    assert not guard.check("The price will rise after this.", facts)


def test_summary_falls_back_without_llm(monkeypatch):
    from app.assistant import llm

    monkeypatch.setattr(llm, "complete", lambda *a, **k: "Spread exploded to 999 bps, buy now!")
    card = A.build_impact_card("evt_003")
    spread = f"{_xlm_spread(PBB, '2026-03-05'):.1f}"
    assert "999" not in card["ai_summary"] and spread in card["ai_summary"]


# ---------- Partie B : vraies données (OHLC, Flows n_days == 1, enchères depuis les trades) ----------
def test_real_data_status_on_pbb():
    card = A.build_impact_card("evt_002")
    assert card["_data_status"] == {"spreads": "real", "ohlc": "real", "flows": "real", "opening_closing_auction": "real", "intraday": "real"}
    d = A.build_dashboard(PBB, "2026-01-01", "2026-10-30")
    assert d["_data_status"] == {"spreads": "real", "ohlc": "real", "flows": "real"}
    r = A.build_report(PBB, "2026-01-01", "2026-10-30")
    assert r["_data_status"]["ohlc"] == "real" and r["_data_status"]["flows"] == "real"


def test_auction_blocks_match_trades():
    card = A.build_impact_card("evt_002")
    tr = etl.load_trades(PBB)
    day = tr[tr["date"] == pd.Timestamp(card["event"]["trading_day"])]
    for kind in ("opening", "closing"):
        expected = day.loc[day["auction_type"] == kind, "qty"].sum()
        assert card["metrics"][f"{kind}_auction"]["volume"] == expected
        assert card["metrics"][f"{kind}_auction"]["baseline"] is not None


def test_turnover_comes_from_ohlc():
    card = A.build_impact_card("evt_002")
    px = etl.load_ohlc()
    row = px[(px["isin"] == PBB) & (px["date"] == pd.Timestamp("2026-02-13"))]
    assert card["metrics"]["turnover_eur"]["event"] == round(float(row["turnover_eur"].iloc[0]))


def test_flows_ignore_multi_day_rows(monkeypatch):
    real = etl.load_flows()
    day = pd.Timestamp("2026-02-13")
    one = real[(real["isin"] == PBB) & (real["date"] == day)].copy()
    multi = one.copy()
    multi["volume"] = multi["volume"] * 1000  # ligne agrégée sur 2 jours : ne doit rien changer
    multi["notional_eur"] = multi["notional_eur"] * 1000
    multi["n_days"] = 2
    monkeypatch.setattr(etl, "load_flows", lambda: pd.concat([real, multi], ignore_index=True))
    data.clear_caches()
    try:
        f = data.flows(PBB)
        assert (f["n_days"] == 1).all()
        got = A.build_impact_card("evt_002")["flows"]["by_participant"]
        agent = one[one["participant"] == "AGENT"]
        buy = agent.loc[agent["side"] == "BUY", "volume"].sum()
        assert next(p for p in got if p["type"] == "AGENT")["buy"] == round(buy)
    finally:
        data.clear_caches()


# ---------- Prix vs spread ----------
def test_infer_tick_on_synthetic_grid():
    from app.analytics import pricing

    rng = np.random.default_rng(1)
    prices = pd.Series(np.round(rng.uniform(2.5, 4.5, 500) / 0.002) * 0.002)
    assert pricing.infer_tick(prices) == 0.002
    assert pricing.infer_tick(prices.head(10)) is None  # pas assez de prix


def test_spread_decomposition_adds_up():
    from app.analytics import pricing

    d = pricing.decompose(PBB, ("2026-01-01", "2026-03-31"), ("2026-08-01", "2026-10-31"))
    assert d["price_effect_bps"] + d["liquidity_effect_bps"] == pytest.approx(d["total_change_bps"])
    # effet prix = spread de a ramené au prix moyen de b, à coût constant en € par action
    assert d["price_effect_bps"] == pytest.approx(d["bps_a"] * d["price_a"] / d["price_b"] - d["bps_a"])
    # le cours de pbb baisse sur l'année -> effet prix positif
    assert (d["price_b"] < d["price_a"]) == (d["price_effect_bps"] > 0)


def test_dashboard_spread_in_eur_and_ticks():
    d = A.build_dashboard(PBB, "2026-10-01", "2026-10-30")
    for row in d["series"]:
        if row["spread_bps"] is not None:
            assert row["spread_eur"] == pytest.approx(row["spread_bps"] * 2.5, abs=0.2)  # bps et € arrondis à 0,1 : écart max 0,175
            assert row["spread_ticks"] is not None and row["spread_ticks"] > 0


# ---------- Partie C : intraday ----------
def test_intraday_during_session_evt_002():
    card = A.build_impact_card("evt_002")  # ad hoc du 13.02 à 12:26
    it = card["intraday"]
    assert it["during_session"] is True
    assert it["reference_time"] == card["event"]["published_at"]
    offs = [m["offset_min"] for m in it["minutes"]]
    assert offs == list(range(-30, 121))
    assert it["minutes"][30]["time"] == "12:26"
    cum = [m["cum_volume"] for m in it["minutes"]]
    assert cum == sorted(cum) and cum[-1] == sum(m["volume"] for m in it["minutes"])
    # volume des 15 premières minutes = somme des trades de la séance dans [12:26, 12:41)
    t = data.trades(PBB)
    ref = pd.Timestamp(it["reference_time"])
    w = t[(t["ts_local"] >= ref) & (t["ts_local"] < ref + pd.Timedelta(minutes=15))]
    assert it["first_15min"]["volume"] == w["qty"].sum()
    assert it["first_15min"]["baseline"] is not None
    # prix à +30 min vs dernier prix avant l'annonce
    before = t[(t["date"] == pd.Timestamp("2026-02-13")) & (t["ts_local"] < ref)]["price"].iloc[-1]
    upto = t[(t["date"] == pd.Timestamp("2026-02-13")) & (t["ts_local"] <= ref + pd.Timedelta(minutes=30))]["price"].iloc[-1]
    assert it["price_change_pct"]["after_30min"] == pytest.approx((upto / before - 1) * 100, abs=0.06)
    _no_nan(it)


def test_intraday_outside_session_starts_at_open():
    from app.analytics import intraday

    day = pd.Timestamp("2026-03-05")
    opening = data.trades(PBB)
    opening = opening[(opening["date"] == day) & (opening["auction_type"] == "opening")]["ts_local"].iloc[0]
    # annonce la veille à 18:00 -> trading_day suivant, référence = ouverture
    it = intraday.intraday_block(PBB, day, "2026-03-04T18:00:00+01:00")
    assert it["during_session"] is False
    assert pd.Timestamp(it["reference_time"]) == opening.floor("min")
    # heure inconnue (evt_003) -> idem
    card_it = A.build_impact_card("evt_003")["intraday"]
    assert card_it["during_session"] is False and card_it["reference_time"] == it["reference_time"]
    # annonce à 07:00 le jour même : avant l'ouverture -> ouverture
    assert intraday.intraday_block(PBB, day, "2026-03-05T07:00:00+01:00")["during_session"] is False


def test_intraday_null_without_trades(monkeypatch):
    monkeypatch.setattr(etl, "load_trades", lambda isin: pd.DataFrame(columns=etl.TRADES_COLS))
    data.clear_caches()
    try:
        card = A.build_impact_card("evt_002")
        assert card["intraday"] is None and card["_data_status"]["intraday"] == "missing"
    finally:
        data.clear_caches()


# ---------- Partie D : alertes sur les exécutions ----------
def _synthetic_trades(day: str, rows: list[tuple[str, float, int, str]]) -> pd.DataFrame:
    """rows = (HH:MM:SS.ffffff, prix, quantité, side). Format etl.load_trades."""
    ts = [pd.Timestamp(f"{day} {t}").tz_localize("Europe/Berlin") for t, *_ in rows]
    df = pd.DataFrame(
        {
            "ts_utc": [t.tz_convert("UTC") for t in ts],
            "ts_local": ts,
            "date": pd.Timestamp(day),
            "price": [p for _, p, _, _ in rows],
            "qty": [q for _, _, q, _ in rows],
            "side": [s for *_, s in rows],
        }
    )
    df["notional_eur"] = df["price"] * df["qty"]
    df["is_auction"] = df["side"] == ""
    df["auction_type"] = ""
    return df[etl.TRADES_COLS]


@pytest.fixture
def synthetic_trades(monkeypatch):
    """Trades synthétiques le 2026-03-10 (ADTV réel de pbb ce jour-là)."""
    from app.analytics import alerts

    def install(rows):
        df = _synthetic_trades("2026-03-10", rows)
        monkeypatch.setattr(etl, "load_trades", lambda isin: df if isin == PBB else pd.DataFrame(columns=etl.TRADES_COLS))
        data.clear_caches()
        adtv = data.adtv_series(PBB).get(pd.Timestamp("2026-03-10"))
        return alerts, alerts._threshold_eur(adtv)

    yield install
    data.clear_caches()


def test_large_trade_on_synthetic_trades(synthetic_trades):
    alerts, thr = synthetic_trades([])
    q_big = int(thr * 1.5 / 3.0)  # 1,5 x le seuil à 3 €
    alerts, thr = synthetic_trades([
        ("10:00:00.000", 3.0, 100, "BUY"),
        ("10:05:00.000", 3.0, q_big, "SELL"),           # au-dessus du seuil
        ("11:00:00.000", 3.0, int(q_big * 0.5), "BUY"),  # en dessous
    ])
    lt = alerts.large_trades(PBB)
    assert len(lt) == 1
    r = lt.iloc[0]
    assert r["time"] == "10:05:00" and r["side"] == "SELL" and r["notional_eur"] == pytest.approx(q_big * 3.0)
    rows = alerts.day_alerts(PBB, pd.Timestamp("2026-03-10"))
    big = [a for a in rows if a["type"] == "large_trade"][0]
    assert big["description"].startswith("A single sell-initiated execution") and "investor" not in big["description"]


def test_aggressor_sweep_on_synthetic_trades(synthetic_trades):
    alerts, thr = synthetic_trades([])
    q = int(thr * 0.4 / 3.0)  # chaque exécution = 40 % du seuil : il en faut 3 pour le dépasser
    alerts, thr = synthetic_trades([
        # rafale 1 : 3 achats en 0,6 s -> 120 % du seuil -> alerte
        ("10:00:00.000", 3.0, q, "BUY"), ("10:00:00.300", 3.0, q, "BUY"), ("10:00:00.600", 3.0, q, "BUY"),
        # rafale 2 : 3 ventes mais coupées par un achat -> pas d'alerte
        ("11:00:00.000", 3.0, q, "SELL"), ("11:00:00.100", 3.0, q, "SELL"), ("11:00:00.200", 3.0, 10, "BUY"), ("11:00:00.300", 3.0, q, "SELL"),
        # rafale 3 : 3 ventes étalées sur 1,5 s -> > 1 s, pas d'alerte
        ("12:00:00.000", 3.0, q, "SELL"), ("12:00:00.700", 3.0, q, "SELL"), ("12:00:01.500", 3.0, q, "SELL"),
    ])
    runs = alerts.sweep_runs(data.continuous_trades(PBB))
    assert runs["duration_s"].max() <= 1.0
    sw = alerts.sweeps(PBB)
    assert len(sw) == 1
    r = sw.iloc[0]
    assert r["time"] == "10:00:00" and r["side"] == "BUY" and r["n"] == 3
    assert r["notional_eur"] == pytest.approx(3 * q * 3.0)
    desc = [a for a in alerts.day_alerts(PBB, pd.Timestamp("2026-03-10")) if a["type"] == "aggressor_sweep"][0]["description"]
    assert desc.startswith("Aggressive buy orders") and "investor" not in desc


def test_net_flow_ignores_multi_day_rows(monkeypatch):
    from app.analytics import alerts

    day = pd.Timestamp("2026-03-10")
    base = {(r["participant"]): r["share"] for _, r in alerts.net_flows(PBB).query("date == @day").iterrows()}
    real = etl.load_flows()
    fake = real[(real["isin"] == PBB) & (real["date"] == day) & (real["participant"] == "AGENT")].copy()
    fake = fake[fake["side"] == "BUY"]
    fake["notional_eur"] = 1e9  # énorme achat net... mais sur une ligne multi-jours
    fake["n_days"] = 3
    monkeypatch.setattr(etl, "load_flows", lambda: pd.concat([real, fake], ignore_index=True))
    data.clear_caches()
    try:
        after = {(r["participant"]): r["share"] for _, r in alerts.net_flows(PBB).query("date == @day").iterrows()}
        assert after == pytest.approx(base)
    finally:
        data.clear_caches()


def test_alerts_on_pbb_are_consistent():
    from app import config

    d = A.build_dashboard(PBB, "2026-01-01", "2026-10-30")
    event_ids = {e["event_id"] for e in A.list_events(PBB)["events"]}
    ev_days = {e["trading_day"] for e in A.list_events(PBB)["events"]}
    ct = data.continuous_trades(PBB)
    adtv = data.adtv_series(PBB)
    types = set()
    for a in d["anomalies"]:
        types.add(a["type"])
        assert "investor" not in a["description"].lower()
        assert a["linked_event_id"] is None or a["linked_event_id"] in event_ids
        assert (a["linked_event_id"] is not None) == (a["date"] in ev_days)
        if a["type"] == "large_trade":
            day = ct[ct["date"] == pd.Timestamp(a["date"])]
            assert a["notional_eur"] == round(day["notional_eur"].max())
            from app.analytics import alerts as AL

            thr = AL._threshold_eur(adtv[pd.Timestamp(a["date"])])
            assert a["notional_eur"] >= thr - 1 and a["time"] and a["side"] in {"BUY", "SELL"}
        if a["type"] == "net_flow":
            assert abs(a["value"]) >= config.ALERT_NET_FLOW_ADTV_SHARE  # value arrondie à 0,01
        if a["type"] == "auction_spike":
            assert a["value"] >= config.ALERT_AUCTION_SPIKE_RATIO
    assert {"large_trade", "aggressor_sweep", "net_flow", "auction_spike"} <= types
    _no_nan(d)


# ---------- Assistant : faits réels, templates, wording ----------
def _sentences(text: str) -> int:
    import re

    return len(re.findall(r"[.!?](?:\s|$)", text))


@pytest.mark.parametrize("which", ["evt_002", "evt_003", "day"])
def test_real_summaries_are_short_guarded_and_neutral(which):
    from app.assistant import facts as F

    card = A.build_day_card(PBB, "2026-08-31") if which == "day" else A.build_impact_card(which)
    s = card["ai_summary"]
    f = F.impact_facts(card)
    assert 3 <= _sentences(s) <= 5
    assert guard.check(s, f)
    assert "investor" not in s.lower()
    assert {"intraday", "auctions", "volume", "price"} <= set(f)


def test_facts_include_intraday_and_day_alerts():
    from app.assistant import facts as F

    card = A.build_impact_card("evt_002")
    f = F.impact_facts(card)
    it = card["intraday"]
    assert f["intraday"]["first_15min_volume_ratio_vs_same_time_20d"] == it["first_15min"]["ratio"]
    assert f["intraday"]["announcement_during_session"] is True
    assert f["auctions"]["closing_auction_ratio_vs_baseline"] == card["metrics"]["closing_auction"]["ratio"]
    d = A.build_dashboard(PBB, "2026-02-13", "2026-02-13")
    from app.analytics import alerts as AL

    trade_alerts = {a["description"] for a in d["anomalies"] if a["type"] in AL.ALERT_TYPES}
    assert {a["description"] for a in f["execution_alerts_that_day"]} <= trade_alerts
    assert f"{it['first_15min']['ratio']:.1f}x" in card["ai_summary"]  # arrondi à 1 décimale dans le texte


def test_llm_text_naming_an_investor_is_rejected(monkeypatch):
    from app.assistant import llm

    card = A.build_impact_card("evt_003")
    spread = f"{card['metrics']['spread_bps']['event']:.1f}"
    monkeypatch.setattr(llm, "complete", lambda *a, **k: f"An investor drove the spread to {spread} bps.")
    assert "investor" not in A.build_impact_card("evt_003")["ai_summary"].lower()


def test_extended_closing_auctions_are_kept():
    """Une closing auction prolongée (après 17:36) compte quand même (ex. 12.02.2026)."""
    raw = etl.load_trades(PBB)
    closing = raw[raw["auction_type"] == "closing"].groupby("date")["qty"].sum()
    s = data.auction_volume_series(PBB, "closing")
    assert s.reindex(closing.index).tolist() == closing.astype(float).tolist()
    assert (s > 0).all()


def test_sweep_needs_three_executions_and_no_absolute_floor(synthetic_trades):
    from app import config

    alerts, thr = synthetic_trades([])
    assert config.ALERT_LARGE_TRADE_EUR is None
    adtv = data.adtv_series(PBB).get(pd.Timestamp("2026-03-10"))
    assert thr == pytest.approx(config.ALERT_LARGE_TRADE_ADTV_SHARE * adtv)
    q = int(thr * 0.8 / 3.0)
    # 2 exécutions = 160 % du seuil, mais < 3 exécutions -> pas d'alerte sweep
    alerts, _ = synthetic_trades([("10:00:00.000", 3.0, q, "BUY"), ("10:00:00.200", 3.0, q, "BUY")])
    assert alerts.sweeps(PBB).empty
    alerts, _ = synthetic_trades([("10:00:00.000", 3.0, q, "BUY"), ("10:00:00.200", 3.0, q, "BUY"), ("10:00:00.400", 3.0, 10, "BUY")])
    assert len(alerts.sweeps(PBB)) == 1


# ---------- price_move et level_break ----------
def _ohlc_frame(isin: str, closes: list[float], vols: list[float], days) -> pd.DataFrame:
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame({"date": days, "isin": isin, "open": c, "high": c * 1.002, "low": c * 0.998, "close": c,
                         "volume": vols, "turnover_eur": c * pd.Series(vols, dtype=float)})


@pytest.fixture
def synthetic_ohlc(monkeypatch):
    """OHLC synthétique pbb + peers sur les 60 premiers jours de trading ; renvoie une fonction d'installation."""
    days = list(data.trading_days()[:60])

    def install(own_close, own_vol, peer_close):
        frames = [_ohlc_frame(PBB, own_close, own_vol, days)]
        frames += [_ohlc_frame(p, peer_close, [1e5] * len(days), days) for p in data.peers_of(PBB)]
        df = pd.concat(frames, ignore_index=True)
        monkeypatch.setattr(etl, "load_ohlc", lambda: df)
        data.clear_caches()
        return days

    yield install
    data.clear_caches()


def test_price_move_uses_excess_return(synthetic_ohlc):
    from app.analytics import alerts

    n = 60
    own = [10.0] * n
    peers = [10.0] * n
    vol = [1e5] * n
    own[40] = 10.5; own[41:] = [10.5] * (n - 41)      # jour 40 : +5 % sur 2x volume, peers plats -> alerte
    vol[40] = 2e5
    own[50] = 10.5 * 1.04; own[51:] = [own[50]] * (n - 51)  # jour 50 : +4 %, mais peers aussi +4 % -> pas d'alerte
    peers[50:] = [10.4] * (n - 50)
    vol[50] = 3e5
    own[55] = own[54] * 1.05; own[56:] = [own[55]] * (n - 56)  # jour 55 : +5 % excédentaire mais volume normal -> rien
    days = synthetic_ohlc(own, vol, peers)
    pm = alerts.price_moves(PBB)
    assert list(pm["date"]) == [days[40]]
    assert pm.iloc[0]["excess_pct"] == pytest.approx(5.0)
    row = [a for a in alerts.alert_rows(PBB, days[0], days[-1], {}) if a["type"] == "price_move"][0]
    assert row["description"] == "Price moved +5.0% vs peers on 2.0x usual volume"
    assert row["detail_url"] == f"/days/{PBB}/{days[40]:%Y-%m-%d}/impact-card"
    assert alerts.detail_url(PBB, days[40], "evt_002") == "/events/evt_002/impact-card"


def test_level_break_needs_volume_and_large_execution(synthetic_ohlc, monkeypatch):
    from app.analytics import alerts, indicators

    n = 60
    # deux sommets à ~11 (jours 10 et 25) -> résistance à 11 ; cassure à la hausse au jour 45
    own = [10.0] * n
    own[10], own[25] = 11.0, 11.0
    own[45:] = [11.5] * (n - 45)
    vol = [1e5] * n
    vol[45] = 2e5
    days = synthetic_ohlc(own, vol, [10.0] * n)
    lv = indicators.broken_level(data.ohlc(PBB), days[45])
    assert lv["type"] == "resistance" and lv["price"] == pytest.approx(11.0 * 1.002, abs=0.01)
    # niveaux calculés AVANT le jour : la cassure elle-même ne crée pas de niveau
    assert indicators.broken_level(data.ohlc(PBB), days[30]) is None
    # (les trades réels restent chargés : on fixe les jours d'exécutions inhabituelles à la main)
    monkeypatch.setattr(alerts, "sweeps", lambda isin: pd.DataFrame({"date": []}))
    # sans exécution inhabituelle le même jour : pas de level_break
    monkeypatch.setattr(alerts, "large_trades", lambda isin: pd.DataFrame({"date": []}))
    assert alerts.level_breaks.__wrapped__(PBB).empty
    # avec un large_trade ce jour-là : alerte
    monkeypatch.setattr(alerts, "large_trades", lambda isin: pd.DataFrame({"date": [days[45]]}))
    lb = alerts.level_breaks.__wrapped__(PBB)
    assert list(lb["date"]) == [days[45]] and lb.iloc[0]["level_type"] == "resistance"


def test_new_alert_wording_on_pbb():
    d = A.build_dashboard(PBB, "2026-01-01", "2026-10-30")
    for a in d["anomalies"]:
        low = a["description"].lower()
        assert "institutional" not in low and "retail" not in low and "investor" not in low
        assert a["detail_url"] == (f"/events/{a['linked_event_id']}/impact-card" if a["linked_event_id"]
                                   else f"/days/{PBB}/{a['date']}/impact-card")
        if a["type"] == "level_break":
            assert a["level_type"] in {"support", "resistance"} and a["level_price"] > 0
            assert "confirmed by unusually large executions" in a["description"]


# ---------- pre_disclosure_activity (notifications WpHG) ----------
def _with_extra_events(monkeypatch, rows: list[dict]):
    real = etl.load_events()
    extra = pd.DataFrame([{**{c: "" for c in real.columns}, **r} for r in rows])
    monkeypatch.setattr(etl, "load_events", lambda: pd.concat([real, extra], ignore_index=True))
    data.clear_caches()


def test_pre_disclosure_looks_only_before_publication(monkeypatch):
    from app.analytics import disclosure

    # 31.08.2026 est un jour très inhabituel (volume 22x, enchère de clôture, flux nets)
    _with_extra_events(monkeypatch, [
        {"event_id": "vr_after", "isin": PBB, "date": "2026-09-01", "time": "08:00", "type": "voting_rights", "title": "VR test"},
        {"event_id": "vr_same", "isin": PBB, "date": "2026-08-31", "time": "08:00", "type": "voting_rights", "title": "VR test"},
    ])
    after = A.build_impact_card("vr_after")["pre_disclosure_activity"]
    assert "2026-08-31" in [d["date"] for d in after["days"]]
    days = data.trading_days()
    i = days.get_loc(pd.Timestamp("2026-09-01"))
    assert after["window"] == {"from": f"{days[i - 7]:%Y-%m-%d}", "to": "2026-08-31", "sessions": 7}
    same = A.build_impact_card("vr_same")["pre_disclosure_activity"]
    assert same is None or all(d["date"] < "2026-08-31" for d in same["days"])  # jour de publication exclu
    # fenêtre = 7 séances strictement avant
    win = disclosure.window_before(pd.Timestamp("2026-09-01"))
    assert len(win) == 7 and win[-1] < pd.Timestamp("2026-09-01")
    for d in after["days"]:
        assert pd.Timestamp(d["date"]) in win and d["anomaly_types"]
    s = after["summary"]
    assert s.startswith("Unusual activity in the 7 sessions before the disclosure") and "may coincide with" in s
    assert "investor" not in s.lower()


def test_pre_disclosure_null_when_quiet_or_not_voting_rights():
    assert A.build_impact_card("evt_002")["pre_disclosure_activity"] is None  # ad hoc, pas une notification
    vr = [e["event_id"] for e in A.list_events(PBB)["events"] if e["type"] == "voting_rights"]
    blocks = [A.build_impact_card(e)["pre_disclosure_activity"] for e in vr]
    assert any(b is None for b in blocks) and any(b is not None for b in blocks)


# ---------- Bug reports : peers_text et KPIs sans période précédente ----------
def test_peers_text_uses_sector_label():
    from app import config
    from app.assistant import templates

    assert config.SECTORS[PBB] == "Financials"
    txt = templates.peers_text(69.9, 77.5, 6, "Financials")
    assert "6 financial peers" in txt and "industrial" not in txt
    assert "its 6 peers (" in templates.peers_text(69.9, 77.5, 6, None)
    assert "its 6 peers (" in templates.peers_text(69.9, 77.5, 6, "Unknown sector")
    r = A.build_report(PBB, "2026-01-02", "2026-10-30")
    peer_txt = next(s for s in r["sections"] if s["title"] == "Peer comparison")["text"]
    assert "financial peers" in peer_txt and "industrial" not in peer_txt


def test_report_without_previous_period_compares_halves():
    r = A.build_report(PBB, "2026-01-02", "2026-10-30")  # aucune donnée avant le 02.01
    prof = r["sections"][0]
    days = data.trading_days()
    rng = days[(days >= "2026-01-02") & (days <= "2026-10-30")]
    first, second = rng[: len(rng) // 2], rng[len(rng) // 2 :]
    sp = data.spread_series(PBB)
    for k in prof["kpis"]:
        assert k["change_basis"] == "first_half"
        assert k["change_pct"] is not None and k["trend"] in {"up", "down", "flat"}
    spread_kpi = next(k for k in prof["kpis"] if k["label"].startswith("Avg spread"))
    assert spread_kpi["change_pct"] == pytest.approx((sp.reindex(second).mean() / sp.reindex(first).mean() - 1) * 100, abs=0.06)
    assert "vs first half of the period" in prof["text"] and "vs previous period" not in prof["text"]
    assert "first half of the period" in r["headline"]


def test_report_with_previous_period_keeps_it():
    r = A.build_report(PBB, "2026-07-01", "2026-10-30")
    for k in r["sections"][0]["kpis"]:
        assert k["change_basis"] == "previous_period"
    assert "vs previous period" in r["sections"][0]["text"]


def test_unknown_change_is_never_flat():
    from app.analytics import report

    assert report._trend(None) is None
    assert report._trend(1.0) == "flat" and report._trend(5.0) == "up" and report._trend(-5.0) == "down"
    empty = pd.Series(dtype=float)
    days = data.trading_days()[:10]
    assert report._change(empty, days, days[:0]) == (None, None)
    kpi = report._kpi("X", 1, "ratio", (None, None))
    assert kpi["trend"] is None and kpi["change_pct"] is None and kpi["change_basis"] is None


# ---------- Event preview : assistant et garde-fou ----------
def _stat(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "median": None, "min": None, "max": None}
    return {"n": len(vals), "median": float(np.median(vals)), "min": min(vals), "max": max(vals)}


def _fake_preview(spreads, vols, stns, event_type="quarterly_results"):
    own = {"n": len(spreads), "events": []}
    own["spread_change_pct"] = _stat(spreads)
    own["volume_ratio"] = _stat(vols)
    own["sessions_to_normal"] = _stat(stns)
    for k in ("price_abs_change_pct", "auction_share_change_pts", "first_15min_ratio"):
        own[k] = _stat([])
    return {
        "stock": {"isin": PBB, "name": "Deutsche Pfandbriefbank AG", "index": "SDAX"},
        "event_type": event_type, "own_history": own,
        "peers": {"n": 0, "spread_change_pct": _stat([])},
        "confidence": "low", "note": "Based on 2026 data only (Jan–Oct).",
    }


@pytest.mark.parametrize(
    "text",
    [
        "The share price will rise after the Q3 results.",
        "We expect the price to recover.",
        "Analysts see upside of 12.0%.",
        "The downside is limited.",
        "Our target is EUR 4.",
        "The stock will fall on the release.",
    ],
)
def test_guard_rejects_price_predictions(text):
    assert not guard.check(text, {"x": 12.0, "y": 4})


def test_preview_template_past_reactions_only():
    from app.assistant import facts as F, templates

    p = _fake_preview([7.9, 15.5], [1.36, 2.52], [0, 1])
    s = templates.preview_summary(p)
    assert s.startswith("In its past 2 quarterly results releases")
    assert "+11.7%" in s and "7.9% to 15.5%" in s
    assert 2 <= len(__import__("re").findall(r"[.!?](?:\s|$)", s)) <= 4
    assert guard.check(s, F.preview_facts(p))
    p1 = _fake_preview([-2.2], [15.0], [0], "ad_hoc")
    one = templates.preview_summary(p1)
    assert one.startswith("In its only past ad hoc announcement") and "median" not in one
    assert guard.check(one, F.preview_facts(p1))
    p0 = _fake_preview([], [], [], "dividend")
    none = templates.preview_summary(p0)
    assert none.startswith("No past dividend announcements") and guard.check(none, F.preview_facts(p0))


def test_llm_price_prediction_in_preview_falls_back(monkeypatch):
    from app import assistant
    from app.assistant import llm, templates

    p = _fake_preview([7.9, 15.5], [1.36, 2.52], [0, 1])
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "In its past 2 quarterly results releases, the price will rise 11.7%.")
    assert assistant.summarize_event_preview(p) == templates.preview_summary(p)


# ---------- Event preview ----------
def test_preview_never_uses_events_after_day():
    from app.analytics import preview as PV

    before = A.build_event_preview(PBB, "quarterly_results", "2026-08-13")  # H1 publié le 13.08 : exclu
    assert before["reference_date"] == "2026-08-13" and before["as_of"] == "2026-10-30"
    assert [e["event_id"] for e in before["own_history"]["events"]] == ["evt_016"]
    assert all(e["date"] < "2026-08-13" for e in before["own_history"]["events"])
    after = A.build_event_preview(PBB, "quarterly_results", "2026-08-14")
    assert [e["event_id"] for e in after["own_history"]["events"]] == ["evt_016", "evt_018"]
    # upcoming = prochain événement du type à partir de `day`
    assert before["upcoming"]["event_id"] == "evt_018"
    assert PV._upcoming(PBB, "quarterly_results", pd.Timestamp("2026-12-01")) == {
        "date": "2026-12-01", "title": None, "event_id": None, "source_url": None}


def test_preview_stats_on_synthetic_events(monkeypatch):
    from app.analytics import preview as PV

    days = ["2026-04-14", "2026-06-16", "2026-07-14", "2026-09-15"]
    _with_extra_events(monkeypatch, [
        {"event_id": f"syn_{i}", "isin": PBB, "date": d, "time": "07:00", "type": "m_and_a", "title": "synthetic"}
        for i, d in enumerate(days)
    ])
    p = A.build_event_preview(PBB, "m_and_a")
    own = p["own_history"]
    assert own["n"] == 4 and p["confidence"] == "medium"
    for k in PV.METRICS:
        vals = [e[k] for e in own["events"] if e[k] is not None]
        st = own[k]
        assert st["n"] == len(vals)
        if vals:
            assert st["median"] == pytest.approx(np.median(vals), abs=0.06)  # médiane arrondie à 0,1
            assert st["min"] == pytest.approx(min(vals), abs=0.01) and st["max"] == pytest.approx(max(vals), abs=0.01)
    # chaque événement = son impact card
    card = A.build_impact_card("syn_0")
    e0 = own["events"][0]
    assert e0["spread_change_pct"] == card["metrics"]["spread_bps"]["change_pct"]
    assert e0["volume_ratio"] == card["metrics"]["volume"]["ratio"]
    _no_nan(p)


def test_stats_and_confidence_rules():
    from app.analytics import preview as PV

    assert PV._stats([3.0, 1.0, 2.0, None]) == {"n": 3, "median": 2.0, "min": 1.0, "max": 3.0}
    assert PV._stats([]) == {"n": 0, "median": None, "min": None, "max": None}
    assert [PV._confidence(n) for n in (0, 2, 3, 5, 6)] == ["low", "low", "medium", "medium", "high"]


def test_preview_with_no_past_event_is_all_null():
    p = A.build_event_preview(PBB, "dividend")
    assert p["own_history"]["n"] == 0 and p["own_history"]["events"] == []
    from app.analytics import preview as PV

    for k in PV.METRICS:
        assert p["own_history"][k] == {"n": 0, "median": None, "min": None, "max": None}
    assert p["attention_points"] == [] and p["confidence"] == "low" and p["ai_summary"]
    assert p["peers"]["n"] == 0 and p["peers"]["peers_note"] == "No peer events of this type in the event calendar"
    _no_nan(p)
    with pytest.raises(A.NotFound):
        A.build_event_preview("XX0000000000", "dividend")


def test_attention_points_rules():
    from app.analytics import preview as PV

    def st(m):
        return {"n": 1 if m is not None else 0, "median": m, "min": m, "max": m}

    own = {"spread_change_pct": st(30.0), "sessions_to_normal": st(2), "first_15min_ratio": st(6.0)}
    peers = {"spread_change_pct": st(15.0)}
    pts = PV._attention_points(own, peers)
    assert len(pts) == 4 and pts[-1] == "The stock reacts more strongly than its peers."
    assert PV._attention_points({"spread_change_pct": st(10.0), "sessions_to_normal": st(1), "first_15min_ratio": st(2.0)},
                                {"spread_change_pct": st(None)}) == []
    # réel : l'ad hoc du 13.02 -> 136x en 15 min
    assert "Most of the reaction happens in the first 15 minutes after publication." in A.build_event_preview(PBB, "ad_hoc")["attention_points"]


def test_price_abs_change_never_negative_and_no_direction():
    for t in ("quarterly_results", "annual_results", "ad_hoc", "agm", "voting_rights", "directors_dealings"):
        p = A.build_event_preview(PBB, t)
        for e in p["own_history"]["events"]:
            assert e["price_abs_change_pct"] is None or e["price_abs_change_pct"] >= 0
            assert "price_change_pct" not in e  # jamais de rendement signé
        s = p["ai_summary"].lower()
        assert not any(w in s for w in ("will rise", "will fall", "target", "upside", "downside", "expect the price"))
    ah = A.build_event_preview(PBB, "ad_hoc")["own_history"]["events"][0]
    assert ah["price_abs_change_pct"] == abs(A.build_impact_card("evt_002")["metrics"]["price"]["change_pct"])


# ---------- Report : section Alerts ----------
def test_report_alerts_section_matches_dashboard():
    from collections import Counter

    r = A.build_report(PBB, "2026-01-02", "2026-10-30")
    sec = next(s for s in r["sections"] if s["title"] == "Alerts")
    d = A.build_dashboard(PBB, "2026-01-02", "2026-10-30")
    counts = Counter(a["type"] for a in d["anomalies"])
    assert {k["alert_type"]: k["value"] for k in sec["kpis"]} == dict(counts)
    for k in sec["kpis"]:
        assert k["unit"] == "count" and k["trend"] is None
    top = sec["alert_days"]
    assert len(top) == 5
    by_day = {}
    for a in d["anomalies"]:
        by_day.setdefault(a["date"], []).append(a)
    key = lambda day: (sum(a["severity"] == "high" for a in by_day[day]), len(by_day[day]))  # noqa: E731
    assert [key(t["date"]) for t in top] == sorted([key(t["date"]) for t in top], reverse=True)
    best_other = max(key(dd) for dd in by_day if dd not in {t["date"] for t in top})
    assert key(top[-1]["date"]) >= best_other
    for t in top:
        assert t["n_alerts"] == len(by_day[t["date"]])
        assert t["detail_url"].endswith("/impact-card")
    assert sec["text"].startswith(f"{sum(counts.values())} alerts on {len(by_day)} of ")
    _no_nan(r)


def test_report_alerts_section_on_quiet_period(monkeypatch):
    monkeypatch.setattr(etl, "load_ohlc", lambda: pd.DataFrame(columns=etl.OHLC_COLS))
    monkeypatch.setattr(etl, "load_flows", lambda: pd.DataFrame(columns=etl.FLOWS_COLS))
    data.clear_caches()
    try:
        r = A.build_report(PBB, "2026-04-01", "2026-04-30")
        sec = next(s for s in r["sections"] if s["title"] == "Alerts")
        assert isinstance(sec["kpis"], list) and isinstance(sec["alert_days"], list)
        assert all(k["unit"] == "count" for k in sec["kpis"])
    finally:
        data.clear_caches()


# ---------- Formatage IR des textes (assistant.fmt) ----------
def test_fmt_units():
    from app.assistant import fmt

    assert fmt.value(440981, "shares") == "440,981 shares"
    assert fmt.value(1_234_567, "EUR") == "EUR 1.2m"
    assert fmt.value(640_000, "EUR") == "EUR 640,000"
    assert fmt.value(0.31, "ratio") == "31.0%"
    assert fmt.value(25.24, "bps") == "25.2 bps"
    assert fmt.value(12, "count") == "12"
    assert fmt.value(None, "bps") == "n/a"


def test_profile_text_is_formatted_and_guarded():
    from app.assistant import facts as F

    kpis = [
        {"label": "Avg daily volume", "value": 440981, "unit": "shares", "change_pct": 12.3, "change_basis": "previous_period"},
        {"label": "Avg daily turnover", "value": 1234567, "unit": "EUR", "change_pct": -4.0, "change_basis": "previous_period"},
        {"label": "Avg spread (25k EUR)", "value": 25.2, "unit": "bps", "change_pct": 3.1, "change_basis": "first_half"},
        {"label": "Auction share", "value": 0.31, "unit": "ratio", "change_pct": 1.0, "change_basis": "previous_period"},
    ]
    txt = templates.profile_text(kpis)
    assert "440,981 shares" in txt and "EUR 1.2m" in txt and "25.2 bps" in txt and "31.0%" in txt
    assert "ratio" not in txt and "0.31" not in txt
    report = {"stock": {"name": "X"}, "period": {}, "sections": [{"title": "Trading profile", "kpis": kpis}]}
    assert guard.check(txt, F.report_facts(report))


def test_guard_accepts_formatted_numbers_only_from_facts():
    facts = {"share": 0.31, "turnover": 1234567, "volume": 440981}
    assert guard.check("Auctions were 31.0% of volume, turnover EUR 1.2m, 440,981 shares.", facts)
    assert not guard.check("Auctions were 47.0% of volume.", facts)
    assert not guard.check("Turnover reached EUR 3.4m.", facts)
    assert not guard.check("Volume was 512,300 shares.", facts)


def test_report_texts_use_ir_formats():
    rep = A.build_report(PBB, "2026-01-02", "2026-10-30")
    prof = next(s for s in rep["sections"] if s["title"] == "Trading profile")
    assert " ratio" not in prof["text"] and re.search(r"\d{1,3},\d{3} shares", prof["text"])
    assert re.search(r"EUR \d+(\.\d)?m|EUR \d{1,3}(,\d{3})+", prof["text"])
    assert re.search(r"Auction share: \d+\.\d%", prof["text"])
    share = next(k for k in prof["kpis"] if k["unit"] == "ratio")
    assert 0 <= share["value"] <= 1  # la valeur JSON reste un ratio


# ---------- Événement à venir : Q3 pbb du 12.11.2026 (evt_026, scène de démo) ----------
def test_future_event_has_no_market_data_yet():
    from app.analytics import NoMarketData

    ids = [e["event_id"] for e in A.list_events(PBB)["events"]]
    assert "evt_026" not in ids  # rien de mesurable : pas dans la liste des impact cards
    with pytest.raises(NoMarketData, match="No market data yet"):
        A.build_impact_card("evt_026")


def test_future_event_api_returns_clean_404():
    from tests.helpers import logged_in_client

    c = logged_in_client()
    for url in ("/events/evt_026/impact-card", "/events/evt_026/impact-card.pdf"):
        r = c.get(url)
        assert r.status_code == 404 and r.json()["detail"].startswith("No market data yet for evt_026")


@pytest.mark.parametrize("day", [None, "2026-11-12"])
def test_preview_for_q3_demo_event(day):
    from app.assistant import facts as F

    p = A.build_event_preview(PBB, "quarterly_results", day=day)
    assert p["own_history"]["n"] == 2  # Q1 (12.05) + H1 (13.08), jamais evt_026 lui-même
    assert {e["event_id"] for e in p["own_history"]["events"]} == {"evt_016", "evt_018"}
    assert p["upcoming"]["event_id"] == "evt_026" and p["upcoming"]["date"] == "2026-11-12"
    assert p["confidence"] == "low"
    s = p["ai_summary"]
    assert guard.check(s, F.preview_facts(p)) and "investor" not in s.lower()


# ---------- as_of, checklist IR, peers ----------
def test_as_of_is_last_data_date_everywhere():
    assert A.build_dashboard(PBB, "2026-03-02", "2026-03-31")["as_of"] == "2026-10-30"
    assert A.list_events(PBB)["as_of"] == "2026-10-30"
    p = A.build_event_preview(PBB, "quarterly_results")
    assert p["as_of"] == "2026-10-30" and p["reference_date"] is None


def test_checklist_rules_and_wording():
    from app.analytics import preview as PV
    from app.assistant import guard

    p = A.build_event_preview(PBB, "quarterly_results", "2026-11-12")
    assert len(p["checklist"]) == 3  # volume 1.9x > 1.5, spread +11.7% > 10, 0.5 session <= 1
    assert "designated sponsor" in p["checklist"][0] and "before the market opens" in p["checklist"][1]
    for line in p["checklist"]:
        assert not guard._BANNED.search(line) and "investor" not in line.lower()
    own = {"volume_ratio": {"median": 1.2}, "spread_change_pct": {"median": 4.0}, "sessions_to_normal": {"median": 3}}
    assert PV._checklist(own, "quarterly_results") == []
    assert A.build_event_preview(PBB, "dividend")["checklist"] == []


def test_pbb_preview_has_peer_results():
    p = A.build_event_preview(PBB, "quarterly_results", "2026-11-12")
    assert p["peers"]["n"] >= 6 and "peers_note" not in p["peers"]
    ids = {e["event_id"] for e in p["peers"]["events"]}
    assert "evt_039" in ids  # flatexDEGIRO Q3, publié à 18:00 le 21.10 -> séance du 22.10
    assert next(e for e in p["peers"]["events"] if e["event_id"] == "evt_039")["date"] == "2026-10-22"


# ---------- AI points (3–4 phrases courtes) ----------
def test_ai_points_everywhere_and_guarded():
    from app.assistant import facts as F

    card = A.build_impact_card("evt_002")
    prev = A.build_event_preview(PBB, "quarterly_results", "2026-11-12")
    rep = A.build_report(PBB, "2026-10-26", "2026-10-30")
    for pts, facts in ((card["ai_points"], F.impact_facts(card)), (prev["ai_points"], F.preview_facts(prev)),
                       (rep["ai_points"], F.report_facts(rep))):
        assert 3 <= len(pts) <= 4
        for p in pts:
            assert guard.check(p, facts) and "investor" not in p.lower() and len(p.split()) <= 20


def test_ai_points_llm_kept_only_if_each_point_passes(monkeypatch):
    from app import assistant
    from app.assistant import llm

    card = A.build_impact_card("evt_002", with_summary=False)
    good = "- Volume was 15.0x its usual level.\n- The price moved -10.3%.\n- Spread 57.7 bps versus 59.0 bps."
    monkeypatch.setattr(llm, "complete", lambda *a, **k: good)
    assert assistant.points_impact_card(card) == ["Volume was 15.0x its usual level.", "The price moved -10.3%.",
                                                  "Spread 57.7 bps versus 59.0 bps."]
    bad = good + "\n- Spread will rise to 99.9 bps."  # chiffre inventé + prédiction -> repli template
    monkeypatch.setattr(llm, "complete", lambda *a, **k: bad)
    assert assistant.points_impact_card(card) == templates.impact_points(card)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "- Retail investors bought.\n- a.\n- b.")
    assert assistant.points_impact_card(card) == templates.impact_points(card)


def test_ai_points_no_past_events():
    p = A.build_event_preview(PBB, "dividend")
    assert p["ai_points"] == ["No past dividend announcements are available in the 2026 data."]


# ---------- Seuils modifiables (point 16) ----------
@pytest.fixture()
def clean_thresholds():
    from app.analytics import thresholds as TH

    TH.reset(PBB, "tests")
    yield TH
    TH.reset(PBB, "tests")


def test_threshold_change_changes_alert_count(clean_thresholds):
    TH = clean_thresholds
    from app.analytics.dashboard import flag_count

    base = flag_count(PBB)
    assert base == 149  # 149 alertes avec les seuils du code
    log = TH.save(PBB, {"net_flow_adtv_pct": 50, "volume_z_min": 3.0}, "tests")
    assert {e["item_id"] for e in log} == {"net_flow_adtv_pct", "volume_z_min"}
    assert all(e["decision"] == "threshold_changed" for e in log)
    assert next(e for e in log if e["item_id"] == "net_flow_adtv_pct")["old_value"] == "20"
    stricter = flag_count(PBB)
    assert stricter < base and TH.is_custom(PBB)
    d = A.build_dashboard(PBB, "2026-01-02", "2026-10-30")
    assert len(d["anomalies"]) == stricter  # dashboard, top 5 et chat lisent les mêmes seuils
    TH.reset(PBB, "tests")
    assert flag_count(PBB) == base and not TH.is_custom(PBB) and TH.current(PBB) == TH.defaults()


def test_threshold_bounds_and_preview(clean_thresholds):
    TH = clean_thresholds
    from app.analytics.dashboard import threshold_preview

    with pytest.raises(TH.InvalidThresholds) as e:
        TH.validate({"volume_z_min": 9, "sweep_min_trades": 2.5, "nope": 1})
    assert set(e.value.errors) == {"volume_z_min", "sweep_min_trades", "nope"}
    p = threshold_preview(PBB, {"net_flow_adtv_pct": 200})
    assert p["alerts_current"] == 149 and p["alerts_with_values"] < 149
    assert TH.current(PBB)["net_flow_adtv_pct"] == 20  # l'aperçu n'enregistre rien


def test_defaults_equal_code_values():
    from app import config
    from app.analytics import thresholds as TH

    d = TH.defaults()
    assert d["large_trade_adtv_pct"] == config.ALERT_LARGE_TRADE_ADTV_SHARE * 100
    assert d["sweep_min_trades"] == config.ALERT_SWEEP_MIN_TRADES
    assert d["net_flow_adtv_pct"] == config.ALERT_NET_FLOW_ADTV_SHARE * 100
    assert d["auction_spike_ratio"] == config.ALERT_AUCTION_SPIKE_RATIO
    assert (d["volume_z_min"], d["spread_z_min"], d["spread_ratio_min"]) == (2.0, 3.0, 1.2)


# ---------- key_finding (point 8) ----------
def test_key_finding_matches_phase1():
    kf = A.build_dashboard(PBB, "2026-10-01", "2026-10-30")["key_finding"]
    assert kf["text"] == ("pbb's cost to trade €25k rose from 54.3 to 97.4 bps (Jan–Oct), "
                          "moving from below to above its peers' median.")
    n = kf["numbers"]
    assert (n["own_first_bps"], n["own_last_bps"]) == (54.3, 97.4)
    assert (n["peers_median_first_bps"], n["peers_median_last_bps"]) == (72.3, 69.9)
    assert (n["index_median_first_bps"], n["index_median_last_bps"]) == (69.8, 71.0)
    assert (n["position_first"], n["position_last"]) == ("below", "above")
    assert n["price_effect_pct"] == 58.1 and n["liquidity_effect_pct"] == 41.9


def test_key_finding_wording_follows_the_data(monkeypatch):
    from app.analytics import key_finding as KF

    days = data.trading_days()
    jan = days.to_period("M") == days[0].to_period("M")
    oct_ = days.to_period("M") == days[-1].to_period("M")
    own = pd.Series(np.nan, index=days)
    own[jan], own[oct_] = 90.0, 60.0
    peers = pd.Series(70.0, index=days)
    monkeypatch.setattr(KF.data, "spread_series", lambda isin: own)
    monkeypatch.setattr("app.analytics.dashboard._peer_spread_median", lambda isin: peers)
    t = KF.build_key_finding(PBB)["text"]
    assert "fell from 90.0 to 60.0 bps" in t and "moving from above to below its peers' median" in t
    own[oct_] = 80.0
    assert "staying above its peers' median" in KF.build_key_finding(PBB)["text"]


# ---------- human-in-the-loop : id, décision, rang (points 9-10) ----------
def test_anomaly_ids_unique_and_rank_order():
    rows = A.build_dashboard(PBB, "2026-01-02", "2026-10-30")["anomalies"]
    assert len({r["id"] for r in rows}) == len(rows)
    ranked = sorted((r for r in rows if r["rank"]), key=lambda r: r["rank"])
    sev = {"high": 0, "medium": 1, "low": 2}
    keys = [(sev[r["severity"]], r["date"]) for r in ranked]
    assert all(keys[i][0] < keys[i + 1][0] or (keys[i][0] == keys[i + 1][0] and keys[i][1] >= keys[i + 1][1])
               for i in range(len(keys) - 1))
    assert {r["item_type"] for r in rows} == {"anomaly", "alert"}


# ---------------------------------------------------------------- auction_trend (dashboard)
def test_auction_trend_real_data():
    import pandas as pd

    from app.analytics import build_dashboard, data
    from app.analytics.auction_trend import WINDOW

    if not (data.has_ohlc() and data.has_flows()):
        pytest.skip("needs OHLC + Flows")
    isin = "DE0008019001"
    dash = build_dashboard(isin, "2026-01-02", "2026-10-30")
    tr = dash["auction_trend"]
    assert len(tr["series"]) == len(dash["series"]) and tr["window"] == WINDOW
    share = data.auction_share_series(isin)
    # Part du jour = Flows AUCTION ÷ total (pas de double comptage : même base au numérateur et au dénominateur)
    f = data.flows(isin)
    d0 = pd.Timestamp(tr["series"][30]["date"])
    day = f[f["date"] == d0]
    expected = day[day["mode"] == "AUCTION"]["volume"].sum() / day["volume"].sum()
    assert tr["series"][30]["auction_share"] == pytest.approx(expected, abs=0.0051)
    # Moyenne mobile : null avant 20 valeurs, puis moyenne des 20 dernières séances (jour inclus)
    assert all(p["baseline_20d"] is None for p in tr["series"][: WINDOW - 1])
    assert tr["series"][WINDOW - 1]["baseline_20d"] == pytest.approx(share.iloc[:WINDOW].mean(), abs=0.0051)
    assert tr["latest"]["value"] == tr["series"][-1]["baseline_20d"]
    assert tr["change_vs_start"] == pytest.approx(tr["latest"]["value"] - tr["start"]["value"], abs=0.011)
    # Pic = maximum journalier de la période
    vals = [p["auction_share"] for p in tr["series"] if p["auction_share"] is not None]
    assert tr["peak"]["value"] == max(vals)
    assert all(0 <= v <= 1 for v in vals)
    if tr["has_parts"]:
        for p in tr["series"]:
            parts = [p[k] for k in ("opening", "intraday", "closing")]
            assert all(x is not None and 0 <= x <= 1 for x in parts)
            assert sum(parts) <= p["auction_share"] + 0.021  # les enchères planifiées ne dépassent pas le total Flows


def test_auction_trend_censored_day_is_null_not_zero(monkeypatch):
    import pandas as pd

    from app.analytics import auction_trend as at
    from app.analytics import data

    days = pd.bdate_range("2026-01-05", periods=25)
    share = pd.Series(0.3, index=days.delete(10))  # jour 10 : pas de ligne Flows journalière (censuré)
    monkeypatch.setattr(data, "auction_share_series", lambda isin: share)
    monkeypatch.setattr(data, "trading_days", lambda: days)
    monkeypatch.setattr(at, "part_shares", lambda isin: {})
    tr = at.build_auction_trend("X", days)
    assert tr["series"][10]["auction_share"] is None and tr["has_parts"] is False
    assert "opening" not in tr["series"][0]
    assert tr["series"][19]["baseline_20d"] is None       # 19 valeurs seulement : le jour censuré ne compte pas pour 0
    assert tr["series"][24]["baseline_20d"] is None       # fenêtre 5..24 : contient encore le jour censuré
    monkeypatch.setattr(data, "auction_share_series", lambda isin: pd.Series(dtype=float))
    assert at.build_auction_trend("X", days) is None


def test_chat_period_summary_cites_auction_trend():
    from app.analytics import data
    from app.assistant import chat as C
    from app.assistant import templates

    if not (data.has_ohlc() and data.has_flows()):
        pytest.skip("needs OHLC + Flows")
    res = C.run_tool("DE0008019001", "get_period_summary", {"from": "2026-01-02", "to": "2026-10-30"})
    tr = res["auction_share_trend_pct"]
    assert tr["change_pts"] == pytest.approx(tr["avg_20d_end"]["pct"] - tr["avg_20d_start"]["pct"], abs=0.11)
    text = templates.chat_period(res, latest=False)
    assert f"{tr['avg_20d_start']['pct']:.1f}% to {tr['avg_20d_end']['pct']:.1f}%" in text
    assert f"peak of {tr['peak_day']['pct']:.1f}%" in text
