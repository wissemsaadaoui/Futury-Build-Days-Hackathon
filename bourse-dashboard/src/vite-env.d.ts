/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Absent = '/api' (proxy Vite) ; vide = même domaine (production). Jamais de secret dans une variable VITE_* :
  // elles sont copiées dans le JavaScript envoyé au navigateur.
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
