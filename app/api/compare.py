"""Route /compare : événements du même type, filtrés par indice et période."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app import analytics
from app.api.params import DateRange, date_range
from app.schemas import CompareResponse
from app.schemas.common import EventType, Index

router = APIRouter(tags=["compare"])


@router.get("/compare", response_model=CompareResponse)
def get_compare(
    event_type: EventType = Query(alias="type"),
    index: Index = Query(),
    period: DateRange = Depends(date_range),
) -> dict:
    return analytics.compare_events(event_type, index, period.start, period.end)
