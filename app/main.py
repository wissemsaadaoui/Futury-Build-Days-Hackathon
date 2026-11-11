"""Point d'entrée FastAPI – propriétaire : partenaire back-end.

Lancer : uvicorn app.main:app --reload --port 8000  (doc : /docs, spec : /openapi.json)
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config
from app.analytics import NotFound
from app.api import compare, health, impact_cards, stocks

app = FastAPI(
    title="Issuer Intelligence Hub API",
    description="Xetra trading analytics and impact cards for Investor Relations teams. "
    "Descriptive analysis of historical Xetra trading data. Not investment advice.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in config.FRONTEND_ORIGIN.split(",") if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)



@app.exception_handler(NotFound)
async def not_found(_: Request, exc: NotFound) -> JSONResponse:
    """ISIN, event_id ou jour inconnu (levé par app.analytics) -> 404 {"detail": "..."}."""
    return JSONResponse(status_code=404, content={"detail": exc.args[0] if exc.args else "Not found"})


for module in (health, stocks, impact_cards, compare):
    app.include_router(module.router)
