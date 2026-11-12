"""Login applicatif (remplace le basic auth Caddy) : mot de passe unique, cookie de session signé (HMAC-SHA256).

POST /auth/login {password} -> cookie HttpOnly, SameSite=Lax, Secure=COOKIE_SECURE, 12 h ; 401 + 1 s sinon
POST /auth/logout           -> efface le cookie
GET  /auth/me               -> 200 si connecté, 401 sinon
`require_session` (middleware) : 401 sur toute route sans cookie valide, sauf /auth/*, /health et OPTIONS.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import config

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "iih_session"
SESSION_TTL_S = 12 * 3600
FAILED_LOGIN_DELAY_S = 1.0
PUBLIC_PREFIXES = ("/auth/",)
PUBLIC_PATHS = {"/health"}


class LoginRequest(BaseModel):
    password: str


def _sign(payload: str) -> str:
    return hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(now: float | None = None) -> str:
    """Jeton « <expiration unix>.<signature> » : rien de secret dedans, seule la signature compte."""
    exp = int((now if now is not None else time.time()) + SESSION_TTL_S)
    return f"{exp}.{_sign(str(exp))}"


def valid_token(token: str | None, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    if not exp.isdigit() or not hmac.compare_digest(sig, _sign(exp)):
        return False
    return int(exp) > (now if now is not None else time.time())


def _password_ok(given: str) -> bool:
    expected = config.APP_PASSWORD
    # Pas de mot de passe configuré -> aucun login possible (jamais d'accès ouvert par défaut)
    return bool(expected) and secrets.compare_digest(given.encode(), expected.encode())


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict[str, bool]:
    if not _password_ok(body.password):
        await asyncio.sleep(FAILED_LOGIN_DELAY_S)  # ralentit le brute force
        raise HTTPException(status_code=401, detail="Invalid password")
    response.set_cookie(
        COOKIE_NAME,
        make_token(),
        max_age=SESSION_TTL_S,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        path="/",
    )
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=config.COOKIE_SECURE)
    return {"authenticated": False}


@router.get("/me")
def me(request: Request) -> dict[str, bool]:
    if not valid_token(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"authenticated": True}


async def require_session(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Middleware HTTP : /docs et /openapi.json sont protégés comme le reste."""
    path = request.url.path
    public = request.method == "OPTIONS" or path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)
    if not public and not valid_token(request.cookies.get(COOKIE_NAME)):
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return await call_next(request)
