# Schémas Pydantic – ajouts v0.3 à faire (pour Wissem)

**De :** Alfred · **Branche :** `alfred/alerts-v2` · **Fichiers :** `app/schemas/dashboard.py`, `app/schemas/impact_card.py`
Je n'ai **pas** modifié les schémas cette fois. Tout est additif ; le contrat de référence est `shared/types.ts` + `mocks/API.md` v0.3.

## ⚠️ Bloquant avant de merger dans `main`

`GET /stocks/DE0008019001/dashboard?from=2026-08-01&to=2026-08-31` renvoie **500** : l'analytics produit une anomalie
`level_break` (13.08.2026) que `AnomalyType` refuse (`ResponseValidationError`). Toute période qui contient le 13.08 est touchée
(dont l'année entière). Les tests passent seulement parce que `tests/api/test_dashboard` interroge mars.

Par ailleurs, `extra="ignore"` supprime silencieusement `detail_url`, `level_type`, `level_price` et `pre_disclosure_activity`.

## 1. `app/schemas/dashboard.py`

```python
AnomalyType = Literal[
    "volume_spike", "spread_widening", "price_move", "auction_spike",
    "large_trade", "aggressor_sweep", "net_flow",
    "level_break",  # v0.3
]


class Anomaly(Schema):
    date: ISODate
    type: AnomalyType
    severity: Severity
    value: OptNumber
    description: str
    linked_event_id: Optional[str]
    detail_url: Optional[str] = None  # v0.3 : /events/{id}/impact-card si lié, sinon /days/{isin}/{date}/impact-card
    time: Optional[str] = None
    side: Optional[Literal["BUY", "SELL"]] = None
    notional_eur: OptNumber = None
    level_type: Optional[Literal["support", "resistance"]] = None  # v0.3 : level_break uniquement
    level_price: OptNumber = None                                  # v0.3 : level_break uniquement
```

(`price_move` est déjà dans le Literal : rien à faire pour lui.)

## 2. `app/schemas/impact_card.py`

```python
class PreDisclosureWindow(Period):  # Period (common.py) a déjà from_ = Field(alias="from") et to
    sessions: int


class PreDisclosureDay(Schema):
    date: ISODate
    anomaly_types: list[AnomalyType]  # importer AnomalyType depuis app.schemas.dashboard (ou common)
    volume_ratio: OptNumber
    agent_net_flow_eur: OptNumber


class PreDisclosureActivity(Schema):
    window: PreDisclosureWindow
    days: list[PreDisclosureDay]
    summary: str


class ImpactCardResponse(DataStatusMixin, Schema):
    ...
    intraday: Optional[IntradayBlock] = None
    pre_disclosure_activity: Optional[PreDisclosureActivity] = None  # v0.3 : voting_rights uniquement
    ai_summary: str
    ...
```

`from` est un mot réservé Python : d'où l'héritage de `Period`, qui gère déjà l'alias.

## 3. Tests `tests/api` suggérés

- `/stocks/{PBB}/dashboard?from=2026-08-01&to=2026-08-31` → 200, au moins une anomalie `level_break` avec `level_type` et `level_price`.
- Toutes les anomalies ont un `detail_url`.
- `/events/evt_019/impact-card` → `pre_disclosure_activity` non nul ; `/events/evt_002/impact-card` → `null`.
- Ensuite, je pourrai régénérer `mocks/dashboard.json` sur une fenêtre qui inclut le 13.08 (exclu pour l'instant, sinon
  `test_mock_validates[dashboard]` échoue).

## 4. `app/schemas/report.py` (ajout v0.3, branche `alfred/report-fixes`)

```python
class ReportKpi(Schema):
    label: str
    value: OptNumber
    unit: Literal["shares", "EUR", "bps", "ratio", "pct"]
    trend: Optional[Trend]  # v0.3 : None si la variation est inconnue (au lieu de "flat")
    change_pct: OptNumber = None
    change_basis: Optional[Literal["previous_period", "first_half"]] = None  # v0.3
```

Aujourd'hui `trend: Trend` est obligatoire : un KPI sans variation calculable ferait échouer la validation (cas rare depuis
le repli « 2e moitié vs 1re moitié », mais possible sur une période sans OHLC ou Flows dans une moitié).
`change_basis` est supprimé par `extra="ignore"` tant qu'il n'est pas déclaré.

## 5. `app/schemas/compare.py`

`CompareFilter.index` est typé `Index = Literal["DAX", "MDAX", "SDAX"]` (common.py) : une réponse avec
`"index": "ALL"` échoue la validation. Remplacer par `index: Literal["DAX", "MDAX", "SDAX", "ALL"]` dans `CompareFilter`
(garder `Index` tel quel ailleurs).

Constat : `GET /compare?type=voting_rights&index=ALL&from=2026-01-01&to=2026-10-30` renvoie aujourd'hui **422** : le paramètre
`index` de la route (`app/api/compare.py` / `params.py`) refuse déjà `ALL`, alors que `compare_events(..., "ALL", ...)` le gère
(tous indices) et que le contrat (`mocks/API.md` §2) l'annonce. À ouvrir côté route et côté `CompareFilter`.

---

# v0.4 – Event preview + report Alerts (branche `alfred/event-preview`)

## 6. Déjà fait par Alfred (avec l'accord de l'équipe) : `app/schemas/report.py`

Commit `feat(schemas): ReportKpi accepts unit 'count'…` : `unit` + `"count"`, `trend: Optional`, `change_basis`, `alert_type`,
`ReportAlertDay` + `ReportSection.alert_days`. Sans ça, `/report` et `/report.pdf` renvoyaient 500 avec la nouvelle section
« Alerts ». **À relire** ; le point 4 ci-dessus est donc fait.

## 7. À faire : route `GET /stocks/{isin}/event-preview?type=&date=` (`app/api/stocks.py`)

```python
from datetime import date as Date
from typing import Optional

from fastapi import Query

from app.schemas import EventPreviewResponse
from app.schemas.common import EventType


@router.get("/{isin}/event-preview", response_model=EventPreviewResponse)
def get_event_preview(
    isin: str,
    type: EventType = Query(..., description="Type d'annonce, ex. quarterly_results"),
    date: Optional[Date] = Query(None, description="Seuls les événements AVANT cette date sont utilisés"),
) -> dict:
    return analytics.build_event_preview(isin, type, date)
```

`analytics.NotFound` (ISIN inconnu) → 404 via le handler existant ; `type` hors `EventType` → 422 (FastAPI).
`build_event_preview` accepte `day=None` ou une `date`.

## 8. À faire : schéma `app/schemas/event_preview.py` (+ export dans `app/schemas/__init__.py`)

```python
"""GET /stocks/{isin}/event-preview"""
from __future__ import annotations

from typing import Literal, Optional

from app.schemas.common import DataStatusMixin, EventType, ISODate, OptNumber, Schema, StockRef


class PreviewStat(Schema):
    n: int
    median: OptNumber
    min: OptNumber
    max: OptNumber


class PreviewEvent(Schema):
    event_id: str
    date: ISODate
    spread_change_pct: OptNumber
    volume_ratio: OptNumber
    price_abs_change_pct: OptNumber  # amplitude absolue, jamais signée
    sessions_to_normal: OptNumber
    auction_share_change_pts: OptNumber
    first_15min_ratio: OptNumber


class PreviewHistory(Schema):
    n: int
    events: list[PreviewEvent]
    spread_change_pct: PreviewStat
    volume_ratio: PreviewStat
    price_abs_change_pct: PreviewStat
    sessions_to_normal: PreviewStat
    auction_share_change_pts: PreviewStat
    first_15min_ratio: PreviewStat


class PeerHistory(PreviewHistory):
    peers_note: Optional[str] = None


class Upcoming(Schema):
    date: ISODate
    title: Optional[str] = None
    event_id: Optional[str] = None
    source_url: Optional[str] = None


class EventPreviewResponse(DataStatusMixin, Schema):
    stock: StockRef
    event_type: EventType
    as_of: Optional[ISODate] = None
    upcoming: Optional[Upcoming] = None
    own_history: PreviewHistory
    peers: PeerHistory
    attention_points: list[str]
    confidence: Literal["low", "medium", "high"]
    note: str
    ai_summary: str
```

## 9. Tests `tests/api` suggérés

- `/stocks/DE0008019001/event-preview?type=quarterly_results` → 200, `own_history.n == 2`, `upcoming.date == "2026-11-12"`.
- `…?type=quarterly_results&date=2026-08-13` → `own_history.n == 1` (l'H1 du 13.08 est exclu).
- `…?type=dividend` → 200, `own_history.n == 0`, statistiques `null`.
- `/stocks/XX0000000000/event-preview?type=ad_hoc` → 404 ; `?type=nope` → 422.
- Ajouter `("event-preview", EventPreviewResponse)` à `test_mock_validates` (mock : `mocks/event-preview.json`).
