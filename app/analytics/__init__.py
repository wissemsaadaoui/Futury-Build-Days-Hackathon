"""Analytics – API publique (propriétaire : Alfred).

Contrat avec app/api : chaque fonction renvoie un dict au format du mock du même nom.
Lève `NotFound` (sous-classe de KeyError) -> l'API renvoie 404.

Champ supplémentaire `_data_status` : indique quelles parties sont calculées sur des données réelles
et lesquelles viennent encore du mock (ignoré par les schémas Pydantic, extra="ignore").
"""
from __future__ import annotations

import functools

from app.analytics.compare import compare_events, list_events
from app.analytics.dashboard import build_dashboard
from app.analytics.impact import InsufficientData, NoMarketData, NotFound, build_day_card, build_impact_card
from app.analytics.preview import build_event_preview
from app.analytics.report import build_report
from app.analytics.universe import list_stocks


def _label_synthetic(fn):
    """Données synthétiques (app/etl/synthetic.py) : chaque valeur de `_data_status` devient "synthetic"."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        out = fn(*args, **kwargs)
        from app.etl import synthetic

        if synthetic.ACTIVE and isinstance(out, dict) and isinstance(out.get("_data_status"), dict):
            out["_data_status"] = {k: "synthetic" for k in out["_data_status"]}
        return out

    return wrapper


build_dashboard = _label_synthetic(build_dashboard)
build_impact_card = _label_synthetic(build_impact_card)
build_day_card = _label_synthetic(build_day_card)
build_report = _label_synthetic(build_report)
build_event_preview = _label_synthetic(build_event_preview)

__all__ = [
    "InsufficientData",
    "NoMarketData",
    "NotFound",
    "build_dashboard",
    "list_stocks",
    "list_events",
    "build_impact_card",
    "build_day_card",
    "compare_events",
    "build_report",
    "build_event_preview",
]
