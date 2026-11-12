// Définitions affichées dans les tooltips « ? » (une phrase par métrique, en anglais).
// Vérifiées contre app/analytics (12.11.2026) : config.BASELINE_DAYS = 20, metrics.rolling_baseline (jour exclu),
// metrics.volume_anomalies / spread_anomalies (seuils), config.PEERS, preview._sessions_to_normal, preview._confidence.
export const metricHelp = {
  spread:
    'Round-trip cost of buying and immediately selling €25,000 of the share, in basis points, measured from the Xetra order book (XLM).',
  baseline: 'Average of the previous 20 trading days, excluding the measured day.',
  ratio: 'Value ÷ baseline (1.0× = normal).',
  zScore:
    'How unusual the value is compared with the previous 20 trading days. Default thresholds: volume is flagged above 2 (high above 3); the spread above 3 and only when it is also more than 20% above its baseline (adjustable on the Thresholds page).',
  volume: 'Number of shares traded on Xetra that day.',
  turnover: 'Value in euros traded on Xetra that day.',
  vwap: 'Volume-weighted average price of the day: turnover ÷ number of shares traded.',
  auctionShare: 'Share of volume executed in the opening, intraday and closing auctions.',
  peers:
    'Median of comparable listed financials with data that day: GRENKE, Hypoport, MLP, ProCredit (data from 14 Oct 2026), W&W (data until 5 Oct 2026) and flatexDEGIRO.',
  sessionsToNormal:
    'Trading sessions until the spread is back within 10% of its 20-day baseline (0 = it stayed within that range on the day); volume is not part of this measure.',
  confidence: 'Based on the number of past comparable events: low < 3, medium 3–5, high > 5.',
} as const

export type MetricHelpKey = keyof typeof metricHelp
