# CLAUDE.md – Issuer Intelligence Hub (Back-end)

Instructions pour Claude Code et pour toute l'équipe back-end.
Contexte complet du challenge, glossaire et données : voir `PROJECT.md`.

## Projet en une phrase

Back-end Python d'un outil self-service pour les équipes **Investor Relations** de mid/small caps : il analyse le trading Xetra d'une action (liquidity, spread, auctions, peers) et génère des **impact cards** pour chaque annonce, avec un résumé écrit par un LLM. Démo : **SUSS MicroTec SE** (`DE000A1K0235`, mnemonic `SMHN`).

## Stack

- **Python 3.11+**
- **FastAPI** + **uvicorn** : API REST
- **Pydantic v2** : schémas des réponses (miroir exact de `shared/types.ts`)
- **pandas** / **numpy** : chargement et calculs
- **LLM** : SDK OpenAI ou Anthropic (clé dans `.env`, jamais commitée)
- **pytest** : tests
- Front-end séparé en TypeScript (Yassine), branché via HTTP/JSON

## Équipe et ownership

Un seul repo. Chaque personne est **propriétaire** de ses dossiers : on ne modifie pas les fichiers de l'autre sans prévenir.

| Qui | Dossiers | Responsabilités |
|---|---|---|
| **Alfred** – Analyse & Assistant | `app/analytics/`, `app/assistant/`, `data/events.csv` | Métriques, baseline, anomalies, peers, indicateurs techniques, logique des impact cards, comparaison d'événements, résumés LLM, prompts |
| **Partenaire back-end** | `app/api/`, `app/schemas/`, `app/etl/`, `app/export/`, `app/main.py`, `app/config.py`, `tests/api/` | Serveur FastAPI, routes, CORS, schémas Pydantic, chargement des données (ETL), cache, export PDF, gestion d'erreurs, setup du repo |
| **Yassine** – Front-end | repo/dossier front séparé | UI TypeScript, à partir de `mocks/` puis de l'API |

Fichiers **partagés** (modification = prévenir les deux autres) : `shared/types.ts`, `mocks/`, `PROJECT.md`, `CLAUDE.md`, `requirements.txt`.

## Structure du repo

```
issuer-hub/
├── CLAUDE.md
├── PROJECT.md
├── requirements.txt
├── .env.example              # LLM_PROVIDER, LLM_API_KEY, DATA_DIR
├── shared/
│   └── types.ts              # contrat API de référence (front)
├── mocks/                    # un JSON par endpoint + API.md
├── data/
│   ├── raw/                  # données Deutsche Börse (gitignore)
│   │   ├── spreads/          # dax_mdax_sdax_xlm.YYYYMMDD.csv
│   │   ├── ohlc/
│   │   └── flows/
│   └── events.csv            # annonces SUSS MicroTec (fait main)
├── app/
│   ├── main.py               # [backend] création de l'app, CORS, routers
│   ├── config.py             # [backend] chemins, constantes, .env
│   ├── etl/                  # [backend] load_xlm, load_ohlc, load_flows, load_events
│   ├── schemas/              # [backend] modèles Pydantic = types.ts
│   ├── api/                  # [backend] routes FastAPI
│   ├── export/               # [backend] génération PDF
│   ├── analytics/            # [Alfred] metrics, anomalies, peers, indicators, impact, compare, report
│   └── assistant/            # [Alfred] client LLM, prompts, summaries
└── tests/
    ├── api/                  # [backend]
    └── analytics/            # [Alfred]
```

## Commandes

```bash
python -m venv .venv                     # crée un environnement Python isolé pour le projet
source .venv/bin/activate                # l'active (Windows : .venv\Scripts\activate)
pip install -r requirements.txt          # installe les dépendances
cp .env.example .env                     # crée le fichier de config local (y mettre la clé LLM)
uvicorn app.main:app --reload --port 8000  # lance l'API ; --reload redémarre à chaque modification
pytest                                   # lance tous les tests
```

- Doc interactive de l'API : `http://localhost:8000/docs`
- Spec OpenAPI (pour générer les types du front) : `http://localhost:8000/openapi.json`

## Interfaces entre les modules (le contrat interne)

C'est ce qui permet de travailler en parallèle. **Ne pas changer une signature sans prévenir.**

### ETL → Analytics (backend fournit, Alfred consomme)

Toutes les fonctions renvoient des `pandas.DataFrame` avec **exactement** ces colonnes. Les données sont chargées une fois au démarrage et mises en cache.

```python
# app/etl/__init__.py
def load_xlm() -> pd.DataFrame:
    """date (datetime64), isin, mnemonic, index, notional (float), impact_bps (float, NaN possible)"""

def load_ohlc() -> pd.DataFrame:
    """date, isin, open, high, low, close, volume, turnover_eur (+ colonnes selon NOTES.md)"""

def load_flows() -> pd.DataFrame:
    """date, isin, participant (AGENT|PROP|MARKET_MAKER), mode (AGGRESSIVE|PASSIVE|AUCTION),
       side (BUY|SELL), volume"""

def load_events() -> pd.DataFrame:
    """event_id, isin, date, time, trading_day, type, title, source_url"""

def get_universe() -> pd.DataFrame:
    """isin, name, mnemonic, index (actuel), sector (peut être vide)"""
```

### Analytics → API (Alfred fournit, backend consomme)

Chaque fonction renvoie un `dict` dont la forme correspond **exactement** au mock JSON du même nom. Le backend le valide avec le schéma Pydantic correspondant.

```python
# app/analytics/__init__.py
def build_dashboard(isin: str, start: date, end: date) -> dict:          # = mocks/dashboard.json
def list_events(isin: str) -> dict:                                     # = mocks/events.json
def build_impact_card(event_id: str) -> dict:                            # = mocks/impact-card.json
def build_day_card(isin: str, day: date) -> dict:                        # idem, avec "event": None
def compare_events(event_type: str, index: str, start: date, end: date) -> dict:  # = mocks/compare.json
def build_report(isin: str, start: date, end: date) -> dict:             # = mocks/report.json
```

### Assistant (Alfred)

```python
# app/assistant/__init__.py
def summarize_impact_card(card: dict) -> str:   # remplit card["ai_summary"]
def summarize_report(report: dict) -> str:      # remplit report["headline"] et les textes
```

`build_impact_card` et `build_report` appellent l'assistant eux-mêmes. Si le LLM échoue ou si aucune clé n'est configurée, ils renvoient un **résumé de secours généré par template** : l'API ne doit jamais planter à cause du LLM.

### Pendant le développement

Tant qu'une fonction n'est pas prête, elle renvoie le mock correspondant (`json.load` du fichier dans `mocks/`). Le backend peut donc brancher toutes les routes dès le premier jour.

## Endpoints

| Route | Fonction analytics | Schéma Pydantic |
|---|---|---|
| `GET /stocks` | `etl.get_universe()` (+ sélection démo) | `StocksResponse` |
| `GET /stocks/{isin}/dashboard?from=&to=` | `build_dashboard` | `DashboardResponse` |
| `GET /stocks/{isin}/events` | `list_events` | `EventsResponse` |
| `GET /events/{event_id}/impact-card` | `build_impact_card` | `ImpactCardResponse` |
| `GET /days/{isin}/{date}/impact-card` | `build_day_card` | `ImpactCardResponse` |
| `GET /compare?type=&index=&from=&to=` | `compare_events` | `CompareResponse` |
| `GET /stocks/{isin}/report?from=&to=` | `build_report` | `ReportResponse` |
| `GET /events/{event_id}/impact-card.pdf` | `build_impact_card` + `export` | PDF |
| `GET /stocks/{isin}/report.pdf` | `build_report` + `export` | PDF |

Erreurs : `404` si l'ISIN ou l'event_id est inconnu, `422` pour des dates invalides (FastAPI le fait automatiquement), réponse JSON `{"detail": "..."}`.

## Règles de calcul (Alfred)

| Métrique | Règle |
|---|---|
| Notional de référence | **25 000 €** pour `spread_bps` (colonne `Impact_bps` du XLM) |
| `baseline` | Moyenne des **20 jours de trading** précédents (jour mesuré exclu) |
| `volume_ratio` | volume ÷ baseline volume |
| `z_score` | (valeur − moyenne 20j) ÷ écart-type 20j |
| `auction_share` | volume en mode AUCTION ÷ volume total |
| Anomalie volume | `z_score > 2` → medium, `> 3` → high |
| Anomalie spread | z-score > 3 **et** spread > 1,2 × baseline (high si z > 4 ou > 1,5 ×) – calibré : ~3,7 alertes/action sur 10 mois |
| `trading_day` | Annonce avant 17:30 → même jour ; après → jour de trading suivant |
| `window` | Jours de trading −5 à +5 autour du `trading_day` |
| Peers | Même indice + liste manuelle (`config.PEERS`) : pas de colonne secteur dans les données. SUSS : Aixtron, Jenoptik, Siltronic, Elmos Semiconductor |
| Indicateurs | EMA20, EMA50, MACD(12, 26, 9), support/resistance sur pivots locaux (fenêtre 5, tolérance 1,5 %) |

## Règles pour l'assistant LLM (Alfred)

- Le LLM **reformule uniquement les chiffres fournis** dans le prompt. Il n'invente aucun chiffre, aucune cause, aucune information externe.
- **Aucune prédiction de prix, aucune recommandation d'achat/vente.** Ton factuel, destiné à une équipe IR.
- 3 à 5 phrases, en anglais, chiffres arrondis (1 décimale).
- Chaque export contient le disclaimer : *"Descriptive analysis of historical Xetra trading data. Not investment advice."*
- Prompts versionnés dans `app/assistant/prompts.py`, pas dispersés dans le code.

## Conventions de code

- Type hints partout ; `from __future__ import annotations` en tête de fichier.
- Noms de champs JSON en **snake_case**, identiques à `types.ts` et aux mocks.
- Dates en `YYYY-MM-DD`, timestamps en ISO 8601 avec fuseau (`Europe/Berlin`).
- Ratios entre 0 et 1 (`auction_share`), pourcentages en % (`change_pct`), spreads en bps.
- Arrondir les sorties JSON : 2 décimales (prix, ratios), 1 décimale (bps, %).
- Pas de `NaN` dans le JSON : convertir en `null`.
- Aucun calcul dans `app/api/` : les routes appellent `analytics` et valident avec Pydantic, c'est tout.
- Ne jamais committer `data/raw/` ni `.env`.

## Changer le contrat API

1. Modifier le mock dans `mocks/` **et** `shared/types.ts`.
2. Modifier le schéma Pydantic dans `app/schemas/`.
3. Adapter la fonction analytics.
4. Prévenir Yassine pour qu'il régénère ses types : `npx openapi-typescript http://localhost:8000/openapi.json -o src/api-types.ts`.

## Git

- Branche `main` toujours fonctionnelle (l'API démarre et les tests passent).
- Branches par personne et par feature : `alfred/impact-card`, `<prénom>/api-routes`, etc.
- Petits commits, pull request (ou au minimum un message à l'équipe) avant de merger dans `main`.
- Conflits : on garde la version du propriétaire du dossier.

## Données : points d'attention

- Les fichiers XLM sont nommés `dax_mdax_sdax_xlm.YYYYMMDD.csv` ; 213 jours (02.01–30.10.2026), 174 actions.
- `Impact_bps = nan` quand le carnet n'est pas assez profond pour le notional : ne pas remplacer par 0.
- La colonne `Index` change dans le temps (SUSS MicroTec : SDAX jusqu'au 19.06.2026, MDAX dès le 22.06.2026). Pour les peers, utiliser l'indice **à la date** concernée.
- Lire le `NOTES.md` et le PDF de chaque dossier de données avant d'écrire l'ETL correspondant.
- Les Flows décrivent le trading de la **veille** : vérifier l'alignement des dates.
