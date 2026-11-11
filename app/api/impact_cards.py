"""Routes impact card : par annonce ou par jour (« notable day »), JSON et PDF."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Response

from app import analytics, export
from app.schemas import ImpactCardResponse

router = APIRouter(tags=["impact cards"])

PDF_RESPONSE = {200: {"content": {"application/pdf": {}}, "description": "PDF (A4)"}}


def pdf_response(content: bytes, filename: str) -> Response:
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/events/{event_id}/impact-card", response_model=ImpactCardResponse)
def get_event_impact_card(event_id: str) -> dict:
    return analytics.build_impact_card(event_id)


@router.get("/events/{event_id}/impact-card.pdf", response_class=Response, responses=PDF_RESPONSE)
def get_event_impact_card_pdf(event_id: str) -> Response:
    card = ImpactCardResponse.model_validate(analytics.build_impact_card(event_id)).model_dump(by_alias=True)
    return pdf_response(export.impact_card_pdf(card), export.impact_card_filename(card))


@router.get("/days/{isin}/{day}/impact-card", response_model=ImpactCardResponse)
def get_day_impact_card(isin: str, day: date) -> dict:
    return analytics.build_day_card(isin, day)


@router.get("/days/{isin}/{day}/impact-card.pdf", response_class=Response, responses=PDF_RESPONSE)
def get_day_impact_card_pdf(isin: str, day: date) -> Response:
    card = ImpactCardResponse.model_validate(analytics.build_day_card(isin, day)).model_dump(by_alias=True)
    return pdf_response(export.impact_card_pdf(card), export.impact_card_filename(card))
