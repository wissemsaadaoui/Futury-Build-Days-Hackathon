"""Paramètres de requête partagés par les routes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, Query

DEFAULT_FROM = date(2026, 1, 1)
DEFAULT_TO = date(2026, 10, 30)


@dataclass
class DateRange:
    start: date
    end: date


def date_range(
    start: date = Query(DEFAULT_FROM, alias="from", description="Début de période (YYYY-MM-DD)"),
    end: date = Query(DEFAULT_TO, alias="to", description="Fin de période (YYYY-MM-DD)"),
) -> DateRange:
    """`from` / `to` (« from » est un mot réservé en Python, d'où l'alias)."""
    if start > end:
        raise HTTPException(422, "'from' must be on or before 'to'")
    return DateRange(start, end)
