// Couleur d'un delta : un seul helper pour toute l'application.
// - 'price' : cours, returns, écart vs peers -> hausse = vert (positive), baisse = rouge (negative)
// - 'cost'  : spread et tout coût de trading -> hausse = rouge (negative), baisse = vert (positive)
// - 'neutral' : volume, turnover, enchères… -> jamais coloré (une hausse n'est ni bonne ni mauvaise en soi)
export type ToneKind = 'price' | 'cost' | 'neutral'
export type Tone = 'positive' | 'negative' | 'neutral'

const FLAT = 0.05 // |variation| < 0.05 : affichée sans couleur

export function tone(value: number | null | undefined, kind: ToneKind = 'price'): Tone {
  if (kind === 'neutral' || value === null || value === undefined || Number.isNaN(value) || Math.abs(value) < FLAT) {
    return 'neutral'
  }
  const up = value > 0
  if (kind === 'cost') return up ? 'negative' : 'positive'
  return up ? 'positive' : 'negative'
}

// Unité d'un KPI du report -> type de couleur
export function toneForUnit(unit: string): ToneKind {
  return unit === 'bps' ? 'cost' : 'neutral'
}
