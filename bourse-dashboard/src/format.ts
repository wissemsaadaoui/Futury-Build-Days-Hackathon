// Formatage d'affichage partagé (dashboard, vue détail d'une journée, carte What to expect).
// Toute valeur absente (null, undefined, NaN) s'affiche « – » : jamais de NaN à l'écran.
import type { DataStatus } from './api/types.ts'

export const anomalyLabels: Record<string, string> = {
  volume_spike: 'Volume spike',
  spread_widening: 'Spread widening',
  price_move: 'Price move vs peers',
  auction_spike: 'Closing auction spike',
  large_trade: 'Large single execution',
  aggressor_sweep: 'Aggressor sweep',
  net_flow: 'Unusual net flow',
  level_break: 'Support / resistance break',
}

export const eventLabels: Record<string, string> = {
  annual_results: 'Annual results',
  quarterly_results: 'Quarterly results',
  ad_hoc: 'Ad hoc announcement',
  dividend: 'Dividend',
  agm: 'AGM',
  press_release: 'Press release',
  index_change: 'Index change',
  m_and_a: 'M&A',
  voting_rights: 'Voting rights notification',
  directors_dealings: "Directors' dealings",
}

export function formatNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'

  return value.toLocaleString('en-GB', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  return `${value > 0 ? '+' : ''}${formatNumber(value, 1)}%`
}

export function formatEuro(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'

  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatCompact(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  return new Intl.NumberFormat('en-GB', { notation: 'compact' }).format(value)
}

export function formatDate(value: string) {
  return new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export function trendClass(value: number | null | undefined) {
  if (value === null || value === undefined || Math.abs(value) < 0.05) {
    return 'neutral'
  }
  return value > 0 ? 'positive' : 'negative'
}

export function formatRatio(value: number | null | undefined, digits = 1) {
  return value === null || value === undefined ? '–' : `${formatNumber(value, digits)}×`
}

// La valeur d'une anomalie dépend de son type (mocks/API.md §5.2)
export function formatAnomalyValue(type: string, value: number | null) {
  if (value === null) return '–'
  if (type === 'price_move') return formatPercent(value) // écart vs médiane des peers
  if (['large_trade', 'aggressor_sweep', 'net_flow'].includes(type)) {
    return `${value > 0 && type === 'net_flow' ? '+' : ''}${formatNumber(value * 100, 0)}% ADTV` // part du turnover moyen 30 j
  }
  return formatRatio(value) // volume, spread, enchère, cassure de niveau : × la normale
}

export function hasDemoData(status: DataStatus | undefined) {
  return Object.values(status ?? {}).some((value) => value !== 'real')
}

// Valeur absente : null, undefined ou NaN (jamais affichée telle quelle)
export function isMissing(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || Number.isNaN(value)
}

export const DISCLAIMER = 'Descriptive analysis of historical Xetra trading data. Not investment advice.'

// "2026-10-26", "2026-10-30" -> "26–30 Oct 2026" (même mois) ; "29 Sep – 2 Oct 2026" sinon
export function formatDateRange(from: string, to: string) {
  const a = new Date(`${from}T12:00:00`)
  const b = new Date(`${to}T12:00:00`)
  const month = (d: Date) => d.toLocaleDateString('en-GB', { month: 'short' })
  if (a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear()) {
    return `${a.getDate()}–${b.getDate()} ${month(b)} ${b.getFullYear()}`
  }
  return `${a.getDate()} ${month(a)} – ${b.getDate()} ${month(b)} ${b.getFullYear()}`
}
