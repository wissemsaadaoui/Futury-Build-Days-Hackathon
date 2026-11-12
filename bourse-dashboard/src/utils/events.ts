// Annonces du même jour de trading : une seule carte (les chiffres de trading sont ceux de la séance, identiques
// pour toutes les annonces du jour). L'annonce « principale » sert de titre et ouvre l'impact card.
import type { CorporateEvent } from '../api/types.ts'

export type EventDay = {
  trading_day: string
  events: CorporateEvent[] // triées par heure de publication
  primary: CorporateEvent
  headline_metric: CorporateEvent['headline_metric']
}

// Plus le rang est petit, plus l'annonce est importante pour l'IR
const TYPE_RANK: Record<string, number> = {
  ad_hoc: 0,
  annual_results: 1,
  quarterly_results: 1,
  m_and_a: 2,
  dividend: 3,
  agm: 3,
  index_change: 4,
  press_release: 5,
  voting_rights: 6,
  directors_dealings: 7,
}

const rank = (event: CorporateEvent) => TYPE_RANK[event.type] ?? 9

export function groupByTradingDay(events: CorporateEvent[]): EventDay[] {
  const byDay = new Map<string, CorporateEvent[]>()
  for (const event of events) {
    const list = byDay.get(event.trading_day) ?? []
    list.push(event)
    byDay.set(event.trading_day, list)
  }
  return [...byDay.entries()]
    .map(([trading_day, list]) => {
      const sorted = [...list].sort((a, b) => (a.time || '99:99').localeCompare(b.time || '99:99'))
      const primary = [...sorted].sort((a, b) => rank(a) - rank(b))[0]
      return { trading_day, events: sorted, primary, headline_metric: primary.headline_metric }
    })
    .sort((a, b) => b.trading_day.localeCompare(a.trading_day))
}

export function announcementsLabel(n: number) {
  return `${n} announcement${n === 1 ? '' : 's'} on this day`
}
