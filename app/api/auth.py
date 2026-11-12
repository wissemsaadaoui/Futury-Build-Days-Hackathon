"""Login applicatif par Bearer token (fonctionne aussi cross-site : front local -> API du VPS, sans cookie).

POST /auth/login {password} -> {"token", "expires_at"} (token signé HMAC-SHA256, 12 h) ; 401 après 1 s sinon
GET  /auth/me               -> 200 si "Authorization: Bearer <token>" est valide, 401 sinon
`require_token` (middleware) : 401 sur toute route sans token valide, sauf /auth/login, /health et OPTIONS
(/docs et /openapi.json compris). Une seule vérification : `request_is_authenticated`.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import config

router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_TTL_S = 12 * 3600
FAILED_LOGIN_DELAY_S = 1.0
TOKEN_VERSION = "v1"
PUBLIC_PATHS = {"/auth/login", "/health"}


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: str  # ISO 8601, Europe/Berlin


def _sign(payload: str) -> str:
    return hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(now: float | None = None) -> tuple[str, int]:
    """Jeton « v1.<expiration unix>.<signature> » (URL-safe) ; rien de secret dedans, seule la signature compte."""
    exp = int((now if now is not None else time.time()) + TOKEN_TTL_S)
    payload = f"{TOKEN_VERSION}.{exp}"
    return f"{payload}.{_sign(payload)}", exp


def token_is_valid(token: str | None, now: float | None = None) -> bool:
    parts = (token or "").split(".")
    if len(parts) != 3 or parts[0] != TOKEN_VERSION or not parts[1].isdigit():
        return False
    if not hmac.compare_digest(parts[2], _sign(f"{parts[0]}.{parts[1]}")):
        return False
    return int(parts[1]) > (now if now is not None else time.time())


def request_is_authenticated(request: Request) -> bool:
    """LA vérification, utilisée par le middleware et par /auth/me."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return scheme.lower() == "bearer" and token_is_valid(token.strip())


def _password_ok(given: str) -> bool:
    expected = config.APP_PASSWORD
    # Pas de mot de passe configuré -> aucun login possible (jamais d'accès ouvert par défaut)
    return bool(expected) and secrets.compare_digest(given.encode(), expected.encode())


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    if not _password_ok(body.password):
        await asyncio.sleep(FAILED_LOGIN_DELAY_S)  # ralentit le brute force
        raise HTTPException(status_code=401, detail="Invalid password")
    token, exp = make_token()
    return LoginResponse(token=token, expires_at=datetime.fromtimestamp(exp, ZoneInfo(config.TZ)).isoformat())


@router.get("/me")
def me(request: Request) -> dict[str, bool]:
    if not request_is_authenticated(request):  # déjà filtré par le middleware ; gardé si la route est réutilisée
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"authenticated": True}


async def require_token(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Middleware HTTP : 401 JSON sans token valide (sauf routes publiques et preflight CORS)."""
    public = request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS
    if not public and not request_is_authenticated(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)
