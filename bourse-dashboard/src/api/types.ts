// Types des réponses de l'API utilisées par le front (contrat : shared/types.ts + mocks/API.md v0.4).
// Les nombres peuvent être null quand une donnée manque : toujours afficher « – » dans ce cas.

export type Num = number | null

export type DataStatus = Record<string, 'real' | 'mock' | 'missing'>

export type StockRef = { isin: string; name: string; index: string; sector?: string | null }

export type DailyPoint = {
  date: string
  open: Num
  high: Num
  low: Num
  close: Num
  volume: Num
  turnover_eur: Num
  volume_ratio: Num
  spread_bps: Num
  spread_eur?: Num
  auction_share: Num
  ema_20: Num
  ema_50: Num
  macd: Num
  macd_signal: Num
  macd_hist: Num
  anomaly: boolean
}

export type Anomaly = {
  date: string
  type: string
  severity: 'low' | 'medium' | 'high'
  value: Num
  description: string
  linked_event_id: string | null
  detail_url: string
}

export type DashboardResponse = {
  stock: StockRef
  period: { from: string; to: string }
  as_of: string // v0.5 : dernière date des données (ex. "2026-10-30")
  kpis: {
    avg_daily_volume: Num
    avg_daily_turnover_eur: Num
    avg_spread_bps: Num
    avg_auction_share: Num
    price_change_pct: Num
    anomaly_days: number
  }
  series: DailyPoint[]
  anomalies: Anomaly[]
  _data_status?: DataStatus
}

export type CorporateEvent = {
  event_id: string
  date: string
  time: string
  trading_day: string
  type: string
  title: string
  source_url: string | null
  has_impact_card?: boolean
  headline_metric: { volume_ratio: Num; price_change_pct: Num; spread_change_pct: Num }
}

export type EventsResponse = { isin: string; as_of: string; events: CorporateEvent[]; event_types: string[] }

// Champs vérifiés sur /days/{isin}/{date}/impact-card et /events/{id}/impact-card (API locale, 12.11.2026).
export type ImpactCardResponse = {
  card_id: string
  stock: StockRef
  event: {
    event_id: string
    type: string
    title: string
    published_at: string | null
    trading_day: string
    source_url: string | null
  } | null
  baseline?: { method: string; from: string; to: string }
  metrics: {
    volume: { event: Num; baseline: Num; ratio: Num; z_score?: Num }
    turnover_eur?: { event: Num; baseline: Num; ratio: Num; z_score?: Num }
    price: { prev_close: Num; open: Num; close: Num; change_pct: Num; intraday_range_pct?: Num }
    spread_bps: { event: Num; baseline: Num; change_pct: Num }
    auction_share: { event: Num; baseline: Num; change_pts: Num }
    opening_auction?: { volume: Num; baseline: Num; ratio: Num }
    closing_auction?: { volume: Num; baseline: Num; ratio: Num }
  }
  flows?: {
    by_participant: { type: string; buy: Num; sell: Num; net: Num }[]
    by_mode: { mode: string; share: Num }[]
  }
  window: { offset: number; date: string; close: Num; volume_ratio: Num; spread_bps: Num }[]
  vs_peers: { peer_avg_volume_ratio?: Num; peer_avg_price_change_pct?: Num; excess_return_pct: Num }
  technical_context?: {
    trend_before?: string | null
    macd_before?: string | null
    macd_after?: string | null
    broke_level?: { type: string; price: Num } | null
  } | null
  intraday: {
    reference_time: string
    during_session: boolean
    minutes?: { offset_min: number; time: string; vwap: Num; volume: Num; cum_volume: Num; buy_aggressor_share: Num }[]
    first_15min: { volume?: Num; baseline?: Num; ratio: Num }
    price_change_pct: { after_5min: Num; after_30min: Num; after_60min: Num }
  } | null
  pre_disclosure_activity: { summary: string } | null
  ai_summary: string
  generated_at?: string
  export: { pdf_url: string }
  _data_status?: DataStatus
}

export type CompareResponse = {
  filter: { type: string; index: string; from: string; to: string }
  summary: {
    n_events: number
    median_volume_ratio: Num
    median_abs_price_change_pct: Num
    median_spread_change_pct: Num
  }
  events: {
    event_id: string
    isin: string
    name: string
    date: string
    volume_ratio: Num
    price_change_pct: Num
    spread_change_pct: Num
    auction_share_change_pts: Num
  }[]
}

export type ReportKpi = { label: string; value: Num; unit: string; trend: string | null; change_pct?: Num }

export type ReportResponse = {
  stock: StockRef
  period: { from: string; to: string }
  headline: string
  sections: {
    title: string
    kpis?: ReportKpi[] | null
    items?: { event_id: string; date: string; title: string; volume_ratio: Num; price_change_pct: Num; spread_change_pct: Num }[] | null
    text?: string | null
  }[]
  disclaimer: string
  export: { pdf_url: string }
}

export type PreviewStat = { n: number; median: Num; min: Num; max: Num }

export type PreviewEvent = {
  event_id: string
  date: string
  spread_change_pct: Num
  volume_ratio: Num
  price_abs_change_pct: Num
  sessions_to_normal: Num
  auction_share_change_pts: Num
  first_15min_ratio: Num
}

export type PreviewHistory = {
  n: number
  events: PreviewEvent[]
  spread_change_pct: PreviewStat
  volume_ratio: PreviewStat
  price_abs_change_pct: PreviewStat
  sessions_to_normal: PreviewStat
  auction_share_change_pts: PreviewStat
  first_15min_ratio: PreviewStat
}

// Champs vérifiés sur /stocks/{isin}/event-preview?type=&date= (API locale, 12.11.2026, contrat v0.5).
export type EventPreviewResponse = {
  stock?: StockRef
  event_type: string
  as_of: string // dernière date des données
  reference_date: string | null // `date` demandé (seuls les événements avant cette date sont utilisés)
  upcoming: { date: string; title: string | null; event_id?: string | null; source_url?: string | null } | null
  own_history: PreviewHistory
  peers: PreviewHistory & { peers_note?: string | null }
  attention_points: string[]
  checklist: string[] // préparation IR par règles ; [] si rien
  confidence: 'low' | 'medium' | 'high'
  note: string
  ai_summary: string
  _data_status?: DataStatus
}

// POST /assistant/chat (vérifié sur l'API locale, 12.11.2026)
export type ChatLink = { label: string; type: 'day' | 'event' | 'preview' | 'compare'; ref: string }

export type ChatResponse = { answer: string; links: ChatLink[]; as_of: string }
