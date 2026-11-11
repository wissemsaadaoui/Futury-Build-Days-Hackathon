"""Emplacement des fichiers bruts (data/raw, voir les NOTES.md de chaque dossier)."""
from __future__ import annotations

from pathlib import Path

from app import config


def daily_files(folder: str, pattern: str) -> list[Path]:
    """Fichiers journaliers triés par date (le nom se termine par YYYYMMDD)."""
    return sorted((config.DATA_DIR / folder).glob(pattern))


SPREADS = ("spreads", "dax_mdax_sdax_xlm.*.csv")
OHLC = ("XETRA/XETRA_OHLC", "XETRA_OHLC_*.csv.gz")
FLOWS = ("XETRA/XETRA_FLOW_DYNAMICS_EQUITY", "XETRA_FLOW_DYNAMICS_EQUITY_*.csv.gz")
TRADES = ("XETRA/XETRA_ONBOOK_TRADES", "XETRA_ONBOOK_TRADES_*.csv.gz")
CONSTITUENTS = ("index_constituents", "*_CONSTITUENTS_*.csv.gz")
