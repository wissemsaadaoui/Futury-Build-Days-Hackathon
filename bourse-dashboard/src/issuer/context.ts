// Émetteur affiché : pbb par défaut, ou l'ISIN de l'URL (?isin=…) pour qu'un lien soit partageable.
// Les noms, indices et couvertures viennent de GET /stocks ; avant le login (ou pendant le chargement) on garde
// les infos de pbb pour pbb, sinon l'ISIN seul.
import { createContext, useContext } from 'react'

import type { Coverage, PeerBasis, Stock } from '../api/types.ts'

export const DEFAULT_ISIN = 'DE0008019001'

export type Issuer = {
  isin: string
  name: string // nom d'affichage (« Deutsche Pfandbriefbank AG », « SUSS Microtec SE »)
  brandName: string // dans les textes d'accueil (« Deutsche Pfandbriefbank »)
  short: string // dans les phrases (« pbb ») ; sinon le nom
  ticker: string // mnemonic Xetra (« PBB », « SMHN »)
  index: string
  peerBasis: PeerBasis
  coverage: Coverage | null
  isDefault: boolean
  known: boolean // présent dans /stocks (ou pbb)
}

export const DEFAULT_ISSUER: Issuer = {
  isin: DEFAULT_ISIN,
  name: 'Deutsche Pfandbriefbank AG',
  brandName: 'Deutsche Pfandbriefbank',
  short: 'pbb',
  ticker: 'PBB',
  index: 'SDAX',
  peerBasis: 'manual',
  coverage: null,
  isDefault: true,
  known: true,
}

export function issuerFrom(isin: string, stocks: Stock[]): Issuer {
  const stock = stocks.find((item) => item.isin === isin)
  if (isin === DEFAULT_ISIN) {
    return stock
      ? { ...DEFAULT_ISSUER, index: stock.index, coverage: stock.coverage ?? null }
      : DEFAULT_ISSUER
  }
  if (!stock) {
    return { ...DEFAULT_ISSUER, isin, name: isin, brandName: isin, short: isin, ticker: isin.slice(0, 4), index: '',
      peerBasis: 'index', isDefault: false, known: false }
  }
  return {
    isin,
    name: stock.name,
    brandName: stock.name,
    short: stock.name,
    ticker: stock.ticker,
    index: stock.index,
    peerBasis: stock.peer_basis ?? 'index',
    coverage: stock.coverage ?? null,
    isDefault: false,
    known: true,
  }
}

export type IssuerState = { issuer: Issuer; stocks: Stock[]; setIsin: (isin: string) => void }

export const IssuerContext = createContext<IssuerState>({ issuer: DEFAULT_ISSUER, stocks: [], setIsin: () => {} })

export function useIssuer(): IssuerState {
  return useContext(IssuerContext)
}

const ISIN_PATTERN = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/

export function isinFromUrl(): string {
  try {
    const value = new URLSearchParams(window.location.search).get('isin')?.toUpperCase() ?? ''
    return ISIN_PATTERN.test(value) ? value : DEFAULT_ISIN
  } catch {
    return DEFAULT_ISIN
  }
}

// pbb : l'URL reste sans paramètre (lien de démo inchangé) ; sinon ?isin=… (remplace l'entrée d'historique)
export function writeIsinToUrl(isin: string) {
  try {
    const url = new URL(window.location.href)
    if (isin === DEFAULT_ISIN) url.searchParams.delete('isin')
    else url.searchParams.set('isin', isin)
    window.history.replaceState(window.history.state, '', url)
  } catch {
    // environnement sans history (tests, aperçu) : rien à faire
  }
}

export function dashboardPath(isin: string) {
  return `/stocks/${isin}/dashboard`
}

// Nom de fichier : mnemonic en minuscules (« pbb-report-… »)
export function filePrefix(issuer: Issuer) {
  return issuer.ticker.toLowerCase()
}
