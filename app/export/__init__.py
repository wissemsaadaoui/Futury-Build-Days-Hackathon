"""Export PDF (impact card, IR snapshot) – propriétaire : partenaire back-end.

Met en page les dicts de app.analytics (aucun calcul). Chaque PDF contient le disclaimer de CLAUDE.md.
"""
from __future__ import annotations

from app import etl
from app.export.pdf import DISCLAIMER, impact_card_pdf, report_pdf

__all__ = ["DISCLAIMER", "impact_card_pdf", "report_pdf", "impact_card_filename", "report_filename"]


def _short_name(isin: str) -> str:
    """Mnemonic en minuscules pour le nom de fichier (pbb), sinon l'ISIN."""
    u = etl.get_universe()
    m = u.loc[u["isin"] == isin, "mnemonic"]
    return str(m.iloc[0]).lower() if not m.empty else isin


def impact_card_filename(card: dict) -> str:
    day = card["event"]["trading_day"] if card.get("event") else next((p["date"] for p in card["window"] if p["offset"] == 0), "day")
    return f"{_short_name(card['stock']['isin'])}_impact_{day}.pdf"


def report_filename(report: dict) -> str:
    p = report["period"]
    return f"{_short_name(report['stock']['isin'])}_report_{p['from']}_{p['to']}.pdf"
