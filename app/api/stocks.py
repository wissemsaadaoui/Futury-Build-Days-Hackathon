"""Routes /stocks : liste, dashboard, événements, IR snapshot, event preview."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response

from app import analytics, export
from app.api.impact_cards import PDF_RESPONSE, pdf_response
from app.api.params import DateRange, date_range
from app.schemas import DashboardResponse, EventPreviewResponse, EventsResponse, ReportResponse, StocksResponse
from app.schemas.common import EventType

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("", response_model=StocksResponse)
def get_stocks() -> dict:
    """Tous les émetteurs DAX / MDAX / SDAX (pbb en premier, sélectionné par défaut) avec leur couverture de données."""
    return analytics.list_stocks()


@router.get("/{isin}/dashboard", response_model=DashboardResponse)
def get_dashboard(isin: str, period: DateRange = Depends(date_range)) -> dict:
    return analytics.build_dashboard(isin, period.start, period.end)


@router.get("/{isin}/events", response_model=EventsResponse)
def get_events(isin: str) -> dict:
    return analytics.list_events(isin)


@router.get("/{isin}/report", response_model=ReportResponse)
def get_report(isin: str, period: DateRange = Depends(date_range)) -> dict:
    return analytics.build_report(isin, period.start, period.end)


@router.get("/{isin}/report.pdf", response_class=Response, responses=PDF_RESPONSE)
def get_report_pdf(isin: str, period: DateRange = Depends(date_range)) -> Response:
    report = ReportResponse.model_validate(analytics.build_report(isin, period.start, period.end)).model_dump(by_alias=True)
    return pdf_response(export.report_pdf(report), export.report_filename(report))


@router.get("/{isin}/event-preview", response_model=EventPreviewResponse)
def get_event_preview(
    isin: str,
    event_type: EventType = Query(alias="type", description="Type d'annonce, ex. quarterly_results"),
    day: Optional[date] = Query(None, alias="date", description="Seuls les événements AVANT cette date sont utilisés"),
) -> dict:
    """« What to expect » : statistiques des réactions passées du trading à ce type d'annonce (pas une prédiction)."""
    return analytics.build_event_preview(isin, event_type, day)
