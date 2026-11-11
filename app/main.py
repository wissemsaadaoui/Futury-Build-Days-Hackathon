"""Point d'entrée FastAPI – propriétaire : partenaire back-end.

Lancer : uvicorn app.main:app --reload --port 8000  (doc : /docs, spec : /openapi.json)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api import health

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

app.include_router(health.router)
