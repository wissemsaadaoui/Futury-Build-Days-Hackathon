"""Analytics – API publique (propriétaire : Alfred).

Contrat avec app/api : chaque fonction renvoie un dict au format du mock du même nom.
Lève `NotFound` (sous-classe de KeyError) -> l'API renvoie 404.

Champ supplémentaire `_data_status` : indique quelles parties sont calculées sur des données réelles
et lesquelles viennent encore du mock (ignoré par les schémas Pydantic, extra="ignore").
"""
from __future__ import annotations

from app.analytics.compare import compare_events, list_events
from app.analytics.dashboard import build_dashboard
from app.analytics.impact import NotFound, build_day_card, build_impact_card
from app.analytics.report import build_report

__all__ = [
    "NotFound",
    "build_dashboard",
    "list_events",
    "build_impact_card",
    "build_day_card",
    "compare_events",
    "build_report",
]
