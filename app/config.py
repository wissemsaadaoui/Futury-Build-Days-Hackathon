"""Configuration – propriétaire : partenaire back-end.

Lit `.env` (voir `.env.example`). Les noms ci-dessous sont utilisés par app/analytics et
app/assistant (Alfred) : ne pas les renommer sans prévenir.
"""
from __future__ import annotations

import os
import secrets
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
# Sans data/raw : données de marché SYNTHÉTIQUES (app/etl/synthetic.py). "auto" (défaut) | "on" | "off"
SYNTHETIC_DATA = os.getenv("SYNTHETIC_DATA", "auto").strip().lower()

# API
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173,http://localhost:5174")  # plusieurs origines : séparées par des virgules

# Login applicatif (app/api/auth.py) – jamais de valeur réelle dans le code
APP_PASSWORD = os.getenv("APP_PASSWORD", "")  # vide = aucun login possible
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_hex(32)  # signe les tokens ; vide = aléatoire (tokens perdus au redémarrage)

TZ = "Europe/Berlin"
DEMO_ISINS = ["DE0008019001"]  # Deutsche Pfandbriefbank AG (pbb), SDAX

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

# Alertes sur les exécutions (ajouté par Alfred – mocks/API.md v0.2 §3 et §5.2)
# Ce sont des EXÉCUTIONS (trades on-book), pas des investisseurs identifiés.
ALERT_ADTV_DAYS = 30                 # ADTV = moyenne du turnover_eur (OHLC) des 30 séances précédentes
# v2 (Alfred, 2026-11-11) : 10 % de l'ADTV, plus de seuil absolu. Sur pbb : large_trade 58 -> 13 jours,
# aggressor_sweep 103 -> 38 jours (sur 213). Le seuil absolu de 500 k€ dominait pour les titres liquides
# (flatexDEGIRO : 203 jours sur 213) : None = désactivé.
ALERT_LARGE_TRADE_EUR: float | None = None  # seuil absolu optionnel (€) : alerte si >= ce montant OU >= la part d'ADTV
ALERT_LARGE_TRADE_ADTV_SHARE = 0.10  # large_trade : exécution unique >= 10 % de l'ADTV 30 jours
ALERT_SWEEP_ADTV_SHARE = 0.10        # aggressor_sweep : somme de la rafale >= 10 % de l'ADTV 30 jours
ALERT_SWEEP_MIN_TRADES = 3           # aggressor_sweep : au moins 3 exécutions
ALERT_SWEEP_WINDOW_S = 1.0           # aggressor_sweep : exécutions consécutives du même côté en <= 1 s
ALERT_NET_FLOW_ADTV_SHARE = 0.20     # net_flow : |net AGENT ou PROP en €| > 20 % de l'ADTV 30 jours (Flows n_days == 1)
ALERT_AUCTION_SPIKE_RATIO = 2.0      # auction_spike : part de la closing auction > 2 x sa baseline 20 jours
ALERT_PRICE_MOVE_PCT = 2.5           # price_move : |rendement excédentaire vs médiane des peers| > 2,5 % ...
ALERT_PRICE_MOVE_VOLUME = 1.5        # ... ET volume_ratio > 1,5
ALERT_LEVEL_BREAK_VOLUME = 1.5       # level_break : volume_ratio > 1,5 ET large_trade ou aggressor_sweep le même jour
ALERT_HIGH_FACTOR = 2.0              # severity "high" si la valeur dépasse 2 x le seuil

# LLM (assistant)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "")  # "anthropic" | "openai" | "" (= templates seulement)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "20"))
