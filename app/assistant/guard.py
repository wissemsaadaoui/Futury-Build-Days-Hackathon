"""Garde-fou anti-hallucination : chaque nombre du texte doit exister dans les faits."""
from __future__ import annotations

import json
import re
from typing import Any

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_BANNED = re.compile(
    r"\b(buy|sell|hold|recommend\w*|forecast\w*|predict\w*|targets?|upside|downside"
    r"|will (rise|fall|increase|decrease|go up|go down)|expects? the (share )?price)\b",
    re.I,
)


def _numbers_in(obj: Any) -> set[float]:
    nums: set[float] = set()
    for tok in _NUM.findall(json.dumps(obj, ensure_ascii=False)):
        try:
            nums.add(float(tok.replace(",", "")))
        except ValueError:
            pass
    return nums


def allowed_numbers(facts: dict) -> set[float]:
    base = _numbers_in(facts)
    out: set[float] = set()
    for n in base:
        for v in (n, abs(n)):
            out.update({v, round(v, 1), round(v, 0), round(v, 2)})
    out.update({float(i) for i in range(0, 11)})  # petits entiers ("three sessions", "1 day")
    out.update({20.0, 25.0, 25000.0})  # baseline 20 jours, notional 25k
    return out


def check(text: str, facts: dict) -> bool:
    """True si le texte ne contient que des nombres autorisés et aucun vocabulaire de conseil/prédiction."""
    if not text or _BANNED.search(text):
        return False
    allowed = allowed_numbers(facts)
    for tok in _NUM.findall(text):
        tok = tok.rstrip(",.")
        try:
            v = float(tok.replace(",", ""))
        except ValueError:
            continue
        if not any(abs(v - a) <= 0.051 for a in allowed):
            return False
    return True
