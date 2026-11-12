"""/thresholds : lecture, modification (bornes -> 422), reset, aperçu, journal."""
from __future__ import annotations

import pytest

from app import etl, store
from tests.helpers import logged_in_client

PBB = "DE0008019001"
pytestmark = pytest.mark.skipif(etl.load_xlm().empty, reason="data/raw/spreads absent")


@pytest.fixture()
def client():
    c = logged_in_client()
    c.post("/thresholds/reset", json={"isin": PBB})
    yield c
    c.post("/thresholds/reset", json={"isin": PBB})


def _n_alerts(c) -> int:
    return len(c.get(f"/stocks/{PBB}/dashboard").json()["anomalies"])


def test_get_defaults(client):
    r = client.get(f"/thresholds?isin={PBB}").json()
    assert r["values"] == r["defaults"] and r["custom"] is False
    assert r["bounds"]["volume_z_min"]["min"] == 1.0 and r["bounds"]["sweep_min_trades"]["integer"] is True


def test_put_changes_alerts_and_is_logged(client):
    before = _n_alerts(client)
    r = client.put("/thresholds", json={"isin": PBB, "values": {"net_flow_adtv_pct": 60}})
    assert r.status_code == 200 and r.json()["custom"] is True and r.json()["values"]["net_flow_adtv_pct"] == 60
    assert _n_alerts(client) < before
    log = store.list_decisions(PBB)
    assert log[0]["decision"] == "threshold_changed" and log[0]["item_id"] == "net_flow_adtv_pct"
    assert (log[0]["old_value"], log[0]["new_value"]) == ("20", "60")


def test_out_of_bounds_is_422(client):
    r = client.put("/thresholds", json={"isin": PBB, "values": {"volume_z_min": 0.2}})
    assert r.status_code == 422 and "volume_z_min" in r.json()["detail"]["errors"]
    assert client.put("/thresholds", json={"isin": PBB, "values": {"nope": 1}}).status_code == 422
    assert client.get(f"/thresholds?isin={PBB}").json()["custom"] is False


def test_reset_and_preview(client):
    client.put("/thresholds", json={"isin": PBB, "values": {"volume_z_min": 4}})
    r = client.post("/thresholds/reset", json={"isin": PBB}).json()
    assert r["values"] == r["defaults"] and not r["custom"]
    p = client.post("/thresholds/preview", json={"isin": PBB, "values": {"net_flow_adtv_pct": 200}}).json()
    assert p["alerts_current"] == 149 and p["alerts_with_values"] < 149
    assert client.get(f"/thresholds?isin={PBB}").json()["custom"] is False
    assert client.get("/thresholds?isin=XX0000000000").status_code == 404
