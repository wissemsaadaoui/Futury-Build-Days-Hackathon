"""/decisions : approve / dismiss, journal, décision renvoyée avec les alertes et résumés IA, top 5 sans dismissed."""
from __future__ import annotations

import pytest

from app import etl
from tests.helpers import logged_in_client

PBB = "DE0008019001"
pytestmark = pytest.mark.skipif(etl.load_xlm().empty, reason="data/raw/spreads absent")


@pytest.fixture()
def client():
    return logged_in_client()


def _anomalies(c) -> list[dict]:
    return c.get(f"/stocks/{PBB}/dashboard").json()["anomalies"]


def test_dismissed_alert_leaves_the_top5_and_is_logged(client):
    rows = _anomalies(client)
    top = sorted((r for r in rows if r["rank"]), key=lambda r: r["rank"])
    first = top[0]
    assert first["rank"] == 1 and first["decision"] is None and first["id"]
    r = client.post("/decisions", json={"item_type": first["item_type"], "item_id": first["id"], "isin": PBB,
                                        "decision": "dismissed", "note": "Known index rebalancing"})
    assert r.status_code == 200
    d = r.json()
    assert d["decided_by"] == "ir-team" and d["decided_at"].endswith(("+01:00", "+02:00"))
    after = {x["id"]: x for x in _anomalies(client)}
    assert after[first["id"]]["rank"] is None
    assert after[first["id"]]["decision"]["decision"] == "dismissed"
    assert after[first["id"]]["decision"]["note"] == "Known index rebalancing"
    assert after[top[1]["id"]]["rank"] == 1  # la suivante monte en tête du top 5
    # l'équipe change d'avis : la dernière décision fait foi
    client.post("/decisions", json={"item_type": first["item_type"], "item_id": first["id"], "isin": PBB,
                                    "decision": "approved"})
    assert {x["id"]: x for x in _anomalies(client)}[first["id"]]["rank"] == 1
    log = client.get(f"/decisions?isin={PBB}").json()["decisions"]
    assert [e["decision"] for e in log[:2]] == ["approved", "dismissed"]


def test_ai_summary_decision_on_impact_card(client):
    card = client.get("/events/evt_002/impact-card").json()
    assert card["ai_summary_id"] == "impact:card_evt_002" and card["ai_summary_decision"] is None
    client.post("/decisions", json={"item_type": "ai_summary", "item_id": card["ai_summary_id"], "isin": PBB,
                                    "decision": "approved"})
    assert client.get("/events/evt_002/impact-card").json()["ai_summary_decision"]["decision"] == "approved"


def test_validation(client):
    bad = {"item_type": "alert", "item_id": "x", "isin": PBB, "decision": "maybe"}
    assert client.post("/decisions", json=bad).status_code == 422
    assert client.post("/decisions", json={**bad, "decision": "approved", "item_type": "nope"}).status_code == 422
    assert client.post("/decisions", json={**bad, "decision": "approved", "isin": "XX0000000000"}).status_code == 404
