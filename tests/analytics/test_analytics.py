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

SUSS = "DE000A1K0235"


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


def _no_nan(obj):
    s = json.dumps(obj)  # échoue si objet non sérialisable
    assert "NaN" not in s and "Infinity" not in s


@pytest.fixture
def synthetic_ohlc_flows(monkeypatch):
    """OHLC + Flows synthétiques pour SUSS et ses peers, sur le calendrier réel."""
    xlm = etl.load_xlm()
    days = sorted(xlm["date"].unique())
    rng = np.random.default_rng(0)
    rows, frows = [], []
    for isin in [SUSS] + data.peers_of(SUSS):
        price = 9.0
        for d in days:
            vol = rng.integers(300_000, 500_000)
            if isin == SUSS and d == pd.Timestamp("2026-03-30"):
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
    assert data.index_on(SUSS, pd.Timestamp("2026-06-19")) == "SDAX"
    assert data.index_on(SUSS, pd.Timestamp("2026-06-22")) == "MDAX"


def _xlm_spread(isin: str, day: str) -> float:
    x = etl.load_xlm()
    row = x[(x["isin"] == isin) & (x["date"] == pd.Timestamp(day)) & (x["notional"] == 25_000)]
    return float(row["impact_bps"].iloc[0])


def test_impact_card_shape_matches_mock():
    card = A.build_impact_card("evt_001")
    assert _keys(_util.load_mock("impact-card")) <= _keys(card)
    assert card["event"]["trading_day"] == "2026-03-30"
    assert card["metrics"]["spread_bps"]["event"] == pytest.approx(_xlm_spread(SUSS, "2026-03-30"), abs=0.05)
    assert len(card["window"]) == 11 and card["window"][5]["offset"] == 0
    assert card["ai_summary"]
    _no_nan(card)


def test_after_close_event_maps_to_next_day():
    # evt_006 : 17:35 mais trading_day forcé dans events.csv (dernière clôture avant l'entrée en MDAX)
    assert A.build_impact_card("evt_006")["event"]["trading_day"] == "2026-06-19"
    # sans forçage, une annonce à 18:00 un vendredi tombe sur le lundi suivant
    assert events.resolve_trading_day("2026-06-19", "18:00", data.trading_days()) == pd.Timestamp("2026-06-22")


def test_unknown_ids_raise_notfound():
    with pytest.raises(A.NotFound):
        A.build_impact_card("nope")
    with pytest.raises(A.NotFound):
        A.build_dashboard("XX0000000000", "2026-01-01", "2026-02-01")
    with pytest.raises(A.NotFound):
        A.build_day_card(SUSS, "2026-03-07")  # samedi


def test_dashboard_spread_only():
    d = A.build_dashboard(SUSS, "2026-01-01", "2026-10-30")
    assert _keys(_util.load_mock("dashboard")) <= _keys(d)
    assert d["_data_status"]["spreads"] == "real"
    dates = [a["date"] for a in d["anomalies"]]
    assert dates == sorted(dates)
    event_ids = {e["event_id"] for e in A.list_events(SUSS)["events"]}
    for a in d["anomalies"]:
        assert a["type"] in {"volume_spike", "spread_widening", "price_move", "auction_spike"}
        assert a["severity"] in {"low", "medium", "high"}
        assert a["linked_event_id"] is None or a["linked_event_id"] in event_ids
    _no_nan(d)


def test_events_compare_report():
    ev = A.list_events(SUSS)
    assert [e["event_id"] for e in ev["events"]][:2] == ["evt_001", "evt_002"]
    c = A.compare_events("index_change", "ALL", "2026-01-01", "2026-10-30")
    assert c["summary"]["n_events"] == 3
    r = A.build_report(SUSS, "2026-04-01", "2026-06-30")
    assert r["headline"] and r["disclaimer"].endswith("Not investment advice.")
    for x in (ev, c, r):
        _no_nan(x)


# ---------- chemin complet avec OHLC + Flows ----------
def test_full_path_with_ohlc_and_flows(synthetic_ohlc_flows):
    card = A.build_impact_card("evt_001")
    assert card["_data_status"]["ohlc"] == "real" and card["_data_status"]["flows"] == "real"
    assert card["metrics"]["volume"]["ratio"] > 3
    assert card["metrics"]["volume"]["z_score"] > 3
    assert {p["type"] for p in card["flows"]["by_participant"]} == {"AGENT", "PROP", "MARKET_MAKER"}
    assert math.isclose(sum(m["share"] for m in card["flows"]["by_mode"]), 1.0, abs_tol=0.02)
    assert card["vs_peers"]["peer_avg_volume_ratio"] is not None
    assert all(w["close"] is not None for w in card["window"])

    d = A.build_dashboard(SUSS, "2026-03-01", "2026-04-30")
    assert d["series"][0]["date"] >= "2026-03-01" and len(d["series"]) == len(d["peers_series"])
    assert any(a["type"] == "volume_spike" and a["date"] == "2026-03-30" for a in d["anomalies"])
    _no_nan(d)

    r = A.build_report(SUSS, "2026-04-01", "2026-06-30")
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
    card = A.build_impact_card("evt_001")
    spread = f"{_xlm_spread(SUSS, '2026-03-30'):.1f}"
    assert "999" not in card["ai_summary"] and spread in card["ai_summary"]
