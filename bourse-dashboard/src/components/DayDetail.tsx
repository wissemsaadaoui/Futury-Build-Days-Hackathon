// Vue détail d'une journée : une section par analyse, construite UNIQUEMENT avec les champs que l'impact card
// renvoie (/days/{isin}/{date}/impact-card ou /events/{id}/impact-card). Une section sans données affiche « No data ».
import type { ReactNode } from 'react'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { Anomaly, ImpactCardResponse, Num } from '../api/types.ts'
import {
  anomalyLabels,
  eventLabels,
  formatAnomalyValue,
  formatCompact,
  formatDate,
  formatEuro,
  formatNumber,
  formatPercent,
  formatRatio,
  hasDemoData,
  isMissing,
  trendClass,
} from '../format.ts'
import { PdfButton } from './PdfButton.tsx'

// Anomalies statistiques du jour (badges en haut) ; les autres types sont des alertes d'exécution (en bas).
const SIGNAL_TYPES = new Set(['volume_spike', 'spread_widening', 'price_move'])

const bps = (value: Num | undefined) => (isMissing(value) ? '–' : `${formatNumber(value, 1)} bps`)
const pctOfRatio = (value: Num | undefined) => (isMissing(value) ? '–' : `${formatNumber(value * 100, 1)}%`)
const pts = (value: Num | undefined) =>
  isMissing(value) ? '–' : `${value > 0 ? '+' : ''}${formatNumber(value * 100, 1)} pts`
const zScore = (value: Num | undefined) => (isMissing(value) ? '–' : `${value > 0 ? '+' : ''}${formatNumber(value, 1)}`)

// Un spread qui s'élargit = liquidité moins bonne : affiché en rouge (inverse des prix)
const spreadTone = (value: Num | undefined) => trendClass(isMissing(value) ? value : -value)

function allMissing(...values: (Num | undefined)[]) {
  return values.every(isMissing)
}

function Section({
  kicker,
  title,
  empty,
  children,
  wide = false,
}: {
  kicker: string
  title: string
  empty: boolean
  children: ReactNode
  wide?: boolean
}) {
  return (
    <section className={`panel day-section${wide ? ' wide' : ''}`}>
      <div className="panel-title">
        <div>
          <span className="kicker">{kicker}</span>
          <h2>{title}</h2>
        </div>
      </div>
      {empty ? <p className="no-data">No data</p> : children}
    </section>
  )
}

function Rows({ rows }: { rows: [string, string, string?][] }) {
  return (
    <dl className="day-rows">
      {rows.map(([label, value, tone]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd className={tone ?? ''}>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

// Titre vs médiane des peers : deux barres par ligne, à la même échelle
function PeerBars({ rows }: { rows: { label: string; own: Num | undefined; peers: Num | undefined; format: (v: Num | undefined) => string }[] }) {
  const shown = rows.filter((row) => !allMissing(row.own, row.peers))
  return (
    <div className="peer-bars">
      {shown.map((row) => {
        const max = Math.max(Math.abs(row.own ?? 0), Math.abs(row.peers ?? 0), 0.0001)
        const width = (value: Num | undefined) => `${isMissing(value) ? 0 : Math.max(3, (Math.abs(value) / max) * 100)}%`
        return (
          <div className="peer-bar-row" key={row.label}>
            <span className="peer-bar-label">{row.label}</span>
            <div className="peer-bar-line">
              <small>pbb</small>
              <div className="peer-bar-track"><i className="own" style={{ width: width(row.own) }} /></div>
              <strong>{row.format(row.own)}</strong>
            </div>
            <div className="peer-bar-line">
              <small>Peers</small>
              <div className="peer-bar-track"><i className="peers" style={{ width: width(row.peers) }} /></div>
              <strong>{row.format(row.peers)}</strong>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function WindowChart({ card }: { card: ImpactCardResponse }) {
  const data = card.window.map((day) => ({
    offset: day.offset,
    date: day.date,
    volume_ratio: day.volume_ratio,
    spread_bps: day.spread_bps,
  }))
  return (
    <div className="day-window-chart">
      <ResponsiveContainer width="100%" height={190}>
        <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="#eef1f5" vertical={false} />
          <XAxis
            dataKey="offset"
            tickFormatter={(offset: number) => (offset > 0 ? `+${offset}` : `${offset}`)}
            tick={{ fontSize: 9, fill: '#8792a2' }}
            axisLine={{ stroke: '#dfe5ec' }}
            tickLine={false}
          />
          <YAxis yAxisId="vol" tick={{ fontSize: 9, fill: '#8792a2' }} tickFormatter={(v: number) => `${v}×`} axisLine={false} tickLine={false} width={40} />
          <YAxis yAxisId="spread" orientation="right" tick={{ fontSize: 9, fill: '#8792a2' }} axisLine={false} tickLine={false} width={34} />
          <Tooltip
            contentStyle={{ fontSize: 10, borderRadius: 6, borderColor: '#e1e6ed' }}
            labelFormatter={(_, payload) => {
              const row = payload?.[0]?.payload as { date?: string; offset?: number } | undefined
              return row?.date ? `${formatDate(row.date)} (day ${row.offset})` : ''
            }}
            formatter={(value, name) =>
              name === 'Volume vs 20-day avg' ? formatRatio(value as number, 2) : bps(value as number)
            }
          />
          <ReferenceLine yAxisId="vol" x={0} stroke="#8cbe00" strokeDasharray="3 3" />
          <Bar yAxisId="vol" dataKey="volume_ratio" name="Volume vs 20-day avg" radius={[3, 3, 0, 0]} maxBarSize={22}>
            {data.map((row) => (
              <Cell key={row.offset} fill={row.offset === 0 ? '#8cbe00' : '#c9d6ea'} />
            ))}
          </Bar>
          <Line
            yAxisId="spread"
            dataKey="spread_bps"
            name="Spread (bps)"
            stroke="#000099"
            strokeWidth={2}
            dot={(props: { cx?: number; cy?: number; payload?: { offset: number } }) => (
              <circle
                key={`dot-${props.payload?.offset}`}
                cx={props.cx}
                cy={props.cy}
                r={props.payload?.offset === 0 ? 5 : 2.5}
                fill={props.payload?.offset === 0 ? '#8cbe00' : '#000099'}
                stroke="#fff"
                strokeWidth={1}
              />
            )}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="chart-legend day-window-legend">
        <span><i className="legend-bar" /> Volume vs 20-day average (left)</span>
        <span><i className="legend-price" /> XLM spread, bps (right)</span>
        <span><i className="legend-ema20" /> Selected day (0)</span>
      </div>
    </div>
  )
}

export function DayDetail({ card, dayAnomalies }: { card: ImpactCardResponse; dayAnomalies: Anomaly[] }) {
  const m = card.metrics
  const day = card.window.find((w) => w.offset === 0)?.date ?? card.event?.trading_day ?? ''
  const signals = dayAnomalies.filter((a) => SIGNAL_TYPES.has(a.type))
  const alerts = dayAnomalies.filter((a) => !SIGNAL_TYPES.has(a.type))
  const peers = card.vs_peers
  const level = card.technical_context?.broke_level

  return (
    <div className="day-detail">
      <section className="panel impact-card day-hero">
        <div className="timeline-card-top">
          <span>{card.event ? eventLabels[card.event.type] ?? card.event.type : 'Trading day'}</span>
          <small>{hasDemoData(card._data_status) ? 'PARTLY DEMO DATA' : 'XETRA DATA'}</small>
        </div>
        <h2>{card.event ? card.event.title : `Trading on ${formatDate(day)}`}</h2>
        <p className="muted">
          {formatDate(day)}
          {card.baseline ? ` · Baseline: ${card.baseline.method} (${formatDate(card.baseline.from)} – ${formatDate(card.baseline.to)})` : ''}
        </p>
        <div className="day-badges">
          {signals.length === 0 && <span className="day-badge none">No anomaly flagged this day</span>}
          {signals.map((a) => (
            <span className={`day-badge ${a.severity}`} key={`${a.type}-${a.description}`} title={a.description}>
              <i className={`signal-dot ${a.severity}`} />
              {anomalyLabels[a.type] ?? a.type} · {formatAnomalyValue(a.type, a.value)}
              <small>{a.severity}</small>
            </span>
          ))}
        </div>
      </section>

      <div className="day-sections">
        <Section
          kicker="1 · LIQUIDITY (XLM)"
          title="Spread at EUR 25,000"
          empty={allMissing(m.spread_bps.event, m.spread_bps.baseline)}
        >
          <div className="day-headline">
            <strong>{bps(m.spread_bps.event)}</strong>
            <span className={spreadTone(m.spread_bps.change_pct)}>{formatPercent(m.spread_bps.change_pct)} vs 20-day avg</span>
          </div>
          <Rows
            rows={[
              ['Spread on the day', bps(m.spread_bps.event)],
              ['20-day baseline', bps(m.spread_bps.baseline)],
              ['Change vs baseline', formatPercent(m.spread_bps.change_pct), spreadTone(m.spread_bps.change_pct)],
            ]}
          />
        </Section>

        <Section kicker="2 · RETURNS" title="Closing price" empty={allMissing(m.price.close, m.price.change_pct)}>
          <div className="day-headline">
            <strong>{formatEuro(m.price.close)}</strong>
            <span className={trendClass(m.price.change_pct)}>{formatPercent(m.price.change_pct)} vs previous close</span>
          </div>
          <Rows
            rows={[
              ['Previous close', formatEuro(m.price.prev_close)],
              ['Open', formatEuro(m.price.open)],
              ['Close', formatEuro(m.price.close)],
              ['Intraday range', isMissing(m.price.intraday_range_pct) ? '–' : `${formatNumber(m.price.intraday_range_pct, 1)}%`],
              ...(level ? [[`Price level`, `Crossed ${level.type} at ${formatEuro(level.price)}`] as [string, string]] : []),
            ]}
          />
        </Section>

        <Section
          kicker="3 · VOLUME / TURNOVER"
          title="Activity vs 20-day average"
          empty={allMissing(m.volume.event, m.turnover_eur?.event)}
        >
          <div className="day-headline">
            <strong>{formatRatio(m.volume.ratio, 2)}</strong>
            <span>usual volume</span>
          </div>
          <Rows
            rows={[
              ['Volume', isMissing(m.volume.event) ? '–' : `${formatNumber(m.volume.event, 0)} shares`],
              ['Volume, 20-day avg', isMissing(m.volume.baseline) ? '–' : `${formatNumber(m.volume.baseline, 0)} shares`],
              ['Volume z-score', zScore(m.volume.z_score)],
              ['Turnover', formatCompactEur(m.turnover_eur?.event)],
              ['Turnover, 20-day avg', formatCompactEur(m.turnover_eur?.baseline)],
              ['Turnover vs avg', formatRatio(m.turnover_eur?.ratio, 2)],
            ]}
          />
          <p className="small-note">VWAP: no data (not in the API response).</p>
        </Section>

        <Section
          kicker="4 · PEERS"
          title="pbb vs peer median"
          empty={allMissing(peers.peer_avg_price_change_pct, peers.peer_avg_volume_ratio, peers.excess_return_pct)}
        >
          <PeerBars
            rows={[
              { label: 'Price change', own: m.price.change_pct, peers: peers.peer_avg_price_change_pct, format: formatPercent },
              { label: 'Volume vs usual', own: m.volume.ratio, peers: peers.peer_avg_volume_ratio, format: (v) => formatRatio(v, 2) },
            ]}
          />
          <Rows rows={[['Return vs peer median', formatPercent(peers.excess_return_pct), trendClass(peers.excess_return_pct)]]} />
        </Section>

        <Section
          kicker="5 · HISTORICAL TREND"
          title="Window −5 to +5 sessions"
          empty={card.window.length === 0 || card.window.every((w) => isMissing(w.spread_bps) && isMissing(w.volume_ratio))}
          wide
        >
          <WindowChart card={card} />
        </Section>

        <Section kicker="6 · ANNOUNCEMENT" title={card.event ? 'Linked announcement' : 'No linked announcement'} empty={false} wide>
          {card.event ? (
            <>
              <p className="day-event-title">{card.event.title}</p>
              <p className="muted">
                {eventLabels[card.event.type] ?? card.event.type} · {formatDate(card.event.trading_day)}
                {card.event.published_at ? ` · published ${card.event.published_at.slice(11, 16)} (Frankfurt)` : ' · time unavailable'}
                {card.event.source_url && (
                  <>
                    {' · '}
                    <a href={card.event.source_url} target="_blank" rel="noreferrer">Source ↗</a>
                  </>
                )}
              </p>
            </>
          ) : (
            <p className="muted">No company announcement on record for this trading day.</p>
          )}
          <div className="ai-summary">
            <strong>AI summary</strong>
            <p>{card.ai_summary || 'No data'}</p>
          </div>
        </Section>

        <Section
          kicker="7 · AUCTION PARTICIPATION"
          title="Share of volume in auctions"
          empty={allMissing(m.auction_share.event, m.auction_share.baseline)}
        >
          <div className="day-headline">
            <strong>{pctOfRatio(m.auction_share.event)}</strong>
            <span>vs {pctOfRatio(m.auction_share.baseline)} on average ({pts(m.auction_share.change_pts)})</span>
          </div>
          <Rows
            rows={[
              ['Auction share, day', pctOfRatio(m.auction_share.event)],
              ['Auction share, 20-day avg', pctOfRatio(m.auction_share.baseline)],
              ['Opening auction vs usual', formatRatio(m.opening_auction?.ratio, 2)],
              ['Closing auction vs usual', formatRatio(m.closing_auction?.ratio, 2)],
            ]}
          />
        </Section>

        <Section kicker="EXECUTION ALERTS" title="Alerts on this day" empty={alerts.length === 0}>
          {alerts.map((a) => (
            <div className="signal-row static" key={`${a.type}-${a.description}`}>
              <span className={`signal-dot ${a.severity}`} />
              <span className="signal-copy">
                <strong>{anomalyLabels[a.type] ?? a.type}</strong>
                <small>{a.description}</small>
              </span>
              <span className="signal-value">{formatAnomalyValue(a.type, a.value)}</span>
            </div>
          ))}
        </Section>

        <Section
          kicker="INTRADAY"
          title={card.intraday ? `From ${card.intraday.during_session ? 'the publication' : 'the open'} (${card.intraday.reference_time.slice(11, 16)})` : 'Intraday reaction'}
          empty={!card.intraday}
          wide
        >
          {card.intraday && (
            <div className="impact-metrics">
              <Metric label="First 15 min volume vs usual" value={formatRatio(card.intraday.first_15min.ratio, 2)} />
              <Metric label="Price after 5 min" value={formatPercent(card.intraday.price_change_pct.after_5min)} tone={trendClass(card.intraday.price_change_pct.after_5min)} />
              <Metric label="Price after 30 min" value={formatPercent(card.intraday.price_change_pct.after_30min)} tone={trendClass(card.intraday.price_change_pct.after_30min)} />
              <Metric label="Price after 60 min" value={formatPercent(card.intraday.price_change_pct.after_60min)} tone={trendClass(card.intraday.price_change_pct.after_60min)} />
            </div>
          )}
        </Section>

        {card.pre_disclosure_activity && (
          <Section kicker="BEFORE THE DISCLOSURE" title="Activity in the prior sessions" empty={false} wide>
            <p className="muted">{card.pre_disclosure_activity.summary}</p>
          </Section>
        )}
      </div>

      <div className="report-actions">
        <PdfButton path={card.export.pdf_url} filename={`${card.card_id}.pdf`}>
          Export PDF ↓
        </PdfButton>
      </div>
    </div>
  )
}

function formatCompactEur(value: Num | undefined) {
  return isMissing(value) ? '–' : `EUR ${formatCompact(value)}`
}

function Metric({ label, value, tone = '' }: { label: string; value: string; tone?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  )
}
