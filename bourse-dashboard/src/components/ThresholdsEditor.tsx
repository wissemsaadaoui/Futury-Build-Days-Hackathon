// Seuils d'alerte modifiables (point 16) : valeurs, bornes et défauts viennent de l'API (GET /thresholds).
// Save -> PUT /thresholds ; Reset -> POST /thresholds/reset ; aperçu (sans enregistrer) -> POST /thresholds/preview.
// Chaque changement enregistré est inscrit côté API dans le Decision log (threshold_changed).
import { useEffect, useMemo, useState } from 'react'

import { ApiError, apiGet, apiPost, apiPut } from '../api/clients.ts'
import type { ThresholdsPreview, ThresholdsResponse } from '../api/types.ts'
import { clearApiCache } from '../api/useApi.ts'

const GROUPS: { key: 'anomaly' | 'alert'; title: string; kicker: string }[] = [
  { key: 'anomaly', kicker: 'STATISTICAL ANOMALIES', title: 'Volume and spread' },
  { key: 'alert', kicker: 'EXECUTION ALERTS', title: 'Executions, flows and auctions' },
]

const same = (a: Record<string, number>, b: Record<string, number>) =>
  Object.keys(a).every((key) => Math.abs((a[key] ?? 0) - (b[key] ?? 0)) < 1e-9)

export function ThresholdsEditor({ isin, onSaved }: { isin: string; onSaved: () => void }) {
  const [server, setServer] = useState<ThresholdsResponse | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<ThresholdsPreview | null>(null)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  const applyServer = (data: ThresholdsResponse) => {
    setServer(data)
    setDraft(Object.fromEntries(Object.entries(data.values).map(([key, value]) => [key, String(value)])))
    setFieldErrors({})
  }

  useEffect(() => {
    apiGet<ThresholdsResponse>(`/thresholds?isin=${isin}`)
      .then(applyServer)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [isin])

  // Valeurs saisies : nombres valides dans les bornes, sinon message local (l'API revalide de toute façon)
  const parsed = useMemo(() => {
    const values: Record<string, number> = {}
    const errors: Record<string, string> = {}
    if (!server) return { values, errors }
    for (const [key, spec] of Object.entries(server.bounds)) {
      const value = Number(draft[key])
      if (draft[key] === '' || Number.isNaN(value)) errors[key] = 'Enter a number'
      else if (value < spec.min || value > spec.max) errors[key] = `Between ${spec.min} and ${spec.max}`
      else if (spec.integer && !Number.isInteger(value)) errors[key] = 'Whole number'
      else values[key] = value
    }
    return { values, errors }
  }, [draft, server])

  const valid = server !== null && Object.keys(parsed.errors).length === 0
  const dirty = server !== null && valid && !same(parsed.values, server.values)
  const atDefaults = server !== null && valid && same(parsed.values, server.defaults)

  // Aperçu « With these thresholds: N alerts (currently M) », recalculé 400 ms après la dernière saisie
  useEffect(() => {
    if (!valid || !server) return
    const timer = window.setTimeout(() => {
      apiPost<ThresholdsPreview>('/thresholds/preview', { isin, values: parsed.values })
        .then(setPreview)
        .catch(() => setPreview(null))
    }, 400)
    return () => window.clearTimeout(timer)
  }, [isin, parsed.values, server, valid])

  async function run(action: () => Promise<ThresholdsResponse>, done: string) {
    setSaving(true)
    setMessage('')
    setError('')
    try {
      applyServer(await action())
      clearApiCache() // dashboard, alertes, top 5 et chat doivent relire les nouveaux seuils
      setMessage(done)
      onSaved()
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) setError('Some values are outside the allowed range.')
      else setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  if (error && !server) return <div className="notice-box">Could not load thresholds ({error}).</div>
  if (!server) return <div className="notice-box">Loading thresholds…</div>

  return (
    <section className="panel threshold-editor">
      <div className="panel-title">
        <div>
          <span className="kicker">ALERT THRESHOLDS · {server.custom ? 'CUSTOM' : 'DEFAULTS FROM THE CODE'}</span>
          <h2>Thresholds used for {isin}</h2>
        </div>
        {server.custom && <span className="custom-badge">Custom thresholds</span>}
      </div>

      <div className="threshold-groups">
        {GROUPS.map((group) => (
          <div key={group.key} className="threshold-group">
            <span className="kicker">{group.kicker}</span>
            <h3>{group.title}</h3>
            {Object.entries(server.bounds)
              .filter(([, spec]) => spec.group === group.key)
              .map(([key, spec]) => {
                const changed = parsed.values[key] !== undefined && Math.abs(parsed.values[key] - server.defaults[key]) > 1e-9
                return (
                  <label key={key} className={`threshold-field${parsed.errors[key] || fieldErrors[key] ? ' invalid' : ''}`}>
                    <span>{spec.label}</span>
                    <span className="threshold-input">
                      <input
                        type="number"
                        inputMode="decimal"
                        min={spec.min}
                        max={spec.max}
                        step={spec.step}
                        value={draft[key] ?? ''}
                        onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))}
                      />
                      <small>{spec.unit}</small>
                    </span>
                    <small className="threshold-hint">
                      {parsed.errors[key] ?? `Default ${spec.default} · range ${spec.min}–${spec.max}`}
                      {changed && !parsed.errors[key] ? ' · changed' : ''}
                    </small>
                  </label>
                )
              })}
          </div>
        ))}
      </div>

      <div className="threshold-preview" aria-live="polite">
        {preview && valid ? (
          <>
            With these thresholds: <strong>{preview.alerts_with_values} alerts</strong> (currently{' '}
            {preview.alerts_current}) over 2 Jan – 30 Oct 2026.
          </>
        ) : (
          'Enter valid values to preview the number of alerts.'
        )}
      </div>

      <div className="report-actions">
        <button
          className="primary-button compact"
          disabled={!dirty || saving}
          onClick={() => run(() => apiPut<ThresholdsResponse>('/thresholds', { isin, values: parsed.values }), 'Thresholds saved and logged.')}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          className="outline-button"
          disabled={saving || (atDefaults && !server.custom)}
          onClick={() => run(() => apiPost<ThresholdsResponse>('/thresholds/reset', { isin }), 'Thresholds reset to the defaults and logged.')}
        >
          Reset to defaults
        </button>
        {message && <span className="threshold-message">{message}</span>}
        {error && <span className="login-error">{error}</span>}
      </div>
      <p className="small-note">Every change is recorded in the Decision log (old → new value).</p>
    </section>
  )
}
