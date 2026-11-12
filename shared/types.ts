// Issuer Intelligence Hub – API types (v0.1)
// Correspond exactement aux fichiers mocks/*.json et à API.md

// ---------- Communs ----------
export type ISODate = string;      // "YYYY-MM-DD"
export type ISODateTime = string;  // "2026-03-04T22:00:00+01:00"
export type Index = "DAX" | "MDAX" | "SDAX";

export type EventType =
  | "quarterly_results"
  | "annual_results"
  | "ad_hoc"
  | "dividend"
  | "press_release"
  | "m_and_a"
  | "agm"
  | "index_change"
  | "voting_rights"        // notification de droits de vote WpHG art. 40 (EQS-PVR) – ajouté pour la démo pbb
  | "directors_dealings";  // transaction de dirigeant MAR art. 19 (EQS-DD) – ajouté pour la démo pbb

export type ParticipantType = "AGENT" | "PROP" | "MARKET_MAKER";
export type MarketMode = "AGGRESSIVE" | "PASSIVE" | "AUCTION";

export interface StockRef {
  isin: string;
  name: string;
  index: Index | string;
  sector?: string;
}

export interface ExportLinks {
  pdf_url: string;
}

// ---------- GET /stocks ----------
export interface IndexPeriod {
  index: Index;
  from?: ISODate;
  until?: ISODate;
}

export interface Stock {
  isin: string;
  name: string;
  ticker: string;
  index: Index;
  index_history?: IndexPeriod[];
  sector: string;
  shares_outstanding?: number;
  market_cap_eur: number;
  is_selected: boolean;
  peers: string[]; // ISINs
}

export interface StocksResponse {
  stocks: Stock[];
}

// ---------- GET /stocks/{isin}/dashboard ----------
export interface DashboardKpis {
  avg_daily_volume: number;
  avg_daily_turnover_eur: number;
  avg_spread_bps: number;
  avg_auction_share: number;     // 0–1
  price_change_pct: number;
  anomaly_days: number;
  vs_peers: {
    volume_ratio: number;
    spread_diff_bps: number;     // négatif = mieux que les peers
    auction_share_diff: number;
  };
}

export interface DailyPoint {
  date: ISODate;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  turnover_eur: number;
  volume_ratio: number;          // volume / baseline 20j
  spread_bps: number;
  spread_eur: number | null;     // 🆕 v0.2 : coût aller-retour en € pour 25 000 € échangés (= spread_bps × 2,5)
  spread_ticks: number | null;   // 🆕 v0.2 : coût par action en ticks Xetra (tick déduit des trades), null sans trades
  auction_share: number | null;  // 0–1, null si pas de Flows
  ema_20: number;
  ema_50: number;
  macd: number;
  macd_signal: number;
  macd_hist: number;
  anomaly: boolean;
}

export interface PeerPoint {
  date: ISODate;
  volume_ratio: number | null;
  spread_bps: number | null;
  auction_share: number | null;
}

export type AnomalyType =
  | "volume_spike"
  | "spread_widening"
  | "price_move"        // 🆕 v0.3 : |rendement excédentaire vs médiane des peers| > 2,5 % ET volume_ratio > 1,5
  | "auction_spike"     // closing auction > 2× sa part moyenne 20 j
  | "large_trade"       // v0.3 : exécution unique ≥ 10 % de l'ADTV 30 j
  | "aggressor_sweep"   // v0.3 : ≥ 3 exécutions consécutives du même côté en ≤ 1 s, somme ≥ 10 % de l'ADTV 30 j
  | "net_flow"          // |flux net AGENT ou PROP| > 20 % de l'ADTV 30 j
  | "level_break";      // 🆕 v0.3 : clôture qui franchit un support/une résistance, volume_ratio > 1,5 + exécution inhabituelle
export type Severity = "low" | "medium" | "high";

export interface Anomaly {
  date: ISODate;
  type: AnomalyType;
  severity: Severity;
  value: number;
  description: string;            // anglais ; jamais « an investor » : « a single execution », « aggressive buy orders »
  linked_event_id: string | null;
  time?: string;                  // 🆕 v0.2 : "HH:MM:SS" (large_trade, aggressor_sweep)
  side?: "BUY" | "SELL";          // 🆕 v0.2 : côté agresseur (trades) ou sens du flux net (net_flow)
  notional_eur?: number;          // 🆕 v0.2 : montant de l'exécution / de la rafale / du flux net
  level_type?: "support" | "resistance";  // 🆕 v0.3 : level_break uniquement
  level_price?: number;                   // 🆕 v0.3 : level_break uniquement (€)
  detail_url: string;             // 🆕 v0.3 : /events/{id}/impact-card si linked_event_id, sinon /days/{isin}/{date}/impact-card
  // v0.8 : human-in-the-loop (points 9-10)
  id: string;                          // identifiant stable, pour POST /decisions
  item_type: "anomaly" | "alert";
  decision: DecisionRef | null;        // dernière décision approved / dismissed de l'équipe IR
  rank: number | null;                 // 1 = la plus importante (sévérité puis récence) ; null si dismissed
}

export interface PriceLevel {
  price: number;
  touches: number;
}

export interface DashboardResponse {
  stock: StockRef;
  period: { from: ISODate; to: ISODate };
  as_of: ISODate;  // dernière date des données (ex. "2026-10-30"), indépendante de la période demandée
  key_finding: KeyFinding | null;  // v0.7 : phrase clé calculée par règles (premier vs dernier mois des données)
  auction_trend?: AuctionTrend | null;  // v0.10 : part des enchères dans le volume (null sans Flows)
  kpis: DashboardKpis;
  series: DailyPoint[];
  peers_series: PeerPoint[];
  anomalies: Anomaly[];
  support_resistance: {
    support: PriceLevel[];
    resistance: PriceLevel[];
  };
}

// ---------- GET /stocks/{isin}/events ----------
export interface CorporateEvent {
  event_id: string;
  date: ISODate;
  time: string;                  // "HH:MM"
  trading_day: ISODate;          // jour où l'effet est mesuré
  type: EventType;
  title: string;
  source_url: string | null;
  has_impact_card: boolean;
  headline_metric: {
    volume_ratio: number | null;       // null tant que l'OHLC n'est pas chargé
    price_change_pct: number | null;   // idem
    spread_change_pct: number | null;  // spread du jour vs baseline 20j, en %
  };
}

export interface EventsResponse {
  isin: string;
  as_of: ISODate;  // dernière date des données
  events: CorporateEvent[];
  event_types: EventType[];
}

// ---------- GET /events/{id}/impact-card  |  /days/{isin}/{date}/impact-card ----------
export interface RatioMetric {
  event: number;
  baseline: number;
  ratio: number;
  z_score?: number;
}

export interface ImpactCardResponse {
  card_id: string;
  stock: StockRef;
  event: {
    event_id: string;
    type: EventType;
    title: string;
    published_at: ISODateTime | null;  // null si l'heure de publication n'est pas vérifiée (démo pbb)
    trading_day: ISODate;
    source_url: string | null;
  } | null;                      // null pour un "notable day" sans annonce
  baseline: {
    method: string;
    from: ISODate;
    to: ISODate;
  };
  metrics: {
    volume: RatioMetric;
    turnover_eur: RatioMetric;
    price: {
      prev_close: number;
      open: number;
      close: number;
      change_pct: number;
      intraday_range_pct: number;
    };
    spread_bps: { event: number; baseline: number; change_pct: number };
    auction_share: { event: number; baseline: number; change_pts: number };
    opening_auction: { volume: number; baseline: number; ratio: number };
    closing_auction: { volume: number; baseline: number; ratio: number };
  };
  flows: {
    by_participant: { type: ParticipantType; buy: number; sell: number; net: number }[];
    by_mode: { mode: MarketMode; share: number }[];
  };
  window: {
    offset: number;              // 0 = jour de l'événement
    date: ISODate;
    close: number;
    volume_ratio: number;
    spread_bps: number;
  }[];
  vs_peers: {
    peer_avg_volume_ratio: number;
    peer_avg_price_change_pct: number;
    excess_return_pct: number;
  };
  technical_context: {
    trend_before: "above_ema50" | "below_ema50";
    macd_before: "bullish" | "bearish";
    macd_after: "bullish" | "bearish";
    broke_level: { type: "support" | "resistance"; price: number } | null;
  };
  intraday: IntradayBlock | null;  // 🆕 v0.2 : réaction minute par minute (null si pas de trades ce jour-là)
  pre_disclosure_activity: PreDisclosureActivity | null;  // 🆕 v0.3 : voting_rights uniquement, null sinon ou si rien d'inhabituel
  ai_summary: string;
  ai_points: string[];  // v0.6 : 3–4 phrases courtes (chacune vérifiée par le garde-fou) ; à afficher en liste à puces
  ai_summary_id: string;  // v0.8 : item_id pour POST /decisions (item_type "ai_summary")
  ai_summary_decision: DecisionRef | null;
  generated_at: ISODateTime;
  export: ExportLinks;
}

// 🆕 v0.2 – bloc intraday de l'impact card (mocks/API.md §5.1)
export interface IntradayMinute {
  offset_min: number;                  // -30 … +120 (0 = minute de référence)
  time: string;                        // "HH:MM", heure de Francfort
  vwap: number | null;                 // null si aucune exécution dans la minute
  volume: number;                      // actions (0 si aucune exécution)
  cum_volume: number;                  // cumul depuis offset -30
  buy_aggressor_share: number | null;  // 0–1, part du volume à l'initiative d'un acheteur
}

export interface IntradayBlock {
  reference_time: ISODateTime;  // heure de publication, ou ouverture du trading_day si hors séance
  during_session: boolean;      // true si l'annonce tombe pendant le continu (09:00–17:30)
  minutes: IntradayMinute[];
  first_15min: { volume: number; baseline: number | null; ratio: number | null };  // vs même créneau, 20 séances
  price_change_pct: { after_5min: number | null; after_30min: number | null; after_60min: number | null };
}

// 🆕 v0.3 – activité des 7 séances AVANT une notification de droits de vote (WpHG art. 40)
export interface PreDisclosureActivity {
  window: { from: ISODate; to: ISODate; sessions: number };  // séances strictement avant le jour de publication
  days: {
    date: ISODate;
    anomaly_types: AnomalyType[];
    volume_ratio: number | null;
    agent_net_flow_eur: number | null;  // flux net AGENT (ordres pour compte de clients), € ; null sans Flows
  }[];
  summary: string;  // phrase neutre : « … may coincide with … » ; ne désigne jamais l'investisseur notifié
}

// ---------- GET /compare ----------
export interface CompareResponse {
  filter: { type: EventType; index: Index | "ALL"; from: ISODate; to: ISODate };  // "ALL" = tous indices
  summary: {
    n_events: number;
    median_volume_ratio: number | null;
    median_abs_price_change_pct: number | null;
    median_spread_change_pct: number | null;
  };
  events: {
    event_id: string;
    isin: string;
    name: string;
    date: ISODate;
    volume_ratio: number | null;
    price_change_pct: number | null;
    spread_change_pct: number | null;
    auction_share_change_pts: number | null;
  }[];
}

// ---------- GET /stocks/{isin}/report  (IR snapshot) ----------
export type Trend = "up" | "down" | "flat" | "better" | "worse";

export interface ReportKpi {
  label: string;
  value: number;
  unit: "shares" | "EUR" | "bps" | "ratio" | "pct" | "count";  // 🆕 v0.4 : "count" (section Alerts)
  trend: Trend | null;      // 🆕 v0.3 : null si la variation est inconnue (jamais "flat" faute de données)
  change_pct?: number | null;
  change_basis?: "previous_period" | "first_half" | null;  // 🆕 v0.3 : base de la variation (first_half = 2e moitié vs 1re moitié)
  alert_type?: AnomalyType | null;  // 🆕 v0.4 : section Alerts, type compté
}

// 🆕 v0.4 – section « Alerts » du report : les 5 jours les plus marquants
export interface ReportAlertDay {
  date: ISODate;
  n_alerts: number;
  n_high: number;
  types: AnomalyType[];
  top_description: string;
  linked_event_id: string | null;
  detail_url: string;  // impact card de l'événement, sinon du jour
}

export interface ReportSection {
  title: string;
  kpis?: ReportKpi[];
  items?: {
    event_id: string;
    date: ISODate;
    title: string;
    volume_ratio: number | null;
    price_change_pct: number | null;
    spread_change_pct: number | null;
  }[];
  alert_days?: ReportAlertDay[];  // 🆕 v0.4 : section « Alerts » uniquement
  text?: string;
}

export interface ReportResponse {
  stock: StockRef;
  period: { from: ISODate; to: ISODate };
  headline: string;
  ai_points: string[];  // v0.6
  ai_summary_id: string;  // v0.8 : item_id pour POST /decisions (item_type "ai_summary")
  ai_summary_decision: DecisionRef | null;
  sections: ReportSection[];
  disclaimer: string;
  generated_at: ISODateTime;
  export: ExportLinks;
}

// ---------- 🆕 v0.4 – GET /stocks/{isin}/event-preview?type=&date=  (mocks/API.md §5.3) ----------
// Réactions PASSÉES du trading (liquidité, volume, enchères) aux annonces du même type.
// Pas une prédiction de prix : aucune direction de cours, aucun prix cible, aucune recommandation.
export interface PreviewStat {
  n: number;              // nombre de valeurs disponibles
  median: number | null;  // null si n = 0
  min: number | null;
  max: number | null;
}

export interface PreviewEvent {
  event_id: string;
  date: ISODate;                           // trading_day
  spread_change_pct: number | null;
  volume_ratio: number | null;
  price_abs_change_pct: number | null;     // amplitude ABSOLUE (jamais signée)
  sessions_to_normal: number | null;       // 0 = spread resté <= 110 % de sa baseline ; null = pas revenu en 5 séances
  auction_share_change_pts: number | null;
  first_15min_ratio: number | null;        // null si pas d'intraday
}

export interface PreviewHistory {
  n: number;
  events: PreviewEvent[];
  spread_change_pct: PreviewStat;
  volume_ratio: PreviewStat;
  price_abs_change_pct: PreviewStat;
  sessions_to_normal: PreviewStat;
  auction_share_change_pts: PreviewStat;
  first_15min_ratio: PreviewStat;
}

export interface EventPreviewResponse {
  stock: StockRef;
  event_type: EventType;
  as_of: ISODate;  // dernière date des données (v0.5 ; avant : la date demandée, désormais `reference_date`)
  reference_date: ISODate | null;  // `date` demandé : seuls les événements AVANT cette date sont utilisés ; null = tous
  upcoming: { date: ISODate; title: string | null; event_id: string | null; source_url: string | null } | null;
  own_history: PreviewHistory;
  peers: PreviewHistory & { peers_note?: string };  // peers_note si aucun événement de peer
  attention_points: string[];
  checklist: string[];  // préparation IR par règles (volume > 1.5x, spread > +10 %, retour à la normale <= 1 séance) ; [] si rien
  confidence: "low" | "medium" | "high";  // low : n < 3, medium : 3–5, high : > 5
  note: string;
  ai_summary: string;
  ai_points: string[];  // v0.6 : 3–4 phrases courtes (chacune vérifiée par le garde-fou) ; à afficher en liste à puces
  ai_summary_id: string;  // v0.8 : item_id pour POST /decisions (item_type "ai_summary")
  ai_summary_decision: DecisionRef | null;
  _data_status?: Record<string, "real" | "mock" | "missing">;
}

// ---------- /thresholds (v0.7, point 16) – seuils d'alerte modifiables par l'équipe IR ----------
export interface ThresholdSpec {
  label: string; unit: string; group: "anomaly" | "alert";
  min: number; max: number; step: number; integer: boolean; default: number;
}
export interface ThresholdsResponse {        // GET /thresholds?isin= | PUT /thresholds | POST /thresholds/reset
  isin: string;
  values: Record<string, number>;            // seuils appliqués (défauts du code + personnalisations)
  defaults: Record<string, number>;
  bounds: Record<string, ThresholdSpec>;
  custom: boolean;                           // au moins un seuil différent du défaut -> badge « Custom thresholds »
}
export interface ThresholdsPreview {         // POST /thresholds/preview {isin, values} – rien n'est enregistré
  isin: string; alerts_with_values: number; alerts_current: number;
}
// PUT hors bornes -> 422 { detail: { message, errors: { [key]: string } } }

// ---------- dashboard.key_finding (v0.7, point 8) ----------
export interface KeyFinding {
  text: string;  // ex. "pbb's cost to trade €25k rose from 54.3 to 97.4 bps (Jan–Oct), moving from below to above its peers' median."
  numbers: Record<string, number | string | null>;  // own_first_bps, own_last_bps, peers_median_*_bps, position_*, index_median_*_bps, price_effect_pct…
}

// ---------- dashboard.auction_trend (v0.10) ----------
// Parts entre 0 et 1, 2 décimales. auction_share = volume AUCTION ÷ volume total (Flows).
// opening / intraday / closing : trades horodatés ÷ volume du jour ; leur somme peut rester sous auction_share
// (les Flows comptent aussi les enchères non planifiées, ex. interruptions de volatilité).
export interface AuctionTrendPoint {
  date: ISODate;
  auction_share: number | null;  // null = jour censuré (< 7 exécutions) ou publié agrégé, jamais 0
  baseline_20d: number | null;   // moyenne mobile 20 séances (jour inclus), null avant 20 valeurs
  opening?: number | null;
  intraday?: number | null;
  closing?: number | null;
}
export interface AuctionTrendMark {
  date: ISODate; value: number | null;
  opening?: number | null; intraday?: number | null; closing?: number | null;  // sur `peak` uniquement
}
export interface AuctionTrend {
  window: number;      // 20
  has_parts: boolean;  // opening / intraday / closing disponibles
  series: AuctionTrendPoint[];
  start: AuctionTrendMark | null;   // première moyenne 20 séances de la période
  latest: AuctionTrendMark | null;  // dernière moyenne 20 séances de la période
  change_vs_start: number | null;   // latest − start (0.05 = +5 points)
  peak: AuctionTrendMark | null;    // jour le plus haut de la période (valeur journalière)
}

// ---------- /decisions (v0.8, points 9-10) – « AI suggests, the IR team decides – every decision is logged. » ----------
export interface DecisionRef {
  id: number; decision: "approved" | "dismissed"; note: string | null; decided_at: ISODateTime; decided_by: string;
}
export interface DecisionIn {                 // POST /decisions
  item_type: "alert" | "ai_summary" | "anomaly"; item_id: string; isin: string;
  decision: "approved" | "dismissed"; note?: string;
}
export interface Decision {                   // une ligne du journal
  id: number; item_type: "alert" | "ai_summary" | "anomaly" | "threshold"; item_id: string; isin: string;
  decision: "approved" | "dismissed" | "threshold_changed"; note: string | null;
  old_value: string | null; new_value: string | null;  // threshold_changed : ancien -> nouveau
  decided_at: ISODateTime; decided_by: string;          // Europe/Berlin ; "ir-team"
}
export interface DecisionLog { isin: string | null; decisions: Decision[] }  // GET /decisions?isin=

// ---------- POST /assistant/chat (v0.9) ----------
export interface ChatMessage { role: "user" | "assistant"; content: string }
export interface ChatRequest { isin: string; messages: ChatMessage[] }  // l'API garde les 6 derniers messages
export interface ChatLink {
  label: string;
  type: "day" | "event" | "preview" | "compare" | "question";  // question : suggestion cliquable, ref = texte à envoyer
  ref: string;
}
export interface ChatResponse {
  answer: string;
  links: ChatLink[];
  as_of: ISODate;
  reason: "off_topic" | "prediction" | "advice" | "external_info" | null;  // null = question dans le périmètre
}
