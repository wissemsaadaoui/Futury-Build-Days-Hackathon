// Carte « Auction share trend » du dashboard : part du volume exécutée en enchères (par jour) + moyenne 20 séances.
// Tout vient de dashboard.auction_trend (aucun calcul ici, sauf le passage 0–1 -> %). Clic sur un point -> vue du jour.
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { AuctionTrend, AuctionTrendPoint, Num } from '../api/types.ts'
import { formatDate, formatNumber, isMissing } from '../format.ts'
import { HelpTip } from './HelpTip.tsx'

const share = (value: Num | undefined) => (isMissing(value) ? '–' : `${formatNumber(value * 100, 0)}%`)
const shortDate = (value: string) =>
  new Date(`${value}T12:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

function TrendTooltip({ active, payload, hasParts }: { active?: boolean; payload?: { payload: AuctionTrendPoint }[]; hasParts: boolean }) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null
  return (
    <div className="auction-tooltip">
      <strong>{formatDate(row.date)}</strong>
      <span>Auction share <b>{share(row.auction_share)}</b></span>
      <span>20-session average <b>{share(row.baseline_20d)}</b></span>
      {hasParts && (
        <span className="auction-tooltip-parts">
          Opening {share(row.opening)} · Intraday {share(row.intraday)} · Closing {share(row.closing)}
        </span>
      )}
      <em>Click to open this day</em>
    </div>
  )
}

export function AuctionTrendCard({ trend, openDay }: { trend: AuctionTrend; openDay: (date: string) => void }) {
  const { series, start, latest, peak, change_vs_start: change } = trend
  const months = series.filter((p, i) => i === 0 || p.date.slice(0, 7) !== series[i - 1].date.slice(0, 7)).map((p) => p.date)
  const changePts = isMissing(change) ? null : Math.round(change * 100)

  return (
    <section className="panel auction-trend-card" aria-label="Auction share trend">
      <div className="panel-title">
        <div>
          <span className="kicker">AUCTIONS · XETRA FLOWS</span>
          <h2>
            Auction share trend <HelpTip metric="auctionTrend" label="the auction share trend" />
          </h2>
        </div>
        <div className="auction-trend-stats">
          <div>
            <span>20-session average</span>
            <strong>{share(latest?.value)}</strong>
            <small>{latest ? `on ${shortDate(latest.date)}` : 'not enough sessions'}</small>
          </div>
          <div>
            <span>Change vs start</span>
            <strong>{changePts === null ? '–' : `${changePts > 0 ? '+' : changePts < 0 ? '−' : ''}${Math.abs(changePts)} pts`}</strong>
            <small>{start && latest ? `${share(start.value)} on ${shortDate(start.date)}` : '–'}</small>
          </div>
          <div>
            <span>Peak day</span>
            <strong>{share(peak?.value)}</strong>
            <small>
              {peak ? shortDate(peak.date) : '–'}
              {peak && trend.has_parts && !isMissing(peak.closing) ? ` · closing auction ${share(peak.closing)}` : ''}
            </small>
          </div>
        </div>
      </div>

      <div className="auction-trend-chart">
        <ResponsiveContainer width="100%" height={230}>
          <ComposedChart
            data={series}
            margin={{ top: 22, right: 12, bottom: 0, left: -8 }}
            onClick={(state) => {
              const date = state?.activeLabel
              if (typeof date === 'string') openDay(date)
            }}
            style={{ cursor: 'pointer' }}
          >
            <CartesianGrid stroke="#eef1f5" vertical={false} />
            <XAxis
              dataKey="date"
              ticks={months}
              tickFormatter={(d: string) => new Date(`${d}T12:00:00`).toLocaleDateString('en-GB', { month: 'short' })}
              tick={{ fontSize: 13, fill: '#8792a2' }}
              axisLine={{ stroke: '#dfe5ec' }}
              tickLine={false}
            />
            <YAxis
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
              tick={{ fontSize: 13, fill: '#8792a2' }}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip content={<TrendTooltip hasParts={trend.has_parts} />} cursor={{ stroke: '#c9d6ea' }} />
            <Line
              dataKey="auction_share"
              name="Auction share"
              stroke="#a9bfe0"
              strokeWidth={1.2}
              dot={false}
              activeDot={{ r: 4, fill: '#000099', stroke: '#fff', strokeWidth: 2 }}
              isAnimationActive={false}
            />
            <Line
              dataKey="baseline_20d"
              name="20-session average"
              stroke="#000099"
              strokeWidth={2.2}
              dot={false}
              activeDot={false}
              isAnimationActive={false}
            />
            {peak && !isMissing(peak.value) && (
              <ReferenceDot
                x={peak.date}
                y={peak.value}
                r={5}
                fill="#8cbe00"
                stroke="#fff"
                strokeWidth={2}
                label={{
                  value: `Peak ${share(peak.value)} · ${shortDate(peak.date)}`,
                  position: 'top',
                  fontSize: 13,
                  fontWeight: 700,
                  fill: '#24334b',
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-legend auction-trend-legend">
        <span><i className="legend-auction-day" /> Daily auction share of volume</span>
        <span><i className="legend-auction-avg" /> 20-session average</span>
        <span><i className="legend-auction-peak" /> Peak day</span>
        <span className="auction-trend-hint">Click a point to open the day view</span>
      </div>
    </section>
  )
}
