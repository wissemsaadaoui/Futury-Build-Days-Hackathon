# Issuer Intelligence Hub – Futury Build Days 2026

> Challenge **Deutsche Börse** · Démo avec **SUSS MicroTec SE** (`DE000A1K0235`, mnemonic `SMHN`)
> Document de référence pour toute l'équipe : le problème, les données, l'architecture, l'API et la répartition du travail.

---

## 1. Le problème en bref

Les équipes **Investor Relations (IR)** des entreprises cotées doivent expliquer comment leur action se négocie : **liquidity**, **spread**, réaction aux annonces.

Les **mid et small caps** (MDAX, SDAX) n'ont ni **terminal subscriptions** (Bloomberg…) ni **analysts**. Des questions simples restent sans réponse pendant des jours :
- « Notre liquidity s'est-elle améliorée ? »
- « Notre spread est-il meilleur que celui de nos peers ? »
- « Le trading a-t-il changé après nos résultats ? »

**Objectif :** un **self-service tool** avec IA qui répond à ces questions en un clic.

## 2. Ce qu'on doit livrer

| Partie | Contenu | Rôle |
|---|---|---|
| **Part A – Dashboard** | Volume, spread et **auction participation** dans le temps, **peer benchmarking** (indice, secteur, taille), **anomalies** signalées, export **IR snapshot** | La base : « l'état normal » |
| **Part B – Impact Card** | Pour chaque annonce : volume vs. **baseline**, mouvement du prix et du spread, effet sur les **opening/closing auctions**, comparaison d'événements du même type | Le cœur du challenge |
| **Output – AI assistant** | Un clic sur un événement ou un jour inhabituel → impact card + résumé texte par l'IA + export | Ce que le jury verra |
| **Bonus** | Idées d'autres analyses utiles aux IR et données nécessaires | Slide de pitch |

**Prix :** un ticket d'une journée pour le Deutsches Eigenkapitalforum, le 23 novembre 2026.

## 3. Glossaire

| Terme | Explication |
|---|---|
| **IR (Investor Relations)** | Service de l'entreprise qui communique avec les investisseurs |
| **Issuer** | L'entreprise cotée (l'émetteur des actions) |
| **ISIN** | Identifiant unique d'une action (SUSS MicroTec = `DE000A1K0235`) |
| **Xetra** | Plateforme de trading électronique de la Deutsche Börse |
| **Eurex** | Bourse de produits dérivés (futures, options) de la Deutsche Börse |
| **Volume / Turnover** | Nombre d'actions échangées / montant échangé en € |
| **Bid / Ask** | Meilleur prix d'achat / meilleur prix de vente |
| **Spread** | Écart bid–ask. Petit spread = action liquide |
| **bps (basis points)** | 1 bp = 0,01 % |
| **XLM (Xetra Liquidity Metric)** | Coût d'un aller-retour (acheter puis revendre) pour un montant donné (**notional**), en bps. Tient compte de la profondeur du carnet d'ordres |
| **Liquidity** | Facilité à trader sans faire bouger le prix |
| **Opening / Closing auction** | Enchère de début et de fin de journée sur Xetra |
| **Auction share** | Part du volume exécutée en enchère |
| **Baseline** | Niveau « normal », par exemple la moyenne des 20 jours de trading précédents |
| **Volume ratio** | Volume du jour ÷ baseline (3.0 = 3× plus que normal) |
| **z-score** | Écart à la normale en écarts-types (> 2 = inhabituel) |
| **Peers** | Entreprises comparables (même indice, secteur, taille) |
| **Participant type** | **AGENT** (pour le compte de clients), **PROP** (compte propre, souvent du HFT), **MARKET_MAKER** (fournit des prix en continu) |
| **Market mode** | **AGGRESSIVE** (prend la liquidité), **PASSIVE** (ordre en attente exécuté), **AUCTION**, **OFFBOOK** (hors carnet, Eurex) |
| **Open interest** | Nombre de contrats dérivés encore ouverts |
| **Ad hoc announcement** | Annonce obligatoire et urgente d'une information pouvant influencer le cours (règlement MAR) |
| **EMA / MACD / Support & Resistance** | Indicateurs techniques, utilisés uniquement de façon **descriptive** (pas de prédiction de prix) |

## 4. Les données

### 4.1 Fournies par la Deutsche Börse

Constituants DAX, MDAX et SDAX, 2026. Maximum 3 actions pour le challenge.

| Dataset | Contenu | Statut |
|---|---|---|
| **Spreads (XLM)** | `dax_mdax_sdax_xlm.YYYYMMDD.csv` | ✅ Reçu et analysé |
| **OHLC** | Open, high, low, close + statistiques dont le volume, par action et par jour | ⏳ À télécharger |
| **Xetra/Eurex Flows** | Trading de la veille par participant type, market mode et side (BUY/SELL) | ⏳ À télécharger |
| **Open interest** | Dérivés Eurex par participant type et LONG/SHORT | ⏳ Optionnel |

Chaque dossier est censé contenir un **PDF** (description des colonnes) et un **NOTES.md**. **À lire en premier.**

### 4.2 Dataset Spreads – détails

- **213 fichiers**, un par jour de trading, du 02.01.2026 au 30.10.2026 ; **174 actions** (43 DAX, 59 MDAX, 88 SDAX).
- Colonnes : `Date, Index, Mnemonic, ISIN, WKN, Notional_CCY, Impact_bps`.
- `Notional_CCY` va de 10 000 € à 30 M€. `Impact_bps` = coût de l'aller-retour.
- `nan` = carnet pas assez profond pour ce montant (SUSS MicroTec : au-delà de 1 M€ ; dès 2,5 M€ toujours `nan`, et 1,4 % des jours à 1 M€).
- La colonne `Index` suit les changements d'indice (SUSS MicroTec : SDAX jusqu'au 19.06, MDAX dès le 22.06 ; Siltronic et Elmos changent le même jour, Jenoptik le 23.03).
- **Pas de colonne secteur** : les peers sont à définir à la main.
- **Notional de référence pour l'UI : 25 000 €.**

### 4.3 À collecter nous-mêmes

Le **corporate event calendar** de SUSS MicroTec, depuis des sources publiques (site IR SUSS, communiqués EQS, annonces ad hoc) → `data/events.csv` :

```
event_id,isin,date,time,trading_day,type,title,source_url
```

> ⚠️ **À vérifier** : les heures `07:00` des résultats (evt_001 FY 2025, evt_002 Q1, evt_007 H1) sont des hypothèses ; à confirmer sur le site IR de SUSS (calendrier financier / communiqués EQS). Le Q3 du 05.11.2026 n'est pas inclus : il tombe après la fin des données (30.10.2026).

## 5. Premiers résultats SUSS MicroTec (spread à 25k €)

Calculés depuis `data/raw/spreads` (médiane mensuelle de `Impact_bps` à 25 000 € ; médiane d'indice = tous les titres de l'indice **à la date**).

| Mois | SUSS | Médiane MDAX | Médiane SDAX | Médiane peers | Aixtron | Jenoptik | Siltronic | Elmos |
|---|---|---|---|---|---|---|---|---|
| Janvier | 46.8 bps | 20.0 | 70.0 | 46.2 | 25.2 | 37.2 | 51.9 | 60.7 |
| Février | 56.1 | 23.9 | 69.3 | 43.5 | 28.7 | 39.2 | 57.0 | 55.3 |
| Mars | 51.4 | 24.0 | 72.0 | 46.6 | 22.7 | 43.4 | 65.9 | 48.4 |
| Avril | 45.4 | 21.0 | 71.6 | 35.0 | 19.5 | 24.3 | 57.4 | 43.8 |
| Mai | 40.1 | 20.8 | 74.2 | 33.9 | 17.1 | 22.4 | 42.9 | 43.5 |
| Juin | 45.1 | 21.3 | 81.8 | 32.8 | 15.6 | 23.2 | 43.8 | 50.7 |
| Juillet | 42.8 | 22.0 | 84.1 | 32.8 | 17.1 | 26.1 | 42.3 | 44.7 |
| Août | 37.5 | 20.8 | 73.8 | 32.3 | 17.0 | 24.3 | 37.7 | 44.8 |
| Septembre | 39.4 | 21.5 | 67.9 | 30.1 | 16.5 | 25.5 | 35.7 | 42.7 |
| Octobre | 43.5 | 23.7 | 70.9 | 37.2 | 21.3 | 35.2 | 40.6 | 44.6 |

- SUSS est **~40 % moins cher à trader** que la médiane SDAX, mais reste **~2× plus cher** que la médiane MDAX, même après son entrée.
- Parmi ses peers, SUSS est dans le haut de la fourchette : proche d'Elmos et Siltronic, nettement au-dessus d'Aixtron (~17 bps) et Jenoptik (~25 bps).
- **Entrée en MDAX (22.06)** – spread médian SUSS :

| Période | 25k € | 100k € | 1 M€ | Jours `nan` à 1 M€ |
|---|---|---|---|---|
| SDAX (02.01–19.06) | 46.2 bps | 78.8 | 842 | 2,5 % |
| MDAX (22.06–30.10) | 41.0 bps (−11 %) | 62.2 (−21 %) | 566 (−33 %) | 0 % |
| 20 jours avant (21.05–19.06) | 42.9 | 73.7 | 659 | 4,5 % |
| 20 jours après (22.06–17.07) | 42.3 | 67.5 | 805 | 0 % |

  - À 25k €, **pas d'effet immédiat** : 42.9 → 42.3 bps sur 20 jours. L'amélioration vient progressivement (août–septembre : 37–39 bps).
  - Le gain est **plus net sur les gros tickets** (100k € et 1 M€) et le carnet n'est plus jamais trop mince à 1 M€ après l'entrée.
  - Prudence : les peers baissent aussi sur la période (Siltronic 53 → 39 bps, Jenoptik 33 → 26, Aixtron 22 → 17) et la médiane MDAX est stable (~21–24 bps) : une partie de l'amélioration est sectorielle, pas propre à SUSS.
  - Dans la fenêtre autour de l'entrée : 45.4 bps le 19.06 (rebalancing), **48.5 bps le 22.06** (1er jour MDAX), 36.0 bps le 26.06 ; à 1 M€ en revanche, 437 → 1 159 bps entre le 19.06 et le 26.06.

**Effet de chaque annonce** (`build_impact_card`, spread 25k € du `trading_day` vs baseline 20 jours) :

| Événement | trading_day | Indice | Spread | Baseline | Variation |
|---|---|---|---|---|---|
| evt_001 FY 2025 results | 30.03 | SDAX | 51.4 bps | 55.3 | −7.1 % |
| evt_002 Q1 2026 results | 07.05 | SDAX | 40.2 | 43.1 | −6.7 % |
| evt_003 Annual General Meeting | 03.06 | SDAX | 41.0 | 39.8 | +3.1 % |
| evt_004 MDAX inclusion announced | 04.06 | SDAX | 38.2 | 39.7 | −3.9 % |
| evt_006 Rebalancing day (dernière clôture SDAX) | 19.06 | SDAX | 45.4 | 44.2 | +2.8 % |
| evt_005 First trading day in the MDAX | 22.06 | MDAX | 48.5 | 44.5 | +8.9 % |
| evt_007 H1 2026 results | 06.08 | MDAX | 50.2 | 44.3 | +13.2 % |
| evt_008 Production network / guidance update | 27.10 | MDAX | 38.3 | 44.0 | −13.0 % |

- Aucune annonce ne déclenche d'anomalie de spread le jour même : le carnet de SUSS absorbe bien les publications.
- Le **lendemain de l'annonce MDAX (05.06)**, le spread passe à 52.0 bps (+31 % vs baseline) : anomalie détectée, mais non liée automatiquement (lien = même jour uniquement).
- **H1 (06.08)** : le plus fort écartement parmi les annonces (+13 %), puis resserrement rapide à 35–41 bps sur les 5 jours suivants.
- **Guidance (27.10)** : le spread se **resserre** (38.3 vs 44.0 bps) le jour de la mise à jour de la guidance ; à interpréter avec le volume et le prix (OHLC) une fois chargés.

**Anomalies de spread 2026** (règle z > 3 et > 1,2 × baseline) : 3 jours, aucun lié à un événement → candidats « notable day » pour la démo :

| Date | Indice | Spread | Baseline | Variation |
|---|---|---|---|---|
| 20.02.2026 | SDAX | 75.3 bps | 50.4 | +49.3 % |
| 05.06.2026 | SDAX | 52.0 | 39.6 | +31.2 % (J+1 de l'annonce MDAX) |
| 12.10.2026 | MDAX | 52.1 | 40.8 | +27.8 % |

## 6. Scénario de la démo (SUSS MicroTec SE)

| Date | Événement | Type |
|---|---|---|
| 30.03.2026 | Résultats FY 2025 | `annual_results` |
| 07.05.2026 | Résultats Q1 2026 | `quarterly_results` |
| 03.06.2026 | Assemblée générale | `agm` |
| 04.06.2026 | Annonce de l'entrée en MDAX (effective le 22.06) | `index_change` |
| 19.06.2026 | Rebalancing : dernière closing auction avant l'entrée en MDAX (17:35, `trading_day` forcé au 19.06) | `index_change` |
| 22.06.2026 | Premier jour dans le MDAX | `index_change` |
| 06.08.2026 | Résultats H1 2026 | `quarterly_results` |
| 27.10.2026 | Optimisation du réseau de production et mise à jour de la guidance FY 2026 | `press_release` |

**Storyline du pitch :** « SUSS entre en MDAX : qu'est-ce qui a changé pour la liquidité de l'action, et comment le marché a-t-il réagi à chaque annonce, jusqu'à la baisse de guidance du 27.10 ? »

1. **Dashboard** (janv.–oct.) : SUSS ~40 % moins cher que la médiane SDAX, mais 2× la médiane MDAX et au-dessus d'Aixtron/Jenoptik.
2. **Entrée en MDAX** : impact card evt_004 puis evt_005 ; message honnête : pas de miracle le 1er jour à 25k €, mais −11 % de spread médian sur la période MDAX et −33 % à 1 M€ (en partie sectoriel, cf. peers).
3. **Clic sur l'anomalie du 05.06** : impact card « jour » (`/days/{isin}/2026-06-05/impact-card`) : spread +31 % le lendemain de l'annonce.
4. **Résultats** : compare `quarterly_results` / `annual_results` (FY −7 %, Q1 −7 %, H1 +13 %).
5. **27.10, guidance** : impact card evt_008, résumé IA, export PDF.

## 7. Architecture

```
┌──────────────────────────────────────────────┐
│  FRONT-END (TypeScript)                      │
│  Dashboard · Events · Impact Card ·          │
│  Compare · Export                            │
└──────────────────────┬───────────────────────┘
                       │  HTTP / JSON  (OpenAPI → types TS)
┌──────────────────────▼───────────────────────┐
│  API LAYER (Python · FastAPI)                │
│  /stocks /dashboard /events /impact-card     │
│  /compare /report                            │
└────┬──────────────┬──────────────┬───────────┘
     │              │              │
┌────▼─────────┐ ┌──▼──────────┐ ┌─▼────────────┐
│ ANALYTICS    │ │ EVENT ENGINE│ │ AI LAYER     │
│ baseline,    │ │ annonce →   │ │ LLM : résumé │
│ z-score,     │ │ trading_day │ │ en langage   │
│ anomalies,   │ │ (avant/après│ │ clair à      │
│ peers,       │ │ clôture)    │ │ partir des   │
│ EMA/MACD/S&R │ │             │ │ chiffres     │
└────┬─────────┘ └──┬──────────┘ └──────────────┘
     │              │
┌────▼──────────────▼──────────────────────────┐
│  DATA LAYER (ETL)                            │
│  charge, nettoie, fusionne par isin + date   │
└────┬──────────┬──────────┬──────────┬────────┘
   OHLC      Flows     Spreads (XLM)  events.csv
```

### Stack

| Couche | Choix | Statut |
|---|---|---|
| Front-end | TypeScript | ✅ Décidé |
| Back-end | Python 3.11+ · FastAPI · Pydantic · pandas | ✅ Décidé |
| Données | CSV chargés en mémoire au démarrage (~26 Mo pour les spreads) | ✅ Décidé |
| Lien front/back | HTTP/JSON ; CORS ; types TS générés depuis `/openapi.json` | ✅ Décidé |
| IA | SDK OpenAI ou Anthropic | À choisir |
| Export | PDF (côté back ou front) | À choisir |

### Structure du repo

```
issuer-hub/
├── PROJECT.md              # ce document
├── CLAUDE.md               # règles back-end, ownership, interfaces internes
├── shared/
│   └── types.ts            # contrat API de référence (front)
├── mocks/                  # JSON d'exemple, un par endpoint + API.md
├── data/
│   ├── raw/                # données Deutsche Börse (gitignore)
│   └── events.csv          # annonces SUSS MicroTec (fait main)
├── app/
│   ├── main.py             # [backend] app FastAPI, CORS
│   ├── etl/                # [backend] chargement des CSV
│   ├── schemas/            # [backend] modèles Pydantic
│   ├── api/                # [backend] routes
│   ├── export/             # [backend] PDF
│   ├── analytics/          # [Alfred] metrics, anomalies, peers, impact cards
│   └── assistant/          # [Alfred] LLM, prompts
├── tests/
└── frontend/               # [Yassine] (ou repo séparé)
```

## 8. API contract (v0.1)

Base URL locale : `http://localhost:8000`. Détails de chaque champ : `mocks/API.md`. Types : `shared/types.ts` ; doc auto : `/docs`.

| Endpoint | Réponse (type) | Écran |
|---|---|---|
| `GET /stocks` | `StocksResponse` | Sélecteur d'action |
| `GET /stocks/{isin}/dashboard?from=&to=` | `DashboardResponse` | Part A |
| `GET /stocks/{isin}/events` | `EventsResponse` | Liste des annonces |
| `GET /events/{event_id}/impact-card` | `ImpactCardResponse` | Part B (one click) |
| `GET /days/{isin}/{date}/impact-card` | `ImpactCardResponse` (`event: null`) | Clic sur une anomalie |
| `GET /compare?type=&index=&from=&to=` | `CompareResponse` | Comparaison d'événements |
| `GET /stocks/{isin}/report?from=&to=` | `ReportResponse` | IR snapshot / export |

**Règle d'or :** toute modification du contrat passe par le mock + `types.ts` + le schéma Pydantic, et est annoncée à toute l'équipe (procédure dans `CLAUDE.md`).

## 9. Règles de calcul

| Métrique | Définition |
|---|---|
| `baseline` | Moyenne des **20 jours de trading** avant le jour mesuré (jour exclu) |
| `volume_ratio` | volume du jour ÷ baseline volume |
| `z_score` | (valeur − moyenne 20j) ÷ écart-type 20j |
| `spread_bps` | `Impact_bps` du XLM au notional **25 000 €** |
| `auction_share` | volume AUCTION ÷ volume total (Flows) |
| Anomalie volume | `z_score > 2` (medium) ou `> 3` (high) |
| Anomalie spread | z-score > 3 **et** spread > 1,2 × baseline (high si z > 4 ou > 1,5 ×) – calibré : ~3,7 alertes/action sur 10 mois |
| `trading_day` | Annonce **avant 17:30** → même jour ; **après 17:30** → jour de trading suivant |
| `window` (impact card) | Jours −5 à +5 autour du `trading_day` |
| Peers | Même indice + liste manuelle (pas de colonne secteur) : Aixtron, Jenoptik, Siltronic, Elmos Semiconductor |
| EMA / MACD / S&R | EMA20, EMA50, MACD(12,26,9), support/resistance sur pivots locaux. **Descriptif uniquement, jamais de prédiction de prix** |
| `ai_summary` | Le LLM **reformule uniquement les chiffres fournis**, n'invente rien. Disclaimer : « Not investment advice » |

## 10. Répartition du travail

| Qui | Tâches |
|---|---|
| **Alfred** (analyse & assistant) | `app/analytics/` : metrics, anomalies, peers, indicateurs, impact cards, compare, report · `app/assistant/` : résumés LLM · `data/events.csv` |
| **Partenaire back-end** | Setup du repo, `app/main.py`, `app/etl/` (chargement des CSV), `app/schemas/` (Pydantic), `app/api/` (routes, CORS, erreurs), `app/export/` (PDF) |
| **Yassine** (front-end) | UI à partir des mocks : Dashboard, liste d'événements, Impact Card, Compare, export |
| **Toute l'équipe** | Pitch, slide « ideas for IR », répétition de la démo |

### Ordre de travail

1. ✅ Mocks JSON + `API.md` + `types.ts` → le front peut démarrer
2. ✅ Analyse du dataset Spreads
3. ⏳ Télécharger OHLC et Flows, lire les NOTES.md
4. ⏳ Constituer `events.csv` pour SUSS MicroTec
5. ⏳ ETL + analytics (Part A) → remplacer le mock `dashboard`
6. ⏳ Event engine + impact card (Part B) → remplacer le mock `impact-card`
7. ⏳ AI summary + export
8. ⏳ Compare, peers, finitions, pitch

## 11. Idées bonus pour les IR (slide de pitch)

- **Shareholder / flow analysis** : qui achète et qui vend après une annonce (AGENT vs PROP) → données Flows.
- **Index watch** : alerte quand l'action se rapproche d'un changement d'indice (entrée/sortie MDAX) → market cap + free float.
- **Derivatives sentiment** : évolution de l'open interest LONG/SHORT avant les résultats → données Eurex.
- **News sentiment** : lier la tonalité des articles de presse aux mouvements → données news externes.
- **Analyst coverage** : nombre d'analystes et consensus → données tierces.
- **Alerting** : notification automatique quand une anomalie est détectée.

## 12. Questions ouvertes

- [x] Back-end en Python (FastAPI + pandas)
- [ ] Quel fournisseur LLM (et qui a une clé API) ?
- [x] Peers de SUSS MicroTec : Aixtron (AIXA), Jenoptik (JEN), Siltronic (WAF), Elmos Semiconductor (ELG)
- [ ] Les Flows séparent-ils opening et closing auction ? (vérifier dans NOTES.md)
- [ ] Heures exactes des annonces SUSS MicroTec (07:00 supposé pour les résultats)
