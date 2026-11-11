"""Formatage des nombres dans les TEXTES destinés à l'équipe IR (les valeurs du JSON ne changent pas).

shares -> "440,981 shares" ; EUR -> "EUR 1.2m" (>= 1 million) ou "EUR 640,000" ;
ratio (0–1) -> "31.0%" ; bps -> "25.2 bps" ; pct -> "8.2%" ; count -> "12".
Le garde-fou (guard.allowed_numbers) accepte ces formes : séparateurs de milliers, ratio x 100, EUR en millions.
"""
from __future__ import annotations

NA = "n/a"
MILLION = 1e6


def _ok(x) -> bool:
    return x is not None and x == x  # exclut None et NaN


def shares(x) -> str:
    return f"{float(x):,.0f} shares" if _ok(x) else NA


def eur(x) -> str:
    """>= 1 million : 'EUR 1.2m' ; sinon montant entier avec séparateur : 'EUR 640,000'. Signe conservé."""
    if not _ok(x):
        return NA
    x = float(x)
    sign = "-" if x < 0 else ""
    a = abs(x)
    return f"EUR {sign}{a / MILLION:.1f}m" if a >= MILLION else f"EUR {sign}{a:,.0f}"


def ratio_pct(x) -> str:
    """Ratio entre 0 et 1 affiché en pourcentage : 0.31 -> '31.0%'."""
    return f"{float(x) * 100:.1f}%" if _ok(x) else NA


def bps(x) -> str:
    return f"{float(x):.1f} bps" if _ok(x) else NA


def pct(x) -> str:
    return f"{float(x):.1f}%" if _ok(x) else NA


def count(x) -> str:
    return f"{int(round(float(x))):,}" if _ok(x) else NA


_BY_UNIT = {"shares": shares, "EUR": eur, "ratio": ratio_pct, "bps": bps, "pct": pct, "count": count}


def value(x, unit: str) -> str:
    """Valeur d'un KPI avec son unité, au format lecteur IR (unité inconnue : nombre + unité)."""
    f = _BY_UNIT.get(unit)
    if f:
        return f(x)
    return f"{x} {unit}" if _ok(x) else NA
