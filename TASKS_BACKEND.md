# Tâches – Partenaire Back-end

> Issuer Intelligence Hub · Futury Build Days 2026
> À lire avant : `PROJECT.md` (contexte) et `CLAUDE.md` (règles, ownership, interfaces).

## Ton rôle

Tu construis **l'infrastructure du back-end** : le repo, le serveur FastAPI, le chargement des données, les schémas, les routes et l'export PDF.
Alfred construit **l'analyse et l'assistant IA** (`app/analytics/`, `app/assistant/`).
Yassine construit **le front-end** en TypeScript.

Ton objectif n°1 : **que Yassine puisse appeler une vraie API le plus vite possible**, même si elle renvoie encore des mocks.

## Tes dossiers

`app/main.py` · `app/config.py` · `app/etl/` · `app/schemas/` · `app/api/` · `app/export/` · `tests/api/` · `requirements.txt` · `.env.example` · `.gitignore`

Tu ne modifies pas `app/analytics/` ni `app/assistant/` sans prévenir Alfred.

---

## Phase 1 – Setup (priorité maximale, ~45 min)

### T1. Créer le repo
- [ ] Repo GitHub `issuer-hub`, Alfred et Yassine en collaborateurs
- [ ] Ajouter `PROJECT.md`, `CLAUDE.md`, `mocks/`, `shared/types.ts`
- [ ] Créer la structure de dossiers de `CLAUDE.md` (avec des `__init__.py`)
- [ ] `.gitignore` : `.venv/`, `.env`, `data/raw/`, `__pycache__/`, `*.pdf`

### T2. Dépendances
- [ ] `requirements.txt` :
  ```
  fastapi
  uvicorn[standard]
  pydantic>=2
  pandas
  numpy
  python-dotenv
  openai          # ou anthropic, selon le choix d'Alfred
  weasyprint      # ou reportlab, pour le PDF
  pytest
  httpx           # requis par le TestClient de FastAPI
  ```
- [ ] `.env.example` :
  ```
  DATA_DIR=data/raw
  LLM_PROVIDER=openai
  LLM_API_KEY=
  FRONTEND_ORIGIN=http://localhost:5173
  ```

### T3. App FastAPI minimale
- [ ] `app/config.py` : lit `.env`, expose `DATA_DIR`, `FRONTEND_ORIGIN`, `DEMO_ISINS = ["DE0008019001"]` (pbb), `PEERS = {...}` (vide pour l'instant, Alfred le remplit)
- [ ] `app/main.py` : crée l'app, ajoute **CORS** pour `FRONTEND_ORIGIN`, inclut les routers, route `GET /health` → `{"status": "ok"}`

**Fini quand :** `uvicorn app.main:app --reload --port 8000` démarre et `http://localhost:8000/docs` s'affiche.

---

## Phase 2 – API branchée sur les mocks (~1 h)

But : toutes les routes existent et renvoient les mocks. Yassine passe des fichiers JSON à la vraie API.

### T4. Stubs analytics (temporaires)
- [ ] Dans `app/analytics/__init__.py`, créer les 6 fonctions de `CLAUDE.md` qui renvoient le mock correspondant :
  ```python
  import json
  from pathlib import Path
  MOCKS = Path(__file__).resolve().parents[2] / "mocks"

  def _mock(name: str) -> dict:
      return json.loads((MOCKS / f"{name}.json").read_text())

  def build_dashboard(isin, start, end): return _mock("dashboard")
  # ... list_events, build_impact_card, build_day_card, compare_events, build_report
  ```
- [ ] Prévenir Alfred : à partir de là, **il remplace les stubs** au fur et à mesure ; ce fichier devient le sien.

### T5. Schémas Pydantic
- [ ] Un modèle par type de `shared/types.ts`, dans `app/schemas/` : `StocksResponse`, `DashboardResponse`, `EventsResponse`, `ImpactCardResponse`, `CompareResponse`, `ReportResponse` (+ sous-modèles)
- [ ] Mêmes noms de champs (snake_case), mêmes types ; `Literal[...]` pour les enums (`EventType`, `ParticipantType`, etc.) ; `Optional` là où `types.ts` a `| null`
- [ ] Ignorer les champs `_endpoint` / `_note` des mocks (`model_config = ConfigDict(extra="ignore")`)

**Fini quand :** chaque mock JSON se valide sans erreur avec son modèle (`Model.model_validate(json)`).

### T6. Routes
- [ ] Une route par ligne du tableau « Endpoints » de `CLAUDE.md`, avec `response_model=` le bon schéma
- [ ] Les routes **n'ont aucune logique de calcul** : elles appellent `analytics.*`, c'est tout
- [ ] Paramètres `from` / `to` : utiliser `Query(alias="from")` (car `from` est un mot réservé en Python), type `date`, valeurs par défaut `2026-01-01` / `2026-10-30`
- [ ] Erreurs : `404` si ISIN ou `event_id` inconnu (`HTTPException(404, "Unknown ISIN")`)

**Fini quand :** les 7 routes JSON répondent dans `/docs` et Yassine les appelle depuis le front.

### T7. Message à Yassine
- [ ] Lui envoyer l'URL de l'API et la commande pour générer ses types :
  `npx openapi-typescript http://localhost:8000/openapi.json -o src/api-types.ts`

---

## Phase 3 – Chargement des vraies données / ETL (~2 h)

Les signatures et colonnes sont **fixées dans `CLAUDE.md`** : Alfred code ses analyses en s'appuyant dessus.

### T8. Lire la doc des données
- [ ] Lire le `NOTES.md` et le PDF de chaque dossier (OHLC, Flows, Open interest)
- [ ] Noter dans `PROJECT.md` (section Données) les colonnes réelles et les surprises
- [ ] Vérifier : les Flows séparent-ils **opening** et **closing auction** ? Les Flows décrivent bien **la veille** ?

### T9. `load_xlm()`
- [ ] Lit tous les `data/raw/spreads/dax_mdax_sdax_xlm.*.csv`
- [ ] Renomme : `Date→date` (datetime), `ISIN→isin`, `Mnemonic→mnemonic`, `Index→index`, `Notional_CCY→notional`, `Impact_bps→impact_bps`
- [ ] Garde les `NaN` (carnet pas assez profond), ne pas remplacer par 0
- [ ] Vérif : 213 jours, 174 ISIN, vérifier l'historique d'indice de pbb (colonne `Index`)

### T10. `load_ohlc()`
- [ ] Colonnes de sortie : `date, isin, open, high, low, close, volume, turnover_eur` (+ autres utiles selon NOTES.md)
- [ ] Si `turnover_eur` n'existe pas : l'approximer par `volume × close` et le signaler à Alfred

### T11. `load_flows()`
- [ ] Format **long** : une ligne par `date, isin, participant, mode, side, volume`
- [ ] Normaliser les valeurs : `participant ∈ {AGENT, PROP, MARKET_MAKER}`, `mode ∈ {AGGRESSIVE, PASSIVE, AUCTION}`, `side ∈ {BUY, SELL}`
- [ ] Aligner la date sur le **jour de trading réel** (si le fichier du jour J décrit J-1)
- [ ] Garder seulement Xetra (pas Eurex) sauf avis contraire d'Alfred

### T12. `load_events()` et `get_universe()`
- [ ] `load_events()` lit `data/events.csv` (fait par Alfred)
- [ ] `get_universe()` : un ISIN par ligne avec `name, mnemonic, index` (indice le plus récent) ; `name` vient de l'OHLC ou d'une petite table dans `config.py`

### T13. Cache
- [ ] Charger toutes les données **une seule fois** au démarrage (`@lru_cache` ou `lifespan` de FastAPI)

**Fini quand :** les 5 fonctions renvoient des DataFrames avec exactement les colonnes de `CLAUDE.md`, et un test le vérifie.

---

## Phase 4 – Export PDF (~1 h 30)

### T14. Impact card PDF
- [ ] `GET /events/{event_id}/impact-card.pdf` : appelle `build_impact_card`, rend un template HTML simple (titre, tuiles de chiffres, `ai_summary`, disclaimer), convertit en PDF
- [ ] Header `Content-Disposition: attachment; filename="pbb_impact_<date>.pdf"`

### T15. IR snapshot PDF
- [ ] `GET /stocks/{isin}/report.pdf` : même principe avec `build_report`
- [ ] Une page A4 maximum

### T16. Brancher les URLs
- [ ] Vérifier que `export.pdf_url` dans les réponses JSON pointe bien vers ces routes

**Fini quand :** les deux PDF se téléchargent depuis le front et sont lisibles.

> Si WeasyPrint pose des problèmes d'installation (dépendances système), passer à `reportlab` ou laisser le front faire l'export (impression navigateur). Ne pas y perdre plus de 30 min.

---

## Phase 5 – Robustesse et démo (~1 h)

### T17. Tests (`tests/api/`)
- [ ] Chaque route renvoie `200` pour pbb et un JSON valide selon son schéma
- [ ] `404` pour un ISIN inconnu
- [ ] Les fonctions ETL renvoient les bonnes colonnes

### T18. Nettoyage JSON
- [ ] Aucun `NaN` / `Infinity` dans les réponses (→ `null`) ; arrondis selon `CLAUDE.md`

### T19. Démo
- [ ] `README.md` court : comment lancer back + front en 3 commandes
- [ ] Tester toute la démo de bout en bout avec Alfred et Yassine sur **le laptop de la présentation**
- [ ] Plan B : si le LLM ou le Wi-Fi tombe, l'API renvoie le résumé de secours (géré par Alfred) ; garder une capture vidéo de la démo

---

## Ordre et dépendances

```
T1 → T2 → T3 → T4 → T5 → T6 → T7      ← Yassine débloqué
                     ↓
              T8 → T9 → T10 → T11 → T12 → T13   ← Alfred débloqué pour les vraies données
                                              ↓
                                    T14 → T15 → T16
                                              ↓
                                    T17 → T18 → T19
```

**T9 (`load_xlm`) en premier dans la phase 3** : Alfred a déjà analysé ces données et peut les utiliser tout de suite.

## Points de synchronisation avec l'équipe

| Quand | Avec qui | Quoi |
|---|---|---|
| Après T6 | Yassine | L'API tourne, il branche le front |
| Après T9 | Alfred | `load_xlm()` prêt, il branche les spreads |
| Après T11 | Alfred | Colonnes réelles des Flows, question opening/closing auction |
| Avant T14 | Alfred | Quels champs mettre dans les PDF |
| Fin | Tous | Répétition complète de la démo |

## Definition of Done (global)

- [ ] `uvicorn app.main:app` démarre sans erreur
- [ ] Les 7 routes JSON + 2 routes PDF fonctionnent pour pbb
- [ ] Le front appelle la vraie API (plus les mocks)
- [ ] `pytest` passe
- [ ] La démo tourne de bout en bout sur le laptop de présentation
