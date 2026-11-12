// Développement : '/api' (proxy Vite, voir vite.config.ts).
// Production (VPS) : '' via .env.production -> même domaine que l'API, servie par Caddy.
// Accès : login applicatif (POST /auth/login -> token), envoyé en « Authorization: Bearer » et vérifié par l'API
// sur chaque route. Marche aussi d'un front local (localhost:5173/5174) vers l'API du VPS : pas de cookie.
export const API_BASE_URL = import.meta.env.VITE_API_URL ?? '/api';

// Liens renvoyés par l'API (export.pdf_url, detail_url…) : chemins relatifs à préfixer.
export function apiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

// Token signé renvoyé par /auth/login (valable 12 h). Seul le token est stocké, JAMAIS le mot de passe.
const TOKEN_KEY = 'iih_token'

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY)
  } catch {
    return null // stockage indisponible (navigation privée stricte)
  }
}

export function setToken(token: string) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // stockage indisponible : la session ne survivra pas à un rechargement
  }
}

export function clearToken() {
  try {
    window.localStorage.removeItem(TOKEN_KEY)
  } catch {
    // rien à effacer
  }
}

// Toute réponse 401 (hors /auth/login) efface le token et émet cet événement : l'application affiche le login.
export const UNAUTHORIZED_EVENT = 'iih:unauthorized'

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken()
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })

  if (response.status === 401 && path !== '/auth/login') {
    clearToken()
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }

  if (!response.ok) {
    // L'API renvoie {"detail": "..."} (ex. « Not enough trading days in the requested period »)
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : response.statusText
    throw new ApiError(response.status, `${response.status} – ${detail}`)
  }
  return response
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await send(path, init)
  return response.json() as Promise<T>
}

// Les exports PDF ne peuvent pas porter d'en-tête dans un simple lien : on les télécharge avec le token,
// puis on ouvre le fichier (blob) dans un nouvel onglet. L'onglet est ouvert AVANT l'attente réseau pour ne pas
// être bloqué par le navigateur ; si l'ouverture est refusée, le fichier est téléchargé.
export async function openPdf(path: string, filename = 'issuer-hub-export.pdf'): Promise<void> {
  const tab = window.open('', '_blank')
  try {
    const response = await send(path, { headers: { Accept: 'application/pdf' } })
    const url = URL.createObjectURL(await response.blob())
    if (tab) {
      tab.location.href = url
    } else {
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
    }
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (error) {
    tab?.close()
    throw error
  }
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
