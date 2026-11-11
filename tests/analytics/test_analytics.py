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
