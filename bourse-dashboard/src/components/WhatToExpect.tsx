// Carte « What to expect » (haut du dashboard) : statistiques sur les réactions PASSÉES du trading au même type
// d'annonce (/stocks/{isin}/event-preview). Aucune direction de cours, aucune projection.
// Compacte : titre + badges, 4 tuiles ; résumé IA, peers et note dans « Show details » (fermé par défaut).
import type { EventsResponse, EventPreviewResponse, Num, PreviewStat } from '../api/types.ts'
import { useApi } from '../api/useApi.ts'
import type { MetricHelpKey } from '../content/metricHelp.ts'
import { eventLabels, formatDate, formatNumber, formatPercent, formatRatio, isMissing } from '../format.ts'
import { CountUp } from './CountUp.tsx'
import { HelpTip } from './HelpTip.tsx'

// /events ne liste que les annonces déjà mesurées (données jusqu'au 30.10.2026) : la Quartalsmitteilung Q3 du
// 12.11.2026 (evt_026) n'y figure pas. Repli explicite pour la démo.
const FALLBACK_UPCOMING = { event_id: 'evt_026', type: 'quarterly_results', date: '2026-11-12' }

function todayIso() {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

function nextEvent(events: EventsResponse | null) {
  const today = todayIso()
  const upcoming = (events?.events ?? [])
    .filter((event) => event.date >= today)
    .sort((a, b) => a.date.localeCompare(b.date))[0]
  return upcoming ? { event_id: upcoming.event_id, type: upcoming.type, date: upcoming.date } : FALLBACK_UPCOMING
}

// Séances avant retour à la normale : 0 = même jour ; médiane non entière -> « ≤ n » (arrondi au supérieur)
const sessionWord = (n: number) => `${n} session${n === 1 ? '' : 's'}`

const sessions = (value: Num) => {
  if (isMissing(value)) return '–'
  if (value === 0) return 'Same day'
  return Number.isInteger(value) ? sessionWord(value) : `≤ ${sessionWord(Math.ceil(value))}`
}

const sessionsRange = (stat: PreviewStat) => {
  if (isMissing(stat.min) || isMissing(stat.max)) return '–'
  if (stat.max === 0) return 'same day'
  const max = sessionWord(Math.ceil(stat.max))
  if (stat.min === 0) return `same day – ${max}`
  return stat.min === stat.max ? max : `${sessionWord(stat.min)} – ${max}`
}

const absPct = (value: Num) => (isMissing(value) ? '–' : `${formatNumber(value, 1)}%`)
const ratio = (value: Num) => formatRatio(value, 2)

function Tile({
  label,
  stat,
  format,
  range,
  help,
}: {
  label: string
  stat: PreviewStat
  format: (value: Num) => string
  range?: string
  help?: MetricHelpKey
}) {
  const empty = stat.n === 0
  return (
    <div className="expect-tile">
      <span>
        {label}
        {help && <HelpTip metric={help} label={label} />}
      </span>
      <strong>{empty ? 'No data' : <CountUp text={format(stat.median)} delay={500} />}</strong>
      <small>
        {empty ? 'No past event of this type' : `median · ${range ?? `${format(stat.min)} to ${format(stat.max)}`}`}
      </small>
    </div>
  )
}

export function WhatToExpect({ isin, onOpenFull }: { isin: string; onOpenFull: () => void }) {
  const events = useApi<EventsResponse>(`/stocks/${isin}/events`)
  const ready = events.data !== null || events.error !== null
  const next = nextEvent(events.data)
  const preview = useApi<EventPreviewResponse>(
    ready ? `/stocks/${isin}/event-preview?type=${next.type}&date=${next.date}` : null,
  )
  const p = preview.data
  const own = p?.own_history
  const typeLabel = eventLabels[next.type] ?? next.type

  return (
    <section className="panel expect-card" aria-label="What to expect">
      <div className="expect-head">
        <div className="expect-title">
          <span className="expect-kicker">WHAT TO EXPECT</span>
          <h2>{p?.upcoming?.title ?? typeLabel}</h2>
          <span className="expect-meta">
            {formatDate(p?.upcoming?.date ?? next.date)}
            {p?.upcoming?.source_url && (
              <>
                {' · '}
                <a href={p.upcoming.source_url} target="_blank" rel="noreferrer">Source ↗</a>
              </>
            )}
          </span>
        </div>
        {p && own && (
          <div className="expect-badges">
            <span className={`confidence ${p.confidence}`}>
              {p.confidence.charAt(0).toUpperCase() + p.confidence.slice(1)} confidence
            </span>
            <HelpTip metric="confidence" label="confidence" />
            <strong className="expect-based">
              Based on {own.n} past event{own.n === 1 ? '' : 's'}
            </strong>
          </div>
        )}
      </div>

      {preview.error && <div className="notice-box">Could not load past reactions ({preview.error}).</div>}
      {(preview.loading || !ready) && <div className="notice-box">Loading past reactions…</div>}

      {p && own && (
        <>
          <div className="expect-tiles">
            <Tile label="Spread change" stat={own.spread_change_pct} format={formatPercent} help="spread" />
            <Tile label="Volume vs usual" stat={own.volume_ratio} format={ratio} help="ratio" />
            <Tile
              label="Sessions to normal liquidity"
              stat={own.sessions_to_normal}
              format={sessions}
              range={sessionsRange(own.sessions_to_normal)}
              help="sessionsToNormal"
            />
            <Tile label="Price move (absolute)" stat={own.price_abs_change_pct} format={absPct} />
          </div>

          {p.attention_points.length > 0 && (
            <ul className="expect-attention">
              {p.attention_points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          )}

          <details className="expect-details">
            <summary>Show details</summary>
            <p className="expect-intro">
              Past {typeLabel.toLowerCase()} releases of pbb: trading on the publication day vs its 20-day average.
            </p>
            <div className="ai-summary">
              <strong>AI summary</strong>
              <p>{p.ai_summary || 'No data'}</p>
            </div>
            {p.peers.n > 0 ? (
              <div className="expect-peers">
                <span className="kicker">PEERS · {p.peers.n} PAST EVENTS</span>
                <div className="expect-peer-row">
                  <span>Spread change, median</span>
                  <strong>pbb {formatPercent(own.spread_change_pct.median)}</strong>
                  <strong>Peers {formatPercent(p.peers.spread_change_pct.median)}</strong>
                </div>
                <div className="expect-peer-row">
                  <span>Volume vs usual, median</span>
                  <strong>pbb {ratio(own.volume_ratio.median)}</strong>
                  <strong>Peers {ratio(p.peers.volume_ratio.median)}</strong>
                </div>
              </div>
            ) : (
              p.peers.peers_note && <p className="small-note">Peers: {p.peers.peers_note}.</p>
            )}
            <div className="expect-footer">
              <p className="small-note">
                {p.note} Statistics on past trading reactions only: no price direction is implied.
              </p>
              <button className="text-button" onClick={onOpenFull}>
                Other announcement types →
              </button>
            </div>
          </details>
        </>
      )}
    </section>
  )
}
