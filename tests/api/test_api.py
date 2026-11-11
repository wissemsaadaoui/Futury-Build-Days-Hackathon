from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app import config, etl
from app.main import app
from app.schemas import (
    CompareResponse,
    DashboardResponse,
    EventPreviewResponse,
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
        ("impact-card-voting-rights", ImpactCardResponse),
        ("event-preview", EventPreviewResponse),
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


# ---------- Phase 4 : export PDF ----------
def _pdf(url: str):
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code, r.text[:300])
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    return r


@needs_data
def test_impact_card_pdf_url_downloads_pdf() -> None:
    card = _get("/events/evt_002/impact-card")
    r = _pdf(card["export"]["pdf_url"])  # T16 : export.pdf_url pointe vers la route PDF
    assert r.headers["content-disposition"] == 'attachment; filename="pbb_impact_2026-02-13.pdf"'


@needs_data
def test_report_pdf_url_downloads_pdf() -> None:
    report = _get(f"/stocks/{PBB}/report")
    r = _pdf(report["export"]["pdf_url"])
    assert r.headers["content-disposition"].startswith('attachment; filename="pbb_report_')


@needs_data
def test_pdfs_fit_on_one_a4_page() -> None:
    for url in ("/events/evt_002/impact-card.pdf", f"/stocks/{PBB}/report.pdf"):
        assert re.search(rb"/Count (\d+)", _pdf(url).content).group(1) == b"1", url


@pytest.mark.parametrize("url", ["/events/evt_unknown/impact-card.pdf", "/stocks/XX0000000000/report.pdf"])
@needs_data
def test_pdf_not_found(url: str) -> None:
    assert "detail" in _get(url, 404)


# ---------- v0.3 : level_break, detail_url, pre_disclosure_activity ----------
@needs_data
def test_dashboard_full_year_validates() -> None:
    """Toute l'année (période par défaut, scène a de la démo) : toutes les anomalies passent le schéma."""
    d = _get(f"/stocks/{PBB}/dashboard")
    assert d["anomalies"]


@needs_data
def test_level_break_has_level_fields() -> None:
    anomalies = _get(f"/stocks/{PBB}/dashboard?from=2026-08-01&to=2026-08-31")["anomalies"]
    breaks = [a for a in anomalies if a["type"] == "level_break"]
    assert breaks
    for a in breaks:
        assert a["level_type"] in ("support", "resistance")
        assert a["level_price"] > 0


@needs_data
def test_every_anomaly_has_a_working_detail_url() -> None:
    anomalies = _get(f"/stocks/{PBB}/dashboard")["anomalies"]
    for a in anomalies:
        expected = f"/events/{a['linked_event_id']}/impact-card" if a["linked_event_id"] else f"/days/{PBB}/{a['date']}/impact-card"
        assert a["detail_url"] == expected
    for url in sorted({a["detail_url"] for a in anomalies})[:5]:
        _get(url)


@needs_data
def test_pre_disclosure_activity_only_on_voting_rights() -> None:
    voting = _get("/events/evt_019/impact-card")
    assert voting["event"]["type"] == "voting_rights"
    pre = voting["pre_disclosure_activity"]
    assert pre and pre["window"]["sessions"] > 0 and pre["summary"]
    assert pre["window"]["from"] <= pre["window"]["to"] < voting["event"]["trading_day"]
    assert _get("/events/evt_002/impact-card")["pre_disclosure_activity"] is None


# ---------- Phase 4 : PDF des day cards (scènes c–f de la démo) ----------
@needs_data
def test_day_card_pdf_url_downloads_pdf() -> None:
    card = _get(f"/days/{PBB}/2026-02-12/impact-card")
    assert card["export"]["pdf_url"] == f"/days/{PBB}/2026-02-12/impact-card.pdf"
    r = _pdf(card["export"]["pdf_url"])
    assert r.headers["content-disposition"] == 'attachment; filename="pbb_impact_2026-02-12.pdf"'
    assert re.search(rb"/Count (\d+)", r.content).group(1) == b"1"


@needs_data
def test_voting_rights_pdf_with_pre_disclosure_fits_one_page() -> None:
    r = _pdf("/events/evt_019/impact-card.pdf")
    assert re.search(rb"/Count (\d+)", r.content).group(1) == b"1"


@pytest.mark.parametrize("url", [f"/days/{PBB}/2026-06-06/impact-card.pdf", "/days/XX0000000000/2026-06-05/impact-card.pdf"])
@needs_data
def test_day_card_pdf_not_found(url: str) -> None:
    assert "detail" in _get(url, 404)


# ---------- v0.4 : /compare index=ALL, event preview, section Alerts du report ----------
@needs_data
def test_compare_all_indices_is_default() -> None:
    explicit = _get("/compare?type=voting_rights&index=ALL")
    assert explicit["filter"]["index"] == "ALL"
    assert _get("/compare?type=voting_rights") == explicit  # index absent -> ALL


@needs_data
def test_event_preview_upcoming_quarterly_results() -> None:
    p = _get(f"/stocks/{PBB}/event-preview?type=quarterly_results")
    assert p["stock"]["isin"] == PBB and p["event_type"] == "quarterly_results"
    assert p["own_history"]["n"] == 2
    assert p["upcoming"]["date"] == "2026-11-12"
    assert p["confidence"] in ("low", "medium", "high") and p["ai_summary"]


@needs_data
def test_event_preview_as_of_excludes_later_events() -> None:
    p = _get(f"/stocks/{PBB}/event-preview?type=quarterly_results&date=2026-08-13")
    assert p["as_of"] == "2026-08-13"
    assert p["own_history"]["n"] == 1  # H1 du 13.08 exclu
    assert all(e["date"] < "2026-08-13" for e in p["own_history"]["events"])


@needs_data
def test_event_preview_without_history_has_null_stats() -> None:
    p = _get(f"/stocks/{PBB}/event-preview?type=dividend")
    assert p["own_history"]["n"] == 0
    assert p["own_history"]["spread_change_pct"] == {"n": 0, "median": None, "min": None, "max": None}


@pytest.mark.parametrize(
    "url, status",
    [
        ("/stocks/XX0000000000/event-preview?type=ad_hoc", 404),
        (f"/stocks/{PBB}/event-preview?type=nope", 422),
        (f"/stocks/{PBB}/event-preview", 422),
    ],
)
@needs_data
def test_event_preview_errors(url: str, status: int) -> None:
    assert "detail" in _get(url, status)


@needs_data
def test_report_alerts_section_in_json_and_pdf() -> None:
    report = _get(f"/stocks/{PBB}/report")
    alerts = [s for s in report["sections"] if s.get("alert_days")]
    assert alerts and all(k["unit"] == "count" for k in alerts[0]["kpis"])
    assert all(d["n_alerts"] >= d["n_high"] for d in alerts[0]["alert_days"])
    r = _pdf(f"/stocks/{PBB}/report.pdf")
    assert re.search(rb"/Count (\d+)", r.content).group(1) == b"1"
