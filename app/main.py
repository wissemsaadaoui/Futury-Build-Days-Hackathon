"""Point d'entrée FastAPI – propriétaire : partenaire back-end.

Lancer : uvicorn app.main:app --reload --port 8000  (doc : /docs, spec : /openapi.json)
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config, etl
from app.analytics import NotFound
from app.api import auth, compare, health, impact_cards, stocks


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Charge toutes les données une seule fois au démarrage (~5 s) : les requêtes sont ensuite rapides."""
    etl.warm_up()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Issuer Intelligence Hub API",
    description="Xetra trading analytics and impact cards for Investor Relations teams. "
    "Descriptive analysis of historical Xetra trading data. Not investment advice.",
    version="0.1.0",
)

# Bearer token obligatoire (sauf /auth/login, /health, OPTIONS). Ajouté AVANT CORS : CORS reste la couche externe,
# donc les 401 portent aussi les en-têtes CORS.
app.middleware("http")(auth.require_token)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in config.FRONTEND_ORIGIN.split(",") if o.strip()],  # liste explicite, jamais "*"
    allow_credentials=False,  # pas de cookie : le token passe dans l'en-tête Authorization
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.exception_handler(NotFound)
async def not_found(_: Request, exc: NotFound) -> JSONResponse:
    """ISIN, event_id ou jour inconnu (levé par app.analytics) -> 404 {"detail": "..."}."""
    return JSONResponse(status_code=404, content={"detail": exc.args[0] if exc.args else "Not found"})


for module in (auth, health, stocks, impact_cards, compare):
    app.include_router(module.router)
