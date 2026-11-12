"""Client de test déjà connecté (cookie de session posé par POST /auth/login)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import config
from app.main import app


def logged_in_client() -> TestClient:
    client = TestClient(app)
    r = client.post("/auth/login", json={"password": config.APP_PASSWORD})
    assert r.status_code == 200, r.text
    return client
