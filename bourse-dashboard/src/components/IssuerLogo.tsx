// Pastille texte de l'émetteur (mnemonic Xetra), identique pour tous les émetteurs : aucun logo de société.
import type { Issuer } from '../issuer/context.ts'

export function IssuerLogo({ issuer, className = '' }: { issuer: Issuer; className?: string }) {
  return (
    <span className={`issuer-pill ${className}`} role="img" aria-label={issuer.name}>
      {issuer.ticker}
    </span>
  )
}
