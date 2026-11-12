import { useEffect, useState } from 'react'

import { apiGet } from './clients.ts'

type ApiState<T> = { data: T | null; error: string | null; loading: boolean }

// Une requête par chemin, partagée entre les pages (le dashboard est chargé une seule fois).
const cache = new Map<string, Promise<unknown>>()

function load<T>(path: string): Promise<T> {
  let request = cache.get(path) as Promise<T> | undefined
  if (!request) {
    request = apiGet<T>(path)
    cache.set(path, request)
    request.catch(() => cache.delete(path)) // une erreur n'est pas mise en cache : nouvel essai possible
  }
  return request
}

// path = null : rien à charger pour l'instant.
export function useApi<T>(path: string | null): ApiState<T> {
  const [state, setState] = useState<ApiState<T> & { path: string | null }>({
    data: null,
    error: null,
    loading: path !== null,
    path,
  })

  useEffect(() => {
    if (path === null) return
    let active = true
    load<T>(path)
      .then((data) => active && setState({ data, error: null, loading: false, path }))
      .catch((error: unknown) =>
        active &&
        setState({
          data: null,
          error: error instanceof Error ? error.message : String(error),
          loading: false,
          path,
        }),
      )
    return () => {
      active = false
    }
  }, [path])

  // Changement de chemin : on n'affiche pas les données de la requête précédente.
  if (state.path !== path) return { data: null, error: null, loading: path !== null }
  return state
}
