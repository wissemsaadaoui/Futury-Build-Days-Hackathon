// Liste d'anomalies / alertes : les N plus importantes d'abord (sévérité, puis les plus récentes),
// puis « Show all (N) » pour le reste.
import { useMemo, useState } from 'react'

import type { Anomaly } from '../api/types.ts'
import { anomalyLabels, formatAnomalyValue, formatDate } from '../format.ts'

const SEVERITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }

function byImportance(items: Anomaly[]): Anomaly[] {
  return [...items].sort(
    (a, b) => (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3) || b.date.localeCompare(a.date),
  )
}

export function AnomalyList({
  anomalies,
  onOpen,
  initial = 5,
  emptyText = 'No unusual trading day in the period.',
}: {
  anomalies: Anomaly[]
  onOpen: (detailUrl: string) => void
  initial?: number
  emptyText?: string
}) {
  const [showAll, setShowAll] = useState(false)
  const sorted = useMemo(() => byImportance(anomalies), [anomalies])
  const shown = showAll ? sorted : sorted.slice(0, initial)

  if (sorted.length === 0) return <p className="muted">{emptyText}</p>

  return (
    <>
      {shown.map((anomaly) => (
        <button
          className="signal-row"
          key={`${anomaly.date}-${anomaly.type}-${anomaly.description}`}
          onClick={() => onOpen(anomaly.detail_url)}
        >
          <span className={`signal-dot ${anomaly.severity}`} />
          <span className="signal-date">{formatDate(anomaly.date)}</span>
          <span className="signal-copy">
            <strong>{anomalyLabels[anomaly.type] ?? anomaly.type}</strong>
            <small>{anomaly.description}</small>
          </span>
          <span className="signal-value">{formatAnomalyValue(anomaly.type, anomaly.value)}</span>
          <span>↗</span>
        </button>
      ))}
      {sorted.length > initial && (
        <button className="text-button show-all" onClick={() => setShowAll((value) => !value)} aria-expanded={showAll}>
          {showAll ? `Show top ${initial} only` : `Show all (${sorted.length})`}
        </button>
      )}
    </>
  )
}
