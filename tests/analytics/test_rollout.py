"""Roll-out à tous les émetteurs DAX / MDAX / SDAX (branche alfred/rollout).

5 ISIN : pbb (peers manuels), 2 MDAX, 2 SDAX – dont SUSS MicroTec (SDAX -> MDAX le 22.06.2026) et
STO (spread médian ~154 bps, faible liquidité, un jour de Flows censuré publié agrégé).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from app import etl
from app.analytics import data
from tests.helpers import logged_in_client

PBB = "DE0008019001"
SUSS = "DE000A1K0235"  # MDAX, SDAX jusqu'au 19.06.2026
AURUBIS = "DE0006766504"  # MDAX
STO = "DE0007274136"  # SDAX, faible liquidité
KWS = "DE0007074007"  # SDAX
ISINS = [PBB, SUSS, AURUBIS, STO, KWS]
QIAGEN = "NL0015002CX3"  # 4 séances dans le XLM : trop peu de données

needs_data = pytest.mark.skipif(etl.load_xlm().empty or etl.load_ohlc().empty, reason="données absentes")
client = logged_in_client()


def _strict(text: str):
    def reject(c: str):
        raise ValueError(f"non-JSON constant {c}")

    return json.loads(text, parse_constant=reject)


def _get(url: str, status: int = 200) -> dict:
    r = client.get(url)
    assert r.status_code == status, (url, r.status_code, r.text[:300])
    return _strict(r.text)


# ---------- dashboard et autres routes, pour n'importe quel émetteur ----------
@needs_data
@pytest.mark.parametrize("isin", ISINS)
def test_dashboard_any_issuer(isin: str) -> None:
    d = _get(f"/stocks/{isin}/dashboard")
    assert d["stock"]["isin"] == isin and d["series"]
    assert d["peer_basis"] == ("manual" if isin == PBB else "index")
    assert d["n_peers"] > 0
    # Peers non vides : une médiane peers existe la plupart des jours
    peer_spreads = [p["spread_bps"] for p in d["peers_series"] if p["spread_bps"] is not None]
    assert len(peer_spreads) > len(d["peers_series"]) * 0.5
    assert d["auction_trend"] and d["auction_trend"]["series"]
    assert d["key_finding"] and d["key_finding"]["text"]


@needs_data
@pytest.mark.parametrize("isin", ISINS)
def test_other_routes_any_issuer(isin: str) -> None:
    ev = _get(f"/stocks/{isin}/events")
    assert ev["isin"] == isin
    if isin != PBB:
        assert ev["events"] == []  # events.csv ne couvre que pbb (et ses peers manuels)
    pv = _get(f"/stocks/{isin}/event-preview?type=quarterly_results&date=2026-11-12")
    assert pv["peer_basis"] == ("manual" if isin == PBB else "index")
    if isin != PBB:
        assert pv["events_note"] and pv["own_history"]["n"] == 0 and pv["ai_summary"]
    rep = _get(f"/stocks/{isin}/report?from=2026-10-26&to=2026-10-30")
    assert rep["headline"] and rep["sections"][1]["kpis"][0]["value"] is not None
    day = _get(f"/days/{isin}/2026-10-29/impact-card")
    assert day["vs_peers"]["peer_avg_volume_ratio"] is not None
    assert client.get(f"/stocks/{isin}/report.pdf?from=2026-10-26&to=2026-10-30").status_code == 200
    sug = _get(f"/assistant/suggestions?isin={isin}")["questions"]
    assert len(sug) == 4
    r = client.post("/assistant/chat", json={"isin": isin, "messages": [{"role": "user", "content": sug[3]}]})
    assert r.status_code == 200 and r.json()["reason"] is None  # la question sur les peers obtient une réponse


@needs_data
def test_unknown_and_too_little_data() -> None:
    assert "detail" in _get("/stocks/XX0000000000/dashboard", 404)
    assert "detail" in _get("/assistant/suggestions?isin=XX0000000000", 404)
    msg = _get(f"/stocks/{QIAGEN}/dashboard", 404)["detail"]
    assert "Not enough Xetra data" in msg and "4 session" in msg
    assert "Not enough Xetra data" in _get(f"/stocks/{QIAGEN}/report?from=2026-10-26&to=2026-10-30", 404)["detail"]


# ---------- /stocks ----------
@needs_data
def test_stocks_universe_with_coverage() -> None:
    r = _get("/stocks")
    stocks = r["stocks"]
    assert len(stocks) == len(etl.get_universe()) and r["default_isin"] == PBB
    assert stocks[0]["isin"] == PBB and stocks[0]["is_selected"] and stocks[0]["peer_basis"] == "manual"
    assert sum(s["is_selected"] for s in stocks) == 1
    by = {s["isin"]: s for s in stocks}
    assert by[PBB]["coverage"] == {"dashboard": True, "events": True, "intraday": True, "sessions": 213}
    assert by[SUSS]["coverage"]["events"] is False and by[SUSS]["peer_basis"] == "index"
    assert [h["index"] for h in by[SUSS]["index_history"]] == ["SDAX", "MDAX"]
    assert by[QIAGEN]["coverage"]["dashboard"] is False
    assert {s["index"] for s in stocks} == {"DAX", "MDAX", "SDAX"}


# ---------- peers du même indice À LA DATE ----------
@needs_data
def test_index_peers_follow_index_change() -> None:
    before, after = pd.Timestamp("2026-06-19"), pd.Timestamp("2026-06-22")
    assert data.index_on(SUSS, before) == "SDAX" and data.index_on(SUSS, after) == "MDAX"
    p_before, p_after = set(data.peers_on(SUSS, before)), set(data.peers_on(SUSS, after))
    assert all(data.index_on(p, before) == "SDAX" for p in p_before)
    assert all(data.index_on(p, after) == "MDAX" for p in p_after)
    assert SUSS not in p_before | p_after
    assert len(p_before & p_after) < 10  # seuls les émetteurs qui ont changé d'indice le même jour sont dans les deux
    # Médiane peers d'un jour = médiane des spreads des autres membres de l'indice ce jour-là
    from app.analytics.dashboard import _peer_spread_median

    med = _peer_spread_median(SUSS)
    for day, peers in ((before, p_before), (after, p_after)):
        vals = [data.spread_series(p).get(day, np.nan) for p in peers]
        assert med[day] == pytest.approx(np.nanmedian(vals))


@needs_data
def test_manual_peers_unchanged_for_pbb() -> None:
    from app import config

    assert data.peer_basis(PBB) == "manual"
    assert data.peers_of(PBB) == config.PEERS[PBB]
    assert data.peers_on(PBB, pd.Timestamp("2026-03-02")) == config.PEERS[PBB]


# ---------- Impact_bps NaN -> null, jamais 0 ----------
@needs_data
def test_nan_spread_is_null_not_zero(monkeypatch) -> None:
    from app.analytics import build_dashboard

    real = data.spread_series(STO).copy()
    day = real.index[100]
    patched = real.copy()
    patched.loc[day] = np.nan  # carnet trop mince pour 25 000 €
    orig = data.spread_series
    monkeypatch.setattr(data, "spread_series", lambda isin, *a, **k: patched if isin == STO else orig(isin, *a, **k))
    d = build_dashboard(STO, "2026-01-02", "2026-10-30")
    row = next(r for r in d["series"] if r["date"] == day.strftime("%Y-%m-%d"))
    assert row["spread_bps"] is None
    assert d["kpis"]["avg_spread_bps"] == pytest.approx(round(patched.mean(), 1))  # NaN ignoré, pas compté pour 0


# ---------- seuils et décisions : par ISIN ----------
@needs_data
def test_thresholds_and_decisions_are_per_issuer() -> None:
    base_pbb = _get(f"/thresholds?isin={PBB}")["values"]
    r = client.put("/thresholds", json={"isin": SUSS, "values": {"net_flow_adtv_pct": 60}})
    assert r.status_code == 200 and r.json()["custom"] is True
    try:
        assert _get(f"/thresholds?isin={PBB}")["values"] == base_pbb
        assert _get(f"/thresholds?isin={SUSS}")["values"]["net_flow_adtv_pct"] == 60
    finally:
        client.post("/thresholds/reset", json={"isin": SUSS})
    r = client.post("/decisions", json={"item_type": "anomaly", "item_id": "2026-10-27|volume_spike|test",
                                        "isin": KWS, "decision": "approved", "note": "rollout test"})
    assert r.status_code == 200
    assert all(d["isin"] == KWS for d in _get(f"/decisions?isin={KWS}")["decisions"])
    assert all(d["isin"] == PBB for d in _get(f"/decisions?isin={PBB}")["decisions"])
