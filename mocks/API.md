# Issuer Intelligence Hub – API pour le front-end (v0.3)

> Pour Yassine · Démo : **Deutsche Pfandbriefbank AG (pbb)**, ISIN `DE0008019001`, SDAX
> Ce document remplace `mocks/API.md` v0.1. Les changements depuis la v0.1 sont marqués **🆕**, et ce qui arrive bientôt est marqué **🔜**.

Base URL locale : `http://localhost:8000` · Doc interactive : `http://localhost:8000/docs`

Générer les types TypeScript depuis l'API :

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api-types.ts
```

En attendant l'API, utilise `mocks/*.json` et `shared/types.ts` : même format.

---

## 1. Ce qui a changé depuis la v0.1

| # | Changement | Impact sur le front |
|---|---|---|
| 1 | 🆕 Entreprise de démo : **pbb** (`DE0008019001`, SDAX toute l'année) | Seulement les données affichées ; aucun changement de format |
| 2 | 🆕 Champs **`null`** possibles (volume, prix, auctions…) si une donnée manque | Afficher « – » au lieu de planter ; jamais `NaN` |
| 3 | 🆕 `headline_metric.spread_change_pct` dans les événements | Nouveau chiffre clé à afficher dans la liste |
| 4 | 🆕 `spread_change_pct` dans les items « Notable events » du report | Idem |
| 5 | 🆕 Champ technique **`_data_status`** sur dashboard, impact card, report | Optionnel : badge « demo data » si une valeur vaut `"mock"` |
| 6 | 🆕 Nouveaux **types d'événements** : `voting_rights`, `directors_dealings` (en plus de `index_change`, `annual_results`…) | Prévoir un libellé et une icône |
| 7 | 🆕 Règle d'**anomalie de spread** recalibrée (plus d'alertes pertinentes) | Aucun ; la liste `anomalies` est simplement plus remplie |
| 8 | 🆕 Bloc **`intraday`** dans l'impact card (réaction minute par minute, §5.1) | Nouveau graphique |
| 9 | 🆕 Nouveaux **types d'anomalies** : `large_trade`, `aggressor_sweep`, `net_flow`, `auction_spike` (§5.2), champs optionnels `time`, `side`, `notional_eur` | Libellés, icônes et couleurs |
| 11 | 🆕 `event.published_at` peut valoir `null` (heure de publication non vérifiée) | Afficher seulement la date |
| 12 | 🆕 `dashboard.series[].spread_eur` (coût en € pour 25 000 €) et `spread_ticks` (coût par action en ticks Xetra), nullable | Option : 2e axe « € » sur le graphique spread |
| 13 | 🆕 `_data_status` de l'impact card : clés `opening_closing_auction` et `intraday` en plus | Aucun |
| 10 | 🔜 Nouvel endpoint **`/event-preview`** : anticiper l'impact d'une annonce à venir | Nouvelle carte « What to expect » |
| 14 | 🆕 v0.3 : nouvelles anomalies **`price_move`** (« notable day ») et **`level_break`** (champs `level_type`, `level_price`) | Libellés, icônes |
| 15 | 🆕 v0.3 : **`detail_url`** sur chaque anomalie (impact card de l'événement, sinon du jour) | Utiliser ce lien au clic |
| 16 | 🆕 v0.3 : seuils `large_trade` / `aggressor_sweep` relevés (10 % de l'ADTV, ≥ 3 exécutions) : beaucoup moins d'alertes | Aucun |
| 17 | 🆕 v0.3 : bloc **`pre_disclosure_activity`** dans l'impact card des notifications `voting_rights` (§5.4) | Petit encadré « Before the disclosure » |

---

## 2. Endpoints

| Méthode | Endpoint | Type TS | Écran |
|---|---|---|---|
| GET | `/stocks` | `StocksResponse` | Sélecteur d'action |
| GET | `/stocks/{isin}/dashboard?from=&to=` | `DashboardResponse` | Part A – Dashboard |
| GET | `/stocks/{isin}/events` | `EventsResponse` | Timeline des annonces |
| GET | `/events/{event_id}/impact-card` | `ImpactCardResponse` | Part B – Impact card (one click) |
| GET | `/days/{isin}/{date}/impact-card` | `ImpactCardResponse` (`event: null`) | Clic sur une anomalie sans annonce |
| GET | `/compare?type=&index=&from=&to=` | `CompareResponse` | Comparer des événements du même type |
| GET | `/stocks/{isin}/report?from=&to=` | `ReportResponse` | IR snapshot |
| GET | `/events/{event_id}/impact-card.pdf` | PDF | Bouton export |
| GET | `/stocks/{isin}/report.pdf` | PDF | Bouton export |
| GET | 🔜 `/stocks/{isin}/event-preview?type=&date=` | `EventPreviewResponse` | Carte « What to expect » |

- `from` / `to` : `YYYY-MM-DD`. Données disponibles du **2026-01-02 au 2026-10-30**.
- `index` dans `/compare` : `DAX`, `MDAX`, `SDAX` ou `ALL`.
- Erreurs : `404` (ISIN, événement ou jour inconnu), `422` (paramètre invalide), corps `{"detail": "…"}`.

---

## 3. Conventions

| Champ / unité | Signification |
|---|---|
| Dates | `YYYY-MM-DD` ; timestamps ISO 8601 avec fuseau (`+01:00`) |
| `volume` | Nombre d'actions |
| `turnover_eur` | Montant échangé en € |
| `spread_bps` | Coût d'un aller-retour de **25 000 €**, en basis points (1 bp = 0,01 %). Plus c'est haut, plus l'action est chère à trader |
| `volume_ratio` | Volume du jour ÷ moyenne des 20 jours précédents. `1.0` = normal, `3.0` = 3× la normale |
| `z_score` | Écart à la normale en écarts-types (> 2 = inhabituel, > 3 = très inhabituel) |
| `*_pct` | Variation en % (`8.2` = +8,2 %) |
| `*_pts` | Variation en points de ratio (`0.09` = +9 points de %) |
| `auction_share` | Part du volume exécutée aux enchères, entre 0 et 1 |
| `trading_day` | Jour où l'effet d'une annonce est mesuré : même jour si publiée avant 17:30, sinon jour de trading suivant |
| `window[]` | Jours de trading de −5 à +5 autour de l'événement ; `offset: 0` = jour de l'événement |
| `null` | 🆕 Donnée indisponible → afficher « – » |
| `_data_status` | 🆕 `{ "spreads" \| "ohlc" \| "flows": "real" \| "mock" \| "missing" }`, technique, à ignorer ou afficher en badge |

Arrondis côté API : prix et ratios à 2 décimales, bps et % à 1 décimale. Pas besoin d'arrondir côté front.

### Types d'événements

| `type` | Libellé suggéré |
|---|---|
| `annual_results` | Annual results |
| `quarterly_results` | Quarterly results |
| `ad_hoc` | Ad hoc announcement |
| `dividend` | Dividend |
| `agm` | AGM |
| `press_release` | Press release |
| `index_change` | Index change |
| `m_and_a` | M&A |
| 🆕 `voting_rights` | Voting rights notification (WpHG) |
| 🆕 `directors_dealings` | Directors' dealings |

### Types d'anomalies (`dashboard.anomalies[].type`)

| `type` | Signification | Statut |
|---|---|---|
| `volume_spike` | Volume très au-dessus de la normale | ✅ |
| `spread_widening` | Spread très au-dessus de la normale (action plus chère à trader) | ✅ |
| `large_trade` | Une exécution unique très grosse (≥ 10 % de l'ADTV 30 j) | ✅ v0.3 |
| `aggressor_sweep` | Rafale d'au moins 3 exécutions consécutives du même côté en ≤ 1 s, somme ≥ 10 % de l'ADTV 30 j (proxy d'un gros ordre) | ✅ v0.3 |
| `net_flow` | Flux net AGENT ou PROP (en €) > 20 % de l'ADTV 30 j (Flows journaliers uniquement) | ✅ |
| `auction_spike` | Part de la closing auction > 2 × sa moyenne des 20 séances précédentes | ✅ |
| `price_move` | « Notable day » : \|rendement excédentaire vs médiane des peers\| > 2,5 % **et** volume > 1,5 × la normale (une journée où tout le secteur bouge ne compte pas) | 🆕 v0.3 |
| `level_break` | Clôture qui franchit un support ou une résistance (calculés sur l'historique avant le jour), volume > 1,5 × la normale **et** un `large_trade` ou `aggressor_sweep` le même jour. Descriptif uniquement, aucune projection de prix | 🆕 v0.3 |

Nombre de jours d'alerte sur pbb (213 séances, 02.01–30.10.2026) : `large_trade` 13, `aggressor_sweep` 38, `net_flow` 34, `price_move` 15, `auction_spike` 5, `level_break` 1.

`severity` : `medium` ou `high`. `linked_event_id` : l'annonce du même jour, ou `null` → jour inhabituel **sans explication connue**. 🆕 `detail_url` : lien à ouvrir au clic (`/events/{event_id}/impact-card` si `linked_event_id`, sinon `/days/{isin}/{date}/impact-card`).

---

## 4. Changements de format en détail

### 4.1 Événements – `GET /stocks/{isin}/events` 🆕

```json
{
  "event_id": "evt_002",
  "date": "2026-02-13",
  "time": "12:26",
  "trading_day": "2026-02-13",
  "type": "ad_hoc",
  "title": "Ad hoc: guidance for FY 2026 …",
  "source_url": "https://www.eqs-news.com/…",
  "has_impact_card": true,
  "headline_metric": {
    "volume_ratio": 2.1,          // number | null
    "price_change_pct": -3.4,     // number | null
    "spread_change_pct": -2.2     // 🆕 number | null
  }
}
```

`time` peut être vide (`""`) si l'heure de publication n'est pas connue.

### 4.2 Champs pouvant être `null` 🆕

- `headline_metric.volume_ratio`, `price_change_pct`, `spread_change_pct`
- `compare.events[].volume_ratio`, `price_change_pct`, `spread_change_pct`, `auction_share_change_pts`
- `compare.summary.median_*`
- `dashboard.series[].auction_share`, `dashboard.peers_series[].*`
- `report.sections[].items[].volume_ratio`, `price_change_pct`, `spread_change_pct`

### 4.3 `_data_status` 🆕

```json
"_data_status": { "spreads": "real", "ohlc": "real", "flows": "mock" }
```

---

## 5. Nouveaux blocs

§5.1 et §5.2 sont **implémentés** (mocks `impact-card.json` et `dashboard.json` générés depuis les vraies données pbb). §5.3 reste 🔜 proposé.

> ADTV = moyenne du `turnover_eur` (OHLC) des 30 séances précédentes. Seuils dans `app/config.py` (`ALERT_*`). `severity` = `high` si la valeur dépasse 2 × le seuil.

### 5.1 Bloc `intraday` dans l'impact card ✅

La réaction du marché **minute par minute** autour de l'annonce. `null` si les trades ne sont pas disponibles.

- Annonce pendant le continu (09:00–17:30, le jour même) : référence = heure de publication, `during_session: true`.
- Annonce hors séance, heure inconnue, ou « notable day » : référence = ouverture du `trading_day` (opening auction), `during_session: false` ; `price_change_pct` est alors mesuré depuis le premier prix d'ouverture.
- `volume` / `vwap` comptent toutes les exécutions on-book de la séance (enchères comprises) ; `buy_aggressor_share` seulement celles avec un côté agresseur. `vwap` arrondi à 2 décimales (convention prix).

```json
"intraday": {
  "reference_time": "2026-02-13T12:26:00+01:00",   // heure de publication, ou ouverture si hors séance
  "during_session": true,
  "minutes": [
    { "offset_min": -30, "time": "11:56", "vwap": 5.82, "volume": 1200, "cum_volume": 1200, "buy_aggressor_share": 0.48 },
    { "offset_min": 0,   "time": "12:26", "vwap": 5.80, "volume": 8400, "cum_volume": 31500, "buy_aggressor_share": 0.31 }
    // … jusqu'à +120
  ],
  "first_15min": { "volume": 95000, "baseline": 21000, "ratio": 4.52 },
  "price_change_pct": { "after_5min": -1.2, "after_30min": -2.8, "after_60min": -3.1 }
}
```

**UI suggérée** : graphique avec ligne de prix (`vwap`) + barres de volume, et une ligne verticale à `offset_min = 0` (« announcement »). Trois tuiles : volume des 15 premières minutes (×), prix à +5, +30 et +60 min.

### 5.2 Nouvelles anomalies ✅

Même format que les anomalies actuelles, avec quelques champs en plus selon le type :

```json
{
  "date": "2026-10-02",
  "type": "large_trade",
  "severity": "high",
  "value": 0.08,                       // ici : part de l'ADTV 30 jours
  "description": "A single execution of EUR 640k (8% of 30-day average daily turnover) at 10:42",
  "linked_event_id": null,
  "detail_url": "/days/DE0008019001/2026-10-02/impact-card",   // 🆕 v0.3, sur toutes les anomalies
  "time": "10:42:13",                  // large_trade / aggressor_sweep uniquement
  "side": "SELL",                      // côté agresseur (trades) ou sens du flux net (net_flow)
  "notional_eur": 640000               // exécution / rafale / flux net (large_trade, aggressor_sweep, net_flow)
}
```

🆕 v0.3 – `price_move` et `level_break` (exemples réels pbb) :

```json
{
  "date": "2026-05-13", "type": "price_move", "severity": "high",
  "value": 12.1,                       // rendement excédentaire vs médiane des peers, en %
  "description": "Price moved +12.1% vs peers on 2.5x usual volume",
  "linked_event_id": null,
  "detail_url": "/days/DE0008019001/2026-05-13/impact-card"
}
{
  "date": "2026-08-13", "type": "level_break", "severity": "medium",
  "value": 2.52,                       // volume_ratio du jour
  "description": "Close of EUR 3.60 rose above the resistance at EUR 3.59 (2 previous touches) on 2.5x usual volume, confirmed by unusually large executions",
  "linked_event_id": "evt_018",
  "detail_url": "/events/evt_018/impact-card",
  "level_type": "resistance",          // support | resistance
  "level_price": 3.59
}
```

Wording `level_break` : « confirmed by unusually large executions » ; jamais « institutional » ni « retail » (les données ne permettent pas de les distinguer).

Wording : les textes parlent toujours d'« executions » ou d'« aggressive buy orders », **jamais d'« un investisseur »**. Les données ne disent pas qui a passé l'ordre.

### 5.4 🆕 v0.3 – `pre_disclosure_activity` (impact card des `voting_rights`)

Le franchissement d'un seuil de droits de vote **précède** la notification : l'investisseur a jusqu'à 4 jours de bourse pour notifier l'émetteur, qui publie ensuite. Le bloc liste les anomalies et alertes des **7 séances avant le jour de publication** (jour de publication exclu). `null` si rien d'inhabituel, et pour tous les autres types d'événements.

```json
"pre_disclosure_activity": {
  "window": { "from": "2026-08-26", "to": "2026-09-03", "sessions": 7 },
  "days": [
    { "date": "2026-08-31", "anomaly_types": ["aggressor_sweep", "auction_spike", "large_trade", "net_flow", "price_move", "volume_spike"],
      "volume_ratio": 22.74, "agent_net_flow_eur": 6869279 }
  ],
  "summary": "Unusual activity in the 7 sessions before the disclosure: 2 flagged sessions (…). This trading may coincide with the position change reported in the notification; the data do not show who traded."
}
```

Exemple complet : `mocks/impact-card-voting-rights.json` (evt_019, notification Goldman Sachs du 04.09.2026). **Ne jamais** présenter ce trading comme celui de l'investisseur notifié : « may coincide with ».

### 5.3 Event preview : anticiper l'impact d'une annonce à venir

**L'idée** : avant une annonce (ex. résultats du Q3), montrer à l'IR **comment le trading a réagi lors des annonces passées du même type**, pour s'y préparer : prévenir les market makers, choisir l'heure de publication… Ce n'est **pas** une prédiction de prix : seulement des statistiques sur des réactions passées (liquidité, volume).

`GET /stocks/{isin}/event-preview?type=quarterly_results&date=2026-11-05`

```json
{
  "stock": { "isin": "DE0008019001", "name": "Deutsche Pfandbriefbank AG", "index": "SDAX" },
  "event_type": "quarterly_results",
  "upcoming": { "date": "2026-11-05", "title": "Q3 2026 results" },
  "own_history": {
    "n": 3,
    "events": [
      { "event_id": "evt_007", "date": "2026-05-07", "spread_change_pct": 18.0, "volume_ratio": 2.1, "sessions_to_normal": 1 }
    ],
    "spread_change_pct": { "median": 22.0, "min": 9.4, "max": 38.0 },
    "volume_ratio":      { "median": 2.1,  "min": 1.6, "max": 2.8 },
    "sessions_to_normal":{ "median": 1,    "min": 1,   "max": 3 },
    "price_abs_change_pct": { "median": 2.9, "min": 1.1, "max": 4.2 }
  },
  "peers": {
    "n": 5,
    "spread_change_pct": { "median": 15.0, "min": 3.0, "max": 31.0 },
    "volume_ratio":      { "median": 1.8,  "min": 1.2, "max": 2.6 }
  },
  "attention_points": [
    "Liquidity usually takes 2+ sessions to normalise.",
    "The stock reacts more strongly than its peers."
  ],
  "confidence": "medium",
  "note": "Based on 2026 data only (Jan–Oct).",
  "ai_summary": "In its past 3 quarterly results releases, pbb's spread widened by a median of 22% …",
  "_data_status": { "spreads": "real", "ohlc": "real", "flows": "real" }
}
```

- Chaque statistique `{median, min, max}` peut valoir `null` si `n = 0`.
- `confidence` : `low` (n < 3), `medium` (3–5), `high` (> 5).

**UI suggérée** : une carte **« What to expect »** à côté de la timeline, pour la prochaine annonce :
- en haut, `upcoming.title` et la date ;
- 3 tuiles en **fourchettes** : « Spread +22 % (9–38 %) », « Volume 2.1× (1.6–2.8×) », « Back to normal in ~1 session » ;
- une comparaison avec les peers (petite barre ou texte « vs peers +15 % ») ;
- les `attention_points` en liste ;
- un badge `confidence` et la mention « based on n past events » : important, pour ne pas donner l'impression d'une certitude.

---

## 6. Priorités UI pour la démo

1. **Impact card** (le cœur du challenge) + bouton export
2. **Dashboard** : spread vs peers, volume, anomalies cliquables
3. **Timeline des événements** avec `headline_metric`
4. Graphique **intraday** dans l'impact card
5. 🔜 Carte **What to expect**
6. Compare et report

Disclaimer à afficher sur chaque export et dans le footer : *« Descriptive analysis of historical Xetra trading data. Not investment advice. »*
