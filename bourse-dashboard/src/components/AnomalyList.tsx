// Top 5 des alertes / anomalies (point 10) : rang calculé par l'API (sévérité, puis la plus récente), sans les
// éléments écartés (dismissed) par l'équipe IR ; « Show all (N) » affiche tout, écartés compris (badge).
// Chaque ligne : Approve / Dismiss + note (point 9).
import { useMemo, useState } from 'react'

import type { Anomaly, DecisionRef } from '../api/types.ts'
import { anomalyLabels, formatAnomalyValue, formatDate } from '../format.ts'
import { CountUp } from './CountUp.tsx'
import { DecisionControls } from './DecisionControls.tsx'

const SEVERITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }

// Même règle que l'API (app/analytics/decisions.py) : sévérité, puis la plus récente
function byImportance(a: Anomaly, b: Anomaly) {
  return (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3) || b.date.localeCompare(a.date)
}

export function AnomalyList({
  anomalies,
  onOpen,
  isin,
  initial = 5,
  emptyText = 'No unusual trading day in the period.',
}: {
  anomalies: Anomaly[]
  onOpen: (detailUrl: string) => void
  isin: string
  initial?: number
  emptyText?: string
}) {
  const [showAll, setShowAll] = useState(false)
  // Décisions prises dans cette vue : appliquées tout de suite (même règle que l'API pour le rang)
  const [local, setLocal] = useState<Record<string, DecisionRef>>({})
  const effective = (a: Anomaly) => (a.id && local[a.id]) || a.decision || null
  const ranked = useMemo(() => {
    const isDismissed = (a: Anomaly) => ((a.id && local[a.id]) || a.decision)?.decision === 'dismissed'
    const active = anomalies.filter((a) => !isDismissed(a)).sort(byImportance)
    const dismissed = anomalies.filter(isDismissed).sort(byImportance)
    return { active, all: [...active, ...dismissed] }
  }, [anomalies, local])
  const rankOf = new Map(ranked.active.map((a, index) => [a, index + 1]))
  const shown = showAll ? ranked.all : ranked.active.slice(0, initial)

  if (ranked.all.length === 0) return <p className="muted">{emptyText}</p>

  return (
    <>
      {shown.map((anomaly) => (
        <div
          className={`signal-row-wrap${effective(anomaly)?.decision === 'dismissed' ? ' dismissed' : ''}`}
          key={anomaly.id ?? `${anomaly.date}-${anomaly.type}-${anomaly.description}`}
        >
          <button className="signal-row" onClick={() => onOpen(anomaly.detail_url)}>
            <span className={`signal-dot ${anomaly.severity}`} />
            {rankOf.has(anomaly) && <span className="signal-rank">#{rankOf.get(anomaly)}</span>}
            <span className="signal-date">{formatDate(anomaly.date)}</span>
            <span className="signal-copy">
              <strong>{anomalyLabels[anomaly.type] ?? anomaly.type}</strong>
              <small>{anomaly.description}</small>
            </span>
            <span className="signal-value">
              <CountUp text={formatAnomalyValue(anomaly.type, anomaly.value)} delay={1200} />
            </span>
            <span>↗</span>
          </button>
          <DecisionControls
            isin={isin}
            itemType={anomaly.item_type ?? 'alert'}
            itemId={anomaly.id}
            decision={effective(anomaly)}
            compact
            onDecided={(ref) => anomaly.id && setLocal((current) => ({ ...current, [anomaly.id as string]: ref }))}
          />
        </div>
      ))}
      {ranked.all.length > initial && (
        <button className="text-button show-all" onClick={() => setShowAll((value) => !value)} aria-expanded={showAll}>
          {showAll ? `Show top ${initial} only` : `Show all (${ranked.all.length})`}
        </button>
      )}
    </>
  )
}
