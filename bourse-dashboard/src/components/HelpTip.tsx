// Bouton « ? » avec une définition (src/content/metricHelp.ts).
// Ouvert au survol, au focus clavier et au tap (mobile) ; fermé en quittant, à la perte du focus, au scroll ou avec Échap.
// La bulle est en position fixe, calculée à l'ouverture : toujours dans l'écran, jamais coupée par un parent.
import { useEffect, useId, useRef, useState, type CSSProperties } from 'react'

import { metricHelp, type MetricHelpKey } from '../content/metricHelp.ts'

const MARGIN = 12
const MAX_WIDTH = 260

function placeBelow(button: HTMLElement): CSSProperties {
  const r = button.getBoundingClientRect()
  const width = Math.min(MAX_WIDTH, window.innerWidth - 2 * MARGIN)
  const left = Math.min(Math.max(r.left + r.width / 2 - width / 2, MARGIN), window.innerWidth - MARGIN - width)
  return { top: r.bottom + 8, left, width }
}

export function HelpTip({ metric, label }: { metric: MetricHelpKey; label?: string }) {
  const [style, setStyle] = useState<CSSProperties | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const id = useId()
  const open = style !== null

  const show = () => {
    if (buttonRef.current) setStyle(placeBelow(buttonRef.current))
  }
  const hide = () => setStyle(null)

  useEffect(() => {
    if (!open) return
    window.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
    return () => {
      window.removeEventListener('scroll', hide, true)
      window.removeEventListener('resize', hide)
    }
  }, [open])

  return (
    <span className={`help-tip${open ? ' open' : ''}`} onMouseEnter={show} onMouseLeave={hide}>
      <button
        ref={buttonRef}
        type="button"
        className="help-tip-button"
        aria-label={`What is ${label ?? metric}?`}
        aria-describedby={id}
        aria-expanded={open}
        onFocus={show}
        onBlur={hide}
        onClick={(event) => {
          event.stopPropagation() // ne déclenche pas le bouton / la ligne parente
          show()
        }}
        onKeyDown={(event) => {
          if (event.key === 'Escape') hide()
        }}
      >
        ?
      </button>
      <span role="tooltip" id={id} className="help-tip-bubble" style={style ?? undefined}>
        {metricHelp[metric]}
      </span>
    </span>
  )
}
