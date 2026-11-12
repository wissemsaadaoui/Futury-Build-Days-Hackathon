// Carte « What to expect » (haut du dashboard) : statistiques sur les réactions PASSÉES du trading au même type
// d'annonce (/stocks/{isin}/event-preview). Aucune direction de cours, aucune projection.
import type { EventsResponse, EventPreviewResponse, Num, PreviewStat } from '../api/types.ts'
import { useApi } from '../api/useApi.ts'
import { eventLabels, formatDate, formatNumber, formatPercent, formatRatio, isMissing } from '../format.ts'

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

const sessions = (value: Num) => {
  if (isMissing(value)) return '–'
  const shown = Number.isInteger(value) ? String(value) : formatNumber(value, 1)
  return `${shown} session${value === 1 ? '' : 's'}`
}
const absPct = (value: Num) => (isMissing(value) ? '–' : `${formatNumber(value, 1)}%`)
const ratio = (value: Num) => formatRatio(value, 2)

function Tile({ label, stat, format }: { label: string; stat: PreviewStat; format: (value: Num) => string }) {
  return (
    <div className="expect-tile">
      <span>{label}</span>
      {stat.n === 0 ? (
        <>
          <strong>No data</strong>
          <small>No past event of this type</small>
        </>
      ) : (
        <>
          <strong>{format(stat.median)}</strong>
          <small>
            median · range {format(stat.min)} to {format(stat.max)}
          </small>
        </>
      )}
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
      <div className="panel-title">
        <div>
          <span className="kicker">WHAT TO EXPECT · UPCOMING ANNOUNCEMENT</span>
          <h2>{p?.upcoming?.title ?? typeLabel}</h2>
          <p className="muted">
            {formatDate(p?.upcoming?.date ?? next.date)} · {typeLabel}
            {p?.upcoming?.source_url && (
              <>
                {' · '}
                <a href={p.upcoming.source_url} target="_blank" rel="noreferrer">Source ↗</a>
              </>
            )}
          </p>
        </div>
        {p && own && (
          <div className="expect-badges">
            <span className={`confidence ${p.confidence}`}>
              {p.confidence.charAt(0).toUpperCase() + p.confidence.slice(1)} confidence
            </span>
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
          <p className="expect-intro">
            How pbb's trading reacted to its past {typeLabel.toLowerCase()} releases (publication day vs its 20-day
            average).
          </p>
          <div className="expect-tiles">
            <Tile label="Spread change" stat={own.spread_change_pct} format={formatPercent} />
            <Tile label="Volume vs usual" stat={own.volume_ratio} format={ratio} />
            <Tile label="Sessions to normal liquidity" stat={own.sessions_to_normal} format={sessions} />
            <Tile label="Price move (absolute)" stat={own.price_abs_change_pct} format={absPct} />
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

          {p.attention_points.length > 0 && (
            <div className="attention-box">
              <span className="kicker">POINTS TO WATCH</span>
              <ul>
                {p.attention_points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="ai-summary">
            <strong>AI summary</strong>
            <p>{p.ai_summary || 'No data'}</p>
          </div>

          <div className="expect-footer">
            <p className="small-note">
              {p.note} Statistics on past trading reactions only: no price direction is implied.
            </p>
            <button className="text-button" onClick={onOpenFull}>
              Other announcement types →
            </button>
          </div>
        </>
      )}
    </section>
  )
}
