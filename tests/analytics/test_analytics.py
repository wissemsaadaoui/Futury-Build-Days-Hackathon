from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from app import analytics as A
from app import etl
from app.analytics import _util, data, events, indicators, metrics
from app.assistant import guard

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
        assert not _missing_keys(_util.load_mock("dashboard"), d)
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
