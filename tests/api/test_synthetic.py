"""Without data/raw, the API serves synthetic market data (app/etl/synthetic.py) that matches mocks/*.json.

Run in a subprocess: install() replaces the app.etl loaders for the whole process.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from app import config

SCRIPT = """
import json
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    token = c.post("/auth/login", json={"password": "test-password"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    dash = c.get("/stocks/DE0008019001/dashboard?from=2026-08-17&to=2026-10-09", headers=h)
    card = c.get("/events/evt_002/impact-card", headers=h)
    print(json.dumps({"dash": dash.status_code, "card": card.status_code, "body": dash.json()}))
"""


def test_api_runs_on_synthetic_data_without_xetra_files() -> None:
    empty = tempfile.mkdtemp()
    env = {**os.environ, "DATA_DIR": empty, "PROCESSED_DIR": empty, "SYNTHETIC_DATA": "auto", "LLM_PROVIDER": "",
           "APP_PASSWORD": "test-password", "SESSION_SECRET": "test-session-secret",
           "DECISIONS_DB": os.path.join(empty, "decisions.db")}
    out = subprocess.run([sys.executable, "-c", SCRIPT], env=env, cwd=config.ROOT, capture_output=True, text=True,
                         timeout=300, check=True)
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["dash"] == 200 and res["card"] == 200
    body = res["body"]
    assert set(body["_data_status"].values()) == {"synthetic"}
    mock = json.loads((config.MOCKS_DIR / "dashboard.json").read_text(encoding="utf-8"))
    assert body["series"] == mock["series"]  # same seed: the mocks are exactly what the API serves
