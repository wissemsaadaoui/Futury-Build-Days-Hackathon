// Développement : '/api' (proxy Vite, voir vite.config.ts).
// Production (VPS) : '' via .env.production -> même domaine que l'API, servie par Caddy.
// Le mot de passe n'est jamais dans le code du navigateur : Caddy le demande une fois (Basic auth).
export const API_BASE_URL = import.meta.env.VITE_API_URL ?? '/api';

// Liens renvoyés par l'API (export.pdf_url, detail_url…) : chemins relatifs à préfixer.
export function apiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    // L'API renvoie {"detail": "..."} (ex. « Not enough trading days in the requested period »)
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === 'string' ? body.detail : response.statusText;
    throw new Error(`${response.status} – ${detail}`);
  }

  return response.json() as Promise<T>;
}
