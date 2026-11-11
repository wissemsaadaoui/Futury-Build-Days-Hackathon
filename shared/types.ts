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

export type AnomalyType = "volume_spike" | "spread_widening" | "price_move" | "auction_spike";
export type Severity = "low" | "medium" | "high";

export interface Anomaly {
  date: ISODate;
  type: AnomalyType;
  severity: Severity;
  value: number;
  description: string;
  linked_event_id: string | null;
}

export interface PriceLevel {
  price: number;
  touches: number;
}

export interface DashboardResponse {
  stock: StockRef;
  period: { from: ISODate; to: ISODate };
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
  ai_summary: string;
  generated_at: ISODateTime;
  export: ExportLinks;
}

// ---------- GET /compare ----------
export interface CompareResponse {
  filter: { type: EventType; index: Index; from: ISODate; to: ISODate };
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
  unit: "shares" | "EUR" | "bps" | "ratio" | "pct";
  trend: Trend;
  change_pct?: number;
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
  text?: string;
}

export interface ReportResponse {
  stock: StockRef;
  period: { from: ISODate; to: ISODate };
  headline: string;
  sections: ReportSection[];
  disclaimer: string;
  generated_at: ISODateTime;
  export: ExportLinks;
}
