// Règles de détection RÉELLEMENT appliquées par app/analytics (lecture seule, aucune valeur réglable ici).
// Source de vérité : app/config.py (BASELINE_DAYS, ALERT_*) et app/analytics/metrics.py (volume_anomalies,
// spread_anomalies). À mettre à jour si ces valeurs changent côté back-end.
export type DetectionRule = { type: string; name: string; rule: string; high: string; source: string }

export const BASELINE_SESSIONS = 20 // config.BASELINE_DAYS
export const ADTV_SESSIONS = 30 // config.ALERT_ADTV_DAYS

export const anomalyRules: DetectionRule[] = [
  {
    type: 'volume_spike',
    name: 'Volume anomaly',
    rule: 'Volume z-score above 2 versus the previous 20 trading days.',
    high: 'z-score above 3',
    source: 'metrics.volume_anomalies',
  },
  {
    type: 'spread_widening',
    name: 'Spread anomaly',
    rule: 'Spread z-score above 3 and spread more than 1.2× its 20-day baseline.',
    high: 'z-score above 4 or spread above 1.5× baseline',
    source: 'metrics.spread_anomalies',
  },
]

export const alertRules: DetectionRule[] = [
  {
    type: 'large_trade',
    name: 'Large single execution',
    rule: 'One execution of at least 10% of the 30-day average daily turnover (ADTV).',
    high: 'at least 2× the threshold (20% of ADTV)',
    source: 'config.ALERT_LARGE_TRADE_ADTV_SHARE = 0.10',
  },
  {
    type: 'aggressor_sweep',
    name: 'Aggressor sweep',
    rule: 'At least 3 consecutive same-side aggressive executions within 1 second, together at least 10% of ADTV.',
    high: 'at least 2× the threshold',
    source: 'config.ALERT_SWEEP_MIN_TRADES = 3, ALERT_SWEEP_WINDOW_S = 1.0, ALERT_SWEEP_ADTV_SHARE = 0.10',
  },
  {
    type: 'net_flow',
    name: 'Unusual net flow',
    rule: 'Net agency or proprietary flow (buying minus selling, in EUR) above 20% of ADTV on the day.',
    high: 'at least 2× the threshold (40% of ADTV)',
    source: 'config.ALERT_NET_FLOW_ADTV_SHARE = 0.20',
  },
  {
    type: 'auction_spike',
    name: 'Closing auction spike',
    rule: "Closing auction share of the day's volume above 2× its 20-day baseline share.",
    high: 'at least 2× the threshold (4× baseline)',
    source: 'config.ALERT_AUCTION_SPIKE_RATIO = 2.0',
  },
  {
    type: 'price_move',
    name: 'Price move vs peers',
    rule: 'Return more than 2.5 percentage points away from the peer median, on more than 1.5× usual volume.',
    high: 'at least 2× the threshold (5.0 points)',
    source: 'config.ALERT_PRICE_MOVE_PCT = 2.5, ALERT_PRICE_MOVE_VOLUME = 1.5',
  },
  {
    type: 'level_break',
    name: 'Support / resistance break',
    rule: 'Close crosses a support or resistance level on more than 1.5× usual volume, with a large execution or sweep the same day.',
    high: 'volume at least 2× the threshold (3.0×)',
    source: 'config.ALERT_LEVEL_BREAK_VOLUME = 1.5',
  },
]
