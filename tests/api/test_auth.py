"""Login applicatif : cookie de session signé, routes protégées (app/api/auth.py)."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import auth
from app.main import app


@pytest.fixture()
def anon() -> TestClient:
    return TestClient(app)


def test_without_cookie_protected_routes_return_401(anon):
    for url in ("/stocks", "/stocks/DE0008019001/events", "/docs", "/openapi.json", "/auth/me"):
        r = anon.get(url)
        assert r.status_code == 401, url
        assert r.json() == {"detail": "Not authenticated"}


def test_public_routes_stay_open(anon):
    assert anon.get("/health").status_code == 200
    r = anon.options(
        "/stocks",
        headers={"Origin": config.FRONTEND_ORIGIN.split(",")[0], "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200


def test_wrong_password_is_401_and_delayed(anon):
    t0 = time.monotonic()
    r = anon.post("/auth/login", json={"password": "wrong"})
    assert r.status_code == 401
    assert time.monotonic() - t0 >= auth.FAILED_LOGIN_DELAY_S * 0.9
    assert auth.COOKIE_NAME not in r.cookies
    assert anon.get("/stocks").status_code == 401


def test_good_password_sets_cookie_then_routes_work(anon):
    r = anon.post("/auth/login", json={"password": config.APP_PASSWORD})
    assert r.status_code == 200 and r.json() == {"authenticated": True}
    cookie = r.headers["set-cookie"]
    assert f"{auth.COOKIE_NAME}=" in cookie
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=43200" in cookie
    assert anon.get("/stocks").status_code == 200
    assert anon.get("/auth/me").status_code == 200
    assert anon.get("/openapi.json").status_code == 200


def test_logout_clears_session(anon):
    anon.post("/auth/login", json={"password": config.APP_PASSWORD})
    assert anon.post("/auth/logout").status_code == 200
    assert anon.get("/auth/me").status_code == 401
    assert anon.get("/stocks").status_code == 401


def test_tampered_or_expired_token_rejected():
    token = auth.make_token()
    exp, sig = token.split(".")
    assert auth.valid_token(token)
    assert not auth.valid_token(f"{int(exp) + 3600}.{sig}")  # expiration modifiée -> signature fausse
    assert not auth.valid_token(token, now=int(exp) + 1)  # expiré après 12 h
    assert not auth.valid_token("garbage")
    assert not auth.valid_token(None)


def test_no_configured_password_means_no_login(anon, monkeypatch):
    monkeypatch.setattr(config, "APP_PASSWORD", "")
    assert anon.post("/auth/login", json={"password": ""}).status_code == 401


def test_cors_allows_credentials_for_frontend_origin(anon):
    origin = config.FRONTEND_ORIGIN.split(",")[0].strip()
    r = anon.get("/health", headers={"Origin": origin})
    assert r.headers.get("access-control-allow-origin") == origin  # jamais "*"
    assert r.headers.get("access-control-allow-credentials") == "true"
    r = anon.get("/stocks", headers={"Origin": origin})  # 401 lisible par le front (en-têtes CORS présents)
    assert r.status_code == 401 and r.headers.get("access-control-allow-origin") == origin
