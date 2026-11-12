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
  headline_metric: { volume_ratio: Num; price_change_pct: Num; spread_change_pct: Num }
}

export type EventsResponse = { isin: string; events: CorporateEvent[]; event_types: string[] }

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
  metrics: {
    volume: { event: Num; baseline: Num; ratio: Num }
    price: { prev_close: Num; open: Num; close: Num; change_pct: Num }
    spread_bps: { event: Num; baseline: Num; change_pct: Num }
    auction_share: { event: Num; baseline: Num; change_pts: Num }
  }
  window: { offset: number; date: string; close: Num; volume_ratio: Num; spread_bps: Num }[]
  vs_peers: { excess_return_pct: Num }
  intraday: {
    reference_time: string
    during_session: boolean
    first_15min: { ratio: Num }
    price_change_pct: { after_5min: Num; after_30min: Num; after_60min: Num }
  } | null
  pre_disclosure_activity: { summary: string } | null
  ai_summary: string
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

export type EventPreviewResponse = {
  event_type: string
  upcoming: { date: string; title: string | null } | null
  own_history: {
    n: number
    spread_change_pct: PreviewStat
    volume_ratio: PreviewStat
    sessions_to_normal: PreviewStat
  }
  attention_points: string[]
  confidence: 'low' | 'medium' | 'high'
  note: string
  ai_summary: string
}
