// Bouton d'export PDF : télécharge le fichier avec le Bearer token (openPdf), affiche l'état et les erreurs.
import { useState, type ReactNode } from 'react'

import { openPdf } from '../api/clients.ts'

export function PdfButton({
  path,
  filename,
  className = 'primary-button compact',
  children,
}: {
  path: string
  filename?: string
  className?: string
  children: ReactNode
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function download() {
    setBusy(true)
    setError('')
    try {
      await openPdf(path, filename)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button type="button" className={className} onClick={download} disabled={busy}>
        {busy ? 'Preparing PDF…' : children}
      </button>
      {error && <span className="login-error">Could not export the PDF ({error}).</span>}
    </>
  )
}
