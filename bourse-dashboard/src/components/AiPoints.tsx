// Résumé IA en points : `ai_points` (3–4 phrases courtes vérifiées par le garde-fou côté API).
// Si l'API ne les renvoie pas (ancienne version, mock), on découpe le texte du résumé par phrase.
// Avec `review` : Approve / Dismiss + note sous les points (human-in-the-loop, item_type ai_summary).
import type { DecisionRef } from '../api/types.ts'
import { DecisionControls, HITL_LINE } from './DecisionControls.tsx'

const SENTENCE_BREAK = /(?<=[.!?])\s+(?=[A-Z0-9"(])/

function splitSentences(text: string): string[] {
  return text
    .split(SENTENCE_BREAK)
    .map((sentence) => sentence.trim())
    .filter(Boolean)
}

export function AiPoints({
  points,
  summary,
  title = 'AI summary',
  className = 'ai-summary',
  review,
}: {
  points?: string[] | null
  summary?: string | null
  title?: string | null
  className?: string
  review?: { isin: string; id?: string; decision?: DecisionRef | null }
}) {
  const items = points && points.length > 0 ? points : splitSentences(summary ?? '')
  return (
    <div className={`${className} ai-points`}>
      {title && <strong>{title}</strong>}
      {items.length > 0 ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>No data</p>
      )}
      {review?.id && (
        <div className="ai-review">
          <DecisionControls isin={review.isin} itemType="ai_summary" itemId={review.id} decision={review.decision} compact />
          <small>{HITL_LINE}</small>
        </div>
      )}
    </div>
  )
}
