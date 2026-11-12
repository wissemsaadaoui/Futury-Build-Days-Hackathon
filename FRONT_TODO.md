# FRONT_TODO – nouveaux champs et endpoints pour le front (démo pbb)

> Pour Yassine · Back-end prêt sur la branche `alfred/backend-demo` (contrat `mocks/API.md` v0.5, `shared/types.ts`).
> Tous les exemples ci-dessous sont des **réponses réelles** de l'API locale (12.11.2026, données jusqu'au 30.10.2026).
> Toutes les routes exigent `Authorization: Bearer <token>` (déjà géré par `apiGet` / `apiPost` dans `src/api/clients.ts`).
> Règle de wording partout : jamais « prediction », « investor », « institutional », « retail » ; pas de flèche de direction de cours.

Certaines parties UI existent déjà sur la branche front **`alfred/demo-polish`** (non mergée : tooltips, top 5 alerts, footer,
« Data as of ») : à reprendre ou à réintégrer dans le nouveau design.

---

## 1. Chat de l'AI Assistant – `POST /assistant/chat` (déjà sur `main`)

Requête : historique de la session (le back garde les 6 derniers messages).

```json
{ "isin": "DE0008019001",
  "messages": [ { "role": "user", "content": "Why was 29 Sep unusual?" } ] }
```

Réponse :

```json
{
  "answer": "29 Sep 2026 was flagged for: Spread 1.2x its 20-day baseline. On 2026-09-29, an unusual trading day with no announcement, Deutsche Pfandbriefbank AG traded 0.6x its usual volume and the share price moved -2.2%, 2.3 percentage points worse than the median of its peers. The round-trip cost for a EUR 25,000 trade widened to 84.6 bps versus a 20-day average of 70.0 bps (20.8%). ...",
  "links": [ { "label": "Day view 29 Sep 2026", "type": "day", "ref": "2026-09-29" } ],
  "as_of": "2026-10-30"
}
```

À afficher :
- Bulle de réponse + **boutons** pour chaque `links[]` : `day` → vue jour (`ref` = date), `event` → impact card (`/events/{ref}/impact-card`),
  `preview` → carte What to expect (`ref` = type d'annonce), `compare` → page Compare.
- Indicateur « Analysing… » pendant l'appel ; 429 → « Too many questions in a short time, please wait a minute ».
- 4 questions suggérées cliquables : « What happened in the latest week? », « Why was 29 Sep unusual? »,
  « What to expect from today's Q3 release? », « How does pbb compare with its peers? ».
- Sous le champ : « Answers are based only on historical Xetra data in this tool. Not investment advice. »
- Une question de prédiction (« Should I buy pbb now? ») renvoie un refus poli avec des questions possibles : l'afficher tel quel.

## 2. `as_of` – dernière date des données (nouveau, v0.5)

Présent dans `/stocks/{isin}/dashboard`, `/stocks/{isin}/events`, `/stocks/{isin}/event-preview` (et `/assistant/chat`).

```json
{ "period": { "from": "2026-01-02", "to": "2026-10-30" }, "as_of": "2026-10-30", "...": "..." }
{ "isin": "DE0008019001", "as_of": "2026-10-30", "events": [ "..." ] }
```

À afficher : **« Data as of 30 Oct 2026 »** près du nom de la société (dashboard) et sur la page Events. Ne jamais coder la date en dur.

⚠️ `event-preview` : `as_of` a **changé de sens** (avant : la date demandée). La date demandée est maintenant `reference_date`.

## 3. Checklist IR – `event-preview.checklist` (nouveau)

`GET /stocks/DE0008019001/event-preview?type=quarterly_results&date=2026-11-12`

```json
{
  "as_of": "2026-10-30",
  "reference_date": "2026-11-12",
  "upcoming": { "date": "2026-11-12", "title": "Q3 2026 results (Quartalsmitteilung)", "event_id": "evt_026", "source_url": "https://www.finanznachrichten.de/..." },
  "confidence": "low",
  "checklist": [
    "Past quarterly results releases traded a median of 1.9x usual volume: inform the designated sponsor / market makers ahead of publication.",
    "The spread widened by a median of +11.7% on past publication days: consider publishing before the market opens so the order book can adjust from the opening auction.",
    "On past quarterly results releases the effect on liquidity faded within one session (median 0.5 sessions to normal)."
  ]
}
```

À afficher : liste « IR checklist » (cases à cocher locales, non sauvegardées) dans la carte What to expect. `[]` → masquer le bloc.
Règles : volume médian > 1.5× ; spread médian > +10 % ; retour à la normale ≤ 1 séance.

## 4. Peers dans What to expect (nouveau : n > 0)

Les résultats 2026 des 6 peers sont dans le calendrier (13 événements vérifiés). Pour pbb `quarterly_results` :

```json
"peers": {
  "n": 13,
  "spread_change_pct": { "n": 11, "median": 5.5, "min": -27.2, "max": 66.0 },
  "volume_ratio": { "n": 13, "median": 1.58, "min": 0.51, "max": 4.8 },
  "sessions_to_normal": { "n": 11, "median": 0.0, "min": 0.0, "max": 4.0 },
  "events": [ { "event_id": "evt_037", "date": "2026-04-23", "spread_change_pct": 53.6, "volume_ratio": 2.61, "...": "..." } ]
}
```

À afficher : ligne « pbb vs peers » sous les tuiles (médianes : spread +11.7 % vs +5.5 %, volume 1.94× vs 1.58×,
« based on 13 peer releases »). `stat.n` peut être < `peers.n` (ProCredit n'a pas de spread avant le 14.10) : afficher
`stat.n`. `peers_note` n'est présent que si `n = 0`.

## 5. Tooltips « ? » sur les métriques

Textes vérifiés contre `app/analytics` (déjà dans `bourse-dashboard/src/content/metricHelp.ts` sur `alfred/demo-polish`) :

| Clé | Texte |
|---|---|
| spread | Round-trip cost of buying and immediately selling €25,000 of the share, in basis points, measured from the Xetra order book (XLM). |
| baseline | Average of the previous 20 trading days, excluding the measured day. |
| ratio | Value ÷ baseline (1.0× = normal). |
| zScore | How unusual the value is compared with the previous 20 trading days: volume is flagged above 2 (high above 3); the spread is flagged above 3 and only when it is also more than 20% above its baseline. |
| volume / turnover | Number of shares / value in euros traded on Xetra that day. |
| auctionShare | Share of volume executed in the opening, intraday and closing auctions. |
| peers | Median of comparable listed financials with data that day: GRENKE, Hypoport, MLP, ProCredit (data from 14 Oct 2026), W&W (data until 5 Oct 2026) and flatexDEGIRO. |
| sessionsToNormal | Trading sessions until the spread is back within 10% of its 20-day baseline (0 = it stayed within that range on the day); volume is not part of this measure. |
| confidence | Based on the number of past comparable events: low < 3, medium 3–5, high > 5. |

À afficher : survol + focus clavier (Échap ferme) + tap sur mobile ; bulle toujours dans l'écran.

## 6. Top 5 alerts

Source : `dashboard.anomalies[]` (149 sur l'année), chaque item a `severity` et `detail_url` :

```json
{ "date": "2026-10-26", "type": "volume_spike", "severity": "high", "value": 3.35,
  "description": "Volume 3.3x above 20-day baseline", "linked_event_id": null,
  "detail_url": "/days/DE0008019001/2026-10-26/impact-card" }
```

À afficher : les 5 plus importantes (tri **sévérité** high > medium > low, puis **date la plus récente**), puis un bouton
« Show all (149) ». Même logique pour « Notable days » du dashboard. Clic → `detail_url` (vue jour / impact card).

## 7. Footer

- Retirer l'adresse e-mail Deutsche Börse et le lien « contact page » (non vérifiés).
- Afficher « Data: Deutsche Börse Xetra (2 Jan – 30 Oct 2026) » et « Built at Futury Build Days 2026 ».
- Disclaimer : « Descriptive analysis of historical Xetra trading data. Not investment advice. »

## 8. Bouton « Weekly snapshot » (PDF de la dernière semaine)

Endpoint existant, vérifié pour 26–30 Oct : `GET /stocks/DE0008019001/report.pdf?from=2026-10-26&to=2026-10-30` → 200, PDF d'une page
(headline, trading profile, peers, alerts). JSON équivalent : `/stocks/{isin}/report?from=&to=`.

```json
{ "period": { "from": "2026-10-26", "to": "2026-10-30" },
  "headline": "Spreads widened 1.5% vs the previous period, 25.5 bps wider than peers.",
  "sections": [ { "title": "Trading profile", "text": "Avg daily volume: 296,866 shares (+58.4% vs previous period); ..." },
                { "title": "Alerts", "text": "2 alerts on 1 of 5 sessions. Volume spikes: 1; Price moves vs peers: 1." } ] }
```

À faire :
- `to` = `as_of` ; `from` = 5e séance avant la fin : `dashboard.series.slice(-5)[0].date` (= `2026-10-26`), pas de calcul de calendrier.
- Télécharger avec le token (`openPdf(path)` dans `src/api/clients.ts`) : un simple lien `<a href>` ne passe pas l'en-tête `Authorization`.
- Libellé : « Weekly snapshot (26–30 Oct 2026) ».
