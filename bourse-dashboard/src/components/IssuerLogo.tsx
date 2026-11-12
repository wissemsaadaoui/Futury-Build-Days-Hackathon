// Logo de l'émetteur : celui de pbb pour pbb ; pour les autres, une pastille avec le mnemonic Xetra.
import { LOGOS } from '../content/logos.ts'
import type { Issuer } from '../issuer/context.ts'
import { BrandLogo } from './BrandLogo.tsx'

export function IssuerLogo({ issuer, className = '' }: { issuer: Issuer; className?: string }) {
  if (issuer.isDefault) return <BrandLogo logo={LOGOS.pbb} className={className} />
  return (
    <span className={`issuer-pill ${className}`} role="img" aria-label={issuer.name}>
      {issuer.ticker}
    </span>
  )
}
