// Logos fournis par l'équipe (public/logos/, fichiers NON modifiés). Les images contiennent une marge transparente :
// on les recadre en CSS sur leur zone visible (cadre overflow hidden), sans toucher au fichier ni à ses proportions.
// La hauteur vient de la variable CSS --logo-h (28 px desktop, 22 px mobile ; autre valeur via la classe du parent).
import type { CSSProperties } from 'react'

import type { LogoSpec } from '../content/logos.ts'

export function BrandLogo({ logo, className = '' }: { logo: LogoSpec; className?: string }) {
  const { box, size } = logo
  // proportions exprimées en multiples de la hauteur visible : tout reste proportionnel à --logo-h
  const style = {
    '--logo-w': box.w / box.h,
    '--logo-img-w': size.w / box.h,
    '--logo-img-h': size.h / box.h,
    '--logo-x': box.x / box.h,
    '--logo-y': box.y / box.h,
  } as CSSProperties
  return (
    <span className={`brand-logo ${className}`} style={style}>
      <img src={logo.src} alt={logo.alt} draggable={false} />
    </span>
  )
}
