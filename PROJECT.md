# Issuer Intelligence Hub – Futury Build Days 2026

> Challenge **Deutsche Börse** · Démo avec **Deutsche Pfandbriefbank AG (pbb)** (`DE0008019001`, mnemonic `PBB`)
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
| **ISIN** | Identifiant unique d'une action (pbb = `DE0008019001`) |
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
- `nan` = carnet pas assez profond pour ce montant (seuil à mesurer pour pbb).
- La colonne `Index` suit les changements d'indice (ex. SUSS MicroTec : SDAX → MDAX le 22.06 ; historique de pbb à vérifier).
- **Pas de colonne secteur** : les peers sont à définir à la main.
- **Notional de référence pour l'UI : 25 000 €.**

### 4.3 À collecter nous-mêmes

Le **corporate event calendar** de pbb, depuis des sources publiques (site IR pbb, communiqués EQS, annonces ad hoc) → `data/events.csv` :

```
event_id,isin,date,time,trading_day,type,title,source_url
```

> ⚠️ **À vérifier** : heures exactes des annonces pbb (avant/après 17:30) sur le site IR / EQS. Les données s'arrêtent au 30.10.2026.

## 5. Premiers résultats pbb (spread à 25k €)

> ⏳ À recalculer pour pbb (`DE0008019001`) depuis `data/raw/spreads` : médiane mensuelle à 25 000 € vs médianes d'indice et peers, effet de chaque annonce, anomalies de spread.
> L'analyse précédente portait sur SUSS MicroTec (voir l'historique git, commit `92d9aa0`).

## 6. Scénario de la démo (Deutsche Pfandbriefbank AG (pbb))

> ⏳ À construire une fois `data/events.csv` constitué pour pbb (résultats annuels/trimestriels, AG, ad hoc, éventuels changements d'indice).

**Storyline du pitch :** à définir.

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
│   └── events.csv          # annonces pbb (fait main)
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
| Peers | Même indice + liste manuelle (pas de colonne secteur) : à définir pour pbb |
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
4. ⏳ Constituer `events.csv` pour pbb
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
- [ ] Peers de pbb (banques / immobilier commercial cotés dans DAX/MDAX/SDAX)
- [ ] Les Flows séparent-ils opening et closing auction ? (vérifier dans NOTES.md)
- [ ] Heures exactes des annonces pbb
