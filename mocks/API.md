# Issuer Intelligence Hub – API contract (v0.1)

Base URL (local): `http://localhost:8000`
Toutes les réponses sont en JSON. Les fichiers `*.json` dans ce dossier sont des **mock data** : même format que la vraie API.

## Endpoints

| Méthode | Endpoint | Mock | Écran front-end |
|---|---|---|---|
| GET | `/stocks` | `stocks.json` | Sélecteur d'action |
| GET | `/stocks/{isin}/dashboard?from=&to=` | `dashboard.json` | Part A – Dashboard |
| GET | `/stocks/{isin}/events` | `events.json` | Liste/timeline des annonces |
| GET | `/events/{event_id}/impact-card` | `impact-card.json` | Part B – Impact card (bouton "one click") |
| GET | `/days/{isin}/{date}/impact-card` | `impact-card.json` (`event: null`) | Impact card pour un "notable day" (clic sur une anomalie) |
| GET | `/compare?type=&index=&from=&to=` | `compare.json` | Comparaison d'événements du même type |
| GET | `/stocks/{isin}/report?from=&to=` | `report.json` | IR snapshot (export) |

## Conventions

- **Dates** : `YYYY-MM-DD`. Timestamps : ISO 8601 avec fuseau (`+01:00`).
- **isin** : identifiant unique de l'action (démo : SUSS MicroTec SE = `DE000A1K0235`, mnemonic SMHN).
- **volume** : nombre d'actions. **turnover_eur** : montant en euros.
- **spread_bps** : spread en basis points (1 bp = 0,01 %), basé sur le XLM (colonne "impact").
- **auction_share** : part du volume exécutée en enchère (0–1).
- **volume_ratio** : volume du jour ÷ baseline (moyenne 20 jours). 1.0 = normal, 3.0 = 3× plus que normal.
- **z_score** : écart à la normale en écarts-types (> 2 = inhabituel).
- **change_pct** : variation en %. **change_pts** : variation en points (pour les ratios).
- **anomaly** (`dashboard.series`) : `true` → mettre le point en évidence ; le détail est dans `anomalies[]`.
- **window** (`impact-card`) : jours autour de l'événement, `offset 0` = jour de l'événement. Idéal pour un petit graphique avant/après.
- **trading_day** (`events`) : jour où l'effet est mesuré. Une annonce après la clôture (17:30) compte pour le jour suivant.
- **event_types** : `quarterly_results`, `annual_results`, `ad_hoc`, `dividend`, `press_release`, `m_and_a`, `agm`, `index_change`.
- **technical_context** : valeurs possibles `trend_before`: `above_ema50` | `below_ema50` ; `macd_*`: `bullish` | `bearish` ; `broke_level`: `null` ou `{type: "support"|"resistance", price}`.
- **export.pdf_url** : bouton "Export PDF" (sera disponible plus tard ; en attendant, ignorer).

- **null** : certaines valeurs (volume, prix, auctions) sont `null` tant que les données OHLC/Flows ne sont pas chargées. Afficher « – » dans l'UI.
- **_data_status** : champ technique `{spreads|ohlc|flows: "real"|"mock"|"missing"}` – utile pour afficher un badge « données de démo » pendant le dev.

## Suggestions UI

- **Dashboard** : graphique prix (close + EMA20/EMA50 + lignes support/resistance), graphique volume (barres, anomalies en rouge), graphique spread vs `peers_series`, cartes KPI en haut.
- **Impact card** : 4–6 grosses tuiles (volume ×, prix %, spread %, auctions), graphique `window`, barres `flows.by_participant` (net buy/sell), texte `ai_summary`, bouton export.
- **Compare** : tableau triable + scatter plot (`volume_ratio` vs `price_change_pct`).
