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
  DecisionLog,
  EventPreviewResponse,
  EventsResponse,
  ImpactCardResponse,
  PreviewStat,
  ReportResponse,
  StocksResponse,
  SuggestionsResponse,
  ThresholdsResponse,
} from './api/types.ts'
import { clearApiCache, useApi } from './api/useApi.ts'
import { AnomalyList } from './components/AnomalyList.tsx'
import { CountUp } from './components/CountUp.tsx'
import { AiPoints } from './components/AiPoints.tsx'
import { BrandLogo } from './components/BrandLogo.tsx'
import { IssuerLogo } from './components/IssuerLogo.tsx'
import { IssuerPicker } from './components/IssuerPicker.tsx'
import {
  DEFAULT_ISIN,
  IssuerContext,
  dashboardPath,
  filePrefix,
  isinFromUrl,
  issuerFrom,
  useIssuer,
  writeIsinToUrl,
} from './issuer/context.ts'
import { DayDetail } from './components/DayDetail.tsx'
import { DecisionBadge, HITL_LINE } from './components/DecisionControls.tsx'
import { AuctionTrendCard } from './components/AuctionTrendCard.tsx'
import { HelpTip } from './components/HelpTip.tsx'
import { PdfButton } from './components/PdfButton.tsx'
import { WhatToExpect } from './components/WhatToExpect.tsx'
import { tone, toneForUnit } from './utils/tone.ts'
import { announcementsLabel, groupByTradingDay } from './utils/events.ts'
import { ADTV_SESSIONS, BASELINE_SESSIONS, fixedRules, type DetectionRule } from './content/detectionRules.ts'
import { ThresholdsEditor } from './components/ThresholdsEditor.tsx'
import {
  DISCLAIMER,
  anomalyLabels,
  eventLabels,
  formatCompact,
  formatDate,
  formatEuro,
  formatNumber,
  formatDateRange,
  formatPercent,
  formatRatio,
  hasDemoData,
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
  | 'decisions'

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
  welcome?: boolean // message d'accueil (pas envoyé à l'API)
}

// Message d'accueil : texte construit à l'affichage avec le nom de l'émetteur choisi (welcomeText)
const WELCOME: ChatMessage = { role: 'assistant', welcome: true, text: '' }

function welcomeText(short: string) {
  return `Hello. Ask me about ${short}'s historical Xetra trading: a period, a specific day, an announcement or the peers. Answers are built from the analyses in this tool.`
}

// Questions de la démo pbb (affichées tout de suite) ; les autres émetteurs : GET /assistant/suggestions
const SUGGESTED_QUESTIONS = [
  'What happened in the latest week?',
  'Why was 29 Sep unusual?',
  "What to expect from today's Q3 release?",
  'How does pbb compare with its peers?',
]

const NO_ANNOUNCEMENTS = 'No announcements loaded for this issuer yet.'

const periods: Period[] = ['1W', '1M', '3M', 'YTD']
// Nombre de séances par période (le dashboard couvre 2026 jusqu'au 30.10)
const periodSessions: Record<Period, number> = { '1W': 5, '1M': 21, '3M': 63, YTD: Infinity }

// Impact card ouverte par défaut pour pbb : ad hoc du 13.02.2026 (scène b de la démo) ; autres émetteurs : aucune
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
  const { issuer } = useIssuer()
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
                ['Decision log', 'decisions'],
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

        <button className="brand" onClick={() => navigate('home')} aria-label="Issuer Intelligence Hub – home">
          <span className="brand-logos">
            <BrandLogo />
            <span className="brand-divider" aria-hidden="true" />
            <IssuerLogo issuer={issuer} />
          </span>
          <span className="brand-copy">
            <strong>ISSUER</strong>
            <small>INTELLIGENCE HUB</small>
          </span>
        </button>

        {loggedIn && <IssuerPicker />}

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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  return (
    <footer className="site-footer" id="contact">
      <div className="footer-top">
        <div className="footer-brand">
          <IssuerLogo issuer={issuer} className="footer-logo" />
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
          <strong>{issuer.name}</strong>
          <span>ISIN {isin}{issuer.index ? ` · ${issuer.index}` : ''}</span>
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const { data } = useApi<DashboardResponse>(dashboardPath(isin))
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
                {issuer.ticker} · ISSUER INTELLIGENCE HUB
              </p>
              <h1>
                Every market move
                <br />
                <span>has a story.</span>
              </h1>
              <p className="hero-description">
                A focused market intelligence workspace for {issuer.brandName}.
                Explore trading activity, understand event impact and prepare clear
                IR insights.
              </p>

              <div className="hero-company">
                <span className={`company-logo${issuer.isDefault ? '' : ' is-ticker'}`}>{issuer.isDefault ? 'pbb' : issuer.ticker}</span>
                <span>
                  <strong>{issuer.name}</strong>
                  <small>ISIN {isin}{issuer.index ? ` · ${issuer.index}` : ''}</small>
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
                    <small>{issuer.ticker} · XETRA</small>
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
                <p className="eyebrow">{issuer.ticker} · {isin}</p>
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
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
            <span className="brand-symbol">{issuer.isDefault ? 'pbb' : issuer.ticker}</span>
            <span>ISSUER INTELLIGENCE HUB</span>
          </div>
          <div className="login-copy">
            <p className="eyebrow">PRIVATE WORKSPACE</p>
            <h1>See the market with more context.</h1>
            <p>Sign in to access the {issuer.isDefault ? 'pbb' : 'issuer'} market intelligence dashboard.</p>
          </div>
          <span className="login-caption">{issuer.isDefault ? 'DEUTSCHE PFANDBRIEFBANK AG · ' : ''}{isin}</span>
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
              <strong className={tone(row.amount)}>
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const [from, setFrom] = useState(point.date)
  const [to, setTo] = useState(point.date)
  const [question, setQuestion] = useState('')
  const [request, setRequest] = useState<AnalysisRequest | null>(null)

  // Un jour -> day card (résumé IA du jour) ; une période -> report de la période (résumé IA de la période)
  const singleDay = request !== null && request.from === request.to
  const dayPath = singleDay ? `/days/${isin}/${request.from}/impact-card` : null
  const reportPath =
    request !== null && !singleDay ? `/stocks/${isin}/report?from=${request.from}&to=${request.to}` : null
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
            <span className="kicker">{issuer.ticker} · AI ANALYSIS</span>
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
                <AiPoints points={day.data.ai_points} summary={day.data.ai_summary} title={null} className="drawer-points" />
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
                <AiPoints points={period.data.ai_points} title={null} className="drawer-points" />
                {period.data.sections
                  .filter((section) => section.text)
                  .map((section) => (
                    <p key={section.title}>
                      <strong>{section.title}:</strong> {section.text}
                    </p>
                  ))}
                <PdfButton
                  className="text-button"
                  path={`/stocks/${isin}/report.pdf?from=${request.from}&to=${request.to}`}
                  filename={`${filePrefix(issuer)}-report-${request.from}-${request.to}.pdf`}
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

// Phrase clé (dashboard.key_finding) : calculée par règles côté API, jamais par le LLM ; chiffres sources sous la phrase
function KeyFinding({ finding }: { finding: { text: string; numbers: Record<string, number | string | null> } }) {
  const n = finding.numbers
  const num = (key: string) => (typeof n[key] === 'number' ? formatNumber(n[key] as number, 1) : '–')
  const { issuer } = useIssuer()
  // Spread en hausse : l'effet prix vient d'un cours plus bas (pbb) ; en baisse : d'un cours plus haut
  const widened = Number(n.own_last_bps) >= Number(n.own_first_bps)
  return (
    <section className="panel key-finding" aria-label="Key finding">
      <span className="kicker">
        KEY FINDING <HelpTip metric="spread" label="the cost to trade €25k" />
      </span>
      <p>{finding.text}</p>
      <small>
        {issuer.peerBasis === 'index' ? 'Index peers' : 'Peers'}' median {num('peers_median_first_bps')} →{' '}
        {num('peers_median_last_bps')} bps
        {n.index ? ` · ${n.index} median ${num('index_median_first_bps')} → ${num('index_median_last_bps')} bps` : ''}
        {typeof n.price_effect_pct === 'number'
          ? ` · ${num('price_effect_pct')}% of the change from the ${widened ? 'lower' : 'higher'} share price, ${num('liquidity_effect_pct')}% from liquidity`
          : ''}
      </small>
    </section>
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const [period, setPeriod] = useState<Period>('3M')
  const dashboard = useApi<DashboardResponse>(dashboardPath(isin))
  const events = useApi<EventsResponse>(`/stocks/${isin}/events`)
  const fullSeries = useMemo(
    () => (dashboard.data ? toStockPoints(dashboard.data.series) : []),
    [dashboard.data],
  )
  const points = useMemo(
    () => (period === 'YTD' ? fullSeries : fullSeries.slice(-periodSessions[period])),
    [period, fullSeries],
  )
  // Weekly snapshot : les 5 dernières séances de la série de l'API (fin = as_of), pas de calcul de calendrier
  const weekly = useMemo(() => {
    const last = dashboard.data?.series.slice(-5) ?? []
    if (last.length === 0 || !dashboard.data) return null
    return { from: last[0].date, to: dashboard.data.as_of, label: formatDateRange(last[0].date, dashboard.data.as_of) }
  }, [dashboard.data])
  const thresholdsInfo = useApi<ThresholdsResponse>(`/thresholds?isin=${isin}`)
  const recentDays = useMemo(() => groupByTradingDay(events.data?.events ?? []).slice(0, 5), [events.data])

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
              <p className="eyebrow light">{issuer.ticker} · {isin}</p>
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
              {weekly && (
                <PdfButton
                  className="outline-button weekly-snapshot"
                  path={`/stocks/${isin}/report.pdf?from=${weekly.from}&to=${weekly.to}`}
                  filename={`${filePrefix(issuer)}-weekly-ir-snapshot-${weekly.from}-${weekly.to}.pdf`}
                >
                  Weekly IR snapshot ({weekly.label}) <span>↓</span>
                </PdfButton>
              )}
            </div>
          </div>

          {dashboard.data?.key_finding && <KeyFinding finding={dashboard.data.key_finding} />}

          <div className="dashboard-toolbar">
            <div className="stock-identity">
              <IssuerLogo issuer={issuer} className="stock-logo" />
              <div>
                <strong>{dashboard.data?.stock.name ?? issuer.name}</strong>
                <small>Xetra · {isin} · {dashboard.data?.stock.index ?? issuer.index}</small>
                {dashboard.data && (
                  <small className="data-as-of">Data as of {formatDate(dashboard.data.as_of)}</small>
                )}
                {dashboard.data?.peer_basis === 'index' && (
                  <small
                    className="peer-basis-badge"
                    title={`Peers are the other ${dashboard.data.stock.index} members on each day (${dashboard.data.n_peers ?? '–'} at the end of the period).`}
                  >
                    Peers: same index
                  </small>
                )}
                {thresholdsInfo.data?.custom && (
                  <button className="custom-badge" onClick={() => navigate('alerts')} title="Alerts use thresholds set by the IR team">
                    Custom thresholds ↗
                  </button>
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

          <WhatToExpect isin={isin} onOpenFull={() => navigate('preview')} />

          {issuer.coverage && !issuer.coverage.dashboard ? (
            <div className="notice-box">
              Not enough Xetra data for {issuer.name}: {issuer.coverage.sessions} session
              {issuer.coverage.sessions === 1 ? '' : 's'} with a measured spread, at least 21 are needed (20-day
              baseline + the measured day). Choose another issuer in the header.
            </div>
          ) : (
            <LoadState loading={dashboard.loading} error={dashboard.error} />
          )}

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
                      <span className={`price-change ${tone(periodChange)}`}>
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
                  <span>VWAP <HelpTip metric="vwap" label="VWAP" /></span>
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

          {dashboard.data?.auction_trend && (
            <Reveal className="auction-trend-row">
              <AuctionTrendCard trend={dashboard.data.auction_trend} openDay={openDay} />
            </Reveal>
          )}

          <div className="dashboard-lower">
            <Reveal>
              <section className="panel lower-panel">
                <div className="panel-title">
                  <div>
                    <span className="kicker">TRADING SIGNALS · SEVERITY, THEN MOST RECENT</span>
                    <h2>Top 5 – latest period</h2>
                  </div>
                  <button className="text-button" onClick={() => navigate('alerts')}>
                    Configure alerts →
                  </button>
                </div>
                <p className="hitl-line">{HITL_LINE}</p>
                {dashboard.data && (
                  <AnomalyList anomalies={dashboard.data.anomalies} onOpen={openImpact} isin={isin} />
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
                {events.data && recentDays.length === 0 && <p className="empty-state">{NO_ANNOUNCEMENTS}</p>}
                {recentDays.map((day) => (
                  <button
                    className="recent-event"
                    key={day.trading_day}
                    onClick={() => openImpact(`/events/${day.primary.event_id}/impact-card`)}
                  >
                    <span className="event-date-block">
                      <strong>{new Date(`${day.trading_day}T12:00:00`).getDate()}</strong>
                      <small>
                        {new Date(`${day.trading_day}T12:00:00`).toLocaleDateString('en-GB', {
                          month: 'short',
                        })}
                      </small>
                    </span>
                    <span className="recent-event-copy">
                      <strong>{day.primary.title}</strong>
                      <small>
                        {day.events.length > 1
                          ? `${announcementsLabel(day.events.length)} · ${[...new Set(day.events.map((e) => eventLabels[e.type] ?? e.type))].join(', ')}`
                          : eventLabels[day.primary.type] ?? day.primary.type}
                      </small>
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const { data, error, loading } = useApi<EventsResponse>(`/stocks/${isin}/events`)
  const events = data?.events ?? []
  const days = useMemo(() => groupByTradingDay(data?.events ?? []), [data])

  return (
    <>
      <Header page="events" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container narrow">
          <PageHeading
            eyebrow={`${issuer.ticker} · COMPANY DISCLOSURES`}
            title="Events timeline"
            description="Company announcements and related trading metrics."
          />

          <LoadState loading={loading} error={error} />
          {data && (
            <div className="notice-box">
              <strong className="data-as-of">Data as of {formatDate(data.as_of)} · </strong>
              {events.length > 0 ? (
                <>
                  {events.length} announcements from public sources ({issuer.isDefault ? 'pbb IR' : 'company IR'}, EQS).
                  Values that are not available appear as “–”.
                </>
              ) : (
                <>{NO_ANNOUNCEMENTS}</>
              )}
            </div>
          )}

          <div className="timeline">
            {days.map((day) => (
              <article className="timeline-item" key={day.trading_day}>
                <div className="timeline-date">
                  <strong>{formatDate(day.trading_day)}</strong>
                  <span>
                    {day.events.length > 1
                      ? `${day.events.length} announcements`
                      : day.primary.time || 'Time unavailable'}
                  </span>
                </div>
                <div className="timeline-card">
                  <div className="timeline-card-top">
                    <span>
                      {day.events.length > 1
                        ? announcementsLabel(day.events.length)
                        : eventLabels[day.primary.type] ?? day.primary.type}
                    </span>
                    {day.events.length === 1 && day.primary.source_url && (
                      <a href={day.primary.source_url} target="_blank" rel="noreferrer">
                        <small>SOURCE ↗</small>
                      </a>
                    )}
                  </div>
                  {day.events.length === 1 ? (
                    <h2>{day.primary.title}</h2>
                  ) : (
                    <ul className="day-announcements">
                      {day.events.map((event) => (
                        <li key={event.event_id}>
                          <span className="day-announcement-meta">
                            {event.time || '–'} · {eventLabels[event.type] ?? event.type}
                          </span>
                          <strong>{event.title}</strong>
                          {event.source_url && (
                            <a href={event.source_url} target="_blank" rel="noreferrer">Source ↗</a>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  <p>
                    Trading day: {formatDate(day.trading_day)}
                    {day.events.length > 1 ? ' · one set of trading figures for the session' : ''}
                  </p>
                  <div className="event-metrics">
                    <Metric label="Volume ratio" value={formatRatio(day.headline_metric.volume_ratio)} />
                    <Metric label="Price change" value={formatPercent(day.headline_metric.price_change_pct)} tone={tone(day.headline_metric.price_change_pct)} />
                    <Metric label="Spread change" value={formatPercent(day.headline_metric.spread_change_pct)} tone={tone(day.headline_metric.spread_change_pct, 'cost')} />
                  </div>
                  <button className="text-button" onClick={() => openImpact(`/events/${day.primary.event_id}/impact-card`)}>
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const { data: card, error, loading } = useApi<ImpactCardResponse>(impactPath || null)
  // Badges d'anomalie et alertes du jour : liste `anomalies` du dashboard (l'impact card ne la contient pas)
  const dashboard = useApi<DashboardResponse>(dashboardPath(isin))
  const day = card?.window.find((w) => w.offset === 0)?.date ?? card?.event?.trading_day
  const dayAnomalies = useMemo(
    () => (dashboard.data?.anomalies ?? []).filter((anomaly) => anomaly.date === day),
    [dashboard.data, day],
  )
  // Toutes les annonces du même jour de trading (une seule carte : les chiffres sont ceux de la séance)
  const events = useApi<EventsResponse>(`/stocks/${isin}/events`)
  const sameDayEvents = useMemo(
    () => (events.data?.events ?? []).filter((event) => event.trading_day === day),
    [events.data, day],
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
          {!impactPath && (
            <div className="notice-box empty-state">
              Choose a day on the dashboard chart, in the trading signals or in the auction share trend to open its analysis.
            </div>
          )}
          {card && <DayDetail card={card} dayAnomalies={dayAnomalies} sameDayEvents={sameDayEvents} />}
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const [activeIndicator, setActiveIndicator] = useState<(typeof indicators)[number] | null>(null)
  const { data } = useApi<DashboardResponse>(dashboardPath(isin))
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
            eyebrow={`${issuer.ticker} · SELECTED DATA POINT`}
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

// Seuils de détection : uniquement les règles appliquées par app/analytics (src/content/detectionRules.ts),
// en lecture seule. Aucun réglage de trader ni de données absentes (voting rights, directors' dealings).
function RuleTable({ title, kicker, rules }: { title: string; kicker: string; rules: DetectionRule[] }) {
  return (
    <section className="panel threshold-panel">
      <div className="panel-title">
        <div>
          <span className="kicker">{kicker}</span>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="rule-list">
        {rules.map((rule) => (
          <div className="rule-row" key={rule.type}>
            <strong>{rule.name}</strong>
            <span>{rule.rule}</span>
            <small>
              High severity: {rule.high} · <code>{rule.source}</code>
            </small>
          </div>
        ))}
      </div>
    </section>
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  // Révision : après un Save / Reset, on relit le dashboard pour que la liste des alertes suive les nouveaux seuils
  const [revision, setRevision] = useState(0)
  const { data: dashboard } = useApi<DashboardResponse>(revision ? `${dashboardPath(isin)}?rev=${revision}` : dashboardPath(isin))

  return (
    <>
      <Header page="dashboard" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container">
          <PageHeading
            eyebrow="DETECTION RULES"
            title="Thresholds & alerts"
            description="Alerts detected in the Xetra data, and the thresholds used to detect them. The IR team can adjust them."
          />

          <section className="panel lower-panel">
            <div className="panel-title">
              <div>
                <span className="kicker">DETECTED IN XETRA DATA · {dashboard?.anomalies.length ?? '–'} ALERTS IN 2026</span>
                <h2>Top 5 – latest period</h2>
              </div>
            </div>
            <p className="hitl-line">{HITL_LINE}</p>
            {dashboard && <AnomalyList anomalies={dashboard.anomalies} onOpen={openImpact} isin={isin} />}
          </section>

          <div className="notice-box rules-note">
            Baseline: the previous {BASELINE_SESSIONS} trading days, excluding the measured day. ADTV: average daily
            turnover of the previous {ADTV_SESSIONS} trading days. Alerts describe executions, not who traded. Severity
            is high at 2× the threshold (anomalies: z-score one point above the threshold).
          </div>

          <ThresholdsEditor isin={isin} onSaved={() => setRevision((value) => value + 1)} />

          <div className="rules-grid single">
            <RuleTable kicker="FIXED RULES" title="Not adjustable in this tool" rules={fixedRules} />
          </div>
        </div>
      </main>
      <Footer />
    </>
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
  const [allColumns, setAllColumns] = useState(false) // mobile (< 640 px) : colonnes essentielles par défaut
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
            <div className="table-scroll compare-scroll">
              <table className={`compare-table${allColumns ? ' all-columns' : ''}`}>
                <thead>
                  <tr>
                    <th className="sticky-col">Company</th>
                    <th className="col-extra">Date</th>
                    <th>Spread change</th>
                    <th>Volume ratio</th>
                    <th>Price change</th>
                    <th className="col-extra">Auction share</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.events ?? []).map((event) => (
                    <tr key={event.event_id} onClick={() => openImpact(`/events/${event.event_id}/impact-card`)} style={{ cursor: 'pointer' }}>
                      <td className="sticky-col">
                        {event.name}
                        <small className="compare-date-inline">{formatDate(event.date)}</small>
                      </td>
                      <td className="col-extra">{formatDate(event.date)}</td>
                      <td className={tone(event.spread_change_pct, 'cost')}>
                        {formatPercent(event.spread_change_pct)}
                      </td>
                      <td>{formatRatio(event.volume_ratio)}</td>
                      <td className={tone(event.price_change_pct)}>
                        {formatPercent(event.price_change_pct)}
                      </td>
                      <td className="col-extra">
                        {event.auction_share_change_pts === null
                          ? '–'
                          : `${event.auction_share_change_pts > 0 ? '+' : ''}${formatNumber(event.auction_share_change_pts * 100, 1)} pts`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              className="text-button more-columns"
              onClick={() => setAllColumns((value) => !value)}
              aria-expanded={allColumns}
            >
              {allColumns ? 'Fewer columns' : 'More columns (date, auction share)'}
            </button>
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const { data: report, error, loading } = useApi<ReportResponse>(`/stocks/${isin}/report`)
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
    link.download = `${filePrefix(issuer)}-ir-snapshot-events.csv`
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
            description={`Concise historical summary for ${issuer.name}.`}
          />

          <LoadState loading={loading} error={error} />

          {report && (
            <section className="panel report-panel">
              <div className="report-cover">
                <span className={`company-logo${issuer.isDefault ? '' : ' is-ticker'}`}>{issuer.isDefault ? 'pbb' : issuer.ticker}</span>
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
                <AiPoints
                  points={report.ai_points}
                  title={null}
                  className="report-points"
                  review={{ isin, id: report.ai_summary_id, decision: report.ai_summary_decision }}
                />
              </div>
              {report.sections.map((section) => (
                <div className="report-section" key={section.title}>
                  <span className="kicker">{section.title.toUpperCase()}</span>
                  {(section.kpis ?? []).map((kpi) => (
                    <div className="report-event" key={kpi.label}>
                      <span>{kpi.label}</span>
                      <strong>{formatKpi(kpi.value, kpi.unit)}</strong>
                      <span className={tone(kpi.change_pct, toneForUnit(kpi.unit))}>
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
                      <span className={tone(item.spread_change_pct, 'cost')}>Spread {formatPercent(item.spread_change_pct)}</span>
                    </button>
                  ))}
                </div>
              ))}
              <div className="report-disclaimer">{report.disclaimer}</div>
              <div className="report-actions">
                <PdfButton path={report.export.pdf_url} filename={`${filePrefix(issuer)}-ir-snapshot.pdf`}>
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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const [eventType, setEventType] = useState('quarterly_results')
  const { data: preview, error, loading } = useApi<EventPreviewResponse>(
    `/stocks/${isin}/event-preview?type=${eventType}`,
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
          {preview?.events_note && <div className="notice-box empty-state">{NO_ANNOUNCEMENTS}</div>}

          {preview && history && !preview.events_note && (
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

              <AiPoints
                points={preview.ai_points}
                summary={preview.ai_summary}
                review={{ isin, id: preview.ai_summary_id, decision: preview.ai_summary_decision }}
              />

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
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  // pbb : les questions de la démo ; autres émetteurs : construites par l'API à partir de leurs données
  const suggestions = useApi<SuggestionsResponse>(issuer.isDefault ? null : `/assistant/suggestions?isin=${isin}`)
  const suggestedQuestions = issuer.isDefault ? SUGGESTED_QUESTIONS : suggestions.data?.questions ?? []

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [messages, pending])

  async function ask(question: string) {
    const text = question.trim()
    if (!text || pending) return
    // Historique envoyé : les échanges réels (sans le message d'accueil) ; l'API n'en garde que les 6 derniers
    const history = [...messages.filter((m) => !m.welcome), { role: 'user' as const, text }]
    setMessages((current) => [...current, { role: 'user', text }])
    setDraft('')
    setPending(true)
    try {
      const reply = await apiPost<ChatResponse>('/assistant/chat', {
        isin,
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
    if (link.type === 'question') void ask(link.ref) // question suggérée (réponse hors périmètre)
    else if (link.type === 'day') openDay(link.ref)
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
              <span className="kicker">{issuer.ticker} · IR</span>
              <h1>AI Assistant</h1>
              <p>Ask about trading activity, events, peers or a specific day.</p>
            </div>
          </div>
          <div className="chat-messages" aria-live="polite">
            {messages.map((message, index) => (
              <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                {message.welcome ? welcomeText(issuer.short) : message.text}
                {message.links && message.links.length > 0 && (
                  <div className="chat-links">
                    {message.links.map((link) => (
                      <button
                        key={`${link.type}-${link.ref}`}
                        className={`chat-link${link.type === 'question' ? ' suggestion' : ''}`}
                        onClick={() => openLink(link)}
                        disabled={link.type === 'question' && pending}
                      >
                        {link.type === 'question' ? `Ask: ${link.label}` : `${link.label} ↗`}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {onlyWelcome && (
              <div className="chat-suggestions">
                {suggestedQuestions.map((question) => (
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

// Libellé lisible d'un élément du journal (anomalie / alerte, résumé IA, seuil)
function describeItem(entry: DecisionLog['decisions'][number], isin: string) {
  if (entry.item_type === 'threshold') return entry.note ?? entry.item_id
  if (entry.item_type === 'ai_summary') {
    const [kind, ...rest] = entry.item_id.split(':')
    const label = kind === 'impact' ? 'impact card' : kind === 'preview' ? 'What to expect' : kind === 'report' ? 'IR snapshot' : kind
    return `AI summary · ${label} ${rest.filter((part) => part !== isin).join(' ')}`.trim()
  }
  const [date, type] = entry.item_id.split('|')
  return `${anomalyLabels[type] ?? type} · ${date ? formatDate(date) : ''}`
}

function DecisionLogPage({
  navigate,
  loggedIn,
  logout,
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
}) {
  const { issuer } = useIssuer()
  const isin = issuer.isin
  const { data, error, loading } = useApi<DecisionLog>(`/decisions?isin=${isin}`)
  const entries = data?.decisions ?? []

  return (
    <>
      <Header page="decisions" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container">
          <PageHeading
            eyebrow="HUMAN IN THE LOOP"
            title="Decision log"
            description={HITL_LINE}
          />
          <LoadState loading={loading} error={error} />
          <section className="panel compare-panel">
            <div className="panel-title">
              <div>
                <span className="kicker">{entries.length} DECISIONS · DATA/DECISIONS.DB</span>
                <h2>Every review and threshold change</h2>
              </div>
            </div>
            {data && entries.length === 0 ? (
              <p className="muted">No decision yet. Approve or dismiss an alert, an anomaly or an AI summary to start the log.</p>
            ) : (
              <div className="table-scroll">
                <table className="decision-table">
                  <thead>
                    <tr>
                      <th>When (Frankfurt)</th>
                      <th>Item</th>
                      <th>Decision</th>
                      <th>Note / change</th>
                      <th>By</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((entry) => (
                      <tr key={entry.id}>
                        <td>{entry.decided_at.slice(0, 16).replace('T', ' ')}</td>
                        <td>{describeItem(entry, isin)}</td>
                        <td>
                          {entry.decision === 'threshold_changed' ? (
                            <span className="decision-badge threshold">Threshold changed</span>
                          ) : (
                            <DecisionBadge
                              decision={{
                                id: entry.id,
                                decision: entry.decision,
                                note: entry.note,
                                decided_at: entry.decided_at,
                                decided_by: entry.decided_by,
                              }}
                            />
                          )}
                        </td>
                        <td>
                          {entry.decision === 'threshold_changed'
                            ? `${entry.old_value} → ${entry.new_value}`
                            : entry.note ?? '–'}
                        </td>
                        <td>{entry.decided_by}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </main>
      <Footer />
    </>
  )
}

function App() {
  // Source de vérité : l'API (GET /auth/me au démarrage, puis tout 401 renvoie au login)
  const [auth, setAuth] = useState<AuthState>('checking')
  const loggedIn = auth === 'in'
  const [page, setPage] = useState<Page>('home')
  const [selectedPoint, setSelectedPoint] = useState<StockPoint | null>(null)
  const [assistantPoint, setAssistantPoint] = useState<StockPoint | null>(null)
  // Émetteur : ?isin= dans l'URL (lien partageable), pbb par défaut
  const [urlIsin, setIsinState] = useState(isinFromUrl)
  const stocksApi = useApi<StocksResponse>(loggedIn ? '/stocks' : null)
  const stocks = useMemo(() => stocksApi.data?.stocks ?? [], [stocksApi.data])
  // ISIN de l'URL absent de l'univers (faute de frappe, ancien lien) : on affiche pbb
  const isin = stocks.length > 0 && !stocks.some((stock) => stock.isin === urlIsin) ? DEFAULT_ISIN : urlIsin
  const issuer = useMemo(() => issuerFrom(isin, stocks), [isin, stocks])
  const [impactPath, setImpactPath] = useState(urlIsin === DEFAULT_ISIN ? DEFAULT_IMPACT : '')
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([WELCOME]) // historique de la session

  const setIsin = useCallback((next: string) => {
    setIsinState(next)
    writeIsinToUrl(next)
    // Rien de l'émetteur précédent : point sélectionné, impact card, historique du chat
    setSelectedPoint(null)
    setAssistantPoint(null)
    setImpactPath(next === DEFAULT_ISIN ? DEFAULT_IMPACT : '')
    setChatMessages([WELCOME])
  }, [])

  // L'URL suit l'émetteur réellement affiché (ISIN inconnu corrigé en pbb)
  useEffect(() => {
    if (isin !== urlIsin) writeIsinToUrl(isin)
  }, [isin, urlIsin])

  const issuerState = useMemo(() => ({ issuer, stocks, setIsin }), [issuer, stocks, setIsin])

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

  const eventsList = useApi<EventsResponse>(loggedIn ? `/stocks/${isin}/events` : null)
  const openDay = useCallback(
    (date: string) => {
      const event = eventsList.data?.events.find((item) => item.trading_day === date)
      openImpact(event ? `/events/${event.event_id}/impact-card` : `/days/${isin}/${date}/impact-card`)
    },
    [eventsList.data, openImpact, isin],
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
  } else if (page === 'decisions') {
    content = <DecisionLogPage navigate={navigate} loggedIn={loggedIn} logout={logout} />
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
    <IssuerContext.Provider value={issuerState}>
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
    </IssuerContext.Provider>
  )
}

export default App