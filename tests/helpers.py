"""Client de test authentifié : POST /auth/login, puis "Authorization: Bearer <token>" sur chaque requête."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import config
from app.main import app


def login_token(client: TestClient | None = None) -> str:
    r = (client or TestClient(app)).post("/auth/login", json={"password": config.APP_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def logged_in_client() -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {login_token()}"})
