"""Routes impact card : par annonce ou par jour (« notable day »)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from app import analytics
from app.schemas import ImpactCardResponse

router = APIRouter(tags=["impact cards"])


@router.get("/events/{event_id}/impact-card", response_model=ImpactCardResponse)
def get_event_impact_card(event_id: str) -> dict:
    return analytics.build_impact_card(event_id)


@router.get("/days/{isin}/{day}/impact-card", response_model=ImpactCardResponse)
def get_day_impact_card(isin: str, day: date) -> dict:
    return analytics.build_day_card(isin, day)
