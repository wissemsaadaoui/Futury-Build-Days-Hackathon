"""Seuils d'alerte modifiables (point 16) : routes minimales, logique dans app/analytics/thresholds.py."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.analytics import NotFound, data, thresholds
from app.analytics.dashboard import threshold_preview
from app.schemas.thresholds import ThresholdsPreview, ThresholdsReset, ThresholdsResponse, ThresholdsUpdate

router = APIRouter(prefix="/thresholds", tags=["thresholds"])
DECIDED_BY = "ir-team"  # un seul mot de passe d'équipe : pas d'identité individuelle


def _check(isin: str) -> None:
    if not data.known_isin(isin):
        raise NotFound(f"Unknown ISIN {isin}")


def _payload(isin: str) -> dict:
    return {"isin": isin, "values": thresholds.current(isin), "defaults": thresholds.defaults(),
            "bounds": thresholds.spec(), "custom": thresholds.is_custom(isin)}


def _invalid(exc: thresholds.InvalidThresholds) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": "Invalid thresholds", "errors": exc.errors})


@router.get("", response_model=ThresholdsResponse)
def get_thresholds(isin: str = Query(...)) -> dict:
    _check(isin)
    return _payload(isin)


@router.put("", response_model=ThresholdsResponse)
def put_thresholds(body: ThresholdsUpdate) -> dict:
    _check(body.isin)
    try:
        thresholds.save(body.isin, body.values, DECIDED_BY)
    except thresholds.InvalidThresholds as exc:
        raise _invalid(exc) from exc
    return _payload(body.isin)


@router.post("/reset", response_model=ThresholdsResponse)
def reset_thresholds(body: ThresholdsReset) -> dict:
    _check(body.isin)
    thresholds.reset(body.isin, DECIDED_BY)
    return _payload(body.isin)


@router.post("/preview", response_model=ThresholdsPreview)
def preview_thresholds(body: ThresholdsUpdate) -> dict:
    _check(body.isin)
    try:
        return threshold_preview(body.isin, body.values)
    except thresholds.InvalidThresholds as exc:
        raise _invalid(exc) from exc
