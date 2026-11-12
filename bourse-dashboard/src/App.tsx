import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import {
  AreaSeries,
  ColorType,
  LineSeries,
  createChart,
  type AutoscaleInfo,
  type UTCTimestamp,
} from 'lightweight-charts'

import { ApiError, UNAUTHORIZED_EVENT, apiGet, apiPost, clearToken, getToken, setToken } from './api/clients.ts'
import type {
  ChatLink,
  ChatResponse,
  CompareResponse,
  DailyPoint,
  DashboardResponse,
  EventPreviewResponse,
  EventsResponse,
  ImpactCardResponse,
  PreviewStat,
  ReportResponse,
} from './api/types.ts'
import { clearApiCache, useApi } from './api/useApi.ts'
import { AnomalyList } from './components/AnomalyList.tsx'
import { CountUp } from './components/CountUp.tsx'
import { DayDetail } from './components/DayDetail.tsx'
import { HelpTip } from './components/HelpTip.tsx'
import { PdfButton } from './components/PdfButton.tsx'
import { WhatToExpect } from './components/WhatToExpect.tsx'
import {
  DISCLAIMER,
  eventLabels,
  formatCompact,
  formatDate,
  formatEuro,
  formatNumber,
  formatPercent,
  formatRatio,
  hasDemoData,
  trendClass,
} from './format.ts'

type Page =
  | 'home'
  | 'login'
  | 'dashboard'
  | 'events'
  | 'impact'
  | 'indicators'
  | 'alerts'
  | 'compare'
  | 'report'
  | 'preview'
  | 'assistant'

type Period = '1W' | '1M' | '3M' | 'YTD'

type StockPoint = {
  time: UTCTimestamp
  date: string
  close: number
  ema20: number | null
  ema50: number | null
  volume: number | null
  volumeRatio: number | null
  turnover: number | null
  vwap: number | null
  spreadBps: number | null
  auctionShare: number | null
}

type ChatMessage = {
  role: 'assistant' | 'user'
  text: string
  links?: ChatLink[]
}

const WELCOME: ChatMessage = {
  role: 'assistant',
  text: 'Hello. Ask me about pbb\'s historical Xetra trading: a period, a specific day, an announcement or the peers. Answers are built from the analyses in this tool.',
}

const SUGGESTED_QUESTIONS = [
  'What happened in the latest week?',
  'Why was 29 Sep unusual?',
  "What to expect from today's Q3 release?",
  'How does pbb compare with its peers?',
]

type Thresholds = {
  volumeRatio: number
  breakoutDistance: number
  ema200Distance: number
  macdBars: number
  maxRisk: number
  rewardRisk: number
  directorsDealings: number
}

type AlertInputs = {
  ownershipPct: number
  volumeRatio: number
  breakoutDistance: number
  ema200Distance: number
  macdBars: number
  directorsDealings: number
}

const ISIN = 'DE0008019001'
const COMPANY = 'Deutsche Pfandbriefbank AG'

const periods: Period[] = ['1W', '1M', '3M', 'YTD']
// Nombre de séances par période (le dashboard couvre 2026 jusqu'au 30.10)
const periodSessions: Record<Period, number> = { '1W': 5, '1M': 21, '3M': 63, YTD: Infinity }

// Impact card ouverte par défaut : ad hoc du 13.02.2026 (scène b de la démo)
const DEFAULT_IMPACT = '/events/evt_002/impact-card'

const indicators = [
  {
    id: 'share-price',
    name: 'Share price',
    description: 'Last traded share price in EUR.',
    formula: 'Most recent closing price in the selected interval.',
  },
  {
    id: 'returns',
    name: 'Stock returns',
    description: 'Price change over the selected interval.',
    formula: '(Last close − first close) ÷ first close × 100.',
  },
  {
    id: 'volume',
    name: 'Trading volume',
    description: 'Number of shares traded.',
    formula: 'Sum of shares traded during the selected period.',
  },
  {
    id: 'rvol',
    name: 'Relative volume',
    description: 'Current volume compared with its recent average.',
    formula: 'Current daily volume ÷ average daily volume.',
  },
  {
    id: 'turnover-vwap',
    name: 'Turnover and VWAP',
    description: 'Traded value and volume-weighted average price.',
    formula: 'Turnover is traded value in EUR; VWAP weights price by volume.',
  },
  {
    id: 'spread',
    name: 'XLM spread',
    description: 'Estimated round-trip trading cost in basis points.',
    formula: 'Xetra Liquidity Measure for the reference transaction size.',
  },
  {
    id: 'ema',
    name: 'Moving averages',
    description: 'EMA 20 and EMA 50 trend references.',
    formula: 'Exponential moving averages calculated from closing prices.',
  },
  {
    id: 'auction',
    name: 'Auction participation',
    description: 'Share of volume executed in auctions.',
    formula: 'Auction volume ÷ total trading volume.',
  },
]

const defaultThresholds: Thresholds = {
  volumeRatio: 1.5,
  breakoutDistance: 1,
  ema200Distance: 0.5,
  macdBars: 2,
  maxRisk: 2,
  rewardRisk: 2,
  directorsDealings: 20000,
}

const defaultAlertInputs: AlertInputs = {
  ownershipPct: 2.7,
  volumeRatio: 1.7,
  breakoutDistance: 0.4,
  ema200Distance: 0.8,
  macdBars: 2,
  directorsDealings: 12500,
}

const holdingThresholds = [3, 5, 10, 15, 20, 25, 30, 50, 75]

// Série quotidienne de l'API -> points du graphique (jours sans prix de clôture ignorés)
function toStockPoints(series: DailyPoint[]): StockPoint[] {
  return series
    .filter((day) => day.close !== null)
    .map((day) => {
      const [year, month, dayOfMonth] = day.date.split('-').map(Number)
      return {
        time: (Date.UTC(year, month - 1, dayOfMonth) / 1000) as UTCTimestamp,
        date: day.date,
        close: day.close as number,
        ema20: day.ema_20,
        ema50: day.ema_50,
        volume: day.volume,
        volumeRatio: day.volume_ratio,
        turnover: day.turnover_eur,
        vwap: day.volume && day.turnover_eur !== null ? day.turnover_eur / day.volume : null,
        spreadBps: day.spread_bps,
        auctionShare: day.auction_share,
      }
    })
}

function byDateDesc<T extends { date: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => b.date.localeCompare(a.date))
}

const DASHBOARD_PATH = `/stocks/${ISIN}/dashboard`

// Chargement / erreur d'une requête, avec le style des encadrés existants
function LoadState({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) return <div className="notice-box">Could not load data from the API ({error}).</div>
  if (loading) return <div className="notice-box">Loading data…</div>
  return null
}

function Reveal({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  const elementRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = elementRef.current
    if (!element) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          element.classList.add('is-visible')
          observer.unobserve(element)
        }
      },
      { threshold: 0.12 },
    )

    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={elementRef} className={`reveal ${className}`}>
      {children}
    </div>
  )
}

function Header({
  page,
  loggedIn,
  navigate,
  logout,
}: {
  page: Page
  loggedIn: boolean
  navigate: (page: Page) => void
  logout: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const items: { label: string; page: Page }[] = loggedIn
    ? [
        { label: 'Home', page: 'home' },
        { label: 'Dashboard', page: 'dashboard' },
        { label: 'Events', page: 'events' },
        { label: 'Compare', page: 'compare' },
      ]
    : [{ label: 'Home', page: 'home' }]

  return (
    <header className="site-header">
      <div className="header-inner">
        <div className="menu-wrap">
          <button
            className="menu-toggle"
            aria-label="Open tools menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span />
            <span />
            <span />
          </button>

          {menuOpen && (
            <div className="menu-popover">
              {[
                ['AI Assistant', 'assistant'],
                ['Indicator details', 'indicators'],
                ['Thresholds & alerts', 'alerts'],
                ['IR snapshot', 'report'],
                ['What to expect', 'preview'],
              ].map(([label, target]) => (
                <button
                  key={target}
                  onClick={() => {
                    navigate(target as Page)
                    setMenuOpen(false)
                  }}
                >
                  {label}
                  <span>↗</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <button className="brand" onClick={() => navigate('home')}>
          <span className="brand-symbol">pbb</span>
          <span className="brand-copy">
            <strong>ISSUER</strong>
            <small>INTELLIGENCE HUB</small>
          </span>
        </button>

        <nav className="main-nav" aria-label="Main navigation">
          {items.map((item) => (
            <button
              key={item.page}
              className={page === item.page ? 'active' : ''}
              onClick={() => navigate(item.page)}
            >
              {item.label}
            </button>
          ))}
          <a href="#contact">Contact</a>
        </nav>

        {loggedIn ? (
          <button className="header-login" onClick={logout}>
            Log out <span>↗</span>
          </button>
        ) : (
          <button className="header-login" onClick={() => navigate('login')}>
            Log in <span>↗</span>
          </button>
        )}
      </div>
    </header>
  )
}

function Footer() {
  return (
    <footer className="site-footer" id="contact">
      <div className="footer-top">
        <div className="footer-brand">
          <span className="brand-symbol">pbb</span>
          <div>
            <strong>Issuer Intelligence Hub</strong>
            <p>Market insight for IR teams.</p>
          </div>
        </div>
        <div className="footer-contact">
          <span className="footer-label">ABOUT THIS TOOL</span>
          <span>Data: Deutsche Börse Xetra (2 Jan – 30 Oct 2026)</span>
          <span>Built at Futury Build Days 2026</span>
        </div>
        <div className="footer-company">
          <span className="footer-label">COMPANY PROFILE</span>
          <strong>{COMPANY}</strong>
          <span>ISIN {ISIN} · SDAX</span>
        </div>
      </div>
      <div className="footer-bottom">
        <span>Historical Xetra trading data · 2 Jan–30 Oct 2026 · Source: Deutsche Börse</span>
        <span>{DISCLAIMER}</span>
      </div>
    </footer>
  )
}

function HomePage({
  navigate,
  loggedIn,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
}) {
  const { data } = useApi<DashboardResponse>(DASHBOARD_PATH)
  const points = useMemo(() => (data ? toStockPoints(data.series) : []), [data])
  const latest = points[points.length - 1]
  const lastCloses = points.slice(-10).map((point) => point.close)
  const low = Math.min(...lastCloses)
  const high = Math.max(...lastCloses)
  const change = data?.kpis.price_change_pct ?? null

  return (
    <>
      <Header page="home" loggedIn={loggedIn} navigate={navigate} logout={() => {}} />
      <main>
        <section className="hero">
          <div className="hero-inner">
            <div className="hero-copy">
              <p className="eyebrow">
                <span className="eyebrow-dot" />
                PBB · ISSUER INTELLIGENCE HUB
              </p>
              <h1>
                Every market move
                <br />
                <span>has a story.</span>
              </h1>
              <p className="hero-description">
                A focused market intelligence workspace for Deutsche Pfandbriefbank.
                Explore trading activity, understand event impact and prepare clear
                IR insights.
              </p>

              <div className="hero-company">
                <span className="company-logo">pbb</span>
                <span>
                  <strong>Deutsche Pfandbriefbank AG</strong>
                  <small>ISIN {ISIN} · SDAX</small>
                </span>
              </div>

              <button
                className="primary-button"
                onClick={() => navigate(loggedIn ? 'dashboard' : 'login')}
              >
                {loggedIn ? 'Open dashboard' : 'Log in to your workspace'}
                <span>→</span>
              </button>
              <p className="hero-footnote">Private workspace · Historical Xetra data</p>
            </div>

            <div className="hero-art">
              <div className="hero-orbit orbit-one" />
              <div className="hero-orbit orbit-two" />
              <div className="hero-card">
                <div className="hero-card-top">
                  <span>ISSUER OVERVIEW</span>
                  <span className="demo-label">2026 YTD</span>
                </div>
                <div className="hero-stock">
                  <div>
                    <small>PBB · XETRA</small>
                    <strong>{latest ? formatEuro(latest.close) : '–'}</strong>
                  </div>
                  <span>{change === null ? '–' : `${change >= 0 ? '↗' : '↘'} ${formatPercent(change)}`}</span>
                </div>
                <div className="mini-chart">
                  {lastCloses.map((close, index) => (
                    <i key={index} style={{ height: `${high > low ? 25 + ((close - low) / (high - low)) * 70 : 60}%` }} />
                  ))}
                </div>
                <div className="hero-card-bottom">
                  <span>Share performance</span>
                  <span>Event impact</span>
                  <span>Liquidity</span>
                </div>
              </div>
              <div className="hero-floating-note">
                <span />
                Market data workspace
              </div>
            </div>
          </div>
          <div className="hero-footer-line">
            <span>ONE ISSUER</span>
            <i />
            <span>ONE MARKET VIEW</span>
            <i />
            <span>BETTER CONTEXT</span>
          </div>
        </section>

        <section className="features-section">
          <div className="content-width">
            <Reveal>
              <div className="section-heading">
                <div>
                  <p className="eyebrow light">BUILT FOR IR TEAMS</p>
                  <h2>Market activity, made easier to explain.</h2>
                </div>
                <p>
                  Bring price action, liquidity and announcements into one focused view.
                </p>
              </div>
            </Reveal>

            <div className="feature-grid">
              {[
                ['01', 'Track the share', 'Follow price, volume and spread across useful time periods.', '↗'],
                ['02', 'Understand events', 'See how trading conditions changed around announcements.', '◎'],
                ['03', 'Share the context', 'Prepare consistent market insights for internal teams.', '⌁'],
              ].map(([number, title, text, icon], index) => (
                <Reveal key={number} className={`delay-${index + 1}`}>
                  <article className="feature-card">
                    <div className="feature-card-top">
                      <span>{icon}</span>
                      <small>{number}</small>
                    </div>
                    <h3>{title}</h3>
                    <p>{text}</p>
                    <i />
                  </article>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="home-cta">
          <Reveal>
            <div className="home-cta-inner">
              <div>
                <p className="eyebrow">PBB · {ISIN}</p>
                <h2>Your company. Your market view.</h2>
              </div>
              <button
                className="light-button"
                onClick={() => navigate(loggedIn ? 'dashboard' : 'login')}
              >
                {loggedIn ? 'Open workspace' : 'Access the workspace'} <span>→</span>
              </button>
            </div>
          </Reveal>
        </section>
      </main>
      <Footer />
    </>
  )
}

// Écran de login : le mot de passe part UNE fois vers POST /auth/login ; il n'est ni stocké ni gardé en mémoire
// après l'envoi. L'API renvoie un token signé (12 h), stocké dans localStorage.
function LoginPage({ onLogin }: { onLogin: (password: string) => Promise<string | null> }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    const failure = await onLogin(password)
    setSubmitting(false)
    setPassword('')
    setError(failure ?? '')
  }

  return (
    <>
      <main className="login-page">
        <section className="login-intro-panel">
          <div className="login-brand">
            <span className="brand-symbol">pbb</span>
            <span>ISSUER INTELLIGENCE HUB</span>
          </div>
          <div className="login-copy">
            <p className="eyebrow">PRIVATE WORKSPACE</p>
            <h1>See the market with more context.</h1>
            <p>Sign in to access the pbb market intelligence dashboard.</p>
          </div>
          <span className="login-caption">DEUTSCHE PFANDBRIEFBANK AG · {ISIN}</span>
          <i className="login-orbit orbit-a" />
          <i className="login-orbit orbit-b" />
        </section>

        <section className="login-form-side">
          <form className="login-card" onSubmit={submit}>
            <p className="eyebrow light">WELCOME</p>
            <h2>Issuer Intelligence Hub</h2>
            <p className="login-description">Enter the team password to continue to your workspace.</p>

            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoFocus
            />

            {error && <p className="login-error">{error}</p>}

            <button className="login-submit" type="submit" disabled={submitting || password === ''}>
              {submitting ? 'Checking…' : 'Log in'} <span>→</span>
            </button>

            <p className="login-security-note">
              Your session stays active for 12 hours on this browser. Use Log out on a shared computer.
            </p>
          </form>
        </section>
      </main>
      <Footer />
    </>
  )
}

function MarketChart({
  points,
  onSelect,
}: {
  points: StockPoint[]
  onSelect: (point: StockPoint) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const onSelectRef = useRef(onSelect)
  // first drawing starts once the chart panel has appeared; later ones (period change) start at once
  const firstDrawRef = useRef(true)
  const [hover, setHover] = useState<{
    date: string
    value: number
    x: number
    y: number
  } | null>(null)

  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  useEffect(() => {
    const container = containerRef.current
    if (!container || points.length === 0) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#697386',
        fontFamily: 'DM Sans, sans-serif',
        fontSize: 14,
      },
      grid: {
        vertLines: { color: '#f0f2f5' },
        horzLines: { color: '#e9edf2' },
      },
      rightPriceScale: {
        borderColor: '#e5e9ef',
        scaleMargins: { top: 0.12, bottom: 0.12 },
      },
      timeScale: {
        borderColor: '#e5e9ef',
        timeVisible: false,
        secondsVisible: false,
        rightOffset: 3,
      },
      crosshair: {
        vertLine: { color: '#8cbe00', labelBackgroundColor: '#8cbe00' },
        horzLine: { color: '#8cbe00', labelBackgroundColor: '#8cbe00' },
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: true,
        axisDoubleClickReset: true,
      },
    })

    const price = chart.addSeries(AreaSeries, {
      lineColor: '#000099',
      topColor: 'rgba(0, 0, 153, 0.32)',
      bottomColor: 'rgba(0, 0, 153, 0.03)',
      lineWidth: 3,
      crosshairMarkerRadius: 6,
      crosshairMarkerBorderColor: '#ffffff',
      crosshairMarkerBackgroundColor: '#000099',
      priceLineVisible: true,
      lastValueVisible: true,
    })

    const ema20 = chart.addSeries(LineSeries, {
      color: '#8cbe00',
      lineWidth: 2,
      lineStyle: 2,
      lastValueVisible: false,
      priceLineVisible: false,
    })

    const ema50 = chart.addSeries(LineSeries, {
      color: '#8dbcf0',
      lineWidth: 2,
      lineStyle: 2,
      lastValueVisible: false,
      priceLineVisible: false,
    })

    // The share-price line draws itself from left to right: points not drawn yet are whitespace,
    // so the time axis stays put, and the price axis is fixed to the full range while drawing.
    const priceData = points.map((point) => ({ time: point.time, value: point.close }))
    const closes = priceData.map((point) => point.value)
    const fullRange = { priceRange: { minValue: Math.min(...closes), maxValue: Math.max(...closes) } }
    let drawing = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    price.applyOptions({
      autoscaleInfoProvider: (original: () => AutoscaleInfo | null) => (drawing ? fullRange : original()),
    })

    let frame = 0
    const drawDuration = 3200
    const drawDelay = firstDrawRef.current ? 700 : 0
    firstDrawRef.current = false
    // position along the line (in points, fractional): every point before it is drawn, and the tip point is
    // placed part-way between its neighbours so the line grows continuously instead of jumping point by point
    const drawUpTo = (position: number) => {
      const whole = Math.floor(position)
      const fraction = position - whole
      price.setData(
        priceData.map((point, index) => {
          if (index <= whole) return point
          if (index === whole + 1 && fraction > 0) {
            const previous = priceData[whole].value
            return { time: point.time, value: previous + (point.value - previous) * fraction }
          }
          return { time: point.time }
        }),
      )
    }
    if (drawing && priceData.length > 1) {
      drawUpTo(0)
      const start = performance.now() + drawDelay
      const step = (now: number) => {
        const progress = Math.min(1, Math.max(0, (now - start) / drawDuration))
        const eased = (1 - Math.cos(Math.PI * progress)) / 2
        if (progress < 1) {
          drawUpTo(eased * (priceData.length - 1))
          frame = requestAnimationFrame(step)
        } else {
          drawing = false
          price.setData(priceData)
        }
      }
      frame = requestAnimationFrame(step)
    } else {
      drawing = false
      price.setData(priceData)
    }
    ema20.setData(
      points.flatMap((point) => (point.ema20 === null ? [] : [{ time: point.time, value: point.ema20 }])),
    )
    ema50.setData(
      points.flatMap((point) => (point.ema50 === null ? [] : [{ time: point.time, value: point.ema50 }])),
    )
    chart.timeScale().fitContent()

    chart.subscribeCrosshairMove((parameter) => {
      if (!parameter.point || !parameter.time) {
        setHover(null)
        return
      }

      const row = parameter.seriesData.get(price) as { value?: number } | undefined
      if (row?.value === undefined) {
        setHover(null)
        return
      }

      const point = points.find(
        (item) => Number(item.time) === Number(parameter.time),
      )
      if (!point) {
        setHover(null)
        return
      }

      setHover({
        date: formatDate(point.date),
        value: row.value,
        x: parameter.point.x,
        y: parameter.point.y,
      })
    })

    chart.subscribeClick((parameter) => {
      if (!parameter.time) return
      const point = points.find(
        (item) => Number(item.time) === Number(parameter.time),
      )
      if (point) onSelectRef.current(point)
    })

    const resizeObserver = new ResizeObserver(() => {
      chart.applyOptions({
        width: container.clientWidth,
        height: container.clientHeight,
      })
    })
    resizeObserver.observe(container)

    return () => {
      cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      chart.remove()
    }
  }, [points])

  return (
    <div className="chart-wrap">
      <div className="chart-legend">
        <span><i className="legend-price" /> Share price</span>
        <span><i className="legend-ema20" /> EMA 20</span>
        <span><i className="legend-ema50" /> EMA 50</span>
        <small>Scroll to zoom · Drag to move · Click a point to inspect</small>
      </div>

      <div className="chart-canvas" ref={containerRef}>
        {hover && (
          <div
            className="chart-tooltip"
            style={{
              left: `${Math.max(2, Math.min((hover.x / Math.max(containerRef.current?.clientWidth ?? 1, 1)) * 100 + 2, 72))}%`,
              top: `${Math.max(4, Math.min(hover.y + 12, 65))}px`,
            }}
          >
            <span>{hover.date}</span>
            <strong>{formatEuro(hover.value)}</strong>
            <small>Click this point for analysis options</small>
          </div>
        )}
      </div>
      <p className="chart-note">
        Daily Xetra closing prices · Drag to pan and scroll to zoom
      </p>
    </div>
  )
}

function WeeklyMovement({ points }: { points: StockPoint[] }) {
  const week = points.slice(-7)
  let gain = 0
  let loss = 0

  for (let index = 1; index < week.length; index += 1) {
    const difference = week[index].close - week[index - 1].close
    if (difference > 0) gain += difference
    if (difference < 0) loss += difference
  }

  const net = gain + loss
  const max = Math.max(gain, Math.abs(loss), Math.abs(net), 0.01)
  const rows = [
    { label: 'Weekly gain', amount: gain, tone: 'gain' },
    { label: 'Weekly loss', amount: loss, tone: 'loss' },
    { label: 'Net price move', amount: net, tone: net >= 0 ? 'net-up' : 'net-down' },
  ]

  return (
    <section className="panel weekly-card">
      <div className="panel-title">
        <div>
          <span className="kicker">LAST 7 DATA POINTS</span>
          <h2>Weekly movement</h2>
        </div>
        <span className="round-icon">€</span>
      </div>

      <div className="movement-list">
        {rows.map((row) => (
          <div className="movement-row" key={row.label}>
            <div className="movement-label">
              <span>{row.label}</span>
              <strong className={row.amount < 0 ? 'negative' : row.amount > 0 ? 'positive' : ''}>
                <CountUp text={`${row.amount > 0 ? '+' : ''}${formatEuro(row.amount)}`} delay={1100} />
              </strong>
            </div>
            <div className="movement-track">
              <i
                className={row.tone}
                style={{ width: `${Math.max(3, (Math.abs(row.amount) / max) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="small-note">
        Price movements, not company revenue or accounting profit.
      </p>
    </section>
  )
}

type AnalysisRequest = { from: string; to: string; question: string }

function AnalysisAssistant({
  point,
  onClose,
  openImpact,
  openDay,
}: {
  point: StockPoint
  onClose: () => void
  openImpact: (path: string) => void
  openDay: (date: string) => void
}) {
  const [from, setFrom] = useState(point.date)
  const [to, setTo] = useState(point.date)
  const [question, setQuestion] = useState('')
  const [request, setRequest] = useState<AnalysisRequest | null>(null)

  // Un jour -> day card (résumé IA du jour) ; une période -> report de la période (résumé IA de la période)
  const singleDay = request !== null && request.from === request.to
  const dayPath = singleDay ? `/days/${ISIN}/${request.from}/impact-card` : null
  const reportPath =
    request !== null && !singleDay ? `/stocks/${ISIN}/report?from=${request.from}&to=${request.to}` : null
  const day = useApi<ImpactCardResponse>(dayPath)
  const period = useApi<ReportResponse>(reportPath)
  const validRange = from !== '' && to !== '' && from <= to

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (validRange) setRequest({ from, to, question: question.trim() })
  }

  return (
    <div className="assistant-backdrop" onMouseDown={onClose}>
      <section
        className="analysis-drawer"
        onMouseDown={(event) => event.stopPropagation()}
        aria-label="AI analysis assistant"
      >
        <div className="drawer-heading">
          <div>
            <span className="kicker">PBB · AI ANALYSIS</span>
            <h2>Ask about this period</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="selected-point-card">
          <span>Selected chart point</span>
          <strong>{formatEuro(point.close)}</strong>
          <small>{formatDate(point.date)}</small>
          <button
            className="text-button"
            onClick={() => {
              onClose()
              openDay(point.date)
            }}
          >
            Open day details →
          </button>
        </div>

        <form className="analysis-form" onSubmit={submit}>
          <div className="date-range">
            <label>
              From
              <input type="date" min="2026-01-02" max="2026-10-30" value={from} onChange={(event) => setFrom(event.target.value)} />
            </label>
            <label>
              To
              <input type="date" min="2026-01-02" max="2026-10-30" value={to} onChange={(event) => setTo(event.target.value)} />
            </label>
          </div>

          <label htmlFor="analysis-question">What should the assistant analyse?</label>
          <textarea
            id="analysis-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="For example: explain the change in volume and spread during this period."
            rows={4}
          />

          {!validRange && <p className="login-error">“From” must be on or before “To”.</p>}
          <button className="primary-button full-width" type="submit" disabled={!validRange}>
            {from === to ? 'Analyse this day' : 'Analyse this period'} <span>→</span>
          </button>
        </form>

        {singleDay && <LoadState loading={day.loading} error={day.error} />}
        {!singleDay && request && <LoadState loading={period.loading} error={period.error} />}

        {request && (day.data || period.data) && (
          <div className="request-ready">
            {request.question && (
              <p>
                <strong>Your question:</strong> {request.question}
                <br />
                <small>
                  Below is the standard AI summary for the selected {singleDay ? 'day' : 'period'}. For
                  free-form questions, use the AI Assistant page.
                </small>
              </p>
            )}

            {singleDay && day.data && (
              <>
                <strong>
                  {day.data.event ? day.data.event.title : `Trading on ${formatDate(request.from)}`}
                </strong>
                <p>{day.data.ai_summary}</p>
                <button
                  className="text-button"
                  onClick={() => {
                    onClose()
                    openImpact(dayPath as string)
                  }}
                >
                  Open the full impact card →
                </button>
              </>
            )}

            {!singleDay && period.data && (
              <>
                <strong>
                  {formatDate(period.data.period.from)} – {formatDate(period.data.period.to)}
                </strong>
                <p>{period.data.headline}</p>
                {period.data.sections
                  .filter((section) => section.text)
                  .map((section) => (
                    <p key={section.title}>
                      <strong>{section.title}:</strong> {section.text}
                    </p>
                  ))}
                <PdfButton
                  className="text-button"
                  path={`/stocks/${ISIN}/report.pdf?from=${request.from}&to=${request.to}`}
                  filename={`pbb-report-${request.from}-${request.to}.pdf`}
                >
                  Export this period as PDF ↓
                </PdfButton>
              </>
            )}
          </div>
        )}

        <p className="small-note">
          {DISCLAIMER}
        </p>
      </section>
    </div>
  )
}

function DashboardPage({
  navigate,
  loggedIn,
  logout,
  onPointSelect,
  selectedPoint,
  setSelectedPoint,
  openImpact,
  openDay,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
  onPointSelect: (point: StockPoint) => void
  selectedPoint: StockPoint | null
  setSelectedPoint: (point: StockPoint | null) => void
  openImpact: (path: string) => void
  openDay: (date: string) => void
}) {
  const [period, setPeriod] = useState<Period>('3M')
  const dashboard = useApi<DashboardResponse>(DASHBOARD_PATH)
  const events = useApi<EventsResponse>(`/stocks/${ISIN}/events`)
  const fullSeries = useMemo(
    () => (dashboard.data ? toStockPoints(dashboard.data.series) : []),
    [dashboard.data],
  )
  const points = useMemo(
    () => (period === 'YTD' ? fullSeries : fullSeries.slice(-periodSessions[period])),
    [period, fullSeries],
  )
  const recentEvents = useMemo(() => byDateDesc(events.data?.events ?? []).slice(0, 5), [events.data])

  const latest = points[points.length - 1]
  const first = points[0]
  const periodChange =
    first && latest ? ((latest.close - first.close) / first.close) * 100 : 0

  const selectPoint = useCallback((point: StockPoint) => {
    onPointSelect(point)
  }, [onPointSelect])

  return (
    <>
      <Header page="dashboard" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page dash-enter">
        <div className="workspace-container">
          <div className="page-heading">
            <div>
              <p className="eyebrow light">PBB · {ISIN}</p>
              <h1>Market dashboard</h1>
              <p>Share performance, liquidity and trading context in one view.</p>
            </div>
            <div className="heading-actions">
              <button className="outline-button" onClick={() => navigate('alerts')}>
                Thresholds & alerts <span>↗</span>
              </button>
              <button className="outline-button" onClick={() => navigate('report')}>
                IR snapshot <span>↗</span>
              </button>
            </div>
          </div>

          <div className="dashboard-toolbar">
            <div className="stock-identity">
              <span className="stock-mark">pbb</span>
              <div>
                <strong>{dashboard.data?.stock.name ?? COMPANY}</strong>
                <small>Xetra · {ISIN} · {dashboard.data?.stock.index ?? 'SDAX'}</small>
                {dashboard.data && (
                  <small className="data-as-of">Data as of {formatDate(dashboard.data.period.to)}</small>
                )}
              </div>
            </div>
            <div className="period-select" aria-label="Select chart period">
              {periods.map((option) => (
                <button
                  key={option}
                  className={period === option ? 'selected' : ''}
                  onClick={() => {
                    setPeriod(option)
                    setSelectedPoint(null)
                  }}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>

          <WhatToExpect isin={ISIN} onOpenFull={() => navigate('preview')} />

          <LoadState loading={dashboard.loading} error={dashboard.error} />

          <div className="dashboard-grid">
            <Reveal>
              <section className="panel chart-panel">
                <div className="chart-heading">
                  <div>
                    <span className="kicker">
                      SHARE PRICE · EUR · {hasDemoData(dashboard.data?._data_status) ? 'PARTLY DEMO DATA' : 'XETRA'}
                    </span>
                    <div className="price-line">
                      <strong><CountUp text={latest ? formatEuro(latest.close) : '–'} delay={1000} /></strong>
                      <span className={`price-change ${periodChange >= 0 ? 'positive' : 'negative'}`}>
                        {periodChange >= 0 ? '↑' : '↓'} <CountUp text={formatPercent(periodChange)} delay={1000} />
                      </span>
                    </div>
                  </div>
                  <div className="chart-period-label">
                    <span>Range: {period}</span>
                    <span>{latest ? `Last close ${formatDate(latest.date)}` : 'Currency: EUR'}</span>
                  </div>
                </div>

                <MarketChart points={points} onSelect={selectPoint} />

                {selectedPoint && (
                  <div className="point-actions">
                    <div>
                      <span>Selected point</span>
                      <strong>
                        {formatEuro(selectedPoint.close)} · {formatDate(selectedPoint.date)}
                      </strong>
                    </div>
                    <button className="outline-button" onClick={() => openDay(selectedPoint.date)}>
                      View day details <span>↗</span>
                    </button>
                    <button className="primary-button compact" onClick={() => onPointSelect(selectedPoint)}>
                      Analyse with AI <span>✳</span>
                    </button>
                  </div>
                )}
              </section>
            </Reveal>

            <Reveal className="delay-1 side-widgets">
              <WeeklyMovement points={points} />
              <section className="panel liquidity-card">
                <div className="panel-title">
                  <div>
                    <span className="kicker">LIQUIDITY SNAPSHOT</span>
                    <h2>Latest indicators</h2>
                  </div>
                </div>
                <div className="mini-stat">
                  <span>Trading volume <HelpTip metric="volume" label="trading volume" /></span>
                  <strong><CountUp text={formatCompact(latest?.volume)} delay={1000} /></strong>
                </div>
                <div className="mini-stat">
                  <span>Turnover <HelpTip metric="turnover" label="turnover" /></span>
                  <strong><CountUp text={formatEuro(latest?.turnover)} delay={1000} /></strong>
                </div>
                <div className="mini-stat">
                  <span>XLM spread (25k EUR) <HelpTip metric="spread" label="the XLM spread" /></span>
                  <strong>
                    <CountUp text={latest?.spreadBps == null ? '–' : `${formatNumber(latest.spreadBps, 1)} bps`} delay={1000} />
                  </strong>
                </div>
                <div className="mini-stat">
                  <span>Volume vs 20-day average <HelpTip metric="ratio" label="volume vs 20-day average" /></span>
                  <strong><CountUp text={formatRatio(latest?.volumeRatio)} delay={1000} /></strong>
                </div>
                <div className="mini-stat">
                  <span>VWAP</span>
                  <strong><CountUp text={formatEuro(latest?.vwap)} delay={1000} /></strong>
                </div>
                <div className="mini-stat">
                  <span>Auction share <HelpTip metric="auctionShare" label="auction share" /></span>
                  <strong>
                    <CountUp
                      text={latest?.auctionShare == null ? '–' : `${formatNumber(latest.auctionShare * 100, 1)}%`}
                      delay={1000}
                    />
                  </strong>
                </div>
                <button className="text-button" onClick={() => navigate('indicators')}>
                  View all indicators →
                </button>
              </section>
            </Reveal>
          </div>

          <div className="dashboard-lower">
            <Reveal>
              <section className="panel lower-panel">
                <div className="panel-title">
                  <div>
                    <span className="kicker">TRADING SIGNALS · MOST IMPORTANT FIRST</span>
                    <h2>Notable days</h2>
                  </div>
                  <button className="text-button" onClick={() => navigate('alerts')}>
                    Configure alerts →
                  </button>
                </div>
                {dashboard.data && (
                  <AnomalyList anomalies={dashboard.data.anomalies} onOpen={openImpact} />
                )}
              </section>
            </Reveal>

            <Reveal className="delay-1">
              <section className="panel lower-panel">
                <div className="panel-title">
                  <div>
                    <span className="kicker">COMPANY ANNOUNCEMENTS</span>
                    <h2>Recent events</h2>
                  </div>
                  <button className="text-button" onClick={() => navigate('events')}>
                    See all →
                  </button>
                </div>
                <LoadState loading={events.loading} error={events.error} />
                {recentEvents.map((event) => (
                  <button
                    className="recent-event"
                    key={event.event_id}
                    onClick={() => openImpact(`/events/${event.event_id}/impact-card`)}
                  >
                    <span className="event-date-block">
                      <strong>{new Date(`${event.date}T12:00:00`).getDate()}</strong>
                      <small>
                        {new Date(`${event.date}T12:00:00`).toLocaleDateString('en-GB', {
                          month: 'short',
                        })}
                      </small>
                    </span>
                    <span className="recent-event-copy">
                      <strong>{event.title}</strong>
                      <small>{eventLabels[event.type] ?? event.type}</small>
                    </span>
                    <span>↗</span>
                  </button>
                ))}
              </section>
            </Reveal>
          </div>
        </div>
      </main>
      <Footer />
    </>
  )
}

function EventsPage({
  navigate,
  loggedIn,
  logout,
  openImpact,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
  openImpact: (path: string) => void
}) {
  const { data, error, loading } = useApi<EventsResponse>(`/stocks/${ISIN}/events`)
  // /events ne renvoie pas la dernière date des données : on la lit sur le dashboard (même requête, en cache)
  const dashboard = useApi<DashboardResponse>(DASHBOARD_PATH)
  const events = useMemo(() => byDateDesc(data?.events ?? []), [data])

  return (
    <>
      <Header page="events" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container narrow">
          <PageHeading
            eyebrow="PBB · COMPANY DISCLOSURES"
            title="Events timeline"
            description="Company announcements and related trading metrics."
          />

          <LoadState loading={loading} error={error} />
          {data && (
            <div className="notice-box">
              {dashboard.data && (
                <strong className="data-as-of">Data as of {formatDate(dashboard.data.period.to)} · </strong>
              )}
              {events.length} announcements from public sources (pbb IR, EQS). Values that are
              not available appear as “–”.
            </div>
          )}

          <div className="timeline">
            {events.map((event) => (
              <article className="timeline-item" key={event.event_id}>
                <div className="timeline-date">
                  <strong>{formatDate(event.date)}</strong>
                  <span>{event.time || 'Time unavailable'}</span>
                </div>
                <div className="timeline-card">
                  <div className="timeline-card-top">
                    <span>{eventLabels[event.type] ?? event.type}</span>
                    {event.source_url && (
                      <a href={event.source_url} target="_blank" rel="noreferrer">
                        <small>SOURCE ↗</small>
                      </a>
                    )}
                  </div>
                  <h2>{event.title}</h2>
                  <p>Trading day: {formatDate(event.trading_day)}</p>
                  <div className="event-metrics">
                    <Metric label="Volume ratio" value={formatRatio(event.headline_metric.volume_ratio)} />
                    <Metric label="Price change" value={formatPercent(event.headline_metric.price_change_pct)} tone={trendClass(event.headline_metric.price_change_pct)} />
                    <Metric label="Spread change" value={formatPercent(event.headline_metric.spread_change_pct)} tone={trendClass(event.headline_metric.spread_change_pct)} />
                  </div>
                  <button className="text-button" onClick={() => openImpact(`/events/${event.event_id}/impact-card`)}>
                    View impact card →
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>
      </main>
      <Footer />
    </>
  )
}

function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow light">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  )
}

function Metric({
  label,
  value,
  tone = '',
}: {
  label: string
  value: string
  tone?: string
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  )
}

function ImpactPage({
  navigate,
  loggedIn,
  logout,
  impactPath,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
  impactPath: string
}) {
  const { data: card, error, loading } = useApi<ImpactCardResponse>(impactPath)
  // Badges d'anomalie et alertes du jour : liste `anomalies` du dashboard (l'impact card ne la contient pas)
  const dashboard = useApi<DashboardResponse>(DASHBOARD_PATH)
  const day = card?.window.find((w) => w.offset === 0)?.date ?? card?.event?.trading_day
  const dayAnomalies = useMemo(
    () => (dashboard.data?.anomalies ?? []).filter((anomaly) => anomaly.date === day),
    [dashboard.data, day],
  )

  return (
    <>
      <Header page="events" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container">
          <PageHeading
            eyebrow="DAY DETAIL · IMPACT CARD"
            title="Trading day analysis"
            description="Liquidity, returns, activity, peers, auctions and the linked announcement for one trading day."
            action={
              <button className="outline-button" onClick={() => navigate('dashboard')}>
                ← Back to dashboard
              </button>
            }
          />

          <LoadState loading={loading} error={error} />
          {card && <DayDetail card={card} dayAnomalies={dayAnomalies} />}
        </div>
      </main>
      <Footer />
    </>
  )
}

function IndicatorsPage({
  navigate,
  loggedIn,
  logout,
  selectedPoint,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
  selectedPoint: StockPoint | null
}) {
  const [activeIndicator, setActiveIndicator] = useState<(typeof indicators)[number] | null>(null)
  const { data } = useApi<DashboardResponse>(DASHBOARD_PATH)
  const points = useMemo(() => (data ? toStockPoints(data.series) : []), [data])
  const point = selectedPoint ?? points[points.length - 1] ?? null
  // Rendement : depuis le début de la série jusqu'au point affiché
  const firstClose = points[0]?.close
  const returnPct = point && firstClose ? ((point.close - firstClose) / firstClose) * 100 : null

  const values: Record<string, string> = point
    ? {
        'share-price': formatEuro(point.close),
        returns: `${formatPercent(returnPct)} since ${formatDate(points[0].date)}`,
        volume: formatCompact(point.volume),
        rvol: formatRatio(point.volumeRatio, 2),
        'turnover-vwap': `${formatEuro(point.turnover)} / ${formatEuro(point.vwap)}`,
        spread: point.spreadBps === null ? '–' : `${formatNumber(point.spreadBps, 1)} bps`,
        ema: `${formatEuro(point.ema20)} / ${formatEuro(point.ema50)}`,
        auction: point.auctionShare === null ? '–' : `${formatNumber(point.auctionShare * 100, 1)}%`,
      }
    : {}

  return (
    <>
      <Header page="dashboard" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container narrow">
          <PageHeading
            eyebrow="PBB · SELECTED DATA POINT"
            title="Indicator details"
            description={
              selectedPoint
                ? `Selected chart point: ${formatDate(selectedPoint.date)}. Choose an indicator to open its details.`
                : point
                  ? `Latest trading day: ${formatDate(point.date)}. Choose an indicator to inspect its value and calculation.`
                  : 'Choose an indicator to inspect its value and calculation.'
            }
            action={
              <button className="outline-button" onClick={() => navigate('dashboard')}>
                Back to chart
              </button>
            }
          />

          <div className="indicator-list">
            {indicators.map((indicator) => (
              <button
                className="indicator-row"
                key={indicator.id}
                onClick={() => setActiveIndicator(indicator)}
              >
                <span className="indicator-icon">↗</span>
                <span className="indicator-copy">
                  <strong>{indicator.name}</strong>
                  <small>{indicator.description}</small>
                </span>
                <span className="indicator-open">View details →</span>
              </button>
            ))}
          </div>
        </div>
      </main>
      <Footer />

      {activeIndicator && (
        <div className="modal-backdrop" onMouseDown={() => setActiveIndicator(null)}>
          <section
            className="indicator-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="indicator-modal-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <div>
                <span className="kicker">INDICATOR DETAILS</span>
                <h2 id="indicator-modal-title">{activeIndicator.name}</h2>
              </div>
              <button
                className="icon-button"
                onClick={() => setActiveIndicator(null)}
                aria-label="Close details"
              >
                ×
              </button>
            </div>
            <p>{activeIndicator.description}</p>
            <div className="indicator-value-box">
              <span>Selected value</span>
              <strong>{values[activeIndicator.id] ?? '–'}</strong>
              <small>
                {point ? `${formatDate(point.date)} · Xetra data` : '–'}
              </small>
            </div>
            <div className="modal-explanation">
              <strong>How it is calculated</strong>
              <p>{activeIndicator.formula}</p>
            </div>
            <button className="primary-button compact" onClick={() => navigate('alerts')}>
              Configure an alert for this indicator →
            </button>
          </section>
        </div>
      )}
    </>
  )
}

function AlertsPage({
  navigate,
  loggedIn,
  logout,
  openImpact,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
  openImpact: (path: string) => void
}) {
  const { data: dashboard } = useApi<DashboardResponse>(DASHBOARD_PATH)
  const [thresholds, setThresholds] = useState(defaultThresholds)
  const [inputs, setInputs] = useState(defaultAlertInputs)
  const [alerts, setAlerts] = useState<string[]>([])

  function updateThreshold<K extends keyof Thresholds>(key: K, value: number) {
    setThresholds((current) => ({ ...current, [key]: value }))
  }

  function updateInput<K extends keyof AlertInputs>(key: K, value: number) {
    setInputs((current) => ({ ...current, [key]: value }))
  }

  function evaluateAlerts() {
    const results: string[] = []

    const nextOwnershipThreshold = holdingThresholds.find(
      (threshold) => inputs.ownershipPct < threshold,
    )
    if (
      nextOwnershipThreshold !== undefined &&
      inputs.ownershipPct >= nextOwnershipThreshold - 0.5
    ) {
      results.push(
        `Shareholding is approaching the ${nextOwnershipThreshold}% voting-rights threshold.`,
      )
    }

    if (inputs.ownershipPct >= 30) {
      results.push(
        'The entered shareholding is at or above 30%. Review the applicable takeover rules.',
      )
    }

    if (inputs.volumeRatio >= thresholds.volumeRatio) {
      results.push(
        `Relative volume alert: ${formatNumber(inputs.volumeRatio, 2)}× meets the ${formatNumber(thresholds.volumeRatio, 2)}× threshold.`,
      )
    }

    if (inputs.breakoutDistance >= thresholds.breakoutDistance) {
      results.push(
        `Breakout distance alert: price is ${formatNumber(inputs.breakoutDistance, 2)}% beyond the entered reference level.`,
      )
    }

    if (inputs.ema200Distance >= thresholds.ema200Distance) {
      results.push(
        `EMA 200 trend alert: price is ${formatNumber(inputs.ema200Distance, 2)}% above the configured threshold.`,
      )
    }

    if (inputs.macdBars >= thresholds.macdBars) {
      results.push(
        `MACD confirmation: ${inputs.macdBars} consecutive expanding bars meet the configured minimum.`,
      )
    }

    if (inputs.directorsDealings >= thresholds.directorsDealings) {
      results.push(
        `Directors' dealings entered amount is at or above €${formatNumber(thresholds.directorsDealings, 0)}.`,
      )
    }

    setAlerts(
      results.length > 0
        ? results
        : ['No configured thresholds were crossed by the entered demo values.'],
    )
  }

  return (
    <>
      <Header page="dashboard" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container">
          <PageHeading
            eyebrow="CONFIGURATION"
            title="Thresholds & alerts"
            description="Alerts detected in the Xetra data, and demo rules to preview your own thresholds."
          />

          <section className="panel lower-panel">
            <div className="panel-title">
              <div>
                <span className="kicker">DETECTED IN XETRA DATA · {dashboard?.anomalies.length ?? '–'} ALERTS IN 2026</span>
                <h2>Most important alerts</h2>
              </div>
            </div>
            {dashboard && <AnomalyList anomalies={dashboard.anomalies} onOpen={openImpact} />}
          </section>

          <div className="threshold-layout">
            <section className="panel threshold-panel">
              <div className="panel-title">
                <div>
                  <span className="kicker">LEGAL & REGULATORY REFERENCES</span>
                  <h2>Shareholding thresholds</h2>
                </div>
              </div>
              <p className="section-description">
                Voting-rights thresholds shown here are reference values from the
                supplied project notes. Confirm applicability before production use.
              </p>

              <div className="threshold-chips">
                {holdingThresholds.map((value) => (
                  <span key={value}>{value}%</span>
                ))}
              </div>

              <div className="threshold-reference">
                <strong>30% control reference</strong>
                <span>
                  At 30%, review the applicable takeover rules and circumstances.
                </span>
              </div>

              <label className="field-label" htmlFor="ownership-input">
                Current entered voting-rights share (%)
              </label>
              <input
                id="ownership-input"
                type="number"
                min="0"
                max="100"
                step="0.1"
                value={inputs.ownershipPct}
                onChange={(event) => updateInput('ownershipPct', Number(event.target.value))}
              />

              <div className="form-divider" />

              <div className="panel-title">
                <div>
                  <span className="kicker">TECHNICAL SIGNALS</span>
                  <h2>Trading thresholds</h2>
                </div>
              </div>

              <NumberSetting
                label="Relative volume threshold (×)"
                description="Suggested demo range: 1.5×–2.0× 30-day average daily volume."
                value={thresholds.volumeRatio}
                step={0.1}
                onChange={(value) => updateThreshold('volumeRatio', value)}
              />
              <NumberSetting
                label="Breakout distance (%)"
                description="Distance beyond a reference support or resistance level."
                value={thresholds.breakoutDistance}
                step={0.1}
                onChange={(value) => updateThreshold('breakoutDistance', value)}
              />
              <NumberSetting
                label="EMA 200 distance (%)"
                description="Price distance above the 200-day moving average."
                value={thresholds.ema200Distance}
                step={0.1}
                onChange={(value) => updateThreshold('ema200Distance', value)}
              />
              <NumberSetting
                label="MACD confirmation bars"
                description="Minimum consecutive expanding bars."
                value={thresholds.macdBars}
                step={1}
                onChange={(value) => updateThreshold('macdBars', value)}
              />

              <div className="form-divider" />

              <div className="panel-title">
                <div>
                  <span className="kicker">RISK MANAGEMENT REFERENCES</span>
                  <h2>Risk settings</h2>
                </div>
              </div>

              <NumberSetting
                label="Maximum risk per trade (%)"
                description="Configurable reference range: 1%–2% of entered portfolio equity."
                value={thresholds.maxRisk}
                step={0.1}
                onChange={(value) => updateThreshold('maxRisk', value)}
              />
              <NumberSetting
                label="Minimum reward-to-risk ratio"
                description="Example: 2 means a 1:2 risk-to-reward ratio."
                value={thresholds.rewardRisk}
                step={0.1}
                onChange={(value) => updateThreshold('rewardRisk', value)}
              />

              <div className="form-divider" />

              <div className="panel-title">
                <div>
                  <span className="kicker">DIRECTORS’ DEALINGS</span>
                  <h2>Annual amount reference</h2>
                </div>
              </div>
              <NumberSetting
                label="Entered annual transaction amount (€)"
                description="Reference amount from the project notes; verify applicable rules."
                value={inputs.directorsDealings}
                step={500}
                onChange={(value) => updateInput('directorsDealings', value)}
              />
              <NumberSetting
                label="Configured alert amount (€)"
                description="Amount that triggers a demo alert in this prototype."
                value={thresholds.directorsDealings}
                step={500}
                onChange={(value) => updateThreshold('directorsDealings', value)}
              />
            </section>

            <aside className="threshold-side">
              <section className="panel threshold-panel">
                <div className="panel-title">
                  <div>
                    <span className="kicker">DEMO INPUTS</span>
                    <h2>Test the alert rules</h2>
                  </div>
                </div>

                <NumberSetting
                  label="Relative volume (×)"
                  value={inputs.volumeRatio}
                  step={0.1}
                  onChange={(value) => updateInput('volumeRatio', value)}
                />
                <NumberSetting
                  label="Breakout distance (%)"
                  value={inputs.breakoutDistance}
                  step={0.1}
                  onChange={(value) => updateInput('breakoutDistance', value)}
                />
                <NumberSetting
                  label="Distance above EMA 200 (%)"
                  value={inputs.ema200Distance}
                  step={0.1}
                  onChange={(value) => updateInput('ema200Distance', value)}
                />
                <NumberSetting
                  label="Consecutive MACD bars"
                  value={inputs.macdBars}
                  step={1}
                  onChange={(value) => updateInput('macdBars', value)}
                />

                <button className="primary-button full-width" onClick={evaluateAlerts}>
                  Evaluate demo alerts →
                </button>
              </section>

              <section className="panel alert-results">
                <span className="kicker">ALERT PREVIEW</span>
                <h2>Triggered alerts</h2>
                {alerts.length === 0 ? (
                  <p className="muted">
                    Change the demo inputs and evaluate to preview alerts.
                  </p>
                ) : (
                  <ul>
                    {alerts.map((alert) => (
                      <li key={alert}>
                        <span />
                        {alert}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </aside>
          </div>

          <p className="legal-note">
            These controls are a software prototype, not legal, investment or trading
            advice. Regulatory thresholds and reporting duties can depend on facts and
            current rules.
          </p>
        </div>
      </main>
      <Footer />
    </>
  )
}

function NumberSetting({
  label,
  description,
  value,
  step,
  onChange,
}: {
  label: string
  description?: string
  value: number
  step: number
  onChange: (value: number) => void
}) {
  return (
    <label className="number-setting">
      <span>
        <strong>{label}</strong>
        {description && <small>{description}</small>}
      </span>
      <input
        type="number"
        min="0"
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  )
}

function ComparePage({
  navigate,
  loggedIn,
  logout,
  openImpact,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
  openImpact: (path: string) => void
}) {
  const [eventType, setEventType] = useState('quarterly_results')
  const [index, setIndex] = useState('ALL')
  const [from, setFrom] = useState('2026-01-02')
  const [to, setTo] = useState('2026-10-30')
  const query = new URLSearchParams({ type: eventType, index, from, to })
  const validRange = from !== '' && to !== '' && from <= to
  const { data, error, loading } = useApi<CompareResponse>(validRange ? `/compare?${query}` : null)

  return (
    <>
      <Header page="compare" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container">
          <PageHeading
            eyebrow="HISTORICAL CONTEXT"
            title="Compare events"
            description="Compare past reactions of the same event type and index group."
          />

          <div className="compare-controls">
            <label>
              Event type
              <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
                {Object.entries(eventLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label>
              Index
              <select value={index} onChange={(event) => setIndex(event.target.value)}>
                <option value="ALL">All indices</option>
                <option>DAX</option>
                <option>MDAX</option>
                <option>SDAX</option>
              </select>
            </label>
            <label>
              From
              <input type="date" min="2026-01-02" max="2026-10-30" value={from} onChange={(event) => setFrom(event.target.value)} />
            </label>
            <label>
              To
              <input type="date" min="2026-01-02" max="2026-10-30" value={to} onChange={(event) => setTo(event.target.value)} />
            </label>
          </div>

          {!validRange && <div className="notice-box">“From” must be on or before “To”.</div>}
          <LoadState loading={loading} error={error} />

          <section className="panel compare-panel">
            <div className="panel-title">
              <div>
                <span className="kicker">EVENT COMPARISON · {data?.summary.n_events ?? 0} EVENTS</span>
                <h2>Historical event responses</h2>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Company</th>
                    <th>Volume ratio</th>
                    <th>Price change</th>
                    <th>Spread change</th>
                    <th>Auction share</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.events ?? []).map((event) => (
                    <tr key={event.event_id} onClick={() => openImpact(`/events/${event.event_id}/impact-card`)} style={{ cursor: 'pointer' }}>
                      <td>{formatDate(event.date)}</td>
                      <td>{event.name}</td>
                      <td>{formatRatio(event.volume_ratio)}</td>
                      <td className={trendClass(event.price_change_pct)}>
                        {formatPercent(event.price_change_pct)}
                      </td>
                      <td className={trendClass(event.spread_change_pct)}>
                        {formatPercent(event.spread_change_pct)}
                      </td>
                      <td>
                        {event.auction_share_change_pts === null
                          ? '–'
                          : `${event.auction_share_change_pts > 0 ? '+' : ''}${formatNumber(event.auction_share_change_pts * 100, 1)} pts`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small-note">
              {data && data.events.length === 0
                ? 'No event of this type in the selected index and period.'
                : 'Click a row to open its impact card. Null values are shown as a dash.'}
            </p>
          </section>

          <div className="summary-tiles">
            <div><span>Median volume ratio</span><strong>{formatRatio(data?.summary.median_volume_ratio)}</strong><small>{data?.summary.n_events ?? 0} events</small></div>
            <div><span>Median price move (absolute)</span><strong>{data?.summary.median_abs_price_change_pct == null ? '–' : `${formatNumber(data.summary.median_abs_price_change_pct, 1)}%`}</strong><small>Size of the move, up or down</small></div>
            <div><span>Median spread move</span><strong>{formatPercent(data?.summary.median_spread_change_pct)}</strong><small>vs. 20-day baseline</small></div>
          </div>
        </div>
      </main>
      <Footer />
    </>
  )
}

function ReportPage({
  navigate,
  loggedIn,
  logout,
  openImpact,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
  openImpact: (path: string) => void
}) {
  const { data: report, error, loading } = useApi<ReportResponse>(`/stocks/${ISIN}/report`)
  const items = report?.sections.flatMap((section) => section.items ?? []) ?? []

  function exportCsv() {
    const rows = [
      ['Date', 'Event', 'Volume ratio', 'Price change (%)', 'Spread change (%)'],
      ...items.map((item) => [
        item.date,
        `"${item.title.replace(/"/g, '""')}"`,
        item.volume_ratio ?? '',
        item.price_change_pct ?? '',
        item.spread_change_pct ?? '',
      ]),
    ]
    const csv = rows.map((row) => row.join(';')).join('\n')
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'pbb-ir-snapshot-events.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <Header page="dashboard" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container narrow">
          <PageHeading
            eyebrow="IR SNAPSHOT"
            title="Trading report"
            description={`Concise historical summary for ${COMPANY}.`}
          />

          <LoadState loading={loading} error={error} />

          {report && (
            <section className="panel report-panel">
              <div className="report-cover">
                <span className="company-logo">pbb</span>
                <div>
                  <span className="kicker">ISSUER MARKET REPORT</span>
                  <h2>{report.stock.name}</h2>
                  <p>
                    ISIN {report.stock.isin} · {report.stock.index} · {formatDate(report.period.from)}–{formatDate(report.period.to)}
                  </p>
                </div>
              </div>
              <div className="report-section">
                <span className="kicker">EXECUTIVE SUMMARY</span>
                <p>{report.headline}</p>
              </div>
              {report.sections.map((section) => (
                <div className="report-section" key={section.title}>
                  <span className="kicker">{section.title.toUpperCase()}</span>
                  {(section.kpis ?? []).map((kpi) => (
                    <div className="report-event" key={kpi.label}>
                      <span>{kpi.label}</span>
                      <strong>{formatKpi(kpi.value, kpi.unit)}</strong>
                      <span>
                        {kpi.change_pct == null ? kpi.trend ?? '' : `${formatPercent(kpi.change_pct)} ${kpi.trend ?? ''}`}
                      </span>
                    </div>
                  ))}
                  {section.text && <p>{section.text}</p>}
                  {(section.items ?? []).map((item) => (
                    <button
                      className="report-event"
                      key={item.event_id}
                      onClick={() => openImpact(`/events/${item.event_id}/impact-card`)}
                    >
                      <span>{formatDate(item.date)}</span>
                      <strong>{item.title}</strong>
                      <span>Spread {formatPercent(item.spread_change_pct)}</span>
                    </button>
                  ))}
                </div>
              ))}
              <div className="report-disclaimer">{report.disclaimer}</div>
              <div className="report-actions">
                <PdfButton path={report.export.pdf_url} filename="pbb-ir-snapshot.pdf">
                  Export PDF ↓
                </PdfButton>
                <button className="outline-button" onClick={exportCsv}>
                  Export events CSV ↓
                </button>
              </div>
            </section>
          )}
        </div>
      </main>
      <Footer />
    </>
  )
}

function formatKpi(value: number | null, unit: string) {
  if (unit === 'EUR') return formatEuro(value)
  if (unit === 'bps') return value === null ? '–' : `${formatNumber(value, 1)} bps`
  if (unit === 'ratio') return value === null ? '–' : `${formatNumber(value * 100, 1)}%`
  if (unit === 'pct') return formatPercent(value)
  return value === null ? '–' : formatNumber(value, 0) // shares, count
}

function formatRange(stat: PreviewStat, format: (value: number | null) => string) {
  if (stat.n === 0) return 'No past event'
  return `Range: ${format(stat.min)} to ${format(stat.max)}`
}

function PreviewPage({
  navigate,
  loggedIn,
  logout,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
}) {
  const [eventType, setEventType] = useState('quarterly_results')
  const { data: preview, error, loading } = useApi<EventPreviewResponse>(
    `/stocks/${ISIN}/event-preview?type=${eventType}`,
  )
  const history = preview?.own_history
  const sessions = (value: number | null) => {
    if (value === null) return '–'
    const rounded = Math.round(value)
    return `${rounded} session${rounded === 1 ? '' : 's'}`
  }

  return (
    <>
      <Header page="dashboard" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container narrow">
          <PageHeading
            eyebrow="HISTORICAL PATTERNS"
            title="What to expect"
            description="Statistics on past trading reactions to the same type of announcement."
          />

          <div className="compare-controls">
            <label>
              Announcement type
              <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
                {Object.entries(eventLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
          </div>

          <LoadState loading={loading} error={error} />

          {preview && history && (
            <section className="panel preview-panel">
              <div className="panel-title">
                <div>
                  <span className="kicker">
                    {preview.upcoming ? 'UPCOMING EVENT' : 'NEXT EVENT OF THIS TYPE'} · BASED ON {history.n} PAST EVENT{history.n === 1 ? '' : 'S'}
                  </span>
                  <h2>{preview.upcoming?.title ?? eventLabels[preview.event_type] ?? preview.event_type}</h2>
                  <p className="muted">
                    {preview.upcoming ? `Scheduled: ${formatDate(preview.upcoming.date)}` : 'No date announced'}
                  </p>
                </div>
                <span className="confidence">
                  {preview.confidence.charAt(0).toUpperCase() + preview.confidence.slice(1)} confidence
                </span>
              </div>

              <div className="preview-grid">
                <div>
                  <span>Historical spread change</span>
                  <strong>{formatPercent(history.spread_change_pct.median)}</strong>
                  <small>{formatRange(history.spread_change_pct, formatPercent)}</small>
                </div>
                <div>
                  <span>Historical volume</span>
                  <strong>{formatRatio(history.volume_ratio.median)}</strong>
                  <small>{formatRange(history.volume_ratio, (value) => formatRatio(value))}</small>
                </div>
                <div>
                  <span>Return to normal</span>
                  <strong>{history.sessions_to_normal.median === null ? '–' : `~${sessions(history.sessions_to_normal.median)}`}</strong>
                  <small>{formatRange(history.sessions_to_normal, sessions)}</small>
                </div>
              </div>

              <div className="ai-summary">
                <strong>AI summary</strong>
                <p>{preview.ai_summary}</p>
              </div>

              {preview.attention_points.length > 0 && (
                <div className="attention-box">
                  <span className="kicker">POINTS TO WATCH</span>
                  <ul>
                    {preview.attention_points.map((point) => (
                      <li key={point}>{point}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="small-note">{preview.note} Statistics on past trading reactions only.</p>
            </section>
          )}
        </div>
      </main>
      <Footer />
    </>
  )
}

function AssistantPage({
  navigate,
  loggedIn,
  logout,
  messages,
  setMessages,
  openDay,
  openImpact,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
  messages: ChatMessage[]
  setMessages: (update: (current: ChatMessage[]) => ChatMessage[]) => void
  openDay: (date: string) => void
  openImpact: (path: string) => void
}) {
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [messages, pending])

  async function ask(question: string) {
    const text = question.trim()
    if (!text || pending) return
    // Historique envoyé : les échanges réels (sans le message d'accueil) ; l'API n'en garde que les 6 derniers
    const history = [...messages.filter((m) => m !== WELCOME), { role: 'user' as const, text }]
    setMessages((current) => [...current, { role: 'user', text }])
    setDraft('')
    setPending(true)
    try {
      const reply = await apiPost<ChatResponse>('/assistant/chat', {
        isin: ISIN,
        messages: history.map((m) => ({ role: m.role, content: m.text })),
      })
      setMessages((current) => [...current, { role: 'assistant', text: reply.answer, links: reply.links }])
    } catch (error) {
      const detail = error instanceof ApiError && error.status === 429
        ? 'Too many questions in a short time. Please wait a minute and try again.'
        : 'The assistant could not answer right now. Please try again.'
      setMessages((current) => [...current, { role: 'assistant', text: detail }])
    } finally {
      setPending(false)
    }
  }

  function openLink(link: ChatLink) {
    if (link.type === 'day') openDay(link.ref)
    else if (link.type === 'event') openImpact(`/events/${link.ref}/impact-card`)
    else if (link.type === 'preview') navigate('preview')
    else navigate('compare')
  }

  function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void ask(draft)
  }

  const onlyWelcome = messages.length === 1

  return (
    <>
      <Header page="assistant" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="assistant-page">
        <section className="panel assistant-card">
          <div className="panel-title">
            <div>
              <span className="kicker">PBB · IR</span>
              <h1>AI Assistant</h1>
              <p>Ask about trading activity, events, peers or a specific day.</p>
            </div>
          </div>
          <div className="chat-messages" aria-live="polite">
            {messages.map((message, index) => (
              <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                {message.text}
                {message.links && message.links.length > 0 && (
                  <div className="chat-links">
                    {message.links.map((link) => (
                      <button key={`${link.type}-${link.ref}`} className="chat-link" onClick={() => openLink(link)}>
                        {link.label} ↗
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {onlyWelcome && (
              <div className="chat-suggestions">
                {SUGGESTED_QUESTIONS.map((question) => (
                  <button key={question} onClick={() => void ask(question)} disabled={pending}>
                    {question}
                  </button>
                ))}
              </div>
            )}
            {pending && <div className="chat-message assistant chat-typing">Analysing…</div>}
            <div ref={endRef} />
          </div>
          <form className="chat-form" onSubmit={sendMessage}>
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask a question..."
              aria-label="Your question"
              maxLength={2000}
            />
            <button type="submit" disabled={pending || draft.trim() === ''}>Send →</button>
          </form>
          <p className="small-note">
            Answers are based only on historical Xetra data in this tool. Not investment advice.
          </p>
        </section>
      </main>
      <Footer />
    </>
  )
}

type AuthState = 'checking' | 'in' | 'out'

function App() {
  // Source de vérité : l'API (GET /auth/me au démarrage, puis tout 401 renvoie au login)
  const [auth, setAuth] = useState<AuthState>('checking')
  const loggedIn = auth === 'in'
  const [page, setPage] = useState<Page>('home')
  const [selectedPoint, setSelectedPoint] = useState<StockPoint | null>(null)
  const [assistantPoint, setAssistantPoint] = useState<StockPoint | null>(null)
  const [impactPath, setImpactPath] = useState(DEFAULT_IMPACT)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([WELCOME]) // historique de la session

  const navigate = useCallback(
    (target: Page) => {
      const publicPages: Page[] = ['home', 'login']
      if (!loggedIn && !publicPages.includes(target)) {
        setPage('login')
        return
      }
      setPage(target)
    },
    [loggedIn],
  )

  useEffect(() => {
    try {
      window.localStorage.removeItem('pbb-demo-auth') // ancien login factice : plus utilisé
    } catch {
      // stockage indisponible (navigation privée) : rien à nettoyer
    }
    let active = true
    // Pas de token : écran de login directement. Sinon /auth/me dit s'il est encore valide (un 401 l'efface).
    const check: Promise<unknown> = getToken() ? apiGet('/auth/me') : Promise.reject(new Error('no token'))
    check.then(() => active && setAuth('in')).catch(() => active && setAuth('out'))
    const onUnauthorized = () => {
      clearApiCache()
      setAuth('out')
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => {
      active = false
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    }
  }, [])

  // Renvoie un message d'erreur, ou null si le login a réussi
  const login = useCallback(async (password: string) => {
    try {
      const { token } = await apiPost<{ token: string; expires_at: string }>('/auth/login', { password })
      setToken(token) // seul le token est stocké, jamais le mot de passe
    } catch (error) {
      return error instanceof ApiError && error.status === 401
        ? 'Incorrect password.'
        : 'Could not reach the server. Please try again.'
    }
    clearApiCache()
    setAuth('in')
    setPage('dashboard')
    return null
  }, [])

  const logout = useCallback(() => {
    clearToken() // token sans état côté serveur : l'effacer suffit
    clearApiCache()
    setChatMessages([WELCOME])
    setAuth('out')
    setSelectedPoint(null)
    setAssistantPoint(null)
    setPage('dashboard')
  }, [])

  // detail_url d'une anomalie, /events/{id}/impact-card ou /days/{isin}/{date}/impact-card
  const openImpact = useCallback(
    (path: string) => {
      setImpactPath(path)
      navigate('impact')
    },
    [navigate],
  )

  const eventsList = useApi<EventsResponse>(loggedIn ? `/stocks/${ISIN}/events` : null)
  const openDay = useCallback(
    (date: string) => {
      const event = eventsList.data?.events.find((item) => item.trading_day === date)
      openImpact(event ? `/events/${event.event_id}/impact-card` : `/days/${ISIN}/${date}/impact-card`)
    },
    [eventsList.data, openImpact],
  )

  const selectChartPoint = useCallback((point: StockPoint) => {
    setSelectedPoint(point)
    setAssistantPoint(point)
  }, [])

  let content: ReactNode

  if (auth === 'checking') {
    content = <main className="auth-checking">Loading…</main>
  } else if (auth === 'out') {
    content = <LoginPage onLogin={login} />
  } else if (page === 'dashboard') {
    content = (
      <DashboardPage
        navigate={navigate}
        loggedIn={loggedIn}
        logout={logout}
        onPointSelect={selectChartPoint}
        selectedPoint={selectedPoint}
        setSelectedPoint={setSelectedPoint}
        openImpact={openImpact}
        openDay={openDay}
      />
    )
  } else if (page === 'events') {
    content = <EventsPage navigate={navigate} loggedIn={loggedIn} logout={logout} openImpact={openImpact} />
  } else if (page === 'impact') {
    content = <ImpactPage navigate={navigate} loggedIn={loggedIn} logout={logout} impactPath={impactPath} />
  } else if (page === 'indicators') {
    content = (
      <IndicatorsPage
        navigate={navigate}
        loggedIn={loggedIn}
        logout={logout}
        selectedPoint={selectedPoint}
      />
    )
  } else if (page === 'alerts') {
    content = <AlertsPage navigate={navigate} loggedIn={loggedIn} logout={logout} openImpact={openImpact} />
  } else if (page === 'compare') {
    content = <ComparePage navigate={navigate} loggedIn={loggedIn} logout={logout} openImpact={openImpact} />
  } else if (page === 'report') {
    content = <ReportPage navigate={navigate} loggedIn={loggedIn} logout={logout} openImpact={openImpact} />
  } else if (page === 'preview') {
    content = <PreviewPage navigate={navigate} loggedIn={loggedIn} logout={logout} />
  } else if (page === 'assistant') {
    content = (
      <AssistantPage
        navigate={navigate}
        loggedIn={loggedIn}
        logout={logout}
        messages={chatMessages}
        setMessages={setChatMessages}
        openDay={openDay}
        openImpact={openImpact}
      />
    )
  } else {
    content = <HomePage navigate={navigate} loggedIn={loggedIn} />
  }
  return (
    <div className="app-shell">
      {content}
      {assistantPoint && page === 'dashboard' && (
        <AnalysisAssistant
          point={assistantPoint}
          onClose={() => setAssistantPoint(null)}
          openImpact={openImpact}
          openDay={openDay}
        />
      )}
    </div>
  )
}

export default App