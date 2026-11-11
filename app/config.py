"""Configuration – propriétaire : partenaire back-end.

Lit `.env` (voir `.env.example`). Les noms ci-dessous sont utilisés par app/analytics et
app/assistant (Alfred) : ne pas les renommer sans prévenir.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv optionnel
    pass

ROOT = Path(__file__).resolve().parents[1]


def _path(env: str, default: Path) -> Path:
    """Chemin lu dans `.env` ; un chemin relatif part de la racine du repo (pas du dossier courant)."""
    p = Path(os.getenv(env) or default)
    return p if p.is_absolute() else ROOT / p


# Données
DATA_DIR = _path("DATA_DIR", ROOT / "data" / "raw")  # spreads/, XETRA/, EUREX/, index_constituents/
PROCESSED_DIR = _path("PROCESSED_DIR", ROOT / "data" / "processed")  # sorties de scripts/ (trades_<ISIN>.csv.gz)
EVENTS_CSV = _path("EVENTS_CSV", ROOT / "data" / "events.csv")
MOCKS_DIR = ROOT / "mocks"

# API
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")  # plusieurs origines : séparées par des virgules

TZ = "Europe/Berlin"
DEMO_ISINS = ["DE0008019001"]  # Deutsche Pfandbriefbank AG (pbb), SDAX

# Notional de référence pour spread_bps (colonne Impact_bps du XLM)
REF_NOTIONAL = 25_000.0
BASELINE_DAYS = 20
WINDOW_DAYS = 5
MARKET_CLOSE = "17:30"  # annonce après cette heure -> jour de trading suivant

# Peers choisis à la main (pas de colonne secteur dans les données) – à remplir (Alfred)
PEERS: dict[str, list[str]] = {
    "DE0008019001": [],
}

NAMES: dict[str, str] = {
    "DE0008019001": "Deutsche Pfandbriefbank AG",
}

SECTORS: dict[str, str] = {
    "DE0008019001": "Financials",
}

# LLM (assistant)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "")  # "anthropic" | "openai" | "" (= templates seulement)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "20"))
