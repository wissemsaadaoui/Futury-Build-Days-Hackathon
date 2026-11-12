// Règles de détection appliquées par app/analytics qui ne sont PAS modifiables depuis l'interface.
// Source de vérité : app/config.py (BASELINE_DAYS, ALERT_*) et app/analytics/metrics.py (volume_anomalies,
// spread_anomalies). À mettre à jour si ces valeurs changent côté back-end.
export type DetectionRule = { type: string; name: string; rule: string; high: string; source: string }

export const BASELINE_SESSIONS = 20 // config.BASELINE_DAYS
export const ADTV_SESSIONS = 30 // config.ALERT_ADTV_DAYS

// Règles fixes (non modifiables depuis l'interface). Les seuils modifiables : GET /thresholds (point 16).
export const fixedRules: DetectionRule[] = [
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
