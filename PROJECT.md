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
| **OHLC** | `XETRA/XETRA_OHLC` : open/high/low/close (mid), volume, turnover, VWAP, prix et heures des 3 enchères | ✅ `load_ohlc()` |
| **Xetra Flows (equity)** | `XETRA/XETRA_FLOW_DYNAMICS_EQUITY` : volume par participant type, market mode et side | ✅ `load_flows()` |
| **Trades on-book** | `XETRA/XETRA_ONBOOK_TRADES` : chaque trade (~400k/jour), horodatage UTC ns, side de l'agresseur | ✅ `scripts/extract_trades.py` → `load_trades(isin)` |
| **Index constituents** | `index_constituents` : composition DAX/MDAX/SDAX par jour (mnemonic, ISIN ; pas de nom ni de secteur) | ✅ `get_universe()`, `index_on_date()` |
| **Eurex, ETP, TES off-book** | Dérivés, open interest, ETP, trades hors carnet | ⏸ Ignorés pour l'instant |

Chaque dossier contient un **PDF** (description des colonnes) et un **NOTES.md**. **À lire en premier.**

**Points importants et surprises (ETL, pbb `DE0008019001`)** :
- **OHLC** : une ligne par instrument **et devise** → filtre `EQUITIES` + `EUR`. `OPEN/HIGH/LOW/CLOSE_PRICE` sont des **prix mid cotés**, pas des prix de trade ; `close` = prix de la closing auction (présent les 213 jours pour pbb). `ADJUSTED_PRICE` est obsolète et faux : ignoré.
- **Flows** : `AUCTION` regroupe **toutes** les enchères (pas de séparation opening/closing) → on passe par les trades. La date est `REPORTED_FLOW_DATES` (pas `DATE`) ; pour pbb les 213 jours sont alignés, sans censure ni ligne différée. La colonne `VOLUME` du fichier compte achat + vente (×2). Contrôle : achats totaux pbb du 29.09 = 163 670 actions = volume OHLC.
- **Trades** : horodatage **UTC** (closing auction à 15:35 UTC en été = 17:35 Francfort). Side vide = pas d'agresseur (enchères). pbb : **76 317 trades** sur 213 jours (~360/jour, titre peu liquide). Les trades « opening » et « closing » ont exactement le prix d'enchère de l'OHLC ; part des enchères 32 % du volume (= Flows), dont **30 % en closing auction**. 474 trades sans agresseur hors des 3 enchères (08:00, après 17:40 : heures étendues / interruptions de volatilité) → `auction_type` vide. Le 11.09, la somme des trades est inférieure de 4 666 actions au volume OHLC.
- **Index constituents** : 174 ISIN, identiques au XLM. Pas de nom (→ `config.NAMES` puis `INSTRUMENT_NAME` de l'OHLC). pbb en SDAX toute l'année ; ProCredit entre en SDAX le 14.10, W&W en sort après le 05.10.
- **Temps de chargement** : XLM 0,5 s · OHLC 2,1 s · Flows 1,8 s (2,6 M lignes) · univers 0,4 s · trades pbb 0,1 s · extraction des trades (7 ISIN, 213 fichiers) 30 s.

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

Calculés depuis les données réelles (`app/analytics/pricing.py`). Spread = médiane mensuelle de `Impact_bps` à 25 000 € ; médiane d'indice = tous les titres de l'indice **à la date** ; peers = GRENKE, Hypoport, MLP, ProCredit (dès le 14.10), W&W (jusqu'au 05.10), flatexDEGIRO.

### 5.1 Le fil rouge : 54 → 97 bps

| Mois | pbb (bps) | Médiane SDAX | Médiane peers | Cours moyen pbb | Coût / action | Ticks |
|---|---|---|---|---|---|---|
| Janvier | **54.3** | 70.0 | 72.3 | 4.26 € | 0.023 € | 23.3 |
| Février | 56.4 | 69.3 | 72.1 | 3.90 € | 0.022 € | 21.8 |
| Mars | 56.5 | 72.0 | 81.4 | 2.96 € | 0.017 € | 16.9 |
| Avril | 62.2 | 71.6 | 78.0 | 3.21 € | 0.020 € | 20.0 |
| Mai | 72.6 | 74.2 | 71.2 | 3.46 € | 0.025 € | 24.7 |
| Juin | 72.4 | 81.8 | 84.0 | 3.41 € | 0.025 € | 24.6 |
| Juillet | 78.4 | 84.1 | 92.4 | 3.46 € | 0.028 € | 27.6 |
| Août | 76.6 | 73.8 | 76.2 | 3.43 € | 0.027 € | 26.6 |
| Septembre | 69.8 | 67.9 | 68.5 | 3.26 € | 0.023 € | 23.0 |
| Octobre | **97.4** | 70.9 | 70.6 | 2.92 € | 0.028 € | 27.7 |

- **+79 %** entre janvier et octobre : pbb passe de **moins cher** que la médiane SDAX (54 vs 70 bps) à **nettement plus cher** (97 vs 71) et que ses peers (71).
- **Rupture le 29.09.2026** : médiane 69,4 bps du 01 au 28.09, puis 95,3 bps du 29.09 au 30.10. Trois anomalies de spread consécutives (29.09, 02.10, 06.10, sévérité high), aucune annonce de pbb ce jour-là.
- Coût pour 25 000 € échangés (`spread_eur` = bps × 2,5) : 135,8 € en janvier → 243,4 € en octobre.

### 5.2 Effet prix ou vrai recul de liquidité ?

Le spread XLM est **relatif au prix**. Si le coût en € par action restait constant, une baisse du cours augmenterait mécaniquement le spread en bps. Décomposition (`pricing.decompose`) : effet prix = `bps_a × P_a / P_b − bps_a` (coût constant en € par action), effet liquidité = le reste.

| Comparaison | Spread | Cours moyen | Variation | Effet prix | Effet liquidité |
|---|---|---|---|---|---|
| Janvier → octobre | 54.3 → 97.4 bps | 4.26 → 2.92 € | +43.0 bps | +25.0 (58 %) | +18.0 (42 %) |
| Janv.–mars → août–oct. | 55.9 → 77.3 bps | 3.69 → 3.20 € | +21.4 bps | +8.6 (40 %) | +12.8 (60 %) |
| 01–28.09 → 29.09–30.10 | 69.4 → 95.3 bps | 3.28 → 2.93 € | +25.9 bps | +8.2 (32 %) | +17.6 (68 %) |

Comparaison janv.–mars → août–oct. :

| | Spread | Cours | Effet prix | Effet liquidité |
|---|---|---|---|---|
| **pbb** | 55.9 → 77.3 | −13 % | +8.6 | **+12.8** |
| Médiane SDAX (59 titres restés en SDAX) | 72.7 → 72.1 | −6.5 % (médiane) | +3.3 | −2.0 |
| GRENKE | 72.0 → 66.8 | −24 % | +22.6 | −27.7 |
| Hypoport | 77.9 → 72.5 | −17 % | +15.8 | −21.1 |
| MLP | 103.4 → 76.1 | +32 % | −25.1 | −2.2 |
| W&W | 79.7 → 91.7 | −9 % | +7.5 | +4.5 |
| flatexDEGIRO (MDAX) | 23.4 → 24.0 | −12 % | +3.2 | −2.5 |

**Conclusion (honnête) :**
- Environ **la moitié** de la hausse 54 → 97 bps s'explique par la baisse du cours (58 % sur janvier → octobre, 40 % sur des trimestres). **L'autre moitié est un vrai recul de liquidité** : le coût en € par action monte de 0,023 € à 0,028 € (+19 %), de 23 à 28 ticks.
- La rupture du **29.09** est surtout de la liquidité (68 %) : c'est le jour à expliquer dans la démo.
- Le recul est **propre à pbb** : sur la même période, la médiane SDAX et la plupart des peers voient leur liquidité s'améliorer (effet liquidité négatif), même quand leur cours baisse (GRENKE, Hypoport).
- L'« effet prix » est une **borne haute**, pas une loi : le tick Xetra de pbb (0,001 €, déduit des trades) est très en dessous du spread (17–28 ticks), donc le tick ne force pas le spread en €. Preuve : en mars le cours chute de 30 % mais le spread en bps ne bouge presque pas (coût par action 0,023 → 0,017 €).
- **Limites** : tick déduit empiriquement des prix exécutés (≥ 99,5 % des prix sur la grille, mois par mois), pas lu dans le référentiel MiFID II (bandes de liquidité revues chaque année ; Hypoport passe de 0,05 € à 0,005 € en avril). Médianes mensuelles sur ~20 séances.

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
3. ✅ OHLC, Flows, trades et index constituents chargés (ETL), NOTES.md lus
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
- [x] Peers de pbb (config.PEERS, Alfred) : GRENKE, Hypoport, MLP, ProCredit, W&W, flatexDEGIRO
- [x] Les Flows séparent-ils opening et closing auction ? **Non** (`AUCTION` = toutes les enchères) → `load_trades(isin)["auction_type"]`
- [ ] Heures exactes des annonces pbb
