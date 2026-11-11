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
