// Développement : '/api' (proxy Vite, voir vite.config.ts).
// Production (VPS) : '' via .env.production -> même domaine que l'API, servie par Caddy.
// Le mot de passe n'est jamais dans le code du navigateur : Caddy le demande une fois (Basic auth).
export const API_BASE_URL = import.meta.env.VITE_API_URL ?? '/api';

// Liens renvoyés par l'API (export.pdf_url, detail_url…) : chemins relatifs à préfixer.
export function apiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

// Session : cookie HttpOnly posé par POST /auth/login (jamais lisible en JS, aucun mot de passe stocké côté front).
// Toute réponse 401 émet cet événement : l'application affiche alors l'écran de login.
export const UNAUTHORIZED_EVENT = 'iih:unauthorized'

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
  })

  if (response.status === 401 && !path.startsWith('/auth/')) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }

  if (!response.ok) {
    // L'API renvoie {"detail": "..."} (ex. « Not enough trading days in the requested period »)
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : response.statusText
    throw new ApiError(response.status, `${response.status} – ${detail}`)
  }

  return response.json() as Promise<T>
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path)
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
}
