from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import config, etl
from app.main import app
from app.schemas import (
    CompareResponse,
    DashboardResponse,
    EventsResponse,
    ImpactCardResponse,
    ReportResponse,
    StocksResponse,
)

PBB = "DE0008019001"
client = TestClient(app)

needs_data = pytest.mark.skipif(etl.load_xlm().empty, reason="data/raw/spreads absent")


def _strict_json(text: str):
    """json.loads qui échoue sur NaN / Infinity (interdits par CLAUDE.md)."""

    def reject(c: str):
        raise ValueError(f"non-JSON constant {c}")

    return json.loads(text, parse_constant=reject)


def _get(url: str, status: int = 200) -> dict:
    r = client.get(url)
    assert r.status_code == status, (url, r.status_code, r.text[:300])
    return _strict_json(r.text)


# ---------- T5 : chaque mock se valide avec son schéma ----------
@pytest.mark.parametrize(
    "mock, model",
    [
        ("stocks", StocksResponse),
        ("dashboard", DashboardResponse),
        ("events", EventsResponse),
        ("impact-card", ImpactCardResponse),
        ("compare", CompareResponse),
        ("report", ReportResponse),
    ],
)
def test_mock_validates(mock: str, model) -> None:
    model.model_validate(json.loads((config.MOCKS_DIR / f"{mock}.json").read_text(encoding="utf-8")))


# ---------- T6 : routes ----------
def test_health() -> None:
    assert _get("/health") == {"status": "ok"}


@needs_data
def test_stocks_lists_pbb_selected_with_peers() -> None:
    stocks = _get("/stocks")["stocks"]
    selected = [s for s in stocks if s["is_selected"]]
    assert [s["isin"] for s in selected] == [PBB]
    assert selected[0]["ticker"] == "PBB"
    assert {s["isin"] for s in stocks} <= {PBB, *config.PEERS[PBB]}


@needs_data
def test_dashboard() -> None:
    d = _get(f"/stocks/{PBB}/dashboard?from=2026-03-01&to=2026-03-31")
    assert d["stock"]["isin"] == PBB
    assert d["period"] == {"from": "2026-03-02", "to": "2026-03-31"}  # 01.03 = dimanche -> 1er jour de trading
    assert d["series"] and "_data_status" in d


@needs_data
def test_events_and_impact_card() -> None:
    events = _get(f"/stocks/{PBB}/events")["events"]
    assert events
    card = _get(f"/events/{events[0]['event_id']}/impact-card")
    assert card["event"]["event_id"] == events[0]["event_id"]
    assert card["stock"]["isin"] == PBB


@needs_data
def test_day_impact_card_has_no_event() -> None:
    card = _get(f"/days/{PBB}/2026-06-05/impact-card")
    assert card["event"] is None


@needs_data
def test_compare() -> None:
    c = _get("/compare?type=quarterly_results&index=SDAX&from=2026-01-01&to=2026-10-30")
    assert c["filter"]["type"] == "quarterly_results"
    assert c["summary"]["n_events"] == len(c["events"])


@needs_data
def test_report() -> None:
    r = _get(f"/stocks/{PBB}/report")
    assert r["stock"]["isin"] == PBB
    assert r["disclaimer"]


# ---------- erreurs ----------
@pytest.mark.parametrize(
    "url",
    [
        "/stocks/XX0000000000/dashboard",
        "/stocks/XX0000000000/events",
        "/stocks/XX0000000000/report",
        "/events/evt_unknown/impact-card",
        f"/days/{PBB}/2026-06-06/impact-card",  # samedi : pas un jour de trading
    ],
)
@needs_data
def test_not_found(url: str) -> None:
    assert "detail" in _get(url, 404)


@pytest.mark.parametrize(
    "url",
    [
        f"/stocks/{PBB}/dashboard?from=2026-13-01",
        f"/stocks/{PBB}/dashboard?from=2026-06-01&to=2026-05-01",
        "/compare?type=unknown&index=SDAX",
        "/compare?type=agm&index=TECDAX",
        f"/days/{PBB}/not-a-date/impact-card",
    ],
)
def test_invalid_params(url: str) -> None:
    assert "detail" in _get(url, 422)
