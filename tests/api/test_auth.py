"""Login applicatif par Bearer token, routes protégées, CORS (app/api/auth.py)."""
from __future__ import annotations

import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import auth
from app.main import app
from tests.helpers import login_token

LOCAL_FRONT = "http://localhost:5173"


@pytest.fixture()
def anon() -> TestClient:
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_without_token_protected_routes_return_401(anon):
    for url in ("/stocks", "/stocks/DE0008019001/events", "/docs", "/openapi.json", "/auth/me"):
        r = anon.get(url)
        assert r.status_code == 401, url
        assert r.json() == {"detail": "Not authenticated"}


def test_public_routes_stay_open(anon):
    assert anon.get("/health").status_code == 200


@pytest.mark.parametrize(
    "header",
    [
        "Bearer not-a-token",
        "Bearer v1.9999999999.deadbeef",  # signature fausse
        "Basic dXNlcjpwYXNz",  # mauvais schéma
        "Bearer",  # vide
    ],
)
def test_invalid_token_is_401(anon, header):
    assert anon.get("/stocks", headers={"Authorization": header}).status_code == 401


def test_expired_or_tampered_token_is_401(anon):
    old, _ = auth.make_token(now=time.time() - auth.TOKEN_TTL_S - 10)  # expiré depuis 10 s
    assert anon.get("/stocks", headers=_bearer(old)).status_code == 401
    token, exp = auth.make_token()
    v, _, sig = token.split(".")
    assert anon.get("/stocks", headers=_bearer(f"{v}.{exp + 3600}.{sig}")).status_code == 401  # expiration allongée
    assert not auth.token_is_valid(token, now=exp + 1)


def test_wrong_password_is_401_and_delayed(anon):
    t0 = time.monotonic()
    r = anon.post("/auth/login", json={"password": "wrong"})
    assert r.status_code == 401
    assert time.monotonic() - t0 >= auth.FAILED_LOGIN_DELAY_S * 0.9
    assert "token" not in r.json()


def test_no_configured_password_means_no_login(anon, monkeypatch):
    monkeypatch.setattr(config, "APP_PASSWORD", "")
    assert anon.post("/auth/login", json={"password": ""}).status_code == 401


def test_login_returns_token_then_routes_work(anon):
    r = anon.post("/auth/login", json={"password": config.APP_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"token", "expires_at"}
    assert "set-cookie" not in r.headers  # plus aucun cookie
    hours = (datetime.fromisoformat(body["expires_at"]).timestamp() - time.time()) / 3600
    assert 11.9 < hours <= 12
    h = _bearer(body["token"])
    assert anon.get("/stocks", headers=h).status_code == 200
    assert anon.get("/auth/me", headers=h).json() == {"authenticated": True}
    assert anon.get("/openapi.json", headers=h).status_code == 200


def test_preflight_from_local_front_allows_authorization(anon):
    r = anon.options(
        "/stocks",
        headers={
            "Origin": LOCAL_FRONT,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == LOCAL_FRONT  # jamais "*"
    assert "authorization" in r.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in r.headers


def test_cors_headers_on_200_and_401(anon):
    ok = anon.get("/stocks", headers={"Origin": LOCAL_FRONT, **_bearer(login_token(anon))})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == LOCAL_FRONT
    denied = anon.get("/stocks", headers={"Origin": LOCAL_FRONT})  # 401 lisible par le front
    assert denied.status_code == 401 and denied.headers["access-control-allow-origin"] == LOCAL_FRONT


def test_unknown_origin_gets_no_cors_header(anon):
    r = anon.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
