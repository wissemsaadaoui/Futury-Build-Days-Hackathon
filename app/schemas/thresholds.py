"""/thresholds – seuils d'alerte de l'équipe IR (logique : app/analytics/thresholds.py)."""
from __future__ import annotations

from typing import Optional

from app.schemas.common import Schema


class ThresholdSpec(Schema):
    label: str
    unit: str
    group: str  # "anomaly" | "alert"
    min: float
    max: float
    step: float
    integer: bool
    default: float


class ThresholdsResponse(Schema):
    isin: str
    values: dict[str, float]
    defaults: dict[str, float]
    bounds: dict[str, ThresholdSpec]
    custom: bool


class ThresholdsUpdate(Schema):
    isin: str
    values: dict[str, float]


class ThresholdsReset(Schema):
    isin: str


class ThresholdsPreview(Schema):
    isin: str
    alerts_with_values: int
    alerts_current: int


class ThresholdChange(Schema):
    item_id: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    decided_at: str
