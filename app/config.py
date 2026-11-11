"""Configuration.

TEMPORAIRE (créé par Alfred pour démarrer l'analyse) – propriétaire : partenaire back-end.
Il peut le réécrire librement en gardant les noms ci-dessous, utilisés par app/analytics.
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
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data" / "raw"))
EVENTS_CSV = Path(os.getenv("EVENTS_CSV", ROOT / "data" / "events.csv"))
MOCKS_DIR = ROOT / "mocks"

TZ = "Europe/Berlin"
DEMO_ISINS = ["DE000A1K0235"]  # SUSS MicroTec SE  (modifié par Alfred – démo SUSS)

# Notional de référence pour spread_bps (colonne Impact_bps du XLM)
REF_NOTIONAL = 25_000.0
BASELINE_DAYS = 20
WINDOW_DAYS = 5
MARKET_CLOSE = "17:30"  # annonce après cette heure -> jour de trading suivant

# Peers choisis à la main (pas de colonne secteur dans les données)
# modifié par Alfred – démo SUSS : équipementiers / semi-conducteurs MDAX/SDAX
PEERS: dict[str, list[str]] = {
    "DE000A1K0235": [
        "DE000A0WMPJ6",  # Aixtron (AIXA)
        "DE000A2NB601",  # Jenoptik (JEN)
        "DE000WAF3001",  # Siltronic (WAF)
        "DE0005677108",  # Elmos Semiconductor (ELG)
    ],
}

# modifié par Alfred – démo SUSS
NAMES: dict[str, str] = {
    "DE000A1K0235": "SUSS MicroTec SE",
    "DE000A0WMPJ6": "AIXTRON SE",
    "DE000A2NB601": "JENOPTIK AG",
    "DE000WAF3001": "Siltronic AG",
    "DE0005677108": "Elmos Semiconductor SE",
}

# modifié par Alfred – démo SUSS (semiconductor equipment)
SECTORS: dict[str, str] = {isin: "Technology" for isin in NAMES}

# LLM (assistant)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "")  # "anthropic" | "openai" | "" (= templates seulement)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "20"))
