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
  type UTCTimestamp,
} from 'lightweight-charts'

import { apiGet } from './api/clients.ts';

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

type Period = '1D' | '1W' | '1M' | '3M' | '1Y'

type StockPoint = {
  time: UTCTimestamp
  date: string
  close: number
  ema20: number
  ema50: number
  ema200: number
  volume: number
  volumeRatio: number
  turnover: number
  vwap: number
  spreadBps: number
  auctionShare: number | null
}

type MarketEvent = {
  event_id: string
  date: string
  time: string
  trading_day: string
  type: string
  title: string
  headline_metric: {
    volume_ratio: number | null
    price_change_pct: number | null
    spread_change_pct: number | null
  }
}

type ChatMessage = {
  role: 'assistant' | 'user'
  text: string
}

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
const DEMO_EMAIL = 'abc@gmail.com'
const DEMO_PASSWORD = 'azerty123'

const periods: Period[] = ['1D', '1W', '1M', '3M', '1Y']

const eventLabels: Record<string, string> = {
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

const eventData: MarketEvent[] = [
  {
    event_id: 'demo-evt-001',
    date: '2026-10-21',
    time: '08:00',
    trading_day: '2026-10-21',
    type: 'quarterly_results',
    title: 'Quarterly results — fictional demo event',
    headline_metric: {
      volume_ratio: 2.1,
      price_change_pct: 1.8,
      spread_change_pct: -4.2,
    },
  },
  {
    event_id: 'demo-evt-002',
    date: '2026-10-08',
    time: '12:26',
    trading_day: '2026-10-08',
    type: 'ad_hoc',
    title: 'Ad hoc announcement — fictional demo event',
    headline_metric: {
      volume_ratio: 1.7,
      price_change_pct: -3.4,
      spread_change_pct: 8.6,
    },
  },
  {
    event_id: 'demo-evt-003',
    date: '2026-09-17',
    time: '',
    trading_day: '2026-09-18',
    type: 'voting_rights',
    title: 'Voting rights notification — fictional demo event',
    headline_metric: {
      volume_ratio: null,
      price_change_pct: null,
      spread_change_pct: null,
    },
  },
  {
    event_id: 'demo-evt-004',
    date: '2026-08-28',
    time: '09:15',
    trading_day: '2026-08-28',
    type: 'directors_dealings',
    title: "Directors' dealings — fictional demo event",
    headline_metric: {
      volume_ratio: 1.2,
      price_change_pct: 0.4,
      spread_change_pct: -1.1,
    },
  },
]

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
    description: 'EMA 20, EMA 50 and EMA 200 trend references.',
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

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'

  return value.toLocaleString('en-GB', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  return `${value > 0 ? '+' : ''}${formatNumber(value, 1)}%`
}

function formatEuro(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'

  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatCompact(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  return new Intl.NumberFormat('en-GB', { notation: 'compact' }).format(value)
}

function formatDate(value: string) {
  return new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function trendClass(value: number | null | undefined) {
  if (value === null || value === undefined || Math.abs(value) < 0.05) {
    return 'neutral'
  }
  return value > 0 ? 'positive' : 'negative'
}

function makeMockSeries(period: Period): StockPoint[] {
  const end = new Date('2026-10-30T16:30:00+01:00')
  const count =
    period === '1D'
      ? 24
      : period === '1W'
        ? 7
        : period === '1M'
          ? 30
          : period === '3M'
            ? 90
            : 210

  return Array.from({ length: count }, (_, index) => {
    const date = new Date(end)

    if (period === '1D') {
      date.setHours(index, 0, 0, 0)
    } else {
      date.setDate(end.getDate() - (count - index - 1))
      if (period === '1Y') date.setDate(date.getDate() - 120)
      if (period === '3M') date.setDate(date.getDate() - 30)
    }

    const drift = index * (period === '1D' ? 0.018 : 0.006)
    const wave =
      Math.sin(index * 1.27) * (period === '1D' ? 0.12 : 0.36) +
      Math.cos(index * 0.39) * (period === '1D' ? 0.05 : 0.19)
    const close = 5.82 + drift + wave
    const volume = Math.round(24000 + Math.abs(Math.sin(index * 1.7)) * 92000)

    return {
      time: Math.floor(date.getTime() / 1000) as UTCTimestamp,
      date: date.toISOString(),
      close: Number(close.toFixed(3)),
      ema20: Number((close - Math.sin(index * 0.2) * 0.045).toFixed(3)),
      ema50: Number((close - Math.cos(index * 0.13) * 0.065).toFixed(3)),
      ema200: Number((close - Math.cos(index * 0.08) * 0.09).toFixed(3)),
      volume,
      volumeRatio: Number((0.9 + Math.abs(Math.sin(index * 0.8)) * 1.2).toFixed(2)),
      turnover: Number((volume * close).toFixed(2)),
      vwap: Number((close + Math.sin(index * 0.56) * 0.018).toFixed(3)),
      spreadBps: Number((38 + Math.sin(index * 0.54) * 8).toFixed(1)),
      auctionShare:
        index % 13 === 0
          ? null
          : Number((0.12 + Math.abs(Math.sin(index)) * 0.3).toFixed(2)),
    }
  })
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
            <p>Market insight for investor relations teams.</p>
          </div>
        </div>
        <div className="footer-contact">
          <span className="footer-label">DEUTSCHE BÖRSE · INVESTOR RELATIONS</span>
          <a href="mailto:ir@deutsche-boerse.com">ir@deutsche-boerse.com</a>
          <a
            href="https://www.deutsche-boerse.com/dbg-en/investor-relations/contact"
            target="_blank"
            rel="noreferrer"
          >
            Deutsche Börse contact page ↗
          </a>
        </div>
        <div className="footer-company">
          <span className="footer-label">COMPANY PROFILE</span>
          <strong>{COMPANY}</strong>
          <span>ISIN {ISIN} · SDAX</span>
        </div>
      </div>
      <div className="footer-bottom">
        <span>Frontend prototype · All market figures shown are fictional.</span>
        <span>Historical market analysis only. Not investment advice.</span>
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
                investor relations insights.
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
              <p className="hero-footnote">Private workspace · Demo prototype</p>
            </div>

            <div className="hero-art">
              <div className="hero-orbit orbit-one" />
              <div className="hero-orbit orbit-two" />
              <div className="hero-card">
                <div className="hero-card-top">
                  <span>ISSUER OVERVIEW</span>
                  <span className="demo-label">DEMO</span>
                </div>
                <div className="hero-stock">
                  <div>
                    <small>PBB · XETRA</small>
                    <strong>€5.82</strong>
                  </div>
                  <span>↗ +1.8%</span>
                </div>
                <div className="mini-chart">
                  {[35, 48, 42, 61, 54, 73, 65, 88, 76, 94].map((height, index) => (
                    <i key={index} style={{ height: `${height}%` }} />
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
                  <p className="eyebrow light">BUILT FOR INVESTOR RELATIONS</p>
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

function LoginPage({
  onLogin,
  navigate,
}: {
  onLogin: (email: string, password: string) => boolean
  navigate: (page: Page) => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const accepted = onLogin(email, password)
    setError(accepted ? '' : 'The email or password is incorrect.')
  }

  return (
    <>
      <Header page="login" loggedIn={false} navigate={navigate} logout={() => {}} />
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
            <p className="eyebrow light">WELCOME BACK</p>
            <h2>Log in</h2>
            <p className="login-description">
              Enter your details to continue to your workspace.
            </p>

            <label htmlFor="login-email">Email address</label>
            <input
              id="login-email"
              type="email"
              autoComplete="username"
              placeholder="name@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />

            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />

            {error && <p className="login-error">{error}</p>}

            <button className="login-submit" type="submit">
              Continue <span>→</span>
            </button>

            <div className="prototype-credentials">
              <strong>Prototype credentials</strong>
              <span>{DEMO_EMAIL}</span>
              <span>{DEMO_PASSWORD}</span>
            </div>

            <p className="login-security-note">
              Prototype only. Credentials are stored in frontend code and must not be
              used for a real account.
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
        timeVisible: true,
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
      topColor: 'rgba(0, 0, 153, 0.20)',
      bottomColor: 'rgba(0, 0, 153, 0.015)',
      lineWidth: 2,
      priceLineVisible: true,
      lastValueVisible: true,
    })

    const ema20 = chart.addSeries(LineSeries, {
      color: '#8cbe00',
      lineWidth: 1,
      lineStyle: 2,
      lastValueVisible: false,
      priceLineVisible: false,
    })

    const ema50 = chart.addSeries(LineSeries, {
      color: '#8dbcf0',
      lineWidth: 1,
      lineStyle: 2,
      lastValueVisible: false,
      priceLineVisible: false,
    })

    price.setData(points.map((point) => ({ time: point.time, value: point.close })))
    ema20.setData(points.map((point) => ({ time: point.time, value: point.ema20 })))
    ema50.setData(points.map((point) => ({ time: point.time, value: point.ema50 })))
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
        date: new Date(Number(point.time) * 1000).toLocaleString('en-GB', {
          dateStyle: 'medium',
          timeStyle: 'short',
        }),
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
        Historical trading data · Demo values · Drag to pan and scroll to zoom
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
                {row.amount > 0 ? '+' : ''}
                {formatEuro(row.amount)}
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

function AnalysisAssistant({
  point,
  onClose,
}: {
  point: StockPoint
  onClose: () => void
}) {
  const date = point.date.slice(0, 10)
  const [from, setFrom] = useState(date)
  const [to, setTo] = useState(date)
  const [question, setQuestion] = useState('')
  const [sent, setSent] = useState(false)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSent(true)
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
          <small>{new Date(point.time * 1000).toLocaleString('en-GB')}</small>
        </div>

        <form className="analysis-form" onSubmit={submit}>
          <div className="date-range">
            <label>
              From
              <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
            </label>
            <label>
              To
              <input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
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

          <button className="primary-button full-width" type="submit">
            Prepare analysis request <span>→</span>
          </button>
        </form>

        {sent && (
          <div className="request-ready">
            <strong>Request prepared</strong>
            <p>
              The selected point and {from}–{to} interval are ready to send. The backend
              connection will be added later.
            </p>
          </div>
        )}

        <p className="small-note">
          Demo only · No analysis is sent to an AI service yet.
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
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
  onPointSelect: (point: StockPoint) => void
  selectedPoint: StockPoint | null
  setSelectedPoint: (point: StockPoint | null) => void
}) {
  const [period, setPeriod] = useState<Period>('1M')
  const fullSeries = useMemo(() => makeMockSeries('1Y'), [])
  const points = useMemo(() => {
    if (period === '1Y') return fullSeries
    if (period === '3M') return fullSeries.slice(-90)
    if (period === '1M') return fullSeries.slice(-30)
    if (period === '1W') return fullSeries.slice(-7)
    return makeMockSeries('1D')
  }, [period, fullSeries])

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
      <main className="workspace-page">
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
                <strong>{COMPANY}</strong>
                <small>Xetra · {ISIN} · SDAX</small>
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

          <div className="dashboard-grid">
            <Reveal>
              <section className="panel chart-panel">
                <div className="chart-heading">
                  <div>
                    <span className="kicker">SHARE PRICE · EUR · DEMO DATA</span>
                    <div className="price-line">
                      <strong>{latest ? formatEuro(latest.close) : '–'}</strong>
                      <span className={`price-change ${periodChange >= 0 ? 'positive' : 'negative'}`}>
                        {periodChange >= 0 ? '↑' : '↓'} {formatPercent(periodChange)}
                      </span>
                    </div>
                  </div>
                  <div className="chart-period-label">
                    <span>Range: {period}</span>
                    <span>Currency: EUR</span>
                  </div>
                </div>

                <MarketChart points={points} onSelect={selectPoint} />

                {selectedPoint && (
                  <div className="point-actions">
                    <div>
                      <span>Selected point</span>
                      <strong>
                        {formatEuro(selectedPoint.close)} ·{' '}
                        {new Date(selectedPoint.time * 1000).toLocaleDateString('en-GB')}
                      </strong>
                    </div>
                    <button className="outline-button" onClick={() => navigate('indicators')}>
                      View details <span>↗</span>
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
                  <span>Trading volume</span>
                  <strong>{formatCompact(latest?.volume)}</strong>
                </div>
                <div className="mini-stat">
                  <span>Turnover</span>
                  <strong>{formatEuro(latest?.turnover)}</strong>
                </div>
                <div className="mini-stat">
                  <span>XLM spread</span>
                  <strong>{latest ? `${formatNumber(latest.spreadBps, 1)} bps` : '–'}</strong>
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
                    <span className="kicker">TRADING SIGNALS</span>
                    <h2>Notable days</h2>
                  </div>
                  <button className="text-button" onClick={() => navigate('alerts')}>
                    Configure alerts →
                  </button>
                </div>
                <button className="signal-row" onClick={() => navigate('impact')}>
                  <span className="signal-dot high" />
                  <span className="signal-date">08 Oct 2026</span>
                  <span className="signal-copy">
                    <strong>Spread widening</strong>
                    <small>Unusual spread compared with the recent baseline.</small>
                  </span>
                  <span className="signal-value">3.1×</span>
                  <span>↗</span>
                </button>
                <button className="signal-row" onClick={() => navigate('impact')}>
                  <span className="signal-dot medium" />
                  <span className="signal-date">29 Sep 2026</span>
                  <span className="signal-copy">
                    <strong>Volume spike</strong>
                    <small>Volume exceeded the 20-day average.</small>
                  </span>
                  <span className="signal-value">2.4×</span>
                  <span>↗</span>
                </button>
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
                {eventData.slice(0, 2).map((event) => (
                  <button
                    className="recent-event"
                    key={event.event_id}
                    onClick={() => navigate('impact')}
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
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
}) {
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

          <div className="notice-box">
            These example events are fictional. API fields that are null appear as “–”.
          </div>

          <div className="timeline">
            {eventData.map((event) => (
              <article className="timeline-item" key={event.event_id}>
                <div className="timeline-date">
                  <strong>{formatDate(event.date)}</strong>
                  <span>{event.time || 'Time unavailable'}</span>
                </div>
                <div className="timeline-card">
                  <div className="timeline-card-top">
                    <span>{eventLabels[event.type] ?? event.type}</span>
                    <small>DEMO EVENT</small>
                  </div>
                  <h2>{event.title}</h2>
                  <p>Trading day: {formatDate(event.trading_day)}</p>
                  <div className="event-metrics">
                    <Metric label="Volume ratio" value={event.headline_metric.volume_ratio == null ? '–' : `${formatNumber(event.headline_metric.volume_ratio, 1)}×`} />
                    <Metric label="Price change" value={formatPercent(event.headline_metric.price_change_pct)} tone={trendClass(event.headline_metric.price_change_pct)} />
                    <Metric label="Spread change" value={formatPercent(event.headline_metric.spread_change_pct)} tone={trendClass(event.headline_metric.spread_change_pct)} />
                  </div>
                  <button className="text-button" onClick={() => navigate('impact')}>
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
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
}) {
  const event = eventData[1]

  return (
    <>
      <Header page="events" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container narrow">
          <PageHeading
            eyebrow="ONE-CLICK EVENT ANALYSIS"
            title="Impact card"
            description="Market reaction around a selected company announcement."
          />

          <section className="panel impact-card">
            <div className="timeline-card-top">
              <span>{eventLabels[event.type]}</span>
              <small>FICTIONAL EVENT</small>
            </div>
            <h2>{event.title}</h2>
            <p className="muted">{formatDate(event.date)} · {event.time}</p>

            <div className="impact-metrics">
              <Metric label="Price change" value={formatPercent(event.headline_metric.price_change_pct)} tone="negative" />
              <Metric label="Volume vs. average" value={`${formatNumber(event.headline_metric.volume_ratio, 1)}×`} />
              <Metric label="Spread change" value={formatPercent(event.headline_metric.spread_change_pct)} tone="positive" />
              <Metric label="Auction participation" value="–" />
            </div>

            <div className="impact-window">
              <div className="panel-title">
                <div>
                  <span className="kicker">TRADING WINDOW</span>
                  <h3>Before and after the event</h3>
                </div>
                <span className="muted">−5 to +5 trading days</span>
              </div>
              <div className="window-bars">
                {Array.from({ length: 11 }, (_, index) => {
                  const offset = index - 5
                  const height = 35 + Math.abs(Math.sin(index * 1.8)) * 95
                  return (
                    <div className="window-column" key={offset}>
                      <i
                        className={offset === 0 ? 'event-day' : index % 3 === 0 ? 'bar-down' : 'bar-up'}
                        style={{ height }}
                      />
                      <small>{offset > 0 ? `+${offset}` : offset}</small>
                    </div>
                  )
                })}
              </div>
              <p className="small-note">Illustrative values only. Offset 0 is the event trading day.</p>
            </div>

            <div className="ai-summary">
              <strong>AI summary · Demo</strong>
              <p>
                In this fictional example, volume increased and the spread widened
                after the announcement. This text will be supplied by the backend later.
              </p>
            </div>

            <div className="coming-soon">
              <strong>Intraday reaction</strong>
              <span>
                Minute-by-minute VWAP and volume will be added when the intraday data
                is available.
              </span>
            </div>

            <button className="primary-button compact" onClick={() => navigate('report')}>
              Open IR snapshot →
            </button>
          </section>
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
  const point = selectedPoint ?? makeMockSeries('1M').slice(-1)[0]

  const values: Record<string, string> = {
    'share-price': formatEuro(point.close),
    returns: formatPercent(1.8),
    volume: formatCompact(point.volume),
    rvol: `${formatNumber(point.volumeRatio, 2)}×`,
    'turnover-vwap': `${formatEuro(point.turnover)} / ${formatEuro(point.vwap)}`,
    spread: `${formatNumber(point.spreadBps, 1)} bps`,
    ema: `${formatEuro(point.ema20)} / ${formatEuro(point.ema50)} / ${formatEuro(point.ema200)}`,
    auction: point.auctionShare === null ? '–' : formatPercent(point.auctionShare * 100),
  }

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
                ? `Selected chart point: ${new Date(selectedPoint.time * 1000).toLocaleString('en-GB')}. Choose an indicator to open its details.`
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
                {new Date(point.time * 1000).toLocaleString('en-GB')} · Demo data
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
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
}) {
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
            description="Configure demo rules and preview the alerts they would trigger."
          />

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
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
}) {
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
              <select defaultValue="quarterly_results">
                <option value="quarterly_results">Quarterly results</option>
                <option value="annual_results">Annual results</option>
                <option value="ad_hoc">Ad hoc announcement</option>
                <option value="dividend">Dividend</option>
                <option value="voting_rights">Voting rights</option>
                <option value="directors_dealings">Directors' dealings</option>
              </select>
            </label>
            <label>
              Index
              <select defaultValue="SDAX">
                <option>DAX</option>
                <option>MDAX</option>
                <option>SDAX</option>
                <option>ALL</option>
              </select>
            </label>
            <label>
              From
              <input type="date" defaultValue="2026-01-02" />
            </label>
            <label>
              To
              <input type="date" defaultValue="2026-10-30" />
            </label>
          </div>

          <section className="panel compare-panel">
            <div className="panel-title">
              <div>
                <span className="kicker">EVENT COMPARISON · DEMO DATA</span>
                <h2>Historical event responses</h2>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Event</th>
                    <th>Volume ratio</th>
                    <th>Price change</th>
                    <th>Spread change</th>
                    <th>Auction share</th>
                  </tr>
                </thead>
                <tbody>
                  {eventData.slice(0, 3).map((event) => (
                    <tr key={event.event_id}>
                      <td>{formatDate(event.date)}</td>
                      <td>{eventLabels[event.type] ?? event.type}</td>
                      <td>{event.headline_metric.volume_ratio == null ? '–' : `${formatNumber(event.headline_metric.volume_ratio, 1)}×`}</td>
                      <td className={trendClass(event.headline_metric.price_change_pct)}>
                        {formatPercent(event.headline_metric.price_change_pct)}
                      </td>
                      <td className={trendClass(event.headline_metric.spread_change_pct)}>
                        {formatPercent(event.headline_metric.spread_change_pct)}
                      </td>
                      <td>–</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small-note">
              Null values are shown as a dash. Comparison values are fictional examples.
            </p>
          </section>

          <div className="summary-tiles">
            <div><span>Median volume ratio</span><strong>1.9×</strong><small>Demo value</small></div>
            <div><span>Median price move</span><strong>−0.6%</strong><small>Demo value</small></div>
            <div><span>Median spread move</span><strong>+2.1%</strong><small>Demo value</small></div>
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
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
}) {
  function exportCsv() {
    const rows = [
      ['Date', 'Event type', 'Volume ratio', 'Price change (%)', 'Spread change (%)'],
      ...eventData.map((event) => [
        event.date,
        event.type,
        event.headline_metric.volume_ratio ?? '',
        event.headline_metric.price_change_pct ?? '',
        event.headline_metric.spread_change_pct ?? '',
      ]),
    ]
    const csv = rows.map((row) => row.join(';')).join('\n')
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'pbb-demo-ir-snapshot.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <Header page="dashboard" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container narrow">
          <PageHeading
            eyebrow="INVESTOR RELATIONS SNAPSHOT"
            title="Trading report"
            description={`Concise historical summary for ${COMPANY}.`}
          />

          <section className="panel report-panel">
            <div className="report-cover">
              <span className="company-logo">pbb</span>
              <div>
                <span className="kicker">ISSUER MARKET REPORT · DEMO</span>
                <h2>{COMPANY}</h2>
                <p>ISIN {ISIN} · SDAX · 02 Jan–30 Oct 2026</p>
              </div>
            </div>
            <div className="report-section">
              <span className="kicker">EXECUTIVE SUMMARY</span>
              <p>
                This prototype report groups historical price and liquidity context,
                notable trading days and company events. Replace the demo values with
                API values when the backend connection is added.
              </p>
            </div>
            <div className="report-section">
              <span className="kicker">NOTABLE EVENTS</span>
              {eventData.slice(0, 3).map((event) => (
                <div className="report-event" key={event.event_id}>
                  <span>{formatDate(event.date)}</span>
                  <strong>{eventLabels[event.type] ?? event.type}</strong>
                  <span>Spread {formatPercent(event.headline_metric.spread_change_pct)}</span>
                </div>
              ))}
            </div>
            <div className="report-disclaimer">
              Descriptive analysis of historical trading data. Not investment advice.
              All figures in this report are fictional demo values.
            </div>
            <div className="report-actions">
              <button className="primary-button compact" onClick={exportCsv}>
                Export CSV ↓
              </button>
              <button className="outline-button" disabled title="PDF endpoint not connected">
                Export PDF · unavailable
              </button>
            </div>
          </section>
        </div>
      </main>
      <Footer />
    </>
  )
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
  return (
    <>
      <Header page="dashboard" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="workspace-page">
        <div className="workspace-container narrow">
          <PageHeading
            eyebrow="HISTORICAL PATTERNS"
            title="What to expect"
            description="Historical reactions provide context, not a price prediction."
          />

          <section className="panel preview-panel">
            <div className="panel-title">
              <div>
                <span className="kicker">UPCOMING EVENT · FICTIONAL EXAMPLE</span>
                <h2>Quarterly results announcement</h2>
                <p className="muted">Example date: 12 November 2026</p>
              </div>
              <span className="confidence">Medium confidence</span>
            </div>

            <div className="preview-grid">
              <div><span>Historical spread change</span><strong>+22%</strong><small>Range: +9% to +38%</small></div>
              <div><span>Historical volume</span><strong>2.1×</strong><small>Range: 1.6× to 2.8×</small></div>
              <div><span>Return to normal</span><strong>~1 session</strong><small>Range: 1 to 3 sessions</small></div>
            </div>

            <div className="attention-box">
              <span className="kicker">POINTS TO WATCH</span>
              <ul>
                <li>Liquidity may take more than one trading session to normalise.</li>
                <li>Past reactions in this demo were stronger than the peer median.</li>
              </ul>
            </div>
            <p className="small-note">
              Fictional preview values. This is not a forecast or investment recommendation.
            </p>
          </section>
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
}: {
  navigate: (page: Page) => void
  loggedIn: boolean
  logout: () => void
}) {
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Hello. I can help you explore pbb trading activity and company events once the assistant is connected.',
    },
  ])

  function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = draft.trim()
    if (!text) return

    setMessages((current) => [
      ...current,
      { role: 'user', text },
      {
        role: 'assistant',
        text: 'This is a frontend prototype. AI responses will be connected to Alfred’s backend later.',
      },
    ])
    setDraft('')
  }

  return (
    <>
      <Header page="assistant" loggedIn={loggedIn} navigate={navigate} logout={logout} />
      <main className="assistant-page">
        <section className="panel assistant-card">
          <div className="panel-title">
            <div>
              <span className="kicker">PBB · INVESTOR RELATIONS</span>
              <h1>AI Assistant</h1>
              <p>Ask about trading activity, events or share-price history.</p>
            </div>
          </div>
          <div className="chat-messages">
            {messages.map((message, index) => (
              <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                {message.text}
              </div>
            ))}
          </div>
          <form className="chat-form" onSubmit={sendMessage}>
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask a question..."
              aria-label="Your question"
            />
            <button type="submit">Send →</button>
          </form>
          <p className="small-note">
            Frontend demo only · No API key or backend connection is used.
          </p>
        </section>
      </main>
      <Footer />
    </>
  )
}

function App() {
  const [loggedIn, setLoggedIn] = useState(
    () => window.localStorage.getItem('pbb-demo-auth') === 'true',
  )
  const [page, setPage] = useState<Page>('home')
  const [selectedPoint, setSelectedPoint] = useState<StockPoint | null>(null)
  const [assistantPoint, setAssistantPoint] = useState<StockPoint | null>(null)

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

  const login = useCallback((email: string, password: string) => {
    if (email !== DEMO_EMAIL || password !== DEMO_PASSWORD) return false
    window.localStorage.setItem('pbb-demo-auth', 'true')
    setLoggedIn(true)
    setPage('dashboard')
    return true
  }, [])

  const logout = useCallback(() => {
    window.localStorage.removeItem('pbb-demo-auth')
    setLoggedIn(false)
    setSelectedPoint(null)
    setAssistantPoint(null)
    setPage('home')
  }, [])

  const selectChartPoint = useCallback((point: StockPoint) => {
    setSelectedPoint(point)
    setAssistantPoint(point)
  }, [])

  useEffect(() => {
    const protectedPages: Page[] = [
      'dashboard',
      'events',
      'impact',
      'indicators',
      'alerts',
      'compare',
      'report',
      'preview',
      'assistant',
    ]

    if (!loggedIn && protectedPages.includes(page)) {
      setPage('login')
    }
  }, [loggedIn, page])

  let content: ReactNode

  if (page === 'login') {
    content = <LoginPage onLogin={login} navigate={navigate} />
  } else if (page === 'dashboard') {
    content = (
      <DashboardPage
        navigate={navigate}
        loggedIn={loggedIn}
        logout={logout}
        onPointSelect={selectChartPoint}
        selectedPoint={selectedPoint}
        setSelectedPoint={setSelectedPoint}
      />
    )
  } else if (page === 'events') {
    content = <EventsPage navigate={navigate} loggedIn={loggedIn} logout={logout} />
  } else if (page === 'impact') {
    content = <ImpactPage navigate={navigate} loggedIn={loggedIn} logout={logout} />
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
    content = <AlertsPage navigate={navigate} loggedIn={loggedIn} logout={logout} />
  } else if (page === 'compare') {
    content = <ComparePage navigate={navigate} loggedIn={loggedIn} logout={logout} />
  } else if (page === 'report') {
    content = <ReportPage navigate={navigate} loggedIn={loggedIn} logout={logout} />
  } else if (page === 'preview') {
    content = <PreviewPage navigate={navigate} loggedIn={loggedIn} logout={logout} />
  } else if (page === 'assistant') {
    content = <AssistantPage navigate={navigate} loggedIn={loggedIn} logout={logout} />
  } else {
    content = <HomePage navigate={navigate} loggedIn={loggedIn} />
  }
  useEffect(() => {
  apiGet<unknown>('/stocks')
    .then((data) => console.log('Stocks reçus :', data))
    .catch((error) => console.error('Erreur API :', error))
}, [])

  return (
    <div className="app-shell">
      {content}
      {assistantPoint && page === 'dashboard' && (
        <AnalysisAssistant
          point={assistantPoint}
          onClose={() => setAssistantPoint(null)}
        />
      )}
    </div>
  )
}

export default App