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
DEMO_ISINS = ["DE0008019001"]  # Deutsche Pfandbriefbank AG (pbb)  (modifié par Alfred – démo pbb)

# Notional de référence pour spread_bps (colonne Impact_bps du XLM)
REF_NOTIONAL = 25_000.0
BASELINE_DAYS = 20
WINDOW_DAYS = 5
MARKET_CLOSE = "17:30"  # annonce après cette heure -> jour de trading suivant

# Peers choisis à la main (pas de colonne secteur dans les données)
# modifié par Alfred – démo pbb : financières SDAX/MDAX
# Couverture XLM : ProCredit seulement dès le 14.10.2026 (entrée SDAX), W&W jusqu'au 05.10.2026 (sortie SDAX)
PEERS: dict[str, list[str]] = {
    "DE0008019001": [
        "DE000A161N30",  # GRENKE (GLJ)
        "DE0005493365",  # Hypoport (HYQ)
        "DE0006569908",  # MLP (MLP)
        "DE0006223407",  # ProCredit Holding (PCZ)
        "DE0008051004",  # Wüstenrot & Württembergische (WUW)
        "DE000FTG1111",  # flatexDEGIRO (FTK, MDAX)
    ],
}

# modifié par Alfred – démo pbb
NAMES: dict[str, str] = {
    "DE0008019001": "Deutsche Pfandbriefbank AG",
    "DE000A161N30": "GRENKE AG",
    "DE0005493365": "Hypoport SE",
    "DE0006569908": "MLP SE",
    "DE0006223407": "ProCredit Holding AG",
    "DE0008051004": "Wüstenrot & Württembergische AG",
    "DE000FTG1111": "flatexDEGIRO AG",
}

# modifié par Alfred – démo pbb
SECTORS: dict[str, str] = {isin: "Financials" for isin in NAMES}

# LLM (assistant)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "")  # "anthropic" | "openai" | "" (= templates seulement)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "20"))
