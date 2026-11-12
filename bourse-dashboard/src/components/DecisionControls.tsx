// Human-in-the-loop : « AI suggests, the IR team decides – every decision is logged. »
// Approve / Dismiss + note facultative -> POST /decisions ; badge d'état (dernière décision).
import { useState } from 'react'

import { apiPost } from '../api/clients.ts'
import type { Decision, DecisionRef } from '../api/types.ts'
import { clearApiCache } from '../api/useApi.ts'
import { formatDate } from '../format.ts'

export const HITL_LINE = 'AI suggests, the IR team decides – every decision is logged.'

export function DecisionBadge({ decision }: { decision: DecisionRef | null | undefined }) {
  if (!decision) return <span className="decision-badge pending">To review</span>
  return (
    <span className={`decision-badge ${decision.decision}`} title={decision.note ?? undefined}>
      {decision.decision === 'approved' ? 'Approved' : 'Dismissed'} · {formatDate(decision.decided_at)}
    </span>
  )
}

export function DecisionControls({
  isin,
  itemType,
  itemId,
  decision,
  compact = false,
  onDecided,
}: {
  isin: string
  itemType: 'alert' | 'anomaly' | 'ai_summary'
  itemId: string | undefined
  decision: DecisionRef | null | undefined
  compact?: boolean
  onDecided?: (decision: DecisionRef) => void
}) {
  const [current, setCurrent] = useState<DecisionRef | null | undefined>(decision)
  const [noteOpen, setNoteOpen] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (!itemId) return null

  async function decide(value: 'approved' | 'dismissed') {
    setBusy(true)
    setError('')
    try {
      const saved = await apiPost<Decision>('/decisions', {
        item_type: itemType,
        item_id: itemId,
        isin,
        decision: value,
        note: note.trim() || undefined,
      })
      const ref: DecisionRef = {
        id: saved.id,
        decision: value,
        note: saved.note,
        decided_at: saved.decided_at,
        decided_by: saved.decided_by,
      }
      setCurrent(ref)
      setNote('')
      setNoteOpen(false)
      clearApiCache() // top 5, rangs et journal relus à la prochaine requête
      onDecided?.(ref)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const stop = (event: { stopPropagation: () => void }) => event.stopPropagation()

  return (
    <div className={`decision-controls${compact ? ' compact' : ''}`} onClick={stop}>
      <DecisionBadge decision={current} />
      <button
        type="button"
        className={`decision-button approve${current?.decision === 'approved' ? ' active' : ''}`}
        disabled={busy}
        onClick={() => decide('approved')}
      >
        Approve
      </button>
      <button
        type="button"
        className={`decision-button dismiss${current?.decision === 'dismissed' ? ' active' : ''}`}
        disabled={busy}
        onClick={() => decide('dismissed')}
      >
        Dismiss
      </button>
      <button type="button" className="decision-note-toggle" onClick={() => setNoteOpen((value) => !value)}>
        {noteOpen ? 'Hide note' : current?.note ? 'Note ✓' : '+ Note'}
      </button>
      {noteOpen && (
        <input
          className="decision-note"
          value={note}
          maxLength={500}
          placeholder={current?.note ?? 'Optional note (saved with the decision)'}
          onChange={(event) => setNote(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') decide(current?.decision === 'dismissed' ? 'dismissed' : 'approved')
          }}
        />
      )}
      {error && <span className="login-error">{error}</span>}
    </div>
  )
}
