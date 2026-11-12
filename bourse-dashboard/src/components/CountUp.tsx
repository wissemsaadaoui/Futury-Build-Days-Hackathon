import { useEffect, useState } from 'react'

// Smoothly settles every number inside an already formatted text ("€2.80", "+11.7%", "1.94×", "€364,741.00")
// onto its value: it glides from 90 % of the value while fading in from a light blur (see .count-up in index.css),
// keeping the decimals, thousands separators and surrounding symbols.
const NUMBER = /\d[\d,]*(?:\.\d+)?/g
const HAS_NUMBER = /\d/
const START = 0.9 // starting point, as a share of the final value

function render(text: string, progress: number) {
  return text.replace(NUMBER, (token) => {
    const value = Number(token.replace(/,/g, ''))
    const decimals = token.includes('.') ? token.split('.')[1].length : 0
    return (value * progress).toLocaleString('en-GB', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
      useGrouping: token.includes(','),
    })
  })
}

const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function CountUp({ text, delay = 0, duration = 1100 }: { text: string; delay?: number; duration?: number }) {
  const animate = HAS_NUMBER.test(text) && !reducedMotion()
  const [shown, setShown] = useState(() => render(text, START))

  useEffect(() => {
    if (!animate) return
    let frame = 0
    const start = performance.now() + delay
    const step = (now: number) => {
      const progress = Math.min(1, Math.max(0, (now - start) / duration))
      const eased = 1 - (1 - progress) ** 3
      setShown(progress < 1 ? render(text, START + (1 - START) * eased) : text)
      if (progress < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [animate, text, delay, duration])

  return (
    <span className={animate ? 'count-up settling' : 'count-up'} style={{ animationDelay: `${delay}ms` }}>
      {animate ? shown : text}
    </span>
  )
}
